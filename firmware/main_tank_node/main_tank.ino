/*
  ================================================================
  ESP32 MASTER – MAIN TANK NODE
  HydroNet Monitor — Master Firmware v1.0
  ================================================================
  Hardware (local):
    - TDS sensor     -> GPIO34  (ADC1_CH6)
    - Ultrasonic     -> Trig=GPIO26, Echo=GPIO27

  Receives from SLAVE via ESP-NOW:
    - flow1_Lmin, flow2_Lmin
    - sub-tank TDS, waterQualityCode, tankLevel

  Uploads combined data to Firebase RTDB every 5 seconds:
    Path: /waterSystem/status  (PUT)
    Project: hydronet-monitor

  Libraries needed:
    - (built-in) WiFi, esp_now, HTTPClient, WiFiClientSecure
  ================================================================
*/

#include <WiFi.h>
#include <esp_now.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>

// ── WiFi & Firebase Config ─────────────────────────────────────
const char* WIFI_SSID     = "11i";
const char* WIFI_PASSWORD = "senu@123";

// Firebase RTDB — domain ONLY, no "https://", no trailing slash
const char* FIREBASE_HOST = "hydronet-monitor-default-rtdb.firebaseio.com";

// Database secret (Project Settings → Service accounts → Database secrets)
// ⚠ Keep this private — do NOT commit to public repos
const char* FIREBASE_AUTH = "IKwfkB1eVB2szYTYMRtvPbbrgUZo5fahyDMXUEQ3";

WiFiClientSecure fbClient;  // TLS client (setInsecure — skips cert check)

// ── Pin Config (Master Local Sensors) ─────────────────────────
const int TDS_PIN  = 34;  // TDS sensor analog → ADC1_CH6
const int TRIG_PIN = 26;  // Ultrasonic Trigger
const int ECHO_PIN = 27;  // Ultrasonic Echo

// ── ADC / Voltage ──────────────────────────────────────────────
const float VREF    = 3.3;
const int   ADC_RES = 4095; // 12-bit

// ── Tank Config ────────────────────────────────────────────────
const float TANK_HEIGHT_CM = 100.0; // Master tank height in cm

// ── TDS Calibration ───────────────────────────────────────────
const float TDS_FACTOR = 500.0; // 1.0V → 500 ppm; calibrate per your probe

// ── Firebase Upload Interval ───────────────────────────────────
unsigned long lastFirebaseMillis = 0;
const unsigned long FIREBASE_INTERVAL = 5000; // 5 seconds

// ── ESP-NOW Data Struct (identical to slave) ───────────────────
typedef struct struct_message {
  float   tdsPpm;
  uint8_t waterQualityCode;  // 0=error, 1=excellent, 2=good, 3=average, 4=bad
  float   tankLevelPercent;
  float   tankLevelCm;
  float   flow1_Lmin;
  float   flow2_Lmin;
} struct_message;

struct_message rxData;
bool newDataReceived = false;
bool hasSlaveData    = false;

// =====================================================
// MASTER LOCAL: Ultrasonic Distance (cm)
// =====================================================
float readDistanceCm() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(3);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  long duration = pulseIn(ECHO_PIN, HIGH, 30000);
  if (duration == 0) return -1;
  return duration / 58.0;
}

// =====================================================
// MASTER LOCAL: TDS ppm (30-sample average)
// =====================================================
float readTDSppm() {
  const int N = 30;
  long sum = 0;
  for (int i = 0; i < N; i++) {
    sum += analogRead(TDS_PIN);
    delay(5);
  }
  float voltage = ((float)sum / N / ADC_RES) * VREF;
  return voltage * TDS_FACTOR;
}

// =====================================================
// MASTER: TDS → water quality text
// =====================================================
String getWaterQualityStatus(float ppm) {
  if (ppm <= 0)         return "Sensor Error / No Reading";
  if (ppm <= 50)        return "Very Low Minerals (RO Water) - Not Ideal";
  if (ppm <= 150)       return "Excellent Drinking Water";
  if (ppm <= 300)       return "Good Quality Water";
  if (ppm <= 500)       return "Average Quality - Not Recommended";
  return "BAD Water (High TDS)";
}

// =====================================================
// SLAVE: quality code → text
// =====================================================
String slaveQualityText(uint8_t code) {
  switch (code) {
    case 0:  return "Sensor Error / No Reading";
    case 1:  return "Excellent Drinking Water";
    case 2:  return "Good Quality Water";
    case 3:  return "Average - Not Recommended";
    case 4:  return "BAD Water (High TDS)";
    default: return "Unknown Code";
  }
}

// =====================================================
// ESP-NOW: Receive Callback (data from SLAVE)
// =====================================================
void OnDataRecv(const uint8_t *mac, const uint8_t *incomingData, int len) {
  Serial.println("\n[ESP-NOW] Data received from SLAVE");
  if (len == sizeof(rxData)) {
    memcpy(&rxData, incomingData, sizeof(rxData));
    newDataReceived = true;
    hasSlaveData    = true;
    Serial.printf("  Sub TDS   : %.1f ppm (code %d)\n", rxData.tdsPpm, rxData.waterQualityCode);
    Serial.printf("  Sub Level : %.1f%% (%.1f cm)\n", rxData.tankLevelPercent, rxData.tankLevelCm);
    Serial.printf("  Flow1     : %.2f L/min | Flow2: %.2f L/min\n", rxData.flow1_Lmin, rxData.flow2_Lmin);
  } else {
    Serial.printf("[ESP-NOW] Unexpected packet size: %d (expected %d)\n", len, sizeof(rxData));
  }
}

// =====================================================
// WiFi connect helper
// =====================================================
void connectWiFi() {
  WiFi.mode(WIFI_STA);
  Serial.printf("[WiFi] Connecting to '%s'", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 15000) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("[WiFi] Connected. IP: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("[WiFi] Connection FAILED — running offline");
  }

  fbClient.setInsecure(); // skip TLS certificate verification (dev mode)
}

// =====================================================
// FIREBASE: PUT /waterSystem/status.json
//
// JSON structure (matches backend server.js listener):
// {
//   "master": {
//     "tdsPpm": ..., "waterQuality": "...",
//     "tankLevelPercent": ..., "tankLevelCm": ...
//   },
//   "slave": {
//     "flow1_Lmin": ..., "flow2_Lmin": ...,
//     "tdsPpm": ..., "waterQualityCode": ...,
//     "waterQuality": "...",
//     "tankLevelPercent": ..., "tankLevelCm": ...
//   }
// }
// =====================================================
void sendToFirebase(
  float masterTds,
  float masterLevelPercent,
  float masterLevelCm,
  String masterQuality
) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[Firebase] WiFi not connected — skipping upload");
    return;
  }

  // Build JSON payload
  String json = "{";

  json += "\"master\":{";
  json += "\"tdsPpm\":"             + String(masterTds, 1)           + ",";
  json += "\"waterQuality\":\""     + masterQuality                  + "\",";
  json += "\"tankLevelPercent\":"   + String(masterLevelPercent, 1)  + ",";
  json += "\"tankLevelCm\":"        + String(masterLevelCm, 1);
  json += "}";

  if (hasSlaveData) {
    json += ",\"slave\":{";
    json += "\"flow1_Lmin\":"        + String(rxData.flow1_Lmin, 2)       + ",";
    json += "\"flow2_Lmin\":"        + String(rxData.flow2_Lmin, 2)       + ",";
    json += "\"tdsPpm\":"            + String(rxData.tdsPpm, 1)           + ",";
    json += "\"waterQualityCode\":"  + String(rxData.waterQualityCode)    + ",";
    json += "\"waterQuality\":\""    + slaveQualityText(rxData.waterQualityCode) + "\",";
    json += "\"tankLevelPercent\":"  + String(rxData.tankLevelPercent, 1) + ",";
    json += "\"tankLevelCm\":"       + String(rxData.tankLevelCm, 1);
    json += "}";
  }

  json += "}";

  // Full Firebase REST URL
  String url = "https://" + String(FIREBASE_HOST) +
               "/waterSystem/status.json?auth=" + String(FIREBASE_AUTH);

  Serial.println("[Firebase] Uploading...");
  Serial.println("  URL    : " + url);
  Serial.println("  Payload: " + json);

  HTTPClient http;
  if (!http.begin(fbClient, url)) {
    Serial.println("[Firebase] HTTP begin FAILED");
    return;
  }

  http.addHeader("Content-Type", "application/json");
  int httpCode = http.PUT(json);

  Serial.printf("[Firebase] Response code: %d\n", httpCode);
  if (httpCode > 0) {
    Serial.println("[Firebase] Response: " + http.getString());
  }

  http.end();
}

// =====================================================
// SETUP
// =====================================================
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n[MASTER NODE] HydroNet Monitor — Booting...");

  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(TDS_PIN,  INPUT);

  // WiFi STA mode (required for both ESP-NOW & HTTP)
  // Note: WiFi.begin() is called inside connectWiFi()
  WiFi.mode(WIFI_STA);
  Serial.print("[WiFi] MASTER MAC: ");
  Serial.println(WiFi.macAddress());

  // Init ESP-NOW BEFORE connecting WiFi
  if (esp_now_init() != ESP_OK) {
    Serial.println("[ESP-NOW] Init FAILED");
  } else {
    esp_now_register_recv_cb(esp_now_recv_cb_t(OnDataRecv));
    Serial.println("[ESP-NOW] Receiver ready — listening for SLAVE...");
  }

  // Connect WiFi
  connectWiFi();

  Serial.println("[MASTER NODE] Ready — Firebase upload every 5s");
}

// =====================================================
// LOOP
// =====================================================
void loop() {
  // ── Read local master sensors ──────────────────────────
  float masterTdsPpm      = readTDSppm();
  String masterQualityStr = getWaterQualityStatus(masterTdsPpm);

  float masterDist        = readDistanceCm();
  float masterLevelCm     = -1;
  float masterLevelPct    = -1;

  if (masterDist > 0) {
    masterLevelCm  = constrain(TANK_HEIGHT_CM - masterDist, 0, TANK_HEIGHT_CM);
    masterLevelPct = (masterLevelCm / TANK_HEIGHT_CM) * 100.0;
  }

  // ── Serial print – master ──────────────────────────────
  Serial.println("\n=================================================");
  Serial.println("MASTER TANK — Local Sensors");
  Serial.println("-------------------------------------------------");
  Serial.printf("TDS          : %.1f ppm\n", masterTdsPpm);
  Serial.printf("Water Status : %s\n", masterQualityStr.c_str());
  if (masterDist < 0) {
    Serial.println("Ultrasonic   : ERROR (no echo)");
  } else {
    Serial.printf("Distance     : %.1f cm | Level: %.1f cm (%.1f%%)\n",
      masterDist, masterLevelCm, masterLevelPct);
  }

  // ── Serial print – slave (if new data arrived) ─────────
  if (newDataReceived) {
    newDataReceived = false;
    Serial.println("\nSLAVE TANK (Sub Tank) — via ESP-NOW");
    Serial.println("-------------------------------------------------");
    Serial.printf("Flow Line 1  : %.2f L/min\n", rxData.flow1_Lmin);
    Serial.printf("Flow Line 2  : %.2f L/min\n", rxData.flow2_Lmin);
    Serial.printf("TDS          : %.1f ppm (code %d)\n", rxData.tdsPpm, rxData.waterQualityCode);
    Serial.printf("Water Status : %s\n", slaveQualityText(rxData.waterQualityCode).c_str());
    Serial.printf("Tank Level   : %.1f%% (%.1f cm)\n", rxData.tankLevelPercent, rxData.tankLevelCm);
  }

  // ── Firebase upload every FIREBASE_INTERVAL ms ─────────
  unsigned long now = millis();
  if (now - lastFirebaseMillis >= FIREBASE_INTERVAL) {
    lastFirebaseMillis = now;
    sendToFirebase(masterTdsPpm, masterLevelPct, masterLevelCm, masterQualityStr);
  }

  // WiFi reconnect guard
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] Reconnecting...");
    connectWiFi();
  }

  delay(3000);
}

/*
  ================================================================
  ESP32 SUB/SLAVE – TANK NODE
  HydroNet Monitor — Sub Tank Firmware v1.0
  ================================================================
  Hardware:
    - Flow sensor 1  -> GPIO17  (interrupt-driven, YF-S201 type)
    - Flow sensor 2  -> GPIO16  (interrupt-driven, YF-S201 type)
    - Relay 1        -> GPIO27  (water line 1 control)
    - Relay 2        -> GPIO26  (water line 2 control)
    - TDS sensor     -> GPIO34  (ADC, analog)
    - Ultrasonic     -> Trig=GPIO15, Echo=GPIO2

  Sends struct_message to MASTER every 1 second via ESP-NOW.
  MASTER MAC: EC:62:60:83:EB:C8
  ================================================================
*/

#include <WiFi.h>
#include <esp_now.h>

// ---------------- PIN CONFIG ----------------
const int FLOW1_PIN   = 17;   // Flow sensor 1 (interrupt)
const int FLOW2_PIN   = 16;   // Flow sensor 2 (interrupt)
const int RELAY1_PIN  = 27;   // Relay for line 1
const int RELAY2_PIN  = 26;   // Relay for line 2
const int TDS_PIN     = 34;   // TDS sensor analog output
const int TRIG_PIN    = 15;   // Ultrasonic Trigger
const int ECHO_PIN    = 2;    // Ultrasonic Echo

// ---------------- ADC / VOLTAGE CONFIG ----------------
const float VREF      = 3.3;    // ESP32 ADC reference voltage (3.3V)
const int   ADC_RES   = 4095;   // 12-bit ADC resolution

// ---------------- TANK CONFIG ----------------
const float TANK_HEIGHT_CM = 100.0; // Sub tank height in cm – adjust per actual tank

// ---------------- TDS CALIBRATION ----------------
// 1.0V → 500 ppm for typical TDS probes; adjust TDS_FACTOR per your calibration
const float TDS_FACTOR = 500.0;

// ---------------- FLOW SENSOR CALIBRATION ----------------
// YF-S201: ~450 pulses per litre. Adjust if using a different sensor.
const float PULSES_PER_LITER = 450.0;

// ---------------- ESP-NOW – MASTER MAC ----------------
// MASTER ESP32 MAC address (STA mode) → ec:62:60:83:eb:c8
uint8_t masterAddress[] = { 0xEC, 0x62, 0x60, 0x83, 0xEB, 0xC8 };

// ---------------- DATA STRUCTURE TO SEND ----------------
// Must be identical to the struct in the MASTER sketch
typedef struct struct_message {
  float   tdsPpm;
  uint8_t waterQualityCode;   // 0=error, 1=excellent, 2=good, 3=average, 4=bad
  float   tankLevelPercent;
  float   tankLevelCm;
  float   flow1_Lmin;
  float   flow2_Lmin;
} struct_message;

struct_message txData;

// ---------------- FLOW SENSOR PULSE COUNTS ----------------
volatile unsigned long flow1PulseCount = 0;
volatile unsigned long flow2PulseCount = 0;

// ---------------- TIME CONTROL ----------------
unsigned long lastMeasureMillis = 0;
const unsigned long MEASURE_INTERVAL = 1000; // 1 second

// =====================================================
// INTERRUPT HANDLERS — Flow Sensors
// =====================================================
void IRAM_ATTR flow1ISR() { flow1PulseCount++; }
void IRAM_ATTR flow2ISR() { flow2PulseCount++; }

// =====================================================
// ULTRASONIC — Read Distance (cm)
// =====================================================
float readDistanceCm() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(3);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  long duration = pulseIn(ECHO_PIN, HIGH, 30000); // 30ms timeout
  if (duration == 0) return -1; // sensor error / no echo

  return duration / 58.0; // speed of sound → cm
}

// =====================================================
// TDS — Read ppm (30-sample average)
// =====================================================
float readTDSppm() {
  const int NUM_SAMPLES = 30;
  long sum = 0;
  for (int i = 0; i < NUM_SAMPLES; i++) {
    sum += analogRead(TDS_PIN);
    delay(5);
  }
  float avgAdc   = (float)sum / NUM_SAMPLES;
  float voltage  = (avgAdc / ADC_RES) * VREF;  // Volts
  return voltage * TDS_FACTOR;                  // ppm
}

// =====================================================
// WATER QUALITY — TDS ppm → quality code
// =====================================================
uint8_t getWaterQualityCode(float tdsPpm) {
  if (tdsPpm <= 0)   return 0; // error / no reading
  if (tdsPpm <= 150) return 1; // excellent
  if (tdsPpm <= 300) return 2; // good
  if (tdsPpm <= 500) return 3; // average / not recommended
  return 4;                    // bad
}

// =====================================================
// ESP-NOW — Send Callback
// =====================================================
void OnDataSent(const uint8_t *mac_addr, esp_now_send_status_t status) {
  Serial.print("[ESP-NOW] Send: ");
  Serial.println(status == ESP_NOW_SEND_SUCCESS ? "SUCCESS" : "FAIL");
}

// =====================================================
// SETUP
// =====================================================
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n[SUB TANK NODE] Starting HydroNet Slave...");

  // GPIO init
  pinMode(FLOW1_PIN, INPUT_PULLUP);
  pinMode(FLOW2_PIN, INPUT_PULLUP);
  pinMode(RELAY1_PIN, OUTPUT);
  pinMode(RELAY2_PIN, OUTPUT);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(TDS_PIN, INPUT);

  // Relays OFF at boot
  digitalWrite(RELAY1_PIN, LOW);
  digitalWrite(RELAY2_PIN, LOW);

  // Attach interrupts for flow sensors (rising edge = pulse)
  attachInterrupt(digitalPinToInterrupt(FLOW1_PIN), flow1ISR, RISING);
  attachInterrupt(digitalPinToInterrupt(FLOW2_PIN), flow2ISR, RISING);

  // WiFi STA mode required for ESP-NOW
  WiFi.mode(WIFI_STA);
  Serial.print("[WiFi] This ESP32 MAC: ");
  Serial.println(WiFi.macAddress());

  // Init ESP-NOW
  if (esp_now_init() != ESP_OK) {
    Serial.println("[ESP-NOW] Init FAILED — check WiFi mode");
    return;
  }
  esp_now_register_send_cb(OnDataSent);

  // Register MASTER as a peer
  esp_now_peer_info_t peerInfo;
  memset(&peerInfo, 0, sizeof(peerInfo));
  memcpy(peerInfo.peer_addr, masterAddress, 6);
  peerInfo.channel = 0;
  peerInfo.encrypt = false;

  if (esp_now_add_peer(&peerInfo) != ESP_OK) {
    Serial.println("[ESP-NOW] Failed to add MASTER peer");
    return;
  }

  Serial.println("[SUB TANK NODE] Ready — sending to MASTER every 1s");
}

// =====================================================
// LOOP
// =====================================================
void loop() {
  unsigned long currentMillis = millis();

  if (currentMillis - lastMeasureMillis >= MEASURE_INTERVAL) {
    lastMeasureMillis = currentMillis;

    // ── Safely snapshot & reset pulse counters ─────────────
    noInterrupts();
    unsigned long flow1Count = flow1PulseCount;
    unsigned long flow2Count = flow2PulseCount;
    flow1PulseCount = 0;
    flow2PulseCount = 0;
    interrupts();

    // ── Flow rate (L/min) ──────────────────────────────────
    // Pulses counted in exactly 1 second:
    //   L/s = pulses / PULSES_PER_LITER;  L/min = L/s × 60
    float flow1_Lmin = ((float)flow1Count / PULSES_PER_LITER) * 60.0;
    float flow2_Lmin = ((float)flow2Count / PULSES_PER_LITER) * 60.0;

    // ── TDS & Water Quality ────────────────────────────────
    float   tdsPpm     = readTDSppm();
    uint8_t qualityCode = getWaterQualityCode(tdsPpm);

    // ── Ultrasonic — Tank Level ────────────────────────────
    float distanceToWater  = readDistanceCm();
    float waterLevelCm     = -1;
    float waterLevelPercent = -1;

    if (distanceToWater > 0) {
      waterLevelCm      = TANK_HEIGHT_CM - distanceToWater;
      waterLevelCm      = constrain(waterLevelCm, 0, TANK_HEIGHT_CM);
      waterLevelPercent = (waterLevelCm / TANK_HEIGHT_CM) * 100.0;
    }

    // ── Pack data struct ───────────────────────────────────
    txData.tdsPpm           = tdsPpm;
    txData.waterQualityCode = qualityCode;
    txData.tankLevelPercent = waterLevelPercent;
    txData.tankLevelCm      = waterLevelCm;
    txData.flow1_Lmin       = flow1_Lmin;
    txData.flow2_Lmin       = flow2_Lmin;

    // ── Serial debug ───────────────────────────────────────
    Serial.println("-------------------------------------------------");
    Serial.printf("[FLOW ] Line1: %.2f L/min | Line2: %.2f L/min\n", flow1_Lmin, flow2_Lmin);
    Serial.printf("[TDS  ] %.1f ppm | Quality code: %d\n", tdsPpm, qualityCode);
    if (waterLevelPercent >= 0)
      Serial.printf("[TANK ] %.1f%% (%.1f cm)\n", waterLevelPercent, waterLevelCm);
    else
      Serial.println("[TANK ] Ultrasonic error — no echo");

    // ── Relay logic: cut supply if water quality is BAD ───
    if (qualityCode >= 4) {
      // BAD water → relays OFF (block supply)
      digitalWrite(RELAY1_PIN, LOW);
      digitalWrite(RELAY2_PIN, LOW);
      Serial.println("[RELAY] OFF — BAD water quality");
    } else {
      // Acceptable quality → relays ON
      digitalWrite(RELAY1_PIN, HIGH);
      digitalWrite(RELAY2_PIN, HIGH);
      Serial.println("[RELAY] ON");
    }

    // ── Send via ESP-NOW ───────────────────────────────────
    esp_err_t result = esp_now_send(masterAddress, (uint8_t *)&txData, sizeof(txData));
    if (result == ESP_OK) {
      Serial.println("[ESP-NOW] Packet sent to MASTER");
    } else {
      Serial.printf("[ESP-NOW] Send error: %d\n", result);
    }
  }
}

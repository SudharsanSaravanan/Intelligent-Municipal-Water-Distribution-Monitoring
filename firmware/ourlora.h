/*
 * OurLoRa - Custom LoRa Communication Library

 * This library provides simple LoRa communication functions
 * without external dependencies. Only uses built-in SPI.h
 * 
 * Compatible with: SX1278, SX1276 LoRa modules
 * Frequency: 433 MHz / 868 MHz / 915 MHz (configurable)

 * Date: February 2026
 * DevisGit18 ( devisreesumesh@gmail.com )
 
 */
#ifndef OUR_LORA_H
#define OUR_LORA_H

#include <Arduino.h>
#include <SPI.h>

// ============================================================
//  HARDWARE PIN CONFIGURATION
// ============================================================
// Change these if you wire LoRa module to different pins
#define LORA_CS_PIN    5   // Chip Select (NSS)
#define LORA_RST_PIN   2   // Reset
#define LORA_DIO0_PIN  4   // Digital I/O 0 (interrupt, optional)

// ============================================================
//  SX1278 CHIP REGISTER ADDRESSES
// ============================================================
// These are memory locations inside the LoRa chip
// Reference: SX1278 Datasheet by Semtech
#define REG_FIFO                 0x00  // FIFO data buffer
#define REG_OP_MODE              0x01  // Operating mode control
#define REG_FRF_MSB              0x06  // Frequency setting (MSB)
#define REG_FRF_MID              0x07  // Frequency setting (MID)
#define REG_FRF_LSB              0x08  // Frequency setting (LSB)
#define REG_PA_CONFIG            0x09  // Power amplifier config
#define REG_LNA                  0x0C  // Low noise amplifier
#define REG_FIFO_ADDR_PTR        0x0D  // FIFO SPI pointer
#define REG_FIFO_TX_BASE_ADDR    0x0E  // TX base address in FIFO
#define REG_FIFO_RX_BASE_ADDR    0x0F  // RX base address in FIFO
#define REG_FIFO_RX_CURRENT_ADDR 0x10  // Current RX address
#define REG_IRQ_FLAGS            0x12  // Interrupt flags
#define REG_RX_NB_BYTES          0x13  // Number of bytes received
#define REG_PKT_RSSI_VALUE       0x1A  // Packet signal strength
#define REG_PKT_SNR_VALUE        0x19  // Packet signal to noise (FIXED: was 0x1B)
#define REG_MODEM_CONFIG_1       0x1D  // Modem configuration 1
#define REG_MODEM_CONFIG_2       0x1E  // Modem configuration 2
#define REG_PREAMBLE_MSB         0x20  // Preamble length (MSB)
#define REG_PREAMBLE_LSB         0x21  // Preamble length (LSB)
#define REG_PAYLOAD_LENGTH       0x22  // Payload length
#define REG_MODEM_CONFIG_3       0x26  // Modem configuration 3
#define REG_SYNC_WORD            0x39  // Network sync word
#define REG_VERSION              0x42  // Chip version
#define REG_PA_DAC               0x4D  // High power PA settings

// ============================================================
//  OPERATING MODES
// ============================================================
#define MODE_LONG_RANGE_MODE     0x80  // LoRa mode (vs FSK)
#define MODE_SLEEP               0x00  // Sleep mode
#define MODE_STDBY               0x01  // Standby mode
#define MODE_TX                  0x03  // Transmit mode
#define MODE_RX_CONTINUOUS       0x05  // Continuous receive

// ============================================================
//  INTERRUPT FLAGS
// ============================================================
#define IRQ_TX_DONE_MASK         0x08  // TX complete flag
#define IRQ_RX_DONE_MASK         0x40  // RX complete flag
#define IRQ_PAYLOAD_CRC_ERROR    0x20  // CRC error flag

// ============================================================
//  POWER AMPLIFIER SETTINGS
// ============================================================
#define PA_BOOST                 0x80  // Use PA_BOOST pin

// ============================================================
//  GLOBAL VARIABLES (Private)
// ============================================================
static int _lastRssi = 0;        // Last received signal strength
static int _lastSnr = 0;         // Last signal to noise ratio
static long _currentFreq = 0;    // Current frequency setting

// ============================================================
//  LOW-LEVEL REGISTER ACCESS FUNCTIONS
// ============================================================

/*
 * Write a value to a register in the LoRa chip
 * 
 * Parameters:
 *   address - Register address (0x00 to 0x7F)
 *   value   - Byte value to write
 */
void write_lora_register(uint8_t address, uint8_t value) {
  digitalWrite(LORA_CS_PIN, LOW);        // Select chip
  SPI.transfer(address | 0x80);          // Write mode (MSB = 1)
  SPI.transfer(value);                   // Send value
  digitalWrite(LORA_CS_PIN, HIGH);       // Deselect chip
}

/*
 * Read a value from a register in the LoRa chip
 * 
 * Parameters:
 *   address - Register address (0x00 to 0x7F)
 * 
 * Returns:
 *   Byte value from register
 */
uint8_t read_lora_register(uint8_t address) {
  digitalWrite(LORA_CS_PIN, LOW);        // Select chip
  SPI.transfer(address & 0x7F);          // Read mode (MSB = 0)
  uint8_t value = SPI.transfer(0x00);    // Read value
  digitalWrite(LORA_CS_PIN, HIGH);       // Deselect chip
  return value;
}

// ============================================================
//  MAIN LORA FUNCTIONS
// ============================================================

/*
 * Initialize the LoRa module
 * 
 * Parameters:
 *   frequency_mhz - Operating frequency in MHz (433, 868, or 915)
 * 
 * Returns:
 *   true  - Initialization successful
 *   false - Initialization failed (module not detected)
 * 
 * Example:
 *   if (!setup_ourlora(433)) {
 *     Serial.println("LoRa init failed!");
 *   }
 */
bool setup_ourlora(long frequency_mhz) {
  Serial.println("\n=== Initializing OurLoRa ===");
  
  // Configure pins
  pinMode(LORA_CS_PIN, OUTPUT);
  pinMode(LORA_RST_PIN, OUTPUT);
  pinMode(LORA_DIO0_PIN, INPUT);
  digitalWrite(LORA_CS_PIN, HIGH);
  
  // Hardware reset
  digitalWrite(LORA_RST_PIN, LOW);
  delay(10);
  digitalWrite(LORA_RST_PIN, HIGH);
  delay(10);
  
  // Check chip version (SX1278 should return 0x12)
  uint8_t version = read_lora_register(REG_VERSION);
  Serial.print("LoRa Chip Version: 0x");
  Serial.println(version, HEX);
  
  if (version != 0x12) {
    Serial.println("ERROR: LoRa module not detected!");
    return false;
  }
  
  // Enter sleep mode to configure
  write_lora_register(REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_SLEEP);
  delay(10);
  
  // Calculate and set frequency
  // Formula: FRF = (Frequency × 2^19) / 32000000
  uint32_t frf = ((uint64_t)frequency_mhz * 1000000 << 19) / 32000000;
  write_lora_register(REG_FRF_MSB, (uint8_t)(frf >> 16));
  write_lora_register(REG_FRF_MID, (uint8_t)(frf >> 8));
  write_lora_register(REG_FRF_LSB, (uint8_t)(frf >> 0));
  _currentFreq = frequency_mhz;
  
  // Set FIFO base addresses
  write_lora_register(REG_FIFO_TX_BASE_ADDR, 0x00);
  write_lora_register(REG_FIFO_RX_BASE_ADDR, 0x00);
  
  // Enable LNA boost
  write_lora_register(REG_LNA, read_lora_register(REG_LNA) | 0x03);
  
  // Configure modem
  // Bandwidth = 125 kHz, Coding Rate = 4/5, Explicit Header
  write_lora_register(REG_MODEM_CONFIG_1, 0x72);
  
  // Spreading Factor = 7, CRC enabled
  write_lora_register(REG_MODEM_CONFIG_2, 0x74);
  
  // Low data rate optimize OFF, AGC auto ON
  write_lora_register(REG_MODEM_CONFIG_3, 0x04);
  
  // Set preamble length (8 symbols)
  write_lora_register(REG_PREAMBLE_MSB, 0x00);
  write_lora_register(REG_PREAMBLE_LSB, 0x08);
  
  // Set sync word (0x12 = private network)
  write_lora_register(REG_SYNC_WORD, 0x12);
  
  // Set output power (17 dBm using PA_BOOST)
  write_lora_register(REG_PA_CONFIG, PA_BOOST | 0x0F);
  
  // Enable high power mode
  write_lora_register(REG_PA_DAC, 0x87);
  
  // Enter standby mode
  write_lora_register(REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_STDBY);
  delay(10);
  
  Serial.print("OurLoRa initialized at ");
  Serial.print(frequency_mhz);
  Serial.println(" MHz!");
  
  return true;
}

/*
 * Send a message via LoRa
 * 
 * Parameters:
 *   message - Pointer to data buffer to send
 *   length  - Number of bytes to send
 * 
 * Returns:
 *   true  - Message sent successfully
 *   false - Transmission failed (timeout)
 * 
 * Example:
 *   String msg = "Hello";
 *   send_a_msg((uint8_t*)msg.c_str(), msg.length());
 */
bool send_a_msg(uint8_t *message, uint8_t length) {
  // Enter standby mode
  write_lora_register(REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_STDBY);
  
  // Clear all interrupt flags
  write_lora_register(REG_IRQ_FLAGS, 0xFF);
  
  // Set FIFO pointer to TX base
  write_lora_register(REG_FIFO_ADDR_PTR, 0x00);
  
  // Write data to FIFO buffer
  digitalWrite(LORA_CS_PIN, LOW);
  SPI.transfer(REG_FIFO | 0x80);  // Write mode
  for (int i = 0; i < length; i++) {
    SPI.transfer(message[i]);
  }
  digitalWrite(LORA_CS_PIN, HIGH);
  
  // Set payload length
  write_lora_register(REG_PAYLOAD_LENGTH, length);
  
  // Start transmission
  write_lora_register(REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_TX);
  
  // Wait for TX done (timeout after 2 seconds)
  unsigned long startTime = millis();
  while (!(read_lora_register(REG_IRQ_FLAGS) & IRQ_TX_DONE_MASK)) {
    if (millis() - startTime > 2000) {
      Serial.println("TX timeout!");
      return false;
    }
    delay(1);
  }
  
  // Clear TX done flag
  write_lora_register(REG_IRQ_FLAGS, IRQ_TX_DONE_MASK);
  
  // Return to standby
  write_lora_register(REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_STDBY);
  
  return true;
}

/*
 * Check if a message has been received
 * 
 * Parameters:
 *   buffer    - Pointer to buffer where received data will be stored
 *   maxLength - Maximum size of buffer
 * 
 * Returns:
 *   > 0  - Number of bytes received
 *   0    - No packet received
 *   -1   - CRC error (corrupted packet)
 * 
 * Example:
 *   uint8_t rxBuffer[256];
 *   int size = check_for_msg(rxBuffer, sizeof(rxBuffer));
 *   if (size > 0) {
 *     Serial.print("Received: ");
 *     for (int i = 0; i < size; i++) {
 *       Serial.print((char)rxBuffer[i]);
 *     }
 *   }
 */
int check_for_msg(uint8_t *buffer, uint8_t maxLength) {
  // Read interrupt flags
  uint8_t irqFlags = read_lora_register(REG_IRQ_FLAGS);
  
  // Check if packet received
  if (!(irqFlags & IRQ_RX_DONE_MASK)) {
    return 0;  // No packet
  }
  
  // Clear RX done flag
  write_lora_register(REG_IRQ_FLAGS, IRQ_RX_DONE_MASK);
  
  // Check for CRC error
  if (irqFlags & IRQ_PAYLOAD_CRC_ERROR) {
    Serial.println("CRC error - packet corrupted!");
    write_lora_register(REG_IRQ_FLAGS, IRQ_PAYLOAD_CRC_ERROR);
    return -1;
  }
  
  // Get packet length
  uint8_t packetLength = read_lora_register(REG_RX_NB_BYTES);
  if (packetLength > maxLength) {
    packetLength = maxLength;  // Truncate if too large
  }
  
  // Get current FIFO RX address
  uint8_t currentAddr = read_lora_register(REG_FIFO_RX_CURRENT_ADDR);
  write_lora_register(REG_FIFO_ADDR_PTR, currentAddr);
  
  // Read data from FIFO
  digitalWrite(LORA_CS_PIN, LOW);
  SPI.transfer(REG_FIFO & 0x7F);  // Read mode
  for (int i = 0; i < packetLength; i++) {
    buffer[i] = SPI.transfer(0x00);
  }
  digitalWrite(LORA_CS_PIN, HIGH);
  
  // Read signal quality
  // Use frequency-dependent offset for accurate RSSI
  // < 525 MHz uses offset 164, >= 525 MHz uses offset 157
  int rssi_offset = (_currentFreq < 525) ? 164 : 157;
  _lastRssi = read_lora_register(REG_PKT_RSSI_VALUE) - rssi_offset;
  _lastSnr = (int8_t)read_lora_register(REG_PKT_SNR_VALUE) / 4;
  
  return packetLength;
}

/*
 * Start continuous receive mode
 * Call this once in setup() to enable receiving
 * 
 * Example:
 *   start_listening();
 */
void start_listening() {
  // Enter standby
  write_lora_register(REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_STDBY);
  
  // Clear interrupt flags
  write_lora_register(REG_IRQ_FLAGS, 0xFF);
  
  // Set FIFO RX base
  write_lora_register(REG_FIFO_ADDR_PTR, 0x00);
  
  // Enter continuous RX mode
  write_lora_register(REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_RX_CONTINUOUS);
}

/*
 * Get signal strength of last received packet
 * 
 * Returns:
 *   RSSI value in dBm (typically -120 to -30)
 *   More negative = weaker signal
 * 
 * Example:
 *   int rssi = get_signal_strength();
 *   Serial.print("Signal: ");
 *   Serial.print(rssi);
 *   Serial.println(" dBm");
 */
int get_signal_strength() {
  return _lastRssi;
}

/*
 * Get signal to noise ratio of last received packet
 * 
 * Returns:
 *   SNR value in dB
 *   Higher = better quality
 * 
 * Example:
 *   int snr = get_signal_quality();
 *   Serial.print("SNR: ");
 *   Serial.print(snr);
 *   Serial.println(" dB");
 */
int get_signal_quality() {
  return _lastSnr;
}

/*
 * Put LoRa module in sleep mode (low power)
 * Use when you want to save battery
 * 
 * Example:
 *   go_to_sleep();
 */
void go_to_sleep() {
  write_lora_register(REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_SLEEP);
}

/*
 * Wake up LoRa module (exit sleep mode)
 * 
 * Example:
 *   wake_up_lora();
 */
void wake_up_lora() {
  write_lora_register(REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_STDBY);
  delay(10);
}

/*
 * Change transmission power
 * 
 * Parameters:
 *   power_dbm - Power in dBm (2 to 17)
 *               Higher = longer range, more battery use
 * 
 * Example:
 *   set_tx_power(17);  // Maximum power
 */
void set_tx_power(int power_dbm) {
  if (power_dbm < 2) power_dbm = 2;
  if (power_dbm > 17) power_dbm = 17;
  
  write_lora_register(REG_PA_CONFIG, PA_BOOST | (power_dbm - 2));
}

/*
 * Change sync word (network ID)
 * Both sender and receiver must use same sync word
 * 
 * Parameters:
 *   sync_word - Byte value (0x00 to 0xFF)
 *               Default: 0x12 (private network)
 *               LoRaWAN: 0x34
 * 
 * Example:
 *   set_network_id(0x42);  // Custom network
 */
void set_network_id(uint8_t sync_word) {
  write_lora_register(REG_SYNC_WORD, sync_word);
}

#endif // OUR_LORA_H
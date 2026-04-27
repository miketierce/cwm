/*
 * CWM Relay Multiplexer + AD9833 DDS Controller
 *
 * Extends relay_controller.ino with AD9833 DDS control over SPI.
 * All existing relay commands ('1'–'8', '0', 'A', 'B', '?') work unchanged.
 *
 * New commands (newline-terminated):
 *   F<freq_hz>   → Set DDS frequency (e.g., "F29925\n" for 29.925 kHz)
 *   Foff         → Silence DDS (set to 0 Hz / reset)
 *   D?           → Report current DDS frequency
 *
 * Hardware additions:
 *   Arduino D10  → AD9833 FSYNC (CS)
 *   Arduino D11  → AD9833 SDATA (MOSI)  [shared SPI]
 *   Arduino D13  → AD9833 SCLK          [shared SPI]
 *   AD9833 VCC   → Arduino 5V
 *   AD9833 GND   → Arduino GND
 *   AD9833 OUT   → Relay board COM input (replaces PicoScope AWG)
 */

#include <SPI.h>

// ─── Relay pins (unchanged from relay_controller.ino) ───
const int RELAY_PINS[] = {2, 3, 4, 5, 6, 7, 8, 9};
const int NUM_RELAYS = 8;
const int LED_PIN = 13;  // NOTE: shared with SCK — LED blinks on SPI activity
const int RELAY_ON  = LOW;
const int RELAY_OFF = HIGH;
const int BBM_DELAY_MS = 5;
int activeRelay = 0;

// ─── AD9833 DDS ───
const int DDS_FSYNC = 10;  // CS pin for AD9833
const unsigned long DDS_MCLK = 25000000UL;  // 25 MHz reference clock (standard module)
unsigned long currentFreqHz = 0;

// AD9833 register addresses
#define AD9833_CTRL_RESET   0x2100  // B28=1, RESET=1
#define AD9833_CTRL_RUN     0x2000  // B28=1, RESET=0 (sine output)
#define AD9833_FREQ0_BASE   0x4000  // FREQ0 register (bits 13:0)
#define AD9833_FREQ0_HI     0x4000  // FREQ0 MSB14
#define AD9833_PHASE0       0xC000  // PHASE0 register

void dds_write(uint16_t data) {
  digitalWrite(DDS_FSYNC, LOW);
  // AD9833 wants MSB first, SPI Mode 2 (CPOL=1, CPHA=0)
  SPI.transfer((data >> 8) & 0xFF);
  SPI.transfer(data & 0xFF);
  digitalWrite(DDS_FSYNC, HIGH);
}

void dds_init() {
  pinMode(DDS_FSYNC, OUTPUT);
  digitalWrite(DDS_FSYNC, HIGH);
  SPI.begin();
  SPI.setDataMode(SPI_MODE2);
  SPI.setClockDivider(SPI_CLOCK_DIV2);  // 8 MHz SPI — fast updates

  // Reset the AD9833
  dds_write(AD9833_CTRL_RESET);
  delay(10);
}

void dds_set_freq(unsigned long freq_hz) {
  // Calculate 28-bit frequency register value
  // freqReg = freq * 2^28 / MCLK
  double freqReg = ((double)freq_hz * 268435456.0) / (double)DDS_MCLK;
  unsigned long regVal = (unsigned long)freqReg;

  // Split into two 14-bit writes (B28 mode)
  uint16_t lsb = (regVal & 0x3FFF) | AD9833_FREQ0_BASE;
  uint16_t msb = ((regVal >> 14) & 0x3FFF) | AD9833_FREQ0_BASE;

  dds_write(AD9833_CTRL_RESET);  // Hold reset during update
  dds_write(lsb);                // FREQ0 LSB 14 bits
  dds_write(msb);                // FREQ0 MSB 14 bits
  dds_write(AD9833_CTRL_RUN);    // Release reset — sine output

  currentFreqHz = freq_hz;
}

void dds_off() {
  dds_write(AD9833_CTRL_RESET);
  currentFreqHz = 0;
}

// ─── Relay functions (unchanged) ───
void allOff() {
  for (int i = 0; i < NUM_RELAYS; i++) {
    digitalWrite(RELAY_PINS[i], RELAY_OFF);
  }
  activeRelay = 0;
}

void activateRelay(int relay) {
  if (relay < 1 || relay > NUM_RELAYS) return;
  allOff();
  delay(BBM_DELAY_MS);
  digitalWrite(RELAY_PINS[relay - 1], RELAY_ON);
  activeRelay = relay;
}

void activateSubset(const int* relays, int count, int reportCode) {
  allOff();
  delay(BBM_DELAY_MS);
  for (int i = 0; i < count; i++) {
    int r = relays[i];
    if (r >= 1 && r <= NUM_RELAYS) {
      digitalWrite(RELAY_PINS[r - 1], RELAY_ON);
    }
  }
  activeRelay = reportCode;
}

// ─── Serial command buffer ───
char cmdBuf[32];
int cmdLen = 0;

void processCommand() {
  cmdBuf[cmdLen] = '\0';  // Null-terminate

  if (cmdLen == 0) return;

  // ── DDS commands (start with 'F' or 'D') ──
  if (cmdBuf[0] == 'F' || cmdBuf[0] == 'f') {
    if (cmdLen == 1) {
      // Bare 'F' — report frequency
      Serial.print("DDS:");
      Serial.println(currentFreqHz);
    }
    else if (strcmp(cmdBuf + 1, "off") == 0 || strcmp(cmdBuf + 1, "OFF") == 0) {
      dds_off();
      Serial.println("DDS:0");
    }
    else {
      unsigned long freq = strtoul(cmdBuf + 1, NULL, 10);
      if (freq > 0 && freq <= 12500000UL) {
        dds_set_freq(freq);
        Serial.print("DDS:");
        Serial.println(currentFreqHz);
      } else {
        Serial.println("ERR:freq out of range (1-12500000)");
      }
    }
  }
  else if (cmdBuf[0] == 'D' || cmdBuf[0] == 'd') {
    if (cmdLen >= 2 && cmdBuf[1] == '?') {
      Serial.print("DDS:");
      Serial.println(currentFreqHz);
    } else {
      Serial.println("ERR:unknown D command (use D?)");
    }
  }
  // ── Relay commands (single character, backward compatible) ──
  else if (cmdLen == 1) {
    char cmd = cmdBuf[0];
    if (cmd >= '1' && cmd <= '8') {
      activateRelay(cmd - '0');
      Serial.print("OK:");
      Serial.println(activeRelay);
    }
    else if (cmd == '0' || cmd == 'x' || cmd == 'X') {
      allOff();
      Serial.print("OK:");
      Serial.println(activeRelay);
    }
    else if (cmd == '?') {
      Serial.print("OK:");
      Serial.println(activeRelay);
    }
    else if (cmd == 'A' || cmd == 'a') {
      const int neRelays[] = {1, 2, 3, 5, 7};
      activateSubset(neRelays, 5, 9);
      Serial.println("OK:9");
    }
    else if (cmd == 'B' || cmd == 'b') {
      const int allRelays[] = {1, 2, 3, 4, 5, 6, 7, 8};
      activateSubset(allRelays, 8, 10);
      Serial.println("OK:10");
    }
    else {
      Serial.print("ERR:unknown '");
      Serial.print(cmd);
      Serial.println("'");
    }
  }
  else {
    Serial.print("ERR:unknown cmd '");
    Serial.print(cmdBuf);
    Serial.println("'");
  }
}

void setup() {
  Serial.begin(9600);

  for (int i = 0; i < NUM_RELAYS; i++) {
    pinMode(RELAY_PINS[i], OUTPUT);
    digitalWrite(RELAY_PINS[i], RELAY_OFF);
  }

  // NOTE: D13/LED is shared with SPI SCK after SPI.begin().
  // LED blink only works before SPI init.
  pinMode(LED_PIN, OUTPUT);
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_PIN, HIGH);
    delay(100);
    digitalWrite(LED_PIN, LOW);
    delay(100);
  }

  dds_init();
  dds_off();  // Start silent

  Serial.println("OK:0");
}

void loop() {
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (cmdLen > 0) {
        processCommand();
        cmdLen = 0;
      }
    }
    else if (cmdLen < 31) {
      cmdBuf[cmdLen++] = c;
    }
  }
}

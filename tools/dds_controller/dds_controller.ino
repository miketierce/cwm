/*
 * CWM AD9833 DDS Controller (3-channel)
 *
 * Controls up to 3 AD9833 DDS modules via SPI, each with independent
 * frequency and on/off. Designed for Arduino Nano #2 (DDS-dedicated).
 *
 * Hardware:
 *   - Arduino Nano #2 (ATmega328P, CH340 USB)
 *   - 3× AD9833 DDS modules (HiLetgo GY-9833)
 *   - Port: /dev/cu.usbserial-11330
 *
 * Pin mapping:
 *   D13 → SPI SCK  (shared, all 3 AD9833 CLK)
 *   D11 → SPI MOSI (shared, all 3 AD9833 DAT)
 *   D10 → FSYNC DDS #1 (CS, active LOW)
 *   D9  → FSYNC DDS #2
 *   D8  → FSYNC DDS #3
 *   5V  → All VCC
 *   GND → All GND (DGND + AGND tied together on module)
 *
 * Future: D7/D6/D5 reserved for MCP4921 DAC CS pins.
 *
 * Protocol (115200 baud, newline-terminated):
 *   F<freq>          → Set DDS #1 frequency (backward compat)
 *   F1:<freq>        → Set DDS #1 frequency
 *   F2:<freq>        → Set DDS #2 frequency
 *   F3:<freq>        → Set DDS #3 frequency
 *   Foff             → Silence all DDS
 *   F1:off           → Silence DDS #1 only
 *   F2:off / F3:off  → Silence DDS #2 / #3 only
 *   P1:<phase>       → Set DDS #1 phase offset (0-4095 = 0 to 2π)
 *   P2:<phase>       → Set DDS #2 phase offset
 *   P3:<phase>       → Set DDS #3 phase offset
 *   D?               → Report all DDS frequencies and phases
 *   ?                → Same as D?
 *
 * Response:
 *   "DDS1:<freq>"  after F1 command
 *   "DDS2:<freq>"  after F2 command
 *   "DDS3:<freq>"  after F3 command
 *   "DDS:<freq>"   after bare F command (compat)
 *   "PH1:<phase>"  after P1 command
 *   "PH2:<phase>"  after P2 command
 *   "PH3:<phase>"  after P3 command
 *   "DDS:1=<f1>,2=<f2>,3=<f3>;P:1=<p1>,2=<p2>,3=<p3>"  for D? query
 */

#include <SPI.h>

// ─── DDS chip-select pins ───
const int DDS_CS[] = {10, 9, 8};  // DDS 1, 2, 3
const int NUM_DDS = 3;
const unsigned long DDS_MCLK = 25000000UL;  // 25 MHz reference

unsigned long ddsFreq[3] = {0, 0, 0};
uint16_t ddsPhase[3] = {0, 0, 0};

// AD9833 register constants
#define AD9833_CTRL_RESET 0x2100  // B28=1, RESET=1
#define AD9833_CTRL_RUN   0x2000  // B28=1, RESET=0 (sine)
#define AD9833_FREQ0_BASE 0x4000  // FREQ0 register
#define AD9833_PHASE0_BASE 0xC000 // PHASE0 register (12-bit, 0-4095 = 0 to 2π)

void dds_write(int chip, uint16_t data) {
  int cs = DDS_CS[chip];
  digitalWrite(cs, LOW);
  SPI.transfer((data >> 8) & 0xFF);
  SPI.transfer(data & 0xFF);
  digitalWrite(cs, HIGH);
}

void dds_init(int chip) {
  int cs = DDS_CS[chip];
  pinMode(cs, OUTPUT);
  digitalWrite(cs, HIGH);
  dds_write(chip, AD9833_CTRL_RESET);
}

void dds_set_freq(int chip, unsigned long freq_hz) {
  if (chip < 0 || chip >= NUM_DDS) return;
  double freqReg = ((double)freq_hz * 268435456.0) / (double)DDS_MCLK;
  unsigned long regVal = (unsigned long)freqReg;

  uint16_t lsb = (regVal & 0x3FFF) | AD9833_FREQ0_BASE;
  uint16_t msb = ((regVal >> 14) & 0x3FFF) | AD9833_FREQ0_BASE;

  dds_write(chip, AD9833_CTRL_RESET);
  dds_write(chip, lsb);
  dds_write(chip, msb);
  dds_write(chip, AD9833_PHASE0_BASE | (ddsPhase[chip] & 0x0FFF));
  dds_write(chip, AD9833_CTRL_RUN);

  ddsFreq[chip] = freq_hz;
}

void dds_set_phase(int chip, uint16_t phase_val) {
  if (chip < 0 || chip >= NUM_DDS) return;
  ddsPhase[chip] = phase_val & 0x0FFF;  // 12-bit, 0-4095
  // Write phase register; takes effect immediately if running
  dds_write(chip, AD9833_PHASE0_BASE | ddsPhase[chip]);
}

void dds_off(int chip) {
  if (chip < 0 || chip >= NUM_DDS) return;
  dds_write(chip, AD9833_CTRL_RESET);
  ddsFreq[chip] = 0;
}

void dds_all_off() {
  for (int i = 0; i < NUM_DDS; i++) dds_off(i);
}

// ─── Serial command buffer ───
char cmdBuf[32];
int cmdLen = 0;

void processCommand() {
  cmdBuf[cmdLen] = '\0';
  if (cmdLen == 0) return;

  // ── Query ──
  if (cmdBuf[0] == '?' || (cmdBuf[0] == 'D' && cmdLen >= 2 && cmdBuf[1] == '?') ||
      (cmdBuf[0] == 'd' && cmdLen >= 2 && cmdBuf[1] == '?')) {
    Serial.print("DDS:1=");
    Serial.print(ddsFreq[0]);
    Serial.print(",2=");
    Serial.print(ddsFreq[1]);
    Serial.print(",3=");
    Serial.print(ddsFreq[2]);
    Serial.print(";P:1=");
    Serial.print(ddsPhase[0]);
    Serial.print(",2=");
    Serial.print(ddsPhase[1]);
    Serial.print(",3=");
    Serial.println(ddsPhase[2]);
    return;
  }

  // ── F commands ──
  if (cmdBuf[0] == 'F' || cmdBuf[0] == 'f') {
    // "Foff" — all off
    if (strcasecmp(cmdBuf + 1, "off") == 0) {
      dds_all_off();
      Serial.println("DDS:0");
      return;
    }

    // "F1:off", "F2:off", "F3:off"
    if (cmdLen >= 4 && cmdBuf[2] == ':' && cmdBuf[1] >= '1' && cmdBuf[1] <= '3') {
      int chip = cmdBuf[1] - '1';  // 0-indexed
      if (strcasecmp(cmdBuf + 3, "off") == 0) {
        dds_off(chip);
        Serial.print("DDS");
        Serial.print(chip + 1);
        Serial.println(":0");
        return;
      }
      // "F1:<freq>", "F2:<freq>", "F3:<freq>"
      unsigned long freq = strtoul(cmdBuf + 3, NULL, 10);
      if (freq > 0 && freq <= 12500000UL) {
        dds_set_freq(chip, freq);
        Serial.print("DDS");
        Serial.print(chip + 1);
        Serial.print(":");
        Serial.println(ddsFreq[chip]);
      } else {
        Serial.println("ERR:freq 1-12500000");
      }
      return;
    }

    // Bare "F<freq>" — DDS #1 (backward compat)
    if (cmdLen > 1) {
      unsigned long freq = strtoul(cmdBuf + 1, NULL, 10);
      if (freq > 0 && freq <= 12500000UL) {
        dds_set_freq(0, freq);
        Serial.print("DDS:");
        Serial.println(ddsFreq[0]);
      } else {
        Serial.println("ERR:freq 1-12500000");
      }
      return;
    }

    // Bare "F" — report DDS #1
    Serial.print("DDS:");
    Serial.println(ddsFreq[0]);
    return;
  }

  // ── P commands (phase) ──
  if (cmdBuf[0] == 'P' || cmdBuf[0] == 'p') {
    // "P1:<phase>", "P2:<phase>", "P3:<phase>"
    if (cmdLen >= 4 && cmdBuf[2] == ':' && cmdBuf[1] >= '1' && cmdBuf[1] <= '3') {
      int chip = cmdBuf[1] - '1';
      unsigned long pval = strtoul(cmdBuf + 3, NULL, 10);
      if (pval <= 4095) {
        dds_set_phase(chip, (uint16_t)pval);
        Serial.print("PH");
        Serial.print(chip + 1);
        Serial.print(":");
        Serial.println(ddsPhase[chip]);
      } else {
        Serial.println("ERR:phase 0-4095");
      }
      return;
    }
  }

  Serial.print("ERR:unknown '");
  Serial.print(cmdBuf);
  Serial.println("'");
}

void setup() {
  Serial.begin(115200);

  SPI.begin();
  SPI.setDataMode(SPI_MODE2);
  SPI.setClockDivider(SPI_CLOCK_DIV2);  // 8 MHz

  for (int i = 0; i < NUM_DDS; i++) {
    dds_init(i);
  }
  dds_all_off();

  // Startup blink — D13 is SPI SCK so skip LED blink after SPI.begin()
  // Just send ready message
  Serial.println("DDS:ready");
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

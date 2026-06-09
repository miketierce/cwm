/*
 * CWM 16-Channel Relay Multiplexer Controller
 *
 * Controls a 16-channel opto-isolated relay module for switching
 * plate/rod sense PZTs onto PicoScope Channel A.
 * One relay active at a time (break-before-make) for RX mux (1–7).
 * Relay 8 (TX isolation) can be controlled independently via T commands.
 *
 * Hardware:
 *   - Arduino Nano #1 (ATmega328P, CH340 USB)
 *   - 16-channel 5V relay module (active-LOW opto-isolated)
 *   - Port: /dev/cu.usbserial-11310
 *
 * Pin mapping (16 relays):
 *   Arduino D2   → Relay 1  (RX mux)
 *   Arduino D3   → Relay 2  (RX mux)
 *   Arduino D4   → Relay 3  (RX mux)
 *   Arduino D5   → Relay 4  (RX mux)
 *   Arduino D6   → Relay 5  (RX mux)
 *   Arduino D7   → Relay 6  (RX mux)
 *   Arduino D8   → Relay 7  (RX mux)
 *   Arduino D9   → Relay 8  (TX isolation — NC wiring)
 *   Arduino D10  → Relay 9
 *   Arduino D11  → Relay 10
 *   Arduino D12  → Relay 11
 *   Arduino D13  → Relay 12
 *   Arduino A0   → Relay 13
 *   Arduino A1   → Relay 14
 *   Arduino A2   → Relay 15
 *   Arduino A3   → Relay 16
 *   Arduino 5V   → Relay VCC
 *   Arduino GND  → Relay GND
 *
 * Protocol (9600 baud, newline-terminated):
 *   "1"–"16"  → activate that relay (others off, except relay 8 if T-controlled)
 *   "0" or "x" → all off (including relay 8 T-state)
 *   "?"        → report current state
 *   "T1"       → energize relay 8 independently (NC opens → TX isolated)
 *   "T0"       → de-energize relay 8 independently (NC closes → TX connected)
 *   "T?"       → query TX relay state
 *
 * Response: "OK:n" where n = active relay (0 = none)
 *           "OK:T1" or "OK:T0" for T commands
 */

const int RELAY_PINS[] = {2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, A0, A1, A2, A3};
const int NUM_RELAYS = 16;
const int TX_RELAY_IDX = 7;  // Relay 8 = index 7 in RELAY_PINS[]

// Active-LOW relay module: LOW = relay ON, HIGH = relay OFF
const int RELAY_ON  = LOW;
const int RELAY_OFF = HIGH;

const int BBM_DELAY_MS = 5;

int activeRelay = 0;
int txState = 0;  // 0 = de-energized (NC closed, TX connected), 1 = energized (NC open, TX isolated)

// ─── Serial command buffer (for multi-char commands like "16") ───
char cmdBuf[16];
int cmdLen = 0;

void allOff() {
  for (int i = 0; i < NUM_RELAYS; i++) {
    digitalWrite(RELAY_PINS[i], RELAY_OFF);
  }
  activeRelay = 0;
  txState = 0;
}

void muxOff() {
  // Turn off RX mux relays (1–7, 9–16) without touching relay 8
  for (int i = 0; i < NUM_RELAYS; i++) {
    if (i == TX_RELAY_IDX) continue;  // Skip relay 8
    digitalWrite(RELAY_PINS[i], RELAY_OFF);
  }
  activeRelay = 0;
}

void activateRelay(int relay) {
  if (relay < 1 || relay > NUM_RELAYS) return;

  if (relay == 8) {
    // select(8) works as legacy: full allOff then activate 8
    allOff();
    delay(BBM_DELAY_MS);
    digitalWrite(RELAY_PINS[TX_RELAY_IDX], RELAY_ON);
    activeRelay = 8;
    txState = 1;
  } else {
    // For all other relays: only turn off mux relays, preserve TX relay state
    muxOff();
    delay(BBM_DELAY_MS);
    digitalWrite(RELAY_PINS[relay - 1], RELAY_ON);
    activeRelay = relay;
    // Restore TX relay state
    digitalWrite(RELAY_PINS[TX_RELAY_IDX], txState ? RELAY_ON : RELAY_OFF);
  }
}

void processCommand() {
  cmdBuf[cmdLen] = '\0';
  if (cmdLen == 0) return;

  // "?" → query
  if (cmdLen == 1 && cmdBuf[0] == '?') {
    Serial.print("OK:");
    Serial.println(activeRelay);
    return;
  }

  // "0" or "x" → all off (including TX relay)
  if (cmdLen == 1 && (cmdBuf[0] == '0' || cmdBuf[0] == 'x' || cmdBuf[0] == 'X')) {
    allOff();
    Serial.print("OK:");
    Serial.println(activeRelay);
    return;
  }

  // "T1" → energize relay 8 (NC opens → TX isolated)
  if (cmdLen == 2 && (cmdBuf[0] == 'T' || cmdBuf[0] == 't') && cmdBuf[1] == '1') {
    txState = 1;
    digitalWrite(RELAY_PINS[TX_RELAY_IDX], RELAY_ON);
    Serial.println("OK:T1");
    return;
  }

  // "T0" → de-energize relay 8 (NC closes → TX connected)
  if (cmdLen == 2 && (cmdBuf[0] == 'T' || cmdBuf[0] == 't') && cmdBuf[1] == '0') {
    txState = 0;
    digitalWrite(RELAY_PINS[TX_RELAY_IDX], RELAY_OFF);
    Serial.println("OK:T0");
    return;
  }

  // "T?" → query TX relay state
  if (cmdLen == 2 && (cmdBuf[0] == 'T' || cmdBuf[0] == 't') && cmdBuf[1] == '?') {
    Serial.print("OK:T");
    Serial.println(txState);
    return;
  }

  // Try to parse as number 1–16
  int relay = atoi(cmdBuf);
  if (relay >= 1 && relay <= NUM_RELAYS) {
    activateRelay(relay);
    Serial.print("OK:");
    Serial.println(activeRelay);
    return;
  }

  Serial.print("ERR:unknown '");
  Serial.print(cmdBuf);
  Serial.println("'");
}

void setup() {
  Serial.begin(9600);

  for (int i = 0; i < NUM_RELAYS; i++) {
    pinMode(RELAY_PINS[i], OUTPUT);
    digitalWrite(RELAY_PINS[i], RELAY_OFF);
  }

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
    else if (cmdLen < 15) {
      cmdBuf[cmdLen++] = c;
    }
  }
}

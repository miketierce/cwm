/*
 * CWM 16-Channel Relay Multiplexer Controller
 *
 * Controls a 16-channel opto-isolated relay module for switching
 * plate/rod sense PZTs onto PicoScope Channel A.
 * One relay active at a time (break-before-make).
 *
 * Hardware:
 *   - Arduino Nano #1 (ATmega328P, CH340 USB)
 *   - 16-channel 5V relay module (active-LOW opto-isolated)
 *   - Port: /dev/cu.usbserial-11310
 *
 * Pin mapping (16 relays):
 *   Arduino D2   → Relay 1
 *   Arduino D3   → Relay 2
 *   Arduino D4   → Relay 3
 *   Arduino D5   → Relay 4
 *   Arduino D6   → Relay 5
 *   Arduino D7   → Relay 6
 *   Arduino D8   → Relay 7
 *   Arduino D9   → Relay 8
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
 *   "1"–"16"  → activate that relay (others off)
 *   "0" or "x" → all off
 *   "?"        → report current state
 *
 * Response: "OK:n" where n = active relay (0 = none)
 */

const int RELAY_PINS[] = {2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, A0, A1, A2, A3};
const int NUM_RELAYS = 16;

// Active-LOW relay module: LOW = relay ON, HIGH = relay OFF
const int RELAY_ON  = LOW;
const int RELAY_OFF = HIGH;

const int BBM_DELAY_MS = 5;

int activeRelay = 0;

// ─── Serial command buffer (for multi-char commands like "16") ───
char cmdBuf[16];
int cmdLen = 0;

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

void processCommand() {
  cmdBuf[cmdLen] = '\0';
  if (cmdLen == 0) return;

  // "?" → query
  if (cmdLen == 1 && cmdBuf[0] == '?') {
    Serial.print("OK:");
    Serial.println(activeRelay);
    return;
  }

  // "0" or "x" → all off
  if (cmdLen == 1 && (cmdBuf[0] == '0' || cmdBuf[0] == 'x' || cmdBuf[0] == 'X')) {
    allOff();
    Serial.print("OK:");
    Serial.println(activeRelay);
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

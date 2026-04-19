/*
 * CWM Relay Multiplexer Controller
 *
 * Controls an 8-channel opto-isolated relay module to switch individual
 * plate sense PZTs onto PicoScope Channel A. One relay active at a time
 * (break-before-make) to prevent signal blending.
 *
 * Hardware:
 *   - Arduino Nano (ATmega328P, CH340 USB)
 *   - 8-channel 5V relay module (active-LOW opto-isolated)
 *   - DuPont F-to-F jumper wires: D2–D9 → IN1–IN8
 *   - 5V/GND from Arduino → relay VCC/GND
 *
 * Wiring (Phase 1.6 dual-RX plate layout):
 *   Arduino D2  → Relay IN1  Plate 1 (A)  NE-RX (95,5) diagonal
 *   Arduino D3  → Relay IN2  Plate 2 (B)  NE-RX (95,5) diagonal
 *   Arduino D4  → Relay IN3  Plate 3 (G)  NE-RX (95,5) diagonal
 *   Arduino D5  → Relay IN4  Plate 3 (G)  NW-RX (5,5)  L-path
 *   Arduino D6  → Relay IN5  Plate 4 (D)  NE-RX (95,5) diagonal
 *   Arduino D7  → Relay IN6  Plate 4 (D)  NW-RX (5,5)  L-path
 *   Arduino D8  → Relay IN7  Plate 5 (F)  NE-RX (95,5) diagonal
 *   Arduino D9  → Relay IN8  Plate 5 (F)  NW-RX (5,5)  L-path
 *   Arduino 5V  → Relay VCC
 *   Arduino GND → Relay GND
 *   All TX PZTs wired in parallel → PicoScope AWG
 *
 * Protocol (9600 baud, newline-terminated):
 *   Send '1'–'8' → activate that relay (deactivate all others first)
 *   Send '0' or 'x' → deactivate all relays (open circuit)
 *   Send '?' → report current state
 *
 * Response format:
 *   "OK:n" where n = active relay (0 = none)
 *   "ERR:message" on invalid input
 *
 * Timing:
 *   Break-before-make: all relays off for 5 ms before new relay on.
 *   Total switching time: ~10 ms (safe for the identifier's 200 ms settle).
 */

// Relay pins: D2..D9 map to relays 1..8
const int RELAY_PINS[] = {2, 3, 4, 5, 6, 7, 8, 9};
const int NUM_RELAYS = 8;
const int LED_PIN = 13;  // onboard LED for activity indication

// Active-LOW relay module: LOW = relay ON, HIGH = relay OFF
const int RELAY_ON  = LOW;
const int RELAY_OFF = HIGH;

// Break-before-make delay (ms)
const int BBM_DELAY_MS = 5;

// Current active relay (0 = none, 1–8 = relay number)
int activeRelay = 0;

void allOff() {
  for (int i = 0; i < NUM_RELAYS; i++) {
    digitalWrite(RELAY_PINS[i], RELAY_OFF);
  }
  activeRelay = 0;
}

void activateRelay(int relay) {
  // relay: 1–8
  if (relay < 1 || relay > NUM_RELAYS) return;

  // Break-before-make: turn everything off first
  allOff();
  delay(BBM_DELAY_MS);

  // Activate the requested relay
  digitalWrite(RELAY_PINS[relay - 1], RELAY_ON);
  activeRelay = relay;

  // Blink LED
  digitalWrite(LED_PIN, HIGH);
  delay(20);
  digitalWrite(LED_PIN, LOW);
}

void activateSubset(const int* relays, int count, int reportCode) {
  // Close a specific subset of relays simultaneously
  allOff();
  delay(BBM_DELAY_MS);
  for (int i = 0; i < count; i++) {
    int r = relays[i];
    if (r >= 1 && r <= NUM_RELAYS) {
      digitalWrite(RELAY_PINS[r - 1], RELAY_ON);
    }
  }
  activeRelay = reportCode;
  digitalWrite(LED_PIN, HIGH);
  delay(20);
  digitalWrite(LED_PIN, LOW);
}

void setup() {
  Serial.begin(9600);

  // Configure all relay pins as outputs, initially OFF
  for (int i = 0; i < NUM_RELAYS; i++) {
    pinMode(RELAY_PINS[i], OUTPUT);
    digitalWrite(RELAY_PINS[i], RELAY_OFF);
  }

  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  // Startup blink: 3 quick flashes
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_PIN, HIGH);
    delay(100);
    digitalWrite(LED_PIN, LOW);
    delay(100);
  }

  Serial.println("OK:0");  // Ready, no relay active
}

void loop() {
  if (Serial.available() > 0) {
    char cmd = Serial.read();

    // Drain any trailing newline/carriage return
    delay(5);
    while (Serial.available() > 0) {
      Serial.read();
    }

    if (cmd >= '1' && cmd <= '8') {
      int relay = cmd - '0';
      activateRelay(relay);
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
      // All 5 NE receivers: relays 1,2,3,5,7
      const int neRelays[] = {1, 2, 3, 5, 7};
      activateSubset(neRelays, 5, 9);  // report as 9 = all-NE
      Serial.println("OK:9");
    }
    else if (cmd == 'B' || cmd == 'b') {
      // All 8 relays (NE + NW)
      const int allRelays[] = {1, 2, 3, 4, 5, 6, 7, 8};
      activateSubset(allRelays, 8, 10);  // report as 10 = all
      Serial.println("OK:10");
    }
    else if (cmd == '\n' || cmd == '\r') {
      // Ignore bare newlines
    }
    else {
      Serial.print("ERR:unknown command '");
      Serial.print(cmd);
      Serial.println("'");
    }
  }
}

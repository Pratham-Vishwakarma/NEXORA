#include <Arduino.h>

// ============================================================
// CC2530 UNIVERSAL UART / ZNP / AT PROBE
//
// ESP32 RX2 = GPIO16
// ESP32 TX2 = GPIO17
//
// Move these two wires between CC2530 UART mappings:
//
// A) UART0 ALT1
//    ESP32 TX -> P0.2
//    ESP32 RX <- P0.3
//
// B) UART0 ALT2
//    ESP32 TX -> P1.4
//    ESP32 RX <- P1.5
//
// C) UART1 ALT1
//    ESP32 TX -> P0.5
//    ESP32 RX <- P0.4
//
// D) UART1 ALT2
//    ESP32 TX -> P1.7
//    ESP32 RX <- P1.6
//
// Serial Monitor: 115200
// ============================================================

HardwareSerial CC2530Serial(2);

#define ESP_RX 16
#define ESP_TX 17

// ============================================================
// BAUD RATES
// ============================================================

const uint32_t baudRates[] = {
  115200,
  57600,
  38400,
  19200,
  9600,
  4800,
  2400
};

const size_t BAUD_COUNT =
    sizeof(baudRates) / sizeof(baudRates[0]);

// ============================================================
// ZNP COMMANDS
// ============================================================

// SYS_PING
const uint8_t ZNP_SYS_PING[] = {
  0xFE,
  0x00,
  0x21,
  0x01,
  0x20
};

// SYS_VERSION
const uint8_t ZNP_SYS_VERSION[] = {
  0xFE,
  0x00,
  0x21,
  0x02,
  0x23
};

// ============================================================
// HEX PRINT
// ============================================================

void printHex(uint8_t value) {

  if (value < 0x10) {
    Serial.print("0");
  }

  Serial.print(value, HEX);
}

// ============================================================
// CLEAR UART BUFFER
// ============================================================

void clearInput() {

  while (CC2530Serial.available()) {
    CC2530Serial.read();
  }
}

// ============================================================
// PRINT RECEIVED DATA
//
// Prints BOTH HEX and ASCII.
// ============================================================

size_t readResponse(
    uint32_t timeoutMs,
    uint8_t *buffer,
    size_t maxLength) {

  size_t count = 0;

  unsigned long start =
      millis();

  unsigned long lastByte =
      start;

  while ((millis() - start) < timeoutMs) {

    while (
        CC2530Serial.available() &&
        count < maxLength
    ) {

      buffer[count++] =
          CC2530Serial.read();

      lastByte =
          millis();
    }

    // Once something has arrived,
    // stop after 100 ms of silence.

    if (
        count > 0 &&
        (millis() - lastByte) > 100
    ) {

      break;
    }

    delay(1);
  }

  return count;
}

// ============================================================
// DISPLAY RESPONSE
// ============================================================

void displayResponse(
    const uint8_t *data,
    size_t length) {

  if (length == 0) {

    Serial.println(
        "RX: <nothing>"
    );

    return;
  }

  Serial.print(
      "RX HEX: "
  );

  for (size_t i = 0;
       i < length;
       i++) {

    printHex(
        data[i]
    );

    Serial.print(" ");
  }

  Serial.println();

  Serial.print(
      "RX ASCII: "
  );

  for (size_t i = 0;
       i < length;
       i++) {

    uint8_t c =
        data[i];

    if (
        c >= 32 &&
        c <= 126
    ) {

      Serial.write(c);

    }
    else if (c == '\r') {

      Serial.print("<CR>");

    }
    else if (c == '\n') {

      Serial.print("<LF>");

    }
    else {

      Serial.print(".");
    }
  }

  Serial.println();
}

// ============================================================
// CHECK FOR ZNP FRAME
// ============================================================

bool looksLikeZNP(
    const uint8_t *data,
    size_t length) {

  for (size_t i = 0;
       i < length;
       i++) {

    if (data[i] == 0xFE) {
      return true;
    }
  }

  return false;
}

// ============================================================
// SEND BINARY COMMAND
// ============================================================

void sendBinary(
    const uint8_t *data,
    size_t length) {

  Serial.print(
      "TX HEX: "
  );

  for (size_t i = 0;
       i < length;
       i++) {

    printHex(
        data[i]
    );

    Serial.print(" ");

    CC2530Serial.write(
        data[i]
    );
  }

  CC2530Serial.flush();

  Serial.println();
}

// ============================================================
// TEST ZNP COMMAND
// ============================================================

bool testZNP(
    const char *name,
    const uint8_t *command,
    size_t commandLength) {

  Serial.println();

  Serial.print(
      "Testing "
  );

  Serial.println(name);

  clearInput();

  sendBinary(
      command,
      commandLength
  );

  uint8_t response[256];

  size_t length =
      readResponse(
          1200,
          response,
          sizeof(response)
      );

  displayResponse(
      response,
      length
  );

  if (
      looksLikeZNP(
          response,
          length
      )
  ) {

    Serial.println(
        "*** ZNP-LIKE FRAME DETECTED ***"
    );

    return true;
  }

  return false;
}

// ============================================================
// TEST ASCII COMMAND
// ============================================================

bool testASCII(
    const char *command) {

  Serial.println();

  Serial.print(
      "Testing ASCII: "
  );

  Serial.println(command);

  clearInput();

  CC2530Serial.print(
      command
  );

  CC2530Serial.print(
      "\r\n"
  );

  CC2530Serial.flush();

  uint8_t response[256];

  size_t length =
      readResponse(
          1200,
          response,
          sizeof(response)
      );

  displayResponse(
      response,
      length
  );

  return length > 0;
}

// ============================================================
// LISTEN WITHOUT TRANSMITTING
// ============================================================

bool passiveListen() {

  Serial.println();

  Serial.println(
      "Listening for spontaneous UART data..."
  );

  clearInput();

  uint8_t response[256];

  size_t length =
      readResponse(
          1500,
          response,
          sizeof(response)
      );

  displayResponse(
      response,
      length
  );

  return length > 0;
}

// ============================================================
// TEST ONE BAUD RATE
// ============================================================

bool testBaud(
    uint32_t baud) {

  Serial.println();

  Serial.println(
      "======================================"
  );

  Serial.print(
      "BAUD: "
  );

  Serial.println(
      baud
  );

  Serial.println(
      "======================================"
  );

  CC2530Serial.end();

  delay(100);

  CC2530Serial.begin(
      baud,
      SERIAL_8N1,
      ESP_RX,
      ESP_TX
  );

  delay(300);

  bool activity = false;

  // ----------------------------------------------------------
  // 1. Passive listen
  // ----------------------------------------------------------

  if (passiveListen()) {

    activity = true;
  }

  // ----------------------------------------------------------
  // 2. ZNP SYS_PING
  // ----------------------------------------------------------

  if (
      testZNP(
          "ZNP SYS_PING",
          ZNP_SYS_PING,
          sizeof(ZNP_SYS_PING)
      )
  ) {

    activity = true;
  }

  // ----------------------------------------------------------
  // 3. ZNP SYS_VERSION
  // ----------------------------------------------------------

  if (
      testZNP(
          "ZNP SYS_VERSION",
          ZNP_SYS_VERSION,
          sizeof(ZNP_SYS_VERSION)
      )
  ) {

    activity = true;
  }

  // ----------------------------------------------------------
  // 4. Common AT commands
  // ----------------------------------------------------------

  if (testASCII("AT")) {
    activity = true;
  }

  if (testASCII("AT+HELP")) {
    activity = true;
  }

  if (testASCII("AT+VERSION")) {
    activity = true;
  }

  if (testASCII("AT+VER")) {
    activity = true;
  }

  return activity;
}

// ============================================================
// SETUP
// ============================================================

void setup() {

  Serial.begin(115200);

  delay(2000);

  Serial.println();

  Serial.println(
      "======================================"
  );

  Serial.println(
      "CC2530 MULTI-UART PROBE"
  );

  Serial.println(
      "======================================"
  );

  Serial.println();

  Serial.println(
      "ESP32 GPIO17 = TX"
  );

  Serial.println(
      "ESP32 GPIO16 = RX"
  );

  Serial.println();

  Serial.println(
      "Try this sketch with each wiring pair:"
  );

  Serial.println(
      "A: TX->P0.2   RX<-P0.3  [UART0 ALT1]"
  );

  Serial.println(
      "B: TX->P1.4   RX<-P1.5  [UART0 ALT2]"
  );

  Serial.println(
      "C: TX->P0.5   RX<-P0.4  [UART1 ALT1]"
  );

  Serial.println(
      "D: TX->P1.7   RX<-P1.6  [UART1 ALT2]"
  );

  Serial.println();

  Serial.println(
      "IMPORTANT: P0.4 must NOT be grounded"
  );

  Serial.println(
      "during this test."
  );

  bool anythingFound =
      false;

  // ==========================================================
  // TEST ALL BAUD RATES
  // ==========================================================

  for (
      size_t i = 0;
      i < BAUD_COUNT;
      i++
  ) {

    bool result =
        testBaud(
            baudRates[i]
        );

    if (result) {

      anythingFound =
          true;

      Serial.println();

      Serial.println(
          "**************************************"
      );

      Serial.print(
          "UART ACTIVITY FOUND AT "
      );

      Serial.print(
          baudRates[i]
      );

      Serial.println(
          " BAUD"
      );

      Serial.println(
          "**************************************"
      );
    }
  }

  Serial.println();

  Serial.println(
      "======================================"
  );

  Serial.println(
      "SCAN FINISHED"
  );

  Serial.println(
      "======================================"
  );

  if (!anythingFound) {

    Serial.println();

    Serial.println(
        "NO UART RESPONSE ON THIS PIN PAIR."
    );

  }
  else {

    Serial.println();

    Serial.println(
        "UART ACTIVITY WAS DETECTED."
    );

    Serial.println(
        "Check the output above."
    );
  }

  Serial.println();

  Serial.println(
      "Move the two UART wires to the next"
  );

  Serial.println(
      "CC2530 pin pair and press ESP32 RESET."
  );
}

// ============================================================
// LOOP
// ============================================================

void loop() {

}
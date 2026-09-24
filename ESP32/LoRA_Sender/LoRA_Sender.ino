#include <SPI.h>
#include <LoRa.h>

// ============================================================
// LORA PIN CONFIGURATION - ARDUINO UNO
// ============================================================

#define LORA_SS    10
#define LORA_RST   9
#define LORA_DIO0  2

// Hardware SPI on Arduino UNO:
//
// SCK  -> D13
// MISO -> D12
// MOSI -> D11

// ============================================================
// RADIO CONFIGURATION
// ============================================================

#define LORA_FREQUENCY 433E6

#define LORA_SF        7
#define LORA_BW        125E3
#define LORA_CR        5
#define LORA_TX_POWER  17

// ============================================================
// TEST CONFIGURATION
// ============================================================

#define MAX_PAYLOAD_SIZE 128

uint16_t payloadSize = 16;
uint32_t packetIntervalMs = 500;

uint32_t packetId = 0;
uint32_t lastPacketTime = 0;

const uint32_t ACK_TIMEOUT_MS = 1500;

// ============================================================
// PACKET STRUCTURES
// ============================================================

struct __attribute__((packed)) DataHeader {

  uint32_t packet_id;

  uint32_t timestamp_ms;

  uint16_t payload_size;
};


struct __attribute__((packed)) AckPacket {

  uint32_t packet_id;

  uint8_t success;
};

// ============================================================
// PAYLOAD BUFFER
// ============================================================

uint8_t payload[MAX_PAYLOAD_SIZE];

// ============================================================
// GENERATE PAYLOAD
// ============================================================

void generatePayload(uint16_t size) {

  for (uint16_t i = 0; i < size; i++) {

    payload[i] = 'A' + (i % 26);
  }
}

// ============================================================
// SEND PACKET
// ============================================================

void sendPacket() {

  packetId++;

  generatePayload(payloadSize);

  DataHeader header;

  header.packet_id = packetId;
  header.timestamp_ms = millis();
  header.payload_size = payloadSize;

  // ----------------------------------------------------------
  // Start RTT timer
  // ----------------------------------------------------------

  uint32_t startUs = micros();

  // ----------------------------------------------------------
  // Transmit packet
  // ----------------------------------------------------------

  LoRa.beginPacket();

  LoRa.write(
    (uint8_t *)&header,
    sizeof(header)
  );

  LoRa.write(
    payload,
    payloadSize
  );

  int txStatus = LoRa.endPacket();

  // ----------------------------------------------------------
  // Wait for ACK
  // ----------------------------------------------------------

  bool ackReceived = false;

  int ackRssi = 0;
  float ackSnr = 0.0;

  float rttMs = -1.0;

  uint32_t waitStart = millis();

  while (
    millis() - waitStart <
    ACK_TIMEOUT_MS
  ) {

    int packetSize =
      LoRa.parsePacket();

    if (
      packetSize ==
      sizeof(AckPacket)
    ) {

      AckPacket ack;

      uint8_t *ptr =
        (uint8_t *)&ack;

      for (
        uint8_t i = 0;
        i < sizeof(AckPacket);
        i++
      ) {

        if (LoRa.available()) {

          ptr[i] =
            LoRa.read();
        }
      }

      if (
        ack.packet_id ==
        packetId &&
        ack.success == 1
      ) {

        uint32_t endUs =
          micros();

        rttMs =
          (endUs - startUs)
          / 1000.0;

        ackRssi =
          LoRa.packetRssi();

        ackSnr =
          LoRa.packetSnr();

        ackReceived = true;

        break;
      }
    }
  }

  // ----------------------------------------------------------
  // SERIAL OUTPUT
  //
  // PKT,
  // packet_id,
  // payload_size,
  // rssi,
  // snr,
  // rtt_ms,
  // success,
  // timestamp
  // ----------------------------------------------------------

  Serial.print(F("PKT,"));

  Serial.print(packetId);
  Serial.print(',');

  Serial.print(payloadSize);
  Serial.print(',');

  if (ackReceived) {

    Serial.print(ackRssi);
    Serial.print(',');

    Serial.print(ackSnr, 2);
    Serial.print(',');

    Serial.print(rttMs, 2);
    Serial.print(',');

    Serial.print(1);
  }

  else {

    Serial.print(F("0,"));
    Serial.print(F("0.00,"));
    Serial.print(F("-1.00,"));
    Serial.print(0);
  }

  Serial.print(',');

  Serial.println(millis());
}

// ============================================================
// SERIAL COMMAND HANDLER
// ============================================================

void handleSerialCommand() {

  if (!Serial.available()) {

    return;
  }

  char buffer[40];

  uint8_t index = 0;

  while (
    Serial.available() &&
    index < sizeof(buffer) - 1
  ) {

    char c = Serial.read();

    if (c == '\n') {

      break;
    }

    if (c != '\r') {

      buffer[index++] = c;
    }
  }

  buffer[index] = '\0';

  // ----------------------------------------------------------
  // SIZE,<bytes>
  // ----------------------------------------------------------

  if (
    strncmp(
      buffer,
      "SIZE,",
      5
    ) == 0
  ) {

    int newSize =
      atoi(buffer + 5);

    if (
      newSize > 0 &&
      newSize <=
      MAX_PAYLOAD_SIZE
    ) {

      payloadSize =
        newSize;

      Serial.print(
        F("CONFIG_OK,")
      );

      Serial.print(
        payloadSize
      );

      Serial.print(',');

      Serial.println(
        packetIntervalMs
      );
    }

    return;
  }

  // ----------------------------------------------------------
  // INTERVAL,<milliseconds>
  // ----------------------------------------------------------

  if (
    strncmp(
      buffer,
      "INTERVAL,",
      9
    ) == 0
  ) {

    unsigned long newInterval =
      atol(buffer + 9);

    if (
      newInterval >= 100
    ) {

      packetIntervalMs =
        newInterval;

      Serial.print(
        F("CONFIG_OK,")
      );

      Serial.print(
        payloadSize
      );

      Serial.print(',');

      Serial.println(
        packetIntervalMs
      );
    }
  }
}

// ============================================================
// SETUP
// ============================================================

void setup() {

  Serial.begin(115200);

  delay(1000);

  Serial.println(
    F("LORA_SENDER_START")
  );

  // ----------------------------------------------------------
  // LoRa pin configuration
  // ----------------------------------------------------------

  LoRa.setPins(
    LORA_SS,
    LORA_RST,
    LORA_DIO0
  );

  // ----------------------------------------------------------
  // Initialize LoRa
  // ----------------------------------------------------------

  if (
    !LoRa.begin(
      LORA_FREQUENCY
    )
  ) {

    Serial.println(
      F("LORA_INIT_FAIL")
    );

    while (true) {

      delay(1000);
    }
  }

  // ----------------------------------------------------------
  // Radio configuration
  // ----------------------------------------------------------

  LoRa.setSpreadingFactor(
    LORA_SF
  );

  LoRa.setSignalBandwidth(
    LORA_BW
  );

  LoRa.setCodingRate4(
    LORA_CR
  );

  LoRa.setTxPower(
    LORA_TX_POWER
  );

  LoRa.enableCrc();

  Serial.println(
    F("LORA_INIT_OK")
  );

  Serial.print(
    F("CONFIG_OK,")
  );

  Serial.print(
    payloadSize
  );

  Serial.print(',');

  Serial.println(
    packetIntervalMs
  );
}

// ============================================================
// LOOP
// ============================================================

void loop() {

  handleSerialCommand();

  if (
    millis() -
    lastPacketTime >=
    packetIntervalMs
  ) {

    lastPacketTime =
      millis();

    sendPacket();
  }
}
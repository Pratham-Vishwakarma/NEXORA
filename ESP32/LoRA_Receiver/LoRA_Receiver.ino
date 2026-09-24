#include <SPI.h>
#include <LoRa.h>

// ============================================================
// LORA PIN CONFIGURATION
// ============================================================

#define LORA_SS    10
#define LORA_RST   9
#define LORA_DIO0  2

// ============================================================
// RADIO CONFIGURATION
// ============================================================

#define LORA_FREQUENCY 433E6

#define LORA_SF        7
#define LORA_BW        125E3
#define LORA_CR        5
#define LORA_TX_POWER  17

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
// GLOBALS
// ============================================================

uint32_t lastPacketId = 0;

uint32_t totalPacketsReceived = 0;

uint32_t totalPacketsLost = 0;

// ============================================================
// SEND ACK
// ============================================================

void sendAck(uint32_t packetId) {

  AckPacket ack;

  ack.packet_id = packetId;
  ack.success = 1;

  // Small delay for RX -> TX transition
  delay(10);

  LoRa.beginPacket();

  LoRa.write(
    (uint8_t *)&ack,
    sizeof(ack)
  );

  LoRa.endPacket();
}

// ============================================================
// PROCESS PACKET
// ============================================================

void processPacket(int packetSize) {

  // ----------------------------------------------------------
  // Validate minimum packet size
  // ----------------------------------------------------------

  if (packetSize < sizeof(DataHeader)) {

    while (LoRa.available()) {
      LoRa.read();
    }

    Serial.println("INVALID_PACKET");

    return;
  }

  // ----------------------------------------------------------
  // Capture signal information
  // ----------------------------------------------------------

  int rssi = LoRa.packetRssi();

  float snr = LoRa.packetSnr();

  // ----------------------------------------------------------
  // Read packet header
  // ----------------------------------------------------------

  DataHeader header;

  uint8_t *ptr =
    (uint8_t *)&header;

  for (
    uint8_t i = 0;
    i < sizeof(DataHeader);
    i++
  ) {

    if (!LoRa.available()) {

      Serial.println("INVALID_HEADER");

      return;
    }

    ptr[i] = LoRa.read();
  }

  // ----------------------------------------------------------
  // Read / discard payload
  // ----------------------------------------------------------

  uint16_t payloadBytes = 0;

  while (LoRa.available()) {

    LoRa.read();

    payloadBytes++;
  }

  // ----------------------------------------------------------
  // Validate payload
  // ----------------------------------------------------------

  if (
    payloadBytes !=
    header.payload_size
  ) {

    Serial.print("PAYLOAD_MISMATCH,");

    Serial.print(header.payload_size);

    Serial.print(",");

    Serial.println(payloadBytes);

    return;
  }

  // ----------------------------------------------------------
  // Calculate packet loss
  // ----------------------------------------------------------

  uint32_t lostSinceLast = 0;

  if (
    lastPacketId != 0 &&
    header.packet_id >
    lastPacketId + 1
  ) {

    lostSinceLast =
      header.packet_id -
      lastPacketId -
      1;

    totalPacketsLost +=
      lostSinceLast;
  }

  lastPacketId =
    header.packet_id;

  totalPacketsReceived++;

  // ----------------------------------------------------------
  // Send ACK back to sender
  // ----------------------------------------------------------

  sendAck(
    header.packet_id
  );

  // ----------------------------------------------------------
  // SERIAL OUTPUT
  //
  // RX,
  // packet_id,
  // payload_size,
  // RSSI,
  // SNR,
  // lost_since_last,
  // total_received,
  // total_lost,
  // timestamp
  // ----------------------------------------------------------

  Serial.print("RX,");

  Serial.print(
    header.packet_id
  );

  Serial.print(",");

  Serial.print(
    header.payload_size
  );

  Serial.print(",");

  Serial.print(
    rssi
  );

  Serial.print(",");

  Serial.print(
    snr,
    2
  );

  Serial.print(",");

  Serial.print(
    lostSinceLast
  );

  Serial.print(",");

  Serial.print(
    totalPacketsReceived
  );

  Serial.print(",");

  Serial.print(
    totalPacketsLost
  );

  Serial.print(",");

  Serial.println(
    millis()
  );
}

// ============================================================
// SETUP
// ============================================================

void setup() {

  Serial.begin(115200);

  delay(1000);

  Serial.println(
    "LORA_RECEIVER_START"
  );

  LoRa.setPins(
    LORA_SS,
    LORA_RST,
    LORA_DIO0
  );

  if (
    !LoRa.begin(
      LORA_FREQUENCY
    )
  ) {

    Serial.println(
      "LORA_INIT_FAIL"
    );

    while (true) {

      delay(1000);
    }
  }

  // MUST MATCH SENDER

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

  LoRa.setSyncWord(
    0x12
  );

  LoRa.enableCrc();

  Serial.println(
    "LORA_INIT_OK"
  );
}

// ============================================================
// LOOP
// ============================================================

void loop() {

  int packetSize =
    LoRa.parsePacket();

  if (
    packetSize > 0
  ) {

    processPacket(
      packetSize
    );
  }
}
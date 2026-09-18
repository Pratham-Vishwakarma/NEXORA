#include <BluetoothSerial.h>

// ============================================================
// Classic Bluetooth configuration
// ============================================================

const char* RECEIVER_BT_NAME = "ESP32_BT_RECEIVER";


// ============================================================
// Payload configuration
// ============================================================

const size_t MAX_PAYLOAD_SIZE = 2048;


// ============================================================
// Global objects
// ============================================================

BluetoothSerial SerialBT;

uint8_t payload[MAX_PAYLOAD_SIZE];


// ============================================================
// Packet structures
//
// MUST MATCH bluetooth_sender.ino EXACTLY
// ============================================================

struct __attribute__((packed)) TestHeader {

  uint32_t packet_id;

  uint32_t timestamp_ms;

  uint16_t payload_size;
};


struct __attribute__((packed)) AckPacket {

  uint32_t packet_id;

  uint32_t receiver_timestamp_ms;

  uint8_t success;
};


// ============================================================
// Read exact number of Bluetooth bytes
// ============================================================

bool readExactBytes(
    uint8_t* buffer,
    size_t length,
    uint32_t timeoutMs
) {

  size_t received = 0;

  uint32_t startTime =
    millis();


  while (
    received < length &&
    millis() - startTime < timeoutMs
  ) {

    while (
      SerialBT.available() &&
      received < length
    ) {

      int value =
        SerialBT.read();


      if (
        value >= 0
      ) {

        buffer[received] =
          static_cast<uint8_t>(
            value
          );

        received++;
      }
    }


    if (
      received < length
    ) {

      delay(
        1
      );
    }
  }


  return (
    received == length
  );
}


// ============================================================
// Send ACK
// ============================================================

bool sendAck(
    uint32_t packetId,
    bool success
) {

  AckPacket ack;


  ack.packet_id =
    packetId;


  ack.receiver_timestamp_ms =
    millis();


  ack.success =
    success ? 1 : 0;


  size_t written =
    SerialBT.write(
      reinterpret_cast<
        const uint8_t*
      >(
        &ack
      ),
      sizeof(
        AckPacket
      )
    );


  SerialBT.flush();


  return (
    written
      == sizeof(
        AckPacket
      )
  );
}


// ============================================================
// Print receiver-side telemetry
//
// Format:
//
// RX,
// packet_id,
// payload_bytes,
// sender_timestamp,
// receiver_timestamp,
// success
//
// Example:
//
// RX,42,128,49381,49402,1
//
// This is only for debugging / validation.
// ============================================================

void printReceiverTelemetry(
    uint32_t packetId,
    uint16_t payloadBytes,
    uint32_t senderTimestamp,
    uint32_t receiverTimestamp,
    bool successful
) {

  Serial.print(
    "RX,"
  );


  Serial.print(
    packetId
  );

  Serial.print(",");


  Serial.print(
    payloadBytes
  );

  Serial.print(",");


  Serial.print(
    senderTimestamp
  );

  Serial.print(",");


  Serial.print(
    receiverTimestamp
  );

  Serial.print(",");


  Serial.println(
    successful ? 1 : 0
  );
}


// ============================================================
// Validate payload
//
// Sender generates:
//
// payload[i] = i & 0xFF
//
// So we can check whether the Bluetooth stream arrived
// correctly.
// ============================================================

bool validatePayload(
    uint16_t size
) {

  for (
    uint16_t i = 0;
    i < size;
    i++
  ) {

    uint8_t expected =
      static_cast<uint8_t>(
        i & 0xFF
      );


    if (
      payload[i]
      != expected
    ) {

      return false;
    }
  }


  return true;
}


// ============================================================
// Setup
// ============================================================

void setup() {

  Serial.begin(
    115200
  );


  delay(
    1000
  );


  Serial.println();

  Serial.println(
    "======================================"
  );

  Serial.println(
    "Adaptive IoT Classic Bluetooth Receiver"
  );

  Serial.println(
    "======================================"
  );


  // ----------------------------------------------------------
  // Start Classic Bluetooth in SLAVE mode
  //
  // begin(name)
  //
  // No second argument = normal/slave mode.
  // Sender connects to this device.
  // ----------------------------------------------------------

  bool btStarted =
    SerialBT.begin(
      RECEIVER_BT_NAME
    );


  if (
    !btStarted
  ) {

    Serial.println(
      "ERROR: Bluetooth initialization failed"
    );


    while (
      true
    ) {

      delay(
        1000
      );
    }
  }


  Serial.print(
    "Bluetooth receiver name: "
  );

  Serial.println(
    RECEIVER_BT_NAME
  );


  Serial.print(
    "Maximum payload size: "
  );

  Serial.print(
    MAX_PAYLOAD_SIZE
  );

  Serial.println(
    " bytes"
  );


  Serial.println(
    "Receiver ready"
  );


  Serial.println(
    "Waiting for Bluetooth sender..."
  );
}


// ============================================================
// Main loop
// ============================================================

void loop() {

  // ----------------------------------------------------------
  // Wait until enough bytes for packet header are available
  // ----------------------------------------------------------

  if (
    SerialBT.available()
    < static_cast<int>(
      sizeof(
        TestHeader
      )
    )
  ) {

    delay(
      1
    );

    return;
  }


  // ----------------------------------------------------------
  // Read header
  // ----------------------------------------------------------

  TestHeader header;


  bool headerReceived =
    readExactBytes(
      reinterpret_cast<
        uint8_t*
      >(
        &header
      ),
      sizeof(
        TestHeader
      ),
      1000
    );


  if (
    !headerReceived
  ) {

    Serial.println(
      "RX_ERROR_HEADER_TIMEOUT"
    );

    return;
  }


  // ----------------------------------------------------------
  // Validate payload size
  // ----------------------------------------------------------

  if (
    header.payload_size == 0 ||
    header.payload_size > MAX_PAYLOAD_SIZE
  ) {

    Serial.print(
      "RX_ERROR_PAYLOAD_SIZE,"
    );

    Serial.println(
      header.payload_size
    );


    // Send negative ACK
    sendAck(
      header.packet_id,
      false
    );


    return;
  }


  // ----------------------------------------------------------
  // Read application payload
  // ----------------------------------------------------------

  bool payloadReceived =
    readExactBytes(
      payload,
      header.payload_size,
      1000
    );


  if (
    !payloadReceived
  ) {

    Serial.print(
      "RX_ERROR_PAYLOAD_TIMEOUT,"
    );

    Serial.println(
      header.packet_id
    );


    sendAck(
      header.packet_id,
      false
    );


    return;
  }


  // ----------------------------------------------------------
  // Validate payload contents
  // ----------------------------------------------------------

  bool payloadValid =
    validatePayload(
      header.payload_size
    );


  // ----------------------------------------------------------
  // Capture receiver timestamp
  // ----------------------------------------------------------

  uint32_t receiverTimestamp =
    millis();


  // ----------------------------------------------------------
  // Send ACK
  // ----------------------------------------------------------

  bool ackSent =
    sendAck(
      header.packet_id,
      payloadValid
    );


  // ----------------------------------------------------------
  // Receiver debug output
  // ----------------------------------------------------------

  printReceiverTelemetry(

    header.packet_id,

    header.payload_size,

    header.timestamp_ms,

    receiverTimestamp,

    payloadValid && ackSent
  );
}
#include <BluetoothSerial.h>

// ============================================================
// Classic Bluetooth configuration
// ============================================================
//
// IMPORTANT:
// Classic Bluetooth SPP works on the original ESP32,
// ESP32-WROOM, ESP32-WROVER, etc.
//
// It does NOT work on ESP32-C3 / ESP32-S2 because those
// chips do not support Bluetooth Classic.
//
// Receiver should advertise this Bluetooth name.
//
const char* RECEIVER_BT_NAME = "ESP32_BT_RECEIVER";

const char* SENDER_BT_NAME = "ESP32_BT_SENDER";


// ============================================================
// Network / ACK configuration
// ============================================================

const uint32_t ACK_TIMEOUT_MS = 1000;


// ============================================================
// Runtime experiment configuration
//
// Python sends:
//
// CONFIG,<payload_bytes>,<packet_interval_ms>
//
// Example:
//
// CONFIG,128,500
//
// ESP32 responds:
//
// CONFIG_OK,128,500,0
//
// Last field is kept for compatibility with the existing
// Wi-Fi CONFIG_OK output.
//
// Wi-Fi used this field for channel.
// Bluetooth sender reports 0 here.
// ============================================================

const size_t MAX_PAYLOAD_SIZE = 2048;

// Defaults until Python sends CONFIG
uint16_t payloadSize = 16;

uint32_t sendIntervalMs = 1000;


// ============================================================
// Global objects
// ============================================================

BluetoothSerial SerialBT;

uint32_t packetId = 0;

uint8_t payload[MAX_PAYLOAD_SIZE];


// ============================================================
// Packet structures
// ============================================================
//
// SAME logical structure as Wi-Fi sender.
//
// Packet transmitted over Bluetooth:
//
// [TestHeader]
// [application payload]
//
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
// Bluetooth connection state
// ============================================================

bool bluetoothConnected = false;


// ============================================================
// Prepare application payload
// ============================================================

void preparePayload(
    uint16_t size
) {

  if (
    size > MAX_PAYLOAD_SIZE
  ) {

    size = MAX_PAYLOAD_SIZE;
  }


  for (
    uint16_t i = 0;
    i < size;
    i++
  ) {

    payload[i] =
      static_cast<uint8_t>(
        i & 0xFF
      );
  }
}


// ============================================================
// Connect to Bluetooth receiver
// ============================================================

bool connectBluetooth() {

  if (
    SerialBT.connected()
  ) {

    bluetoothConnected = true;

    return true;
  }


  Serial.print(
    "Connecting to Bluetooth receiver: "
  );

  Serial.println(
    RECEIVER_BT_NAME
  );


  bool connected =
    SerialBT.connect(
      RECEIVER_BT_NAME
    );


  if (
    connected
  ) {

    bluetoothConnected = true;


    Serial.println(
      "Bluetooth connected"
    );


    Serial.print(
      "Receiver: "
    );

    Serial.println(
      RECEIVER_BT_NAME
    );


    return true;
  }


  bluetoothConnected = false;


  Serial.println(
    "Bluetooth connection failed"
  );


  return false;
}


// ============================================================
// Flush stale Bluetooth data
//
// Because Bluetooth SPP is a byte stream, an old ACK
// remaining in the buffer could otherwise be interpreted as
// the ACK for a new packet.
// ============================================================

void flushBluetoothInput() {

  while (
    SerialBT.available()
  ) {

    SerialBT.read();
  }
}


// ============================================================
// Handle configuration from Python
//
// Expected:
//
// CONFIG,128,500
//
// Meaning:
//
// payload  = 128 bytes
// interval = 500 ms
//
// Response:
//
// CONFIG_OK,128,500,0
//
// The fourth field is retained so the Python parser can
// remain compatible with Wi-Fi.
//
// For Bluetooth it is always 0.
// ============================================================

void handleSerialConfig() {

  if (
    !Serial.available()
  ) {

    return;
  }


  String command =
    Serial.readStringUntil(
      '\n'
    );


  command.trim();


  // Only process CONFIG commands
  if (
    !command.startsWith(
      "CONFIG,"
    )
  ) {

    return;
  }


  // ----------------------------------------------------------
  // Find separators
  // ----------------------------------------------------------

  int firstComma =
    command.indexOf(',');


  int secondComma =
    command.indexOf(
      ',',
      firstComma + 1
    );


  if (
    firstComma == -1 ||
    secondComma == -1
  ) {

    Serial.println(
      "CONFIG_ERROR_FORMAT"
    );

    return;
  }


  // ----------------------------------------------------------
  // Extract values
  // ----------------------------------------------------------

  String payloadString =
    command.substring(
      firstComma + 1,
      secondComma
    );


  String intervalString =
    command.substring(
      secondComma + 1
    );


  long newPayload =
    payloadString.toInt();


  long newInterval =
    intervalString.toInt();


  // ----------------------------------------------------------
  // Validate payload
  // ----------------------------------------------------------

  if (
    newPayload <= 0 ||
    newPayload > MAX_PAYLOAD_SIZE
  ) {

    Serial.print(
      "CONFIG_ERROR_PAYLOAD,"
    );

    Serial.println(
      newPayload
    );

    return;
  }


  // ----------------------------------------------------------
  // Validate interval
  // ----------------------------------------------------------

  if (
    newInterval <= 0
  ) {

    Serial.print(
      "CONFIG_ERROR_INTERVAL,"
    );

    Serial.println(
      newInterval
    );

    return;
  }


  // ----------------------------------------------------------
  // Apply configuration
  // ----------------------------------------------------------

  payloadSize =
    static_cast<uint16_t>(
      newPayload
    );


  sendIntervalMs =
    static_cast<uint32_t>(
      newInterval
    );


  preparePayload(
    payloadSize
  );


  // ----------------------------------------------------------
  // Confirm configuration
  //
  // SAME number of fields as Wi-Fi sender:
  //
  // CONFIG_OK,
  // payload,
  // interval,
  // protocol_specific_value
  //
  // For Wi-Fi:
  // protocol_specific_value = Wi-Fi channel
  //
  // For Bluetooth:
  // protocol_specific_value = 0
  // ----------------------------------------------------------

  Serial.print(
    "CONFIG_OK,"
  );

  Serial.print(
    payloadSize
  );

  Serial.print(",");

  Serial.print(
    sendIntervalMs
  );

  Serial.print(",");

  Serial.println(
    0
  );
}


// ============================================================
// Print packet telemetry
//
// SAME FORMAT as Wi-Fi sender:
//
// PKT,
// packet_id,
// payload_bytes,
// RSSI,
// RTT,
// success,
// retries,
// timestamp
//
// Example:
//
// PKT,42,128,-127,8.00,1,0,49381
//
// NOTE:
// Arduino BluetoothSerial does not expose a clean,
// portable RSSI value for an active SPP connection.
//
// Therefore RSSI = -127 is used as "unavailable".
//
// Your Python collector should interpret -127 as missing
// Bluetooth RSSI rather than a real measurement.
// ============================================================

void printPacketTelemetry(
    uint32_t packetId,
    uint16_t payloadBytes,
    int rssi,
    float rttMs,
    bool successful,
    uint16_t retries,
    uint32_t timestampMs
) {

  Serial.print(
    "PKT,"
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
    rssi
  );

  Serial.print(",");


  Serial.print(
    rttMs,
    2
  );

  Serial.print(",");


  Serial.print(
    successful ? 1 : 0
  );

  Serial.print(",");


  Serial.print(
    retries
  );

  Serial.print(",");


  Serial.println(
    timestampMs
  );
}


// ============================================================
// Read an exact number of Bluetooth bytes
//
// Returns true if all requested bytes arrive before timeout.
// ============================================================

bool readBluetoothBytes(
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

    // Keep accepting Python CONFIG messages while waiting
    handleSerialConfig();


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
// Setup
// ============================================================

void setup() {

  Serial.begin(
    115200
  );


  Serial.setTimeout(
    100
  );


  delay(
    1000
  );


  Serial.println();

  Serial.println(
    "======================================"
  );

  Serial.println(
    "Adaptive IoT Classic Bluetooth Sender"
  );

  Serial.println(
    "======================================"
  );


  // ----------------------------------------------------------
  // Prepare default payload
  // ----------------------------------------------------------

  preparePayload(
    payloadSize
  );


  // ----------------------------------------------------------
  // Start Bluetooth in MASTER mode
  //
  // begin(name, true)
  //
  // true = master mode
  // ----------------------------------------------------------

  bool btStarted =
    SerialBT.begin(
      SENDER_BT_NAME,
      true
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


  Serial.println(
    "Bluetooth initialized in MASTER mode"
  );


  Serial.print(
    "Sender Bluetooth name: "
  );

  Serial.println(
    SENDER_BT_NAME
  );


  Serial.print(
    "Expected receiver name: "
  );

  Serial.println(
    RECEIVER_BT_NAME
  );


  // ----------------------------------------------------------
  // Attempt initial connection
  // ----------------------------------------------------------

  connectBluetooth();


  // ----------------------------------------------------------
  // Print experiment defaults
  // ----------------------------------------------------------

  Serial.print(
    "Default payload size: "
  );

  Serial.print(
    payloadSize
  );

  Serial.println(
    " bytes"
  );


  Serial.print(
    "Default packet interval: "
  );

  Serial.print(
    sendIntervalMs
  );

  Serial.println(
    " ms"
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
    "Sender ready"
  );


  Serial.println(
    "Waiting for CONFIG command..."
  );
}


// ============================================================
// Main loop
// ============================================================

void loop() {

  // ----------------------------------------------------------
  // Handle configuration from Python
  // ----------------------------------------------------------

  handleSerialConfig();


  // ----------------------------------------------------------
  // Restore Bluetooth connection if disconnected
  // ----------------------------------------------------------

  if (
    !SerialBT.connected()
  ) {

    bluetoothConnected = false;


    Serial.println(
      "Bluetooth disconnected. Reconnecting..."
    );


    connectBluetooth();


    // Avoid hammering connection attempts
    if (
      !SerialBT.connected()
    ) {

      delay(
        1000
      );

      return;
    }
  }


  bluetoothConnected = true;


  // ----------------------------------------------------------
  // New packet
  // ----------------------------------------------------------

  packetId++;


  // ----------------------------------------------------------
  // Construct packet header
  // ----------------------------------------------------------

  TestHeader header;


  header.packet_id =
    packetId;


  header.timestamp_ms =
    millis();


  header.payload_size =
    payloadSize;


  // ----------------------------------------------------------
  // Remove any stale ACK / Bluetooth bytes
  // ----------------------------------------------------------

  flushBluetoothInput();


  // ----------------------------------------------------------
  // RTT timer
  // ----------------------------------------------------------

  uint32_t sendStart =
    millis();


  // ----------------------------------------------------------
  // Send packet
  //
  // Bluetooth stream:
  //
  // [TestHeader]
  // [application payload]
  //
  // TestHeader = 10 bytes
  // ----------------------------------------------------------

  size_t headerWritten =
    SerialBT.write(
      reinterpret_cast<
        const uint8_t*
      >(
        &header
      ),
      sizeof(
        TestHeader
      )
    );


  size_t payloadWritten =
    SerialBT.write(
      payload,
      payloadSize
    );


  bool sendOk =
    (
      headerWritten
        == sizeof(TestHeader)
      &&
      payloadWritten
        == payloadSize
    );


  // Ensure queued Bluetooth data is transmitted
  SerialBT.flush();


  // ----------------------------------------------------------
  // Wait for receiver ACK
  // ----------------------------------------------------------

  bool ackReceived =
    false;


  float rttMs =
    -1.0;


  uint16_t retryCount =
    0;


  if (
    sendOk
  ) {

    uint32_t timeoutStart =
      millis();


    while (
      millis() - timeoutStart
      < ACK_TIMEOUT_MS
    ) {

      // Python can still change experiment parameters
      handleSerialConfig();


      // Wait until enough bytes for an ACK are available
      if (
        SerialBT.available()
        >= static_cast<int>(
          sizeof(
            AckPacket
          )
        )
      ) {

        AckPacket ack;


        bool ackRead =
          readBluetoothBytes(
            reinterpret_cast<
              uint8_t*
            >(
              &ack
            ),
            sizeof(
              AckPacket
            ),
            ACK_TIMEOUT_MS
          );


        if (
          ackRead
          &&
          ack.packet_id
            == packetId
          &&
          ack.success
            == 1
        ) {

          ackReceived =
            true;


          rttMs =
            static_cast<float>(
              millis()
              - sendStart
            );


          break;
        }
      }


      delay(
        1
      );
    }
  }


  // ----------------------------------------------------------
  // Bluetooth RSSI
  //
  // BluetoothSerial does not provide a portable active-link
  // RSSI API like WiFi.RSSI().
  //
  // -127 therefore means "RSSI unavailable".
  // ----------------------------------------------------------

  int rssi =
    -127;


  // ----------------------------------------------------------
  // Output telemetry to Python
  //
  // Exactly the same column order as Wi-Fi:
  //
  // PKT,
  // ID,
  // payload,
  // RSSI,
  // RTT,
  // success,
  // retries,
  // timestamp
  // ----------------------------------------------------------

  printPacketTelemetry(

    packetId,

    payloadSize,

    rssi,

    ackReceived
      ? rttMs
      : -1.0,

    ackReceived,

    retryCount,

    millis()
  );


  // ----------------------------------------------------------
  // Wait for next transmission
  //
  // Do not use one large delay because Python can issue
  // CONFIG commands at any time.
  // ----------------------------------------------------------

  uint32_t waitStart =
    millis();


  while (
    millis() - waitStart
    < sendIntervalMs
  ) {

    handleSerialConfig();


    // Break early if Bluetooth disconnects
    if (
      !SerialBT.connected()
    ) {

      break;
    }


    delay(
      5
    );
  }
}
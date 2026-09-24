#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEScan.h>
#include <BLEAdvertisedDevice.h>
#include <BLEClient.h>

// ============================================================
// CONFIGURATION
// ============================================================

#define RECEIVER_NAME "NEXORA_BLE_RX"

#define SERVICE_UUID        "12345678-1234-1234-1234-123456789000"
#define RX_CHARACTERISTIC   "12345678-1234-1234-1234-123456789001"
#define TX_CHARACTERISTIC   "12345678-1234-1234-1234-123456789002"

// ------------------------------------------------------------
// Dataset parameters
// ------------------------------------------------------------

uint16_t payloadSize = 16;

uint32_t packetIntervalMs = 500;

// ------------------------------------------------------------
// BLE
// ------------------------------------------------------------

BLEAdvertisedDevice *targetDevice = nullptr;

BLEClient *pClient = nullptr;

BLERemoteCharacteristic *pRxCharacteristic = nullptr;
BLERemoteCharacteristic *pTxCharacteristic = nullptr;

// ------------------------------------------------------------
// Connection state
// ------------------------------------------------------------

bool connected = false;

bool ackReceived = false;

uint32_t ackSequence = 0;

// ------------------------------------------------------------
// Packet sequence
// ------------------------------------------------------------

uint32_t sequenceNumber = 0;


// ============================================================
// NOTIFICATION CALLBACK
// ============================================================

static void notifyCallback(
  BLERemoteCharacteristic *pCharacteristic,
  uint8_t *pData,
  size_t length,
  bool isNotify
) {

  if (length < 4) {
    return;
  }

  uint32_t receivedSequence = 0;

  memcpy(
    &receivedSequence,
    pData,
    sizeof(receivedSequence)
  );

  ackSequence = receivedSequence;

  ackReceived = true;
}


// ============================================================
// BLE SCAN CALLBACK
// ============================================================

class AdvertisedDeviceCallbacks :
  public BLEAdvertisedDeviceCallbacks {

  void onResult(
    BLEAdvertisedDevice advertisedDevice
  ) override {

    // --------------------------------------------------------
    // Ignore devices without service UUID
    // --------------------------------------------------------

    if (!advertisedDevice.haveServiceUUID()) {
      return;
    }

    // --------------------------------------------------------
    // Check NEXORA service UUID
    // --------------------------------------------------------

    if (
      !advertisedDevice.isAdvertisingService(
        BLEUUID(SERVICE_UUID)
      )
    ) {
      return;
    }

    // --------------------------------------------------------
    // Correct receiver found
    // --------------------------------------------------------

    Serial.println();
    Serial.println("BLE_TARGET_FOUND");

    Serial.print("BLE_ADDRESS,");

    Serial.println(
      advertisedDevice
        .getAddress()
        .toString()
        .c_str()
    );

    Serial.print("BLE_NAME,");

    if (advertisedDevice.haveName()) {

      Serial.println(
        advertisedDevice
          .getName()
          .c_str()
      );

    } else {

      Serial.println("UNKNOWN");
    }

    Serial.print("BLE_RSSI,");

    Serial.println(
      advertisedDevice.getRSSI()
    );

    // --------------------------------------------------------
    // Save discovered receiver BEFORE stopping scan
    //
    // Stopping the scanner may unblock pScan->start()
    // immediately, so targetDevice must already be valid.
    // --------------------------------------------------------

    if (targetDevice != nullptr) {

      delete targetDevice;

      targetDevice = nullptr;
    }

    targetDevice =
        new BLEAdvertisedDevice(
          advertisedDevice
        );

    Serial.println(
      "BLE_TARGET_SAVED"
    );

    // --------------------------------------------------------
    // Stop scanning only after device is stored
    // --------------------------------------------------------

    BLEDevice::getScan()->stop();
  }
};


// ============================================================
// CONNECT TO RECEIVER
// ============================================================

bool connectToReceiver() {

  // ----------------------------------------------------------
  // Validate discovered device
  // ----------------------------------------------------------

  if (targetDevice == nullptr) {

    Serial.println(
      "BLE_CONNECT_FAIL,NO_TARGET"
    );

    return false;
  }

  Serial.println();
  Serial.println("BLE_CONNECTING");

  Serial.print("BLE_CONNECT_ADDRESS,");

  Serial.println(
    targetDevice
      ->getAddress()
      .toString()
      .c_str()
  );

  // ----------------------------------------------------------
  // Create client
  // ----------------------------------------------------------

  if (pClient == nullptr) {

    Serial.println(
      "BLE_CLIENT_CREATING"
    );

    pClient =
        BLEDevice::createClient();

    if (pClient == nullptr) {

      Serial.println(
        "BLE_CLIENT_CREATE_FAIL"
      );

      return false;
    }

    Serial.println(
      "BLE_CLIENT_CREATED"
    );
  }

  // ----------------------------------------------------------
  // Disconnect old connection if necessary
  // ----------------------------------------------------------

  if (pClient->isConnected()) {

    Serial.println(
      "BLE_OLD_CONNECTION_DISCONNECT"
    );

    pClient->disconnect();

    delay(200);
  }

  // ----------------------------------------------------------
  // Connect
  // ----------------------------------------------------------

  Serial.println(
    "BLE_CONNECT_ATTEMPT"
  );

  bool connectionResult =
      pClient->connect(
        targetDevice
      );

  if (!connectionResult) {

    Serial.println(
      "BLE_CONNECT_FAIL"
    );

    connected = false;

    return false;
  }

  Serial.println(
    "BLE_CONNECTED"
  );

  delay(200);

  // ----------------------------------------------------------
  // Verify connection
  // ----------------------------------------------------------

  if (!pClient->isConnected()) {

    Serial.println(
      "BLE_CONNECTION_LOST"
    );

    connected = false;

    return false;
  }

  // ----------------------------------------------------------
  // Find service
  // ----------------------------------------------------------

  Serial.println(
    "BLE_SERVICE_SEARCH"
  );

  BLERemoteService *pService =
      pClient->getService(
        BLEUUID(SERVICE_UUID)
      );

  if (pService == nullptr) {

    Serial.println(
      "BLE_SERVICE_NOT_FOUND"
    );

    pClient->disconnect();

    connected = false;

    return false;
  }

  Serial.println(
    "BLE_SERVICE_FOUND"
  );

  // ----------------------------------------------------------
  // Find RX characteristic
  // Sender writes packets here
  // ----------------------------------------------------------

  Serial.println(
    "BLE_RX_SEARCH"
  );

  pRxCharacteristic =
      pService->getCharacteristic(
        BLEUUID(RX_CHARACTERISTIC)
      );

  if (pRxCharacteristic == nullptr) {

    Serial.println(
      "BLE_RX_NOT_FOUND"
    );

    pClient->disconnect();

    connected = false;

    return false;
  }

  Serial.println(
    "BLE_RX_FOUND"
  );

  Serial.print(
    "BLE_RX_CAN_WRITE,"
  );

  Serial.println(
    pRxCharacteristic->canWrite()
      ? "YES"
      : "NO"
  );

  // ----------------------------------------------------------
  // Find TX characteristic
  // Receiver sends ACK here
  // ----------------------------------------------------------

  Serial.println(
    "BLE_TX_SEARCH"
  );

  pTxCharacteristic =
      pService->getCharacteristic(
        BLEUUID(TX_CHARACTERISTIC)
      );

  if (pTxCharacteristic == nullptr) {

    Serial.println(
      "BLE_TX_NOT_FOUND"
    );

    pClient->disconnect();

    connected = false;

    return false;
  }

  Serial.println(
    "BLE_TX_FOUND"
  );

  Serial.print(
    "BLE_TX_CAN_NOTIFY,"
  );

  Serial.println(
    pTxCharacteristic->canNotify()
      ? "YES"
      : "NO"
  );

  // ----------------------------------------------------------
  // Register ACK notification
  // ----------------------------------------------------------

  if (pTxCharacteristic->canNotify()) {

    Serial.println(
      "BLE_NOTIFY_REGISTERING"
    );

    pTxCharacteristic->registerForNotify(
      notifyCallback
    );

    Serial.println(
      "BLE_NOTIFY_REGISTERED"
    );

  } else {

    Serial.println(
      "BLE_NOTIFY_NOT_SUPPORTED"
    );
  }

  // ----------------------------------------------------------
  // Connection complete
  // ----------------------------------------------------------

  connected = true;

  Serial.println();
  Serial.println(
    "BLE_READY"
  );

  return true;
}


// ============================================================
// SCAN
// ============================================================

bool findReceiver() {

  // ----------------------------------------------------------
  // Clear previous target
  // ----------------------------------------------------------

  if (targetDevice != nullptr) {

    delete targetDevice;

    targetDevice = nullptr;
  }

  // ----------------------------------------------------------
  // Get BLE scanner
  // ----------------------------------------------------------

  BLEScan *pScan =
      BLEDevice::getScan();

  // ----------------------------------------------------------
  // Configure callbacks
  // ----------------------------------------------------------

  pScan->setAdvertisedDeviceCallbacks(
    new AdvertisedDeviceCallbacks()
  );

  // ----------------------------------------------------------
  // Active scan required for scan-response data
  // ----------------------------------------------------------

  pScan->setActiveScan(true);

  pScan->setInterval(100);

  pScan->setWindow(99);

  // ----------------------------------------------------------
  // Scan
  // ----------------------------------------------------------

  Serial.println();
  Serial.println(
    "BLE_SCANNING"
  );

  pScan->start(
    5,
    false
  );

  // ----------------------------------------------------------
  // Allow scan callback to finish completely
  // ----------------------------------------------------------

  delay(50);

  // ----------------------------------------------------------
  // Result
  // ----------------------------------------------------------

  if (targetDevice == nullptr) {

    Serial.println(
      "BLE_TARGET_NOT_FOUND"
    );

    return false;
  }

  Serial.println(
    "BLE_SCAN_COMPLETE,TARGET_FOUND"
  );

  return true;
}


// ============================================================
// SEND PACKET
// ============================================================

void sendPacket() {

  if (
    !connected ||
    pClient == nullptr ||
    !pClient->isConnected()
  ) {

    connected = false;

    return;
  }

  // ----------------------------------------------------------
  // Validate RX characteristic
  // ----------------------------------------------------------

  if (pRxCharacteristic == nullptr) {

    Serial.println(
      "BLE_SEND_FAIL,NO_RX_CHARACTERISTIC"
    );

    connected = false;

    return;
  }

  sequenceNumber++;

  // ----------------------------------------------------------
  // Limit payload
  // ----------------------------------------------------------

  if (payloadSize < 4) {
    payloadSize = 4;
  }

  if (payloadSize > 240) {
    payloadSize = 240;
  }

  uint8_t payload[240];

  // ----------------------------------------------------------
  // Fill packet with deterministic test data
  // ----------------------------------------------------------

  memset(
    payload,
    0,
    payloadSize
  );

  // First 4 bytes = packet sequence number

  memcpy(
    payload,
    &sequenceNumber,
    sizeof(sequenceNumber)
  );

  // Remaining bytes = dummy payload

  for (
    uint16_t i = 4;
    i < payloadSize;
    i++
  ) {

    payload[i] =
        (uint8_t)(
          (sequenceNumber + i) & 0xFF
        );
  }

  // ----------------------------------------------------------
  // Reset ACK state
  // ----------------------------------------------------------

  ackReceived = false;

  ackSequence = 0;

  // ----------------------------------------------------------
  // Start RTT
  // ----------------------------------------------------------

  uint32_t txStartUs =
      micros();

  // ----------------------------------------------------------
  // Transmit
  // ----------------------------------------------------------

  pRxCharacteristic->writeValue(
    payload,
    payloadSize,
    true
  );

  // ----------------------------------------------------------
  // Wait for ACK
  // ----------------------------------------------------------

  const uint32_t ACK_TIMEOUT_MS = 1000;

  uint32_t waitStart =
      millis();

  while (
    !ackReceived &&
    (
      millis() - waitStart <
      ACK_TIMEOUT_MS
    )
  ) {

    delay(1);
  }

  uint32_t txEndUs =
      micros();

  // ----------------------------------------------------------
  // Result
  // ----------------------------------------------------------

  uint8_t success = 0;

  float rttMs = -1.0;

  if (
    ackReceived &&
    ackSequence == sequenceNumber
  ) {

    success = 1;

    rttMs =
        (txEndUs - txStartUs)
        / 1000.0f;
  }

  // ----------------------------------------------------------
  // RSSI
  // ----------------------------------------------------------

  int rssi = -127;

  if (
    pClient != nullptr &&
    pClient->isConnected()
  ) {

    rssi =
        pClient->getRssi();
  }

  // ----------------------------------------------------------
  // Timestamp
  // ----------------------------------------------------------

  uint32_t timestampUs =
      micros();

  // ==========================================================
  // SERIAL OUTPUT
  //
  // PKT,
  // sequence,
  // payload_size,
  // RSSI,
  // RTT,
  // success,
  // retries,
  // timestamp
  // ==========================================================

  Serial.print("PKT,");
  Serial.print(sequenceNumber);
  Serial.print(",");
  Serial.print(payloadSize);
  Serial.print(",");
  Serial.print(rssi);
  Serial.print(",");
  Serial.print(rttMs, 2);
  Serial.print(",");
  Serial.print(success);
  Serial.print(",");
  Serial.print(0);
  Serial.print(",");
  Serial.println(timestampUs);
}


// ============================================================
// SERIAL CONFIGURATION
// ============================================================

void handleSerial() {

  if (!Serial.available()) {
    return;
  }

  String command =
      Serial.readStringUntil('\n');

  command.trim();

  // ----------------------------------------------------------
  // Expected:
  //
  // CONFIG,16,500
  // ----------------------------------------------------------

  if (
    command.startsWith("CONFIG,")
  ) {

    int firstComma =
        command.indexOf(',');

    int secondComma =
        command.indexOf(
          ',',
          firstComma + 1
        );

    if (
      firstComma > 0 &&
      secondComma > firstComma
    ) {

      payloadSize =
          command.substring(
            firstComma + 1,
            secondComma
          ).toInt();

      packetIntervalMs =
          command.substring(
            secondComma + 1
          ).toInt();

      // --------------------------------------------------------
      // Safety
      // --------------------------------------------------------

      if (payloadSize < 4) {
        payloadSize = 4;
      }

      if (payloadSize > 240) {
        payloadSize = 240;
      }

      if (packetIntervalMs < 10) {
        packetIntervalMs = 10;
      }

      // --------------------------------------------------------
      // Config response
      // --------------------------------------------------------

      Serial.print("CONFIG_OK,");
      Serial.print(payloadSize);
      Serial.print(",");
      Serial.println(packetIntervalMs);
    }
  }
}


// ============================================================
// SETUP
// ============================================================

void setup() {

  Serial.begin(115200);

  delay(1000);

  Serial.println();
  Serial.println("====================================");
  Serial.println("NEXORA BLE SENDER");
  Serial.println("====================================");

  // ----------------------------------------------------------
  // Initialize BLE
  // ----------------------------------------------------------

  Serial.println(
    "BLE_INITIALIZING"
  );

  BLEDevice::init(
    "NEXORA_BLE_TX"
  );

  Serial.println(
    "BLE_INITIALIZED"
  );

  // ----------------------------------------------------------
  // Search until receiver is found and connected
  // ----------------------------------------------------------

  while (!connected) {

    if (findReceiver()) {

      if (connectToReceiver()) {
        break;
      }
    }

    Serial.println();
    Serial.println(
      "BLE_RETRY"
    );

    delay(2000);
  }

  // ----------------------------------------------------------
  // Initial config line
  // ----------------------------------------------------------

  Serial.print("CONFIG_OK,");
  Serial.print(payloadSize);
  Serial.print(",");
  Serial.println(packetIntervalMs);
}


// ============================================================
// LOOP
// ============================================================

void loop() {

  static uint32_t lastPacketTime = 0;

  // ----------------------------------------------------------
  // Serial commands from Python
  // ----------------------------------------------------------

  handleSerial();

  // ----------------------------------------------------------
  // Reconnect
  // ----------------------------------------------------------

  if (
    pClient == nullptr ||
    !pClient->isConnected()
  ) {

    if (connected) {

      Serial.println(
        "BLE_DISCONNECTED"
      );
    }

    connected = false;

    pRxCharacteristic = nullptr;
    pTxCharacteristic = nullptr;

    delay(500);

    if (findReceiver()) {

      if (!connectToReceiver()) {

        Serial.println(
          "BLE_RECONNECT_FAIL"
        );
      }
    }

    return;
  }

  // ----------------------------------------------------------
  // Packet transmission
  // ----------------------------------------------------------

  if (
    millis() - lastPacketTime >=
    packetIntervalMs
  ) {

    lastPacketTime =
        millis();

    sendPacket();
  }

  delay(1);
}

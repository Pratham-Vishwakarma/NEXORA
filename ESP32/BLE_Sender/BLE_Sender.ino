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
    // Check service UUID
    // --------------------------------------------------------

    if (
      advertisedDevice.haveServiceUUID() &&
      advertisedDevice.isAdvertisingService(
        BLEUUID(SERVICE_UUID)
      )
    ) {

      Serial.print("BLE_FOUND,");

      if (advertisedDevice.haveName()) {
        Serial.println(
          advertisedDevice.getName().c_str()
        );
      } else {
        Serial.println("UNKNOWN");
      }

      BLEDevice::getScan()->stop();

      targetDevice =
          new BLEAdvertisedDevice(
            advertisedDevice
          );
    }
  }
};

// ============================================================
// CONNECT TO RECEIVER
// ============================================================

bool connectToReceiver() {

  if (targetDevice == nullptr) {
    return false;
  }

  Serial.println("BLE_CONNECTING");

  // ----------------------------------------------------------
  // Create client
  // ----------------------------------------------------------

  pClient =
      BLEDevice::createClient();

  // ----------------------------------------------------------
  // Connect
  // ----------------------------------------------------------

  if (!pClient->connect(targetDevice)) {

    Serial.println("BLE_CONNECT_FAIL");

    return false;
  }

  Serial.println("BLE_CONNECTED");

  // ----------------------------------------------------------
  // Find service
  // ----------------------------------------------------------

  BLERemoteService *pService =
      pClient->getService(
        BLEUUID(SERVICE_UUID)
      );

  if (pService == nullptr) {

    Serial.println("BLE_SERVICE_FAIL");

    pClient->disconnect();

    return false;
  }

  // ----------------------------------------------------------
  // Find RX
  // ----------------------------------------------------------

  pRxCharacteristic =
      pService->getCharacteristic(
        BLEUUID(RX_CHARACTERISTIC)
      );

  if (pRxCharacteristic == nullptr) {

    Serial.println("BLE_RX_FAIL");

    pClient->disconnect();

    return false;
  }

  // ----------------------------------------------------------
  // Find TX ACK
  // ----------------------------------------------------------

  pTxCharacteristic =
      pService->getCharacteristic(
        BLEUUID(TX_CHARACTERISTIC)
      );

  if (pTxCharacteristic == nullptr) {

    Serial.println("BLE_TX_FAIL");

    pClient->disconnect();

    return false;
  }

  // ----------------------------------------------------------
  // Register ACK notification
  // ----------------------------------------------------------

  if (pTxCharacteristic->canNotify()) {

    pTxCharacteristic->registerForNotify(
      notifyCallback
    );
  }

  connected = true;

  Serial.println("BLE_READY");

  return true;
}

// ============================================================
// SCAN
// ============================================================

bool findReceiver() {

  targetDevice = nullptr;

  BLEScan *pScan =
      BLEDevice::getScan();

  pScan->setAdvertisedDeviceCallbacks(
    new AdvertisedDeviceCallbacks()
  );

  pScan->setActiveScan(true);

  pScan->setInterval(100);

  pScan->setWindow(99);

  Serial.println("BLE_SCANNING");

  pScan->start(
    5,
    false
  );

  return targetDevice != nullptr;
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

  uint32_t txStartUs = micros();

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
  // SAME STYLE AS YOUR WIFI COLLECTOR
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
  Serial.print(0);             // retries
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

      // Safety

      if (payloadSize < 4) {
        payloadSize = 4;
      }

      if (payloadSize > 240) {
        payloadSize = 240;
      }

      if (packetIntervalMs < 10) {
        packetIntervalMs = 10;
      }

      // Same config response structure

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

  BLEDevice::init(
    "NEXORA_BLE_TX"
  );

  // ----------------------------------------------------------
  // Search until receiver is found
  // ----------------------------------------------------------

  while (!connected) {

    if (findReceiver()) {

      if (connectToReceiver()) {
        break;
      }
    }

    Serial.println("BLE_RETRY");

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

    delay(500);

    if (findReceiver()) {
      connectToReceiver();
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
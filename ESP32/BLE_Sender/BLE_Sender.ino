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

// ============================================================
// ACS712 CURRENT SENSOR
// ============================================================

// Change this only if your ACS712 OUT pin uses another ADC pin.
#define ACS712_PIN 34

// ACS712-5A sensitivity = 185 mV/A.
// Use 100.0f for 20A module or 66.0f for 30A module.
#define ACS712_SENSITIVITY_MV_PER_A 185.0f

// IMPORTANT:
// Set this to your measured zero-current ACS712 output voltage.
// Do not auto-calibrate while the ESP32 is connected as the load.
#define ACS712_ZERO_CURRENT_MV 2500.0f

// Dataset voltage assumption.
#define SUPPLY_VOLTAGE 3.3f

// Current telemetry sampling interval.
// 10 ms = approximately 100 current samples/second.
#define POWER_SAMPLE_INTERVAL_MS 10

// ============================================================
// DATASET PARAMETERS
// ============================================================

# define MAX_PAYLOAD_SIZE 2048
uint16_t payloadSize = 16;
uint32_t packetIntervalMs = 500;

// ============================================================
// BLE
// ============================================================

BLEAdvertisedDevice *targetDevice = nullptr;
BLEClient *pClient = nullptr;
BLERemoteCharacteristic *pRxCharacteristic = nullptr;
BLERemoteCharacteristic *pTxCharacteristic = nullptr;

// ============================================================
// CONNECTION STATE
// ============================================================

bool connected = false;
volatile bool ackReceived = false;
volatile uint32_t ackSequence = 0;

// ============================================================
// PACKET SEQUENCE
// ============================================================

uint32_t sequenceNumber = 0;

// ============================================================
// POWER SAMPLING STATE
// ============================================================

uint32_t lastPowerSampleMs = 0;

// ============================================================
// READ ACS712 CURRENT
// ============================================================

float readCurrentMa() {

  uint32_t milliVolts =
      analogReadMilliVolts(
        ACS712_PIN
      );

  float differenceMv =
      (float)milliVolts -
      ACS712_ZERO_CURRENT_MV;

  float currentA =
      differenceMv /
      ACS712_SENSITIVITY_MV_PER_A;

  // Small negative readings are normally ADC / offset noise.
  if (currentA < 0.0f) {
    currentA = 0.0f;
  }

  return currentA * 1000.0f;
}

// ============================================================
// POWER TELEMETRY
//
// PWR,current_ma,timestamp_us
//
// Python integrates these samples over the experiment window.
// ============================================================

void samplePowerTelemetry() {

  uint32_t nowMs = millis();

  if (
    (uint32_t)(nowMs - lastPowerSampleMs) <
    POWER_SAMPLE_INTERVAL_MS
  ) {
    return;
  }

  // Keep the schedule anchored instead of resetting to now.
  lastPowerSampleMs += POWER_SAMPLE_INTERVAL_MS;

  // If startup / blocking work caused a large delay, resynchronise
  // rather than trying to emit hundreds of catch-up samples.
  if (
    (uint32_t)(nowMs - lastPowerSampleMs) >
    (POWER_SAMPLE_INTERVAL_MS * 5UL)
  ) {
    lastPowerSampleMs = nowMs;
  }

  float currentMa = readCurrentMa();
  uint32_t timestampUs = micros();

  Serial.print("PWR,");
  Serial.print(currentMa, 3);
  Serial.print(",");
  Serial.println(timestampUs);
}

// ============================================================
// NOTIFICATION CALLBACK
// ============================================================

static void notifyCallback(
  BLERemoteCharacteristic *pCharacteristic,
  uint8_t *pData,
  size_t length,
  bool isNotify
) {

  if (length < sizeof(uint32_t)) {
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

    if (!advertisedDevice.haveServiceUUID()) {
      return;
    }

    if (
      !advertisedDevice.isAdvertisingService(
        BLEUUID(SERVICE_UUID)
      )
    ) {
      return;
    }

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

    if (targetDevice != nullptr) {
      delete targetDevice;
      targetDevice = nullptr;
    }

    targetDevice =
        new BLEAdvertisedDevice(
          advertisedDevice
        );

    Serial.println("BLE_TARGET_SAVED");

    BLEDevice::getScan()->stop();
  }
};

// ============================================================
// CONNECT TO RECEIVER
// ============================================================

bool connectToReceiver() {

  if (targetDevice == nullptr) {
    Serial.println("BLE_CONNECT_FAIL,NO_TARGET");
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

  if (pClient == nullptr) {

    Serial.println("BLE_CLIENT_CREATING");

    pClient = BLEDevice::createClient();

    if (pClient == nullptr) {
      Serial.println("BLE_CLIENT_CREATE_FAIL");
      return false;
    }

    Serial.println("BLE_CLIENT_CREATED");
  }

  if (pClient->isConnected()) {

    Serial.println("BLE_OLD_CONNECTION_DISCONNECT");

    pClient->disconnect();
    delay(200);
  }

  Serial.println("BLE_CONNECT_ATTEMPT");

  bool connectionResult =
      pClient->connect(
        targetDevice
      );

  if (!connectionResult) {

    Serial.println("BLE_CONNECT_FAIL");

    connected = false;
    return false;
  }

  Serial.println("BLE_CONNECTED");

  delay(200);

  if (!pClient->isConnected()) {

    Serial.println("BLE_CONNECTION_LOST");

    connected = false;
    return false;
  }

  Serial.println("BLE_SERVICE_SEARCH");

  BLERemoteService *pService =
      pClient->getService(
        BLEUUID(SERVICE_UUID)
      );

  if (pService == nullptr) {

    Serial.println("BLE_SERVICE_NOT_FOUND");

    pClient->disconnect();
    connected = false;

    return false;
  }

  Serial.println("BLE_SERVICE_FOUND");

  Serial.println("BLE_RX_SEARCH");

  pRxCharacteristic =
      pService->getCharacteristic(
        BLEUUID(RX_CHARACTERISTIC)
      );

  if (pRxCharacteristic == nullptr) {

    Serial.println("BLE_RX_NOT_FOUND");

    pClient->disconnect();
    connected = false;

    return false;
  }

  Serial.println("BLE_RX_FOUND");

  Serial.print("BLE_RX_CAN_WRITE,");
  Serial.println(
    pRxCharacteristic->canWrite()
      ? "YES"
      : "NO"
  );

  Serial.println("BLE_TX_SEARCH");

  pTxCharacteristic =
      pService->getCharacteristic(
        BLEUUID(TX_CHARACTERISTIC)
      );

  if (pTxCharacteristic == nullptr) {

    Serial.println("BLE_TX_NOT_FOUND");

    pClient->disconnect();
    connected = false;

    return false;
  }

  Serial.println("BLE_TX_FOUND");

  Serial.print("BLE_TX_CAN_NOTIFY,");
  Serial.println(
    pTxCharacteristic->canNotify()
      ? "YES"
      : "NO"
  );

  if (pTxCharacteristic->canNotify()) {

    Serial.println("BLE_NOTIFY_REGISTERING");

    pTxCharacteristic->registerForNotify(
      notifyCallback
    );

    Serial.println("BLE_NOTIFY_REGISTERED");

  } else {

    Serial.println("BLE_NOTIFY_NOT_SUPPORTED");
  }

  connected = true;

  Serial.println();
  Serial.println("BLE_READY");

  return true;
}

// ============================================================
// SCAN
// ============================================================

bool findReceiver() {

  if (targetDevice != nullptr) {
    delete targetDevice;
    targetDevice = nullptr;
  }

  BLEScan *pScan = BLEDevice::getScan();

  pScan->setAdvertisedDeviceCallbacks(
    new AdvertisedDeviceCallbacks()
  );

  pScan->setActiveScan(true);
  pScan->setInterval(100);
  pScan->setWindow(99);

  Serial.println();
  Serial.println("BLE_SCANNING");

  pScan->start(
    5,
    false
  );

  delay(50);

  if (targetDevice == nullptr) {

    Serial.println("BLE_TARGET_NOT_FOUND");
    return false;
  }

  Serial.println("BLE_SCAN_COMPLETE,TARGET_FOUND");

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

  if (pRxCharacteristic == nullptr) {

    Serial.println("BLE_SEND_FAIL,NO_RX_CHARACTERISTIC");

    connected = false;
    return;
  }

  sequenceNumber++;

  if (payloadSize < 4) {
    payloadSize = 4;
  }

  if (payloadSize > MAX_PAYLOAD_SIZE) {
    payloadSize = MAX_PAYLOAD_SIZE;
  }

  uint8_t payload[MAX_PAYLOAD_SIZE];

  memset(
    payload,
    0,
    payloadSize
  );

  memcpy(
    payload,
    &sequenceNumber,
    sizeof(sequenceNumber)
  );

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

  ackReceived = false;
  ackSequence = 0;

  uint32_t txStartUs = micros();

  pRxCharacteristic->writeValue(
    payload,
    payloadSize,
    true
  );

  const uint32_t ACK_TIMEOUT_MS = 1000;

  uint32_t waitStart = millis();

  while (
    !ackReceived &&
    (millis() - waitStart < ACK_TIMEOUT_MS)
  ) {

    // Continue sampling current while waiting for ACK.
    samplePowerTelemetry();

    delay(1);
  }

  uint32_t txEndUs = micros();

  uint8_t success = 0;
  float rttMs = -1.0f;

  if (
    ackReceived &&
    ackSequence == sequenceNumber
  ) {

    success = 1;

    rttMs =
        (txEndUs - txStartUs) /
        1000.0f;
  }

  int rssi = -127;

  if (
    pClient != nullptr &&
    pClient->isConnected()
  ) {
    rssi = pClient->getRssi();
  }

  uint32_t timestampUs = micros();

  // ==========================================================
  // PACKET SERIAL OUTPUT
  //
  // PKT,
  // sequence,
  // payload_size,
  // RSSI,
  // RTT,
  // success,
  // retries,
  // timestamp_us
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

  if (command.startsWith("CONFIG,")) {

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

      if (payloadSize < 4) {
        payloadSize = 4;
      }

      if (payloadSize > MAX_PAYLOAD_SIZE) {
        payloadSize = MAX_PAYLOAD_SIZE;
      }

      if (packetIntervalMs < 10) {
        packetIntervalMs = 10;
      }

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
  // ACS712
  // ----------------------------------------------------------

  pinMode(
    ACS712_PIN,
    INPUT
  );

  analogReadResolution(12);

  analogSetPinAttenuation(
    ACS712_PIN,
    ADC_11db
  );

  Serial.print("ACS712_PIN,");
  Serial.println(ACS712_PIN);

  Serial.print("ACS712_ZERO_MV,");
  Serial.println(
    ACS712_ZERO_CURRENT_MV,
    2
  );

  Serial.print("ACS712_SENSITIVITY_MV_PER_A,");
  Serial.println(
    ACS712_SENSITIVITY_MV_PER_A,
    2
  );

  Serial.print("SUPPLY_VOLTAGE,");
  Serial.println(
    SUPPLY_VOLTAGE,
    2
  );

  Serial.print("POWER_SAMPLE_INTERVAL_MS,");
  Serial.println(
    POWER_SAMPLE_INTERVAL_MS
  );

  // ----------------------------------------------------------
  // BLE
  // ----------------------------------------------------------

  Serial.println("BLE_INITIALIZING");

  BLEDevice::init(
    "NEXORA_BLE_TX"
  );

  Serial.println("BLE_INITIALIZED");

  while (!connected) {

    if (findReceiver()) {

      if (connectToReceiver()) {
        break;
      }
    }

    Serial.println();
    Serial.println("BLE_RETRY");

    delay(2000);
  }

  Serial.print("CONFIG_OK,");
  Serial.print(payloadSize);
  Serial.print(",");
  Serial.println(packetIntervalMs);

  lastPowerSampleMs = millis();
}

// ============================================================
// LOOP
// ============================================================

void loop() {

  static bool packetSchedulerInitialized = false;
  static uint32_t nextPacketTime = 0;

  handleSerial();

  // Continuous current sampling while the device is idle.
  samplePowerTelemetry();

  if (
    pClient == nullptr ||
    !pClient->isConnected()
  ) {

    if (connected) {
      Serial.println("BLE_DISCONNECTED");
    }

    connected = false;

    pRxCharacteristic = nullptr;
    pTxCharacteristic = nullptr;

    packetSchedulerInitialized = false;

    delay(500);

    if (findReceiver()) {

      if (!connectToReceiver()) {
        Serial.println("BLE_RECONNECT_FAIL");
      }
    }

    return;
  }

  // ----------------------------------------------------------
  // Exact packet schedule
  //
  // The next transmission time is advanced by the configured
  // interval rather than by the duration of sendPacket().
  // ----------------------------------------------------------

  if (!packetSchedulerInitialized) {

    nextPacketTime =
        millis() +
        packetIntervalMs;

    packetSchedulerInitialized = true;
  }

  uint32_t nowMs = millis();

  if (
    (int32_t)(nowMs - nextPacketTime) >= 0
  ) {

    nextPacketTime += packetIntervalMs;

    // If execution fell far behind, resynchronise instead of
    // bursting many packets back-to-back.
    if (
      (int32_t)(nowMs - nextPacketTime) >=
      (int32_t)packetIntervalMs
    ) {
      nextPacketTime =
          nowMs +
          packetIntervalMs;
    }

    sendPacket();
  }

  delay(1);
}

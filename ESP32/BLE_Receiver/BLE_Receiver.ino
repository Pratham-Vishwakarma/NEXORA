#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

// ============================================================
// BLE CONFIGURATION
// ============================================================

#define DEVICE_NAME "NEXORA_BLE_RX"

#define SERVICE_UUID        "12345678-1234-1234-1234-123456789000"
#define RX_CHARACTERISTIC   "12345678-1234-1234-1234-123456789001"
#define TX_CHARACTERISTIC   "12345678-1234-1234-1234-123456789002"

// ============================================================
// GLOBALS
// ============================================================

BLEServer *pServer = nullptr;
BLECharacteristic *pTxCharacteristic = nullptr;

bool deviceConnected = false;
bool oldDeviceConnected = false;

// ============================================================
// SERVER CALLBACKS
// ============================================================

class ServerCallbacks : public BLEServerCallbacks {

  void onConnect(BLEServer *pServer) override {
    deviceConnected = true;

    Serial.println("BLE_CONNECTED");
  }

  void onDisconnect(BLEServer *pServer) override {
    deviceConnected = false;

    Serial.println("BLE_DISCONNECTED");
  }
};

// ============================================================
// RX CALLBACK
// ============================================================

class RxCallbacks : public BLECharacteristicCallbacks {

  void onWrite(BLECharacteristic *pCharacteristic) override {

    std::string value = pCharacteristic->getValue();

    if (value.length() < 4) {
      return;
    }

    // --------------------------------------------------------
    // Extract sequence number from first 4 bytes
    // --------------------------------------------------------

    uint32_t sequenceNumber = 0;

    memcpy(
      &sequenceNumber,
      value.data(),
      sizeof(sequenceNumber)
    );

    uint32_t rxTimestamp = micros();

    // --------------------------------------------------------
    // Serial output
    // --------------------------------------------------------

    Serial.print("RX,");
    Serial.print(sequenceNumber);
    Serial.print(",");
    Serial.print(value.length());
    Serial.print(",");
    Serial.println(rxTimestamp);

    // --------------------------------------------------------
    // ACK
    // --------------------------------------------------------

    uint8_t ackPacket[4];

    memcpy(
      ackPacket,
      &sequenceNumber,
      sizeof(sequenceNumber)
    );

    pTxCharacteristic->setValue(
      ackPacket,
      sizeof(ackPacket)
    );

    pTxCharacteristic->notify();
  }
};

// ============================================================
// SETUP
// ============================================================

void setup() {

  Serial.begin(115200);

  delay(1000);

  Serial.println();
  Serial.println("====================================");
  Serial.println("NEXORA BLE RECEIVER");
  Serial.println("====================================");

  // ----------------------------------------------------------
  // Initialize BLE
  // ----------------------------------------------------------

  BLEDevice::init(DEVICE_NAME);

  // ----------------------------------------------------------
  // Create BLE server
  // ----------------------------------------------------------

  pServer = BLEDevice::createServer();

  pServer->setCallbacks(
    new ServerCallbacks()
  );

  // ----------------------------------------------------------
  // Create service
  // ----------------------------------------------------------

  BLEService *pService =
      pServer->createService(SERVICE_UUID);

  // ----------------------------------------------------------
  // RX characteristic
  //
  // Sender -> Receiver
  // ----------------------------------------------------------

  BLECharacteristic *pRxCharacteristic =
      pService->createCharacteristic(
        RX_CHARACTERISTIC,
        BLECharacteristic::PROPERTY_WRITE |
        BLECharacteristic::PROPERTY_WRITE_NR
      );

  pRxCharacteristic->setCallbacks(
    new RxCallbacks()
  );

  // ----------------------------------------------------------
  // TX characteristic
  //
  // Receiver -> Sender ACK
  // ----------------------------------------------------------

  pTxCharacteristic =
      pService->createCharacteristic(
        TX_CHARACTERISTIC,
        BLECharacteristic::PROPERTY_NOTIFY
      );

  pTxCharacteristic->addDescriptor(
    new BLE2902()
  );

  // ----------------------------------------------------------
  // Start service
  // ----------------------------------------------------------

  pService->start();

  // ----------------------------------------------------------
  // Start advertising
  // ----------------------------------------------------------

  BLEAdvertising *pAdvertising =
      BLEDevice::getAdvertising();

  pAdvertising->addServiceUUID(
    SERVICE_UUID
  );

  pAdvertising->setScanResponse(true);

  BLEDevice::startAdvertising();

  Serial.println("BLE_READY");
  Serial.println("Waiting for sender...");
}

// ============================================================
// LOOP
// ============================================================

void loop() {

  // ----------------------------------------------------------
  // Restart advertising after disconnect
  // ----------------------------------------------------------

  if (!deviceConnected && oldDeviceConnected) {

    delay(500);

    pServer->startAdvertising();

    Serial.println("BLE_ADVERTISING");

    oldDeviceConnected =
        deviceConnected;
  }

  if (deviceConnected && !oldDeviceConnected) {

    oldDeviceConnected =
        deviceConnected;
  }

  delay(10);
}
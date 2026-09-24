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
// PACKET STATISTICS
// ============================================================

uint32_t totalPackets = 0;
uint32_t lastSequenceNumber = 0;
uint32_t lostPackets = 0;
uint32_t duplicatePackets = 0;

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

  void onWrite(
    BLECharacteristic *pCharacteristic
  ) override {

    // --------------------------------------------------------
    // IMPORTANT:
    //
    // ESP32 BLE library version being used returns Arduino
    // String from getValue().
    // --------------------------------------------------------

    String value =
        pCharacteristic->getValue();

    // --------------------------------------------------------
    // Validate packet
    //
    // First 4 bytes contain uint32_t sequence number.
    // --------------------------------------------------------

    if (value.length() < sizeof(uint32_t)) {

      Serial.print("RX_INVALID,");
      Serial.println(value.length());

      return;
    }

    // --------------------------------------------------------
    // Extract sequence number
    // --------------------------------------------------------

    uint32_t sequenceNumber = 0;

    memcpy(
      &sequenceNumber,
      value.c_str(),
      sizeof(sequenceNumber)
    );

    // --------------------------------------------------------
    // Timestamp
    // --------------------------------------------------------

    uint32_t rxTimestamp =
        micros();

    // --------------------------------------------------------
    // Packet statistics
    // --------------------------------------------------------

    totalPackets++;

    if (totalPackets > 1) {

      // ------------------------------------------------------
      // New packet after the previous packet
      // ------------------------------------------------------

      if (sequenceNumber > lastSequenceNumber + 1) {

        lostPackets +=
            sequenceNumber -
            lastSequenceNumber -
            1;
      }

      // ------------------------------------------------------
      // Duplicate or old packet
      // ------------------------------------------------------

      else if (sequenceNumber <= lastSequenceNumber) {

        duplicatePackets++;
      }
    }

    if (sequenceNumber > lastSequenceNumber) {

      lastSequenceNumber =
          sequenceNumber;
    }

    // --------------------------------------------------------
    // Print received packet information
    // --------------------------------------------------------

    Serial.print("RX,");
    Serial.print(sequenceNumber);
    Serial.print(",");
    Serial.print(value.length());
    Serial.print(",");
    Serial.print(rxTimestamp);
    Serial.print(",");
    Serial.print(totalPackets);
    Serial.print(",");
    Serial.print(lostPackets);
    Serial.print(",");
    Serial.println(duplicatePackets);

    // --------------------------------------------------------
    // Send ACK
    //
    // ACK contains the same 4-byte sequence number.
    // --------------------------------------------------------

    if (
      pTxCharacteristic != nullptr &&
      deviceConnected
    ) {

      uint8_t ackPacket[sizeof(uint32_t)];

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
  Serial.println("      NEXORA BLE RECEIVER");
  Serial.println("====================================");

  // ----------------------------------------------------------
  // Initialize BLE
  // ----------------------------------------------------------

  BLEDevice::init(
    DEVICE_NAME
  );

  // ----------------------------------------------------------
  // Create BLE server
  // ----------------------------------------------------------

  pServer =
      BLEDevice::createServer();

  pServer->setCallbacks(
    new ServerCallbacks()
  );

  // ----------------------------------------------------------
  // Create BLE service
  // ----------------------------------------------------------

  BLEService *pService =
      pServer->createService(
        SERVICE_UUID
      );

  // ==========================================================
  // RX CHARACTERISTIC
  //
  // Sender -> Receiver
  // ==========================================================

  BLECharacteristic *pRxCharacteristic =
      pService->createCharacteristic(
        RX_CHARACTERISTIC,
        BLECharacteristic::PROPERTY_WRITE |
        BLECharacteristic::PROPERTY_WRITE_NR
      );

  pRxCharacteristic->setCallbacks(
    new RxCallbacks()
  );

  // ==========================================================
  // TX CHARACTERISTIC
  //
  // Receiver -> Sender
  // Used for ACK notifications
  // ==========================================================

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
  // Configure advertising
  // ----------------------------------------------------------

  BLEAdvertising *pAdvertising =
      BLEDevice::getAdvertising();

  pAdvertising->addServiceUUID(
    SERVICE_UUID
  );

  pAdvertising->setScanResponse(
    true
  );

  pAdvertising->setMinPreferred(
    0x06
  );

  pAdvertising->setMinPreferred(
    0x12
  );

  // ----------------------------------------------------------
  // Start advertising
  // ----------------------------------------------------------

  BLEDevice::startAdvertising();

  Serial.println("BLE_READY");
  Serial.println("BLE_ADVERTISING");
  Serial.println("Waiting for sender...");
}

// ============================================================
// LOOP
// ============================================================

void loop() {

  // ----------------------------------------------------------
  // Detect disconnection
  // ----------------------------------------------------------

  if (
    !deviceConnected &&
    oldDeviceConnected
  ) {

    delay(500);

    pServer->startAdvertising();

    Serial.println("BLE_ADVERTISING");

    oldDeviceConnected =
        deviceConnected;
  }

  // ----------------------------------------------------------
  // Detect new connection
  // ----------------------------------------------------------

  if (
    deviceConnected &&
    !oldDeviceConnected
  ) {

    oldDeviceConnected =
        deviceConnected;
  }

  delay(10);
}
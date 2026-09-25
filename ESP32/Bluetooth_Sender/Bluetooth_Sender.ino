#include <Arduino.h>
#include <BluetoothSerial.h>
#include <math.h>

// ============================================================
// Classic Bluetooth configuration
// ============================================================

const char* RECEIVER_BT_NAME = "ESP32_BT_RECEIVER";
const char* SENDER_BT_NAME   = "ESP32_BT_SENDER";


// ============================================================
// ACK configuration
// ============================================================

const uint32_t ACK_TIMEOUT_MS = 1000;


// ============================================================
// Experiment configuration
// ============================================================

const size_t MAX_PAYLOAD_SIZE = 2048;

uint16_t payloadSize = 16;

uint32_t sendIntervalMs = 100;


// ============================================================
// ACS712 configuration
// ============================================================

const int ACS712_PIN = 34;


// ACS712 5A sensitivity
const float ACS712_SENSITIVITY_MV_PER_A = 185.0;


// IMPORTANT:
//
// Calibrate this using the actual zero-current ADC value.
// 2500 mV is only the nominal starting value.
//
const float ACS712_ZERO_MV = 2500.0;


// Dataset/load voltage
const float LOAD_VOLTAGE_V = 3.3;


// Current measurement rate
const uint32_t CURRENT_SAMPLE_INTERVAL_MS = 5;


// Ignore tiny readings caused by ADC/sensor noise
const float CURRENT_NOISE_FLOOR_MA = 8.0;


// ============================================================
// Global objects
// ============================================================

BluetoothSerial SerialBT;

uint32_t packetId = 0;

uint8_t payload[MAX_PAYLOAD_SIZE];


// ============================================================
// Bluetooth packet structures
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
// Power measurement state
// ============================================================

double currentSumMa = 0.0;

uint32_t currentSampleCount = 0;

double cycleEnergyMj = 0.0;

uint32_t lastCurrentSampleMs = 0;


// ============================================================
// Read ACS712
// ============================================================

float readCurrentMa() {

  uint32_t sensorMv =
    analogReadMilliVolts(
      ACS712_PIN
    );


  float differenceMv =
    static_cast<float>(
      sensorMv
    )
    - ACS712_ZERO_MV;


  float currentA =
    fabs(
      differenceMv
    )
    /
    ACS712_SENSITIVITY_MV_PER_A;


  float currentMa =
    currentA * 1000.0;


  if (
    currentMa
    < CURRENT_NOISE_FLOOR_MA
  ) {

    currentMa = 0.0;
  }


  return currentMa;
}


// ============================================================
// Reset power window
// ============================================================

void resetPowerMeasurement() {

  currentSumMa = 0.0;

  currentSampleCount = 0;

  cycleEnergyMj = 0.0;

  lastCurrentSampleMs =
    millis();
}


// ============================================================
// Sample current and integrate energy
// ============================================================

void samplePower(
    bool forceSample = false
) {

  uint32_t now =
    millis();


  uint32_t elapsedMs =
    now
    - lastCurrentSampleMs;


  if (
    !forceSample
    &&
    elapsedMs < CURRENT_SAMPLE_INTERVAL_MS
  ) {

    return;
  }


  float currentMa =
    readCurrentMa();


  currentSumMa +=
    currentMa;


  currentSampleCount++;


  // ----------------------------------------------------------
  // E(mJ) = V × I(A) × time(ms)
  // ----------------------------------------------------------

  cycleEnergyMj +=

    LOAD_VOLTAGE_V

    *

    (
      currentMa
      / 1000.0
    )

    *

    elapsedMs;


  lastCurrentSampleMs =
    now;
}


// ============================================================
// Average current
// ============================================================

float getAverageCurrentMa() {

  if (
    currentSampleCount == 0
  ) {

    return 0.0;
  }


  return static_cast<float>(

    currentSumMa

    / currentSampleCount
  );
}


// ============================================================
// Prepare payload
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
// Connect Bluetooth
// ============================================================

bool connectBluetooth() {

  if (
    SerialBT.connected()
  ) {

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

    Serial.println(
      "Bluetooth connected"
    );


    return true;
  }


  Serial.println(
    "Bluetooth connection failed"
  );


  return false;
}


// ============================================================
// Flush stale ACK bytes
// ============================================================

void flushBluetoothInput() {

  while (
    SerialBT.available()
  ) {

    SerialBT.read();
  }
}


// ============================================================
// Python CONFIG command
//
// CONFIG,<payload>,<interval>
//
// Example:
//
// CONFIG,16,100
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


  if (
    !command.startsWith(
      "CONFIG,"
    )
  ) {

    return;
  }


  int firstComma =
    command.indexOf(',');


  int secondComma =
    command.indexOf(
      ',',
      firstComma + 1
    );


  if (
    firstComma == -1
    ||
    secondComma == -1
  ) {

    Serial.println(
      "CONFIG_ERROR_FORMAT"
    );

    return;
  }


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


  if (
    newPayload <= 0
    ||
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
// Read exact Bluetooth bytes
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

    received < length

    &&

    millis() - startTime
      < timeoutMs

  ) {

    handleSerialConfig();


    samplePower();


    while (

      SerialBT.available()

      &&

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
// Packet telemetry
//
// NEW FORMAT:
//
// PKT,
// packet_id,
// payload_bytes,
// RSSI,
// RTT,
// success,
// retries,
// timestamp_ms,
// current_ma,
// energy_mj
//
// Example:
//
// PKT,42,16,-127,38.00,1,0,49381,80.931,26.707000
// ============================================================

void printPacketTelemetry(

    uint32_t packetId,

    uint16_t payloadBytes,

    int rssi,

    float rttMs,

    bool successful,

    uint16_t retries,

    uint32_t timestampMs,

    float currentMa,

    double energyMj

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


  Serial.print(
    timestampMs
  );

  Serial.print(",");


  Serial.print(
    currentMa,
    3
  );

  Serial.print(",");


  Serial.println(
    energyMj,
    6
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
  // ACS712 ADC
  // ----------------------------------------------------------

  pinMode(
    ACS712_PIN,
    INPUT
  );


  analogReadResolution(
    12
  );


  analogSetPinAttenuation(
    ACS712_PIN,
    ADC_11db
  );


  Serial.println(
    "ACS712 monitoring enabled"
  );


  Serial.print(
    "ADC pin: GPIO"
  );

  Serial.println(
    ACS712_PIN
  );


  Serial.print(
    "ACS712 sensitivity: "
  );

  Serial.print(
    ACS712_SENSITIVITY_MV_PER_A
  );

  Serial.println(
    " mV/A"
  );


  Serial.print(
    "ACS712 zero point: "
  );

  Serial.print(
    ACS712_ZERO_MV
  );

  Serial.println(
    " mV"
  );


  Serial.print(
    "Dataset voltage: "
  );

  Serial.print(
    LOAD_VOLTAGE_V
  );

  Serial.println(
    " V"
  );


  // ----------------------------------------------------------
  // Default payload
  // ----------------------------------------------------------

  preparePayload(
    payloadSize
  );


  // ----------------------------------------------------------
  // Bluetooth master
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
    "Expected receiver: "
  );

  Serial.println(
    RECEIVER_BT_NAME
  );


  connectBluetooth();


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
    " ms start-to-start"
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

  handleSerialConfig();


  // ----------------------------------------------------------
  // Ensure Bluetooth connection
  // ----------------------------------------------------------

  if (
    !SerialBT.connected()
  ) {

    Serial.println(
      "Bluetooth disconnected. Reconnecting..."
    );


    if (
      !connectBluetooth()
    ) {

      delay(
        1000
      );

      return;
    }
  }


  // ==========================================================
  // FIXED-CADENCE PACKET WINDOW
  //
  // IMPORTANT:
  //
  // packetIntervalMs is measured from the START of this
  // transmission to the START of the next transmission.
  //
  // OLD:
  //
  // TX -> ACK -> wait 100 ms -> next TX
  //
  // NEW:
  //
  // TX -------------------------- next TX
  // |<--------- 100 ms --------->|
  //
  // ACK time is INSIDE this 100 ms period.
  // ==========================================================

  uint32_t cycleStartMs =
    millis();


  uint32_t cycleIntervalMs =
    sendIntervalMs;


  packetId++;


  resetPowerMeasurement();


  samplePower(
    true
  );


  // ----------------------------------------------------------
  // Build packet
  // ----------------------------------------------------------

  TestHeader header;


  header.packet_id =
    packetId;


  header.timestamp_ms =
    cycleStartMs;


  header.payload_size =
    payloadSize;


  flushBluetoothInput();


  uint32_t sendStartMs =
    millis();


  // ----------------------------------------------------------
  // Transmit header
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


  // ----------------------------------------------------------
  // Transmit payload
  // ----------------------------------------------------------

  size_t payloadWritten =
    SerialBT.write(
      payload,
      payloadSize
    );


  bool sendOk = (

    headerWritten
      == sizeof(
        TestHeader
      )

    &&

    payloadWritten
      == payloadSize
  );


  SerialBT.flush();


  samplePower();


  // ----------------------------------------------------------
  // Wait for ACK
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

    uint32_t timeoutStartMs =
      millis();


    while (

      millis()
        - timeoutStartMs

      < ACK_TIMEOUT_MS

    ) {

      handleSerialConfig();


      samplePower();


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
              - sendStartMs
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
  // Classic Bluetooth RSSI unavailable
  // ----------------------------------------------------------

  int rssi =
    -127;


  // ==========================================================
  // WAIT ONLY FOR REMAINING INTERVAL
  //
  // This is the critical timing correction.
  // ==========================================================

  while (

    millis() - cycleStartMs
      < cycleIntervalMs

  ) {

    handleSerialConfig();


    samplePower();


    if (
      !SerialBT.connected()
    ) {

      break;
    }


    delay(
      1
    );
  }


  // ----------------------------------------------------------
  // Final current/energy sample
  // ----------------------------------------------------------

  samplePower(
    true
  );


  float averageCurrentMa =
    getAverageCurrentMa();


  // ----------------------------------------------------------
  // Output complete cycle telemetry
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

    cycleStartMs,

    averageCurrentMa,

    cycleEnergyMj
  );
}
#include <SPI.h>
#include <LoRa.h>

// ============================================================
// LORA PIN CONFIGURATION - ARDUINO UNO
// ============================================================

#define LORA_SS    10
#define LORA_RST   9
#define LORA_DIO0  2

// Hardware SPI:
// SCK  -> D13
// MISO -> D12
// MOSI -> D11


// ============================================================
// ACS712 CONFIGURATION
// ============================================================

#define ACS712_PIN A1

// ACS712 5A version
#define ACS712_SENSITIVITY_V_PER_A 0.185

// Arduino UNO ADC
#define ADC_REFERENCE_VOLTAGE 5.0
#define ADC_MAX_VALUE 1023.0

// Voltage across measured load
#define LOAD_VOLTAGE_V 3.3

// Independent PWR sample interval
#define CURRENT_SAMPLE_INTERVAL_MS 20

// Number of ADC samples averaged per current reading
#define ACS_READ_SAMPLES 32

// Samples used for zero calibration
#define ACS_ZERO_CALIBRATION_SAMPLES 400

// Ignore very small currents caused by noise
#define CURRENT_NOISE_FLOOR_MA 15.0


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

#define MAX_PAYLOAD_SIZE 1024

uint16_t payloadSize = 16;

uint32_t packetIntervalMs = 500;

uint32_t packetId = 0;

uint32_t lastPacketTime = 0;

const uint32_t ACK_TIMEOUT_MS = 1500;


// ============================================================
// ACS712 / ENERGY VARIABLES
// ============================================================

float acsZeroVoltage = 0.0;

uint32_t lastCurrentSampleMs = 0;

float currentMa = 0.0;

float cumulativeEnergyMj = 0.0;

uint32_t currentSampleCount = 0;

double currentAccumulatorMa = 0.0;


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
// ADC -> VOLTAGE
// ============================================================

float adcRawToVoltage(
    float raw
) {

  return (
    raw
    *
    ADC_REFERENCE_VOLTAGE
    /
    ADC_MAX_VALUE
  );
}


// ============================================================
// CALIBRATE ACS712 ZERO CURRENT
//
// IMPORTANT:
// During this function, there must be NO current through
// ACS712 IP+ / IP-.
// ============================================================

void calibrateACS712Zero() {

  Serial.println(
    F("ACS_CALIBRATION_START")
  );

  Serial.println(
    F("ACS_CALIBRATION_NO_LOAD_REQUIRED")
  );

  // Give user/setup time to settle.
  delay(1000);

  uint32_t rawSum = 0;

  for (
    uint16_t i = 0;
    i < ACS_ZERO_CALIBRATION_SAMPLES;
    i++
  ) {

    rawSum +=
      analogRead(
        ACS712_PIN
      );

    delay(2);
  }

  float rawAverage =
    rawSum
    /
    (float) ACS_ZERO_CALIBRATION_SAMPLES;

  acsZeroVoltage =
    adcRawToVoltage(
      rawAverage
    );

  Serial.print(
    F("ACS_ZERO_RAW=")
  );

  Serial.println(
    rawAverage,
    3
  );

  Serial.print(
    F("ACS_ZERO_VOLTAGE=")
  );

  Serial.println(
    acsZeroVoltage,
    4
  );

  Serial.println(
    F("ACS_CALIBRATION_DONE")
  );
}


// ============================================================
// READ ACS712 CURRENT
// ============================================================

float readCurrentMa() {

  uint32_t rawSum = 0;

  for (
    uint8_t i = 0;
    i < ACS_READ_SAMPLES;
    i++
  ) {

    rawSum +=
      analogRead(
        ACS712_PIN
      );
  }

  float rawAverage =
    rawSum
    /
    (float) ACS_READ_SAMPLES;

  float sensorVoltage =
    adcRawToVoltage(
      rawAverage
    );

  // ----------------------------------------------------------
  // Current direction:
  //
  // This version assumes current causes ACS712 output voltage
  // to INCREASE relative to zero.
  //
  // If your voltage falls under load, reverse:
  //
  // sensorVoltage - acsZeroVoltage
  //
  // to:
  //
  // acsZeroVoltage - sensorVoltage
  // ----------------------------------------------------------

  float currentA =
    (
      sensorVoltage
      -
      acsZeroVoltage
    )
    /
    ACS712_SENSITIVITY_V_PER_A;

  float measuredCurrentMa =
    currentA
    *
    1000.0;

  // ----------------------------------------------------------
  // Clamp negative values.
  // ----------------------------------------------------------

  if (
    measuredCurrentMa < 0
  ) {

    measuredCurrentMa = 0.0;
  }

  // ----------------------------------------------------------
  // Remove tiny residual noise.
  // ----------------------------------------------------------

  if (
    measuredCurrentMa
    <
    CURRENT_NOISE_FLOOR_MA
  ) {

    measuredCurrentMa = 0.0;
  }

  return measuredCurrentMa;
}


// ============================================================
// CONTINUOUS ENERGY MEASUREMENT
// ============================================================

void updateEnergyMeasurement() {

  uint32_t now =
    millis();

  if (
    now
    -
    lastCurrentSampleMs
    <
    CURRENT_SAMPLE_INTERVAL_MS
  ) {

    return;
  }

  uint32_t deltaMs =
    now
    -
    lastCurrentSampleMs;

  lastCurrentSampleMs =
    now;

  currentMa =
    readCurrentMa();

  currentAccumulatorMa +=
    currentMa;

  currentSampleCount++;

  // ----------------------------------------------------------
  // E(mJ) = V × I(mA) × t(s)
  // ----------------------------------------------------------

  cumulativeEnergyMj +=
    LOAD_VOLTAGE_V
    *
    currentMa
    *
    (
      deltaMs
      /
      1000.0
    );

  // ----------------------------------------------------------
  // Independent power telemetry for Python
  //
  // PWR,timestamp_ms,current_ma
  // ----------------------------------------------------------

  Serial.print(
    F("PWR,")
  );

  Serial.print(
    now
  );

  Serial.print(',');

  Serial.println(
    currentMa,
    3
  );
}


// ============================================================
// GET AVERAGE CURRENT
// ============================================================

float getAverageCurrentMa() {

  if (
    currentSampleCount == 0
  ) {

    return 0.0;
  }

  return (
    currentAccumulatorMa
    /
    currentSampleCount
  );
}


// ============================================================
// RESET ENERGY MEASUREMENTS
// ============================================================

void resetEnergyMeasurement() {

  cumulativeEnergyMj =
    0.0;

  currentAccumulatorMa =
    0.0;

  currentSampleCount =
    0;

  currentMa =
    0.0;

  lastCurrentSampleMs =
    millis();

  Serial.println(
    F("ENERGY_RESET_OK")
  );
}


// ============================================================
// GENERATE PAYLOAD
// ============================================================

void generatePayload(
    uint16_t size
) {

  for (
    uint16_t i = 0;
    i < size;
    i++
  ) {

    payload[i] =
      'A'
      +
      (
        i % 26
      );
  }
}


// ============================================================
// SEND PACKET
// ============================================================

void sendPacket() {

  packetId++;

  generatePayload(
    payloadSize
  );

  DataHeader header;

  header.packet_id =
    packetId;

  header.timestamp_ms =
    millis();

  header.payload_size =
    payloadSize;


  uint32_t startUs =
    micros();


  LoRa.beginPacket();

  LoRa.write(
    (uint8_t *)&header,
    sizeof(header)
  );

  LoRa.write(
    payload,
    payloadSize
  );

  int txStatus =
    LoRa.endPacket();


  bool ackReceived =
    false;

  int ackRssi =
    0;

  float ackSnr =
    0.0;

  float rttMs =
    -1.0;


  if (
    txStatus != 0
  ) {

    uint32_t waitStart =
      millis();

    while (
      millis()
      -
      waitStart
      <
      ACK_TIMEOUT_MS
    ) {

      updateEnergyMeasurement();

      int packetSize =
        LoRa.parsePacket();

      if (
        packetSize
        !=
        sizeof(AckPacket)
      ) {

        continue;
      }

      AckPacket ack;

      uint8_t *ptr =
        (uint8_t *)&ack;

      bool packetComplete =
        true;

      for (
        uint8_t i = 0;
        i < sizeof(AckPacket);
        i++
      ) {

        if (
          !LoRa.available()
        ) {

          packetComplete =
            false;

          break;
        }

        ptr[i] =
          LoRa.read();
      }

      if (
        !packetComplete
      ) {

        continue;
      }

      if (
        ack.packet_id
        ==
        packetId
        &&
        ack.success
        ==
        1
      ) {

        uint32_t endUs =
          micros();

        rttMs =
          (
            endUs
            -
            startUs
          )
          /
          1000.0;

        ackRssi =
          LoRa.packetRssi();

        ackSnr =
          LoRa.packetSnr();

        ackReceived =
          true;

        break;
      }
    }
  }


  updateEnergyMeasurement();


  float averageCurrentMa =
    getAverageCurrentMa();


  // ==========================================================
  // SERIAL FORMAT
  //
  // PKT,
  // packet_id,
  // payload_size,
  // rssi,
  // snr,
  // rtt_ms,
  // success,
  // average_current_ma,
  // voltage_v,
  // cumulative_energy_mj,
  // timestamp_ms
  // ==========================================================

  Serial.print(
    F("PKT,")
  );

  Serial.print(
    packetId
  );

  Serial.print(',');

  Serial.print(
    payloadSize
  );

  Serial.print(',');


  if (
    ackReceived
  ) {

    Serial.print(
      ackRssi
    );

    Serial.print(',');

    Serial.print(
      ackSnr,
      2
    );

    Serial.print(',');

    Serial.print(
      rttMs,
      2
    );

    Serial.print(',');

    Serial.print(
      1
    );
  }

  else {

    Serial.print(
      F("0,")
    );

    Serial.print(
      F("0.00,")
    );

    Serial.print(
      F("-1.00,")
    );

    Serial.print(
      0
    );
  }


  Serial.print(',');

  Serial.print(
    averageCurrentMa,
    3
  );

  Serial.print(',');

  Serial.print(
    LOAD_VOLTAGE_V,
    2
  );

  Serial.print(',');

  Serial.print(
    cumulativeEnergyMj,
    3
  );

  Serial.print(',');

  Serial.println(
    millis()
  );
}


// ============================================================
// PRINT CONFIGURATION
// ============================================================

void printConfig() {

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
// SERIAL COMMAND HANDLER
// ============================================================

void handleSerialCommand() {

  if (
    !Serial.available()
  ) {

    return;
  }


  char buffer[40];

  uint8_t index = 0;


  while (
    Serial.available()
    &&
    index
    <
    sizeof(buffer) - 1
  ) {

    char c =
      Serial.read();

    if (
      c == '\n'
    ) {

      break;
    }

    if (
      c != '\r'
    ) {

      buffer[index++] =
        c;
    }
  }


  buffer[index] =
    '\0';


  // ----------------------------------------------------------
  // SIZE,<bytes>
  // ----------------------------------------------------------

  if (
    strncmp(
      buffer,
      "SIZE,",
      5
    )
    ==
    0
  ) {

    int newSize =
      atoi(
        buffer + 5
      );

    if (
      newSize > 0
      &&
      newSize
      <=
      MAX_PAYLOAD_SIZE
    ) {

      payloadSize =
        newSize;

      printConfig();
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
    )
    ==
    0
  ) {

    unsigned long newInterval =
      atol(
        buffer + 9
      );

    if (
      newInterval >= 100
    ) {

      packetIntervalMs =
        newInterval;

      printConfig();
    }

    return;
  }


  // ----------------------------------------------------------
  // ENERGY_RESET
  // ----------------------------------------------------------

  if (
    strcmp(
      buffer,
      "ENERGY_RESET"
    )
    ==
    0
  ) {

    resetEnergyMeasurement();

    return;
  }


  // ----------------------------------------------------------
  // CONFIG
  // ----------------------------------------------------------

  if (
    strcmp(
      buffer,
      "CONFIG"
    )
    ==
    0
  ) {

    printConfig();

    return;
  }
}


// ============================================================
// SETUP
// ============================================================

void setup() {

  Serial.begin(
    115200
  );

  pinMode(
    ACS712_PIN,
    INPUT
  );

  delay(
    500
  );


  Serial.println(
    F("LORA_SENDER_START")
  );


  // ==========================================================
  // IMPORTANT:
  //
  // ACS712 must have NO current through IP+/IP-
  // during this calibration.
  // ==========================================================

  calibrateACS712Zero();


  // ----------------------------------------------------------
  // LoRa pin configuration
  // ----------------------------------------------------------

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
      F("LORA_INIT_FAIL")
    );

    while (
      true
    ) {

      delay(
        1000
      );
    }
  }


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


  printConfig();


  resetEnergyMeasurement();
}


// ============================================================
// LOOP
// ============================================================

void loop() {

  updateEnergyMeasurement();

  handleSerialCommand();


  if (
    millis()
    -
    lastPacketTime
    >=
    packetIntervalMs
  ) {

    lastPacketTime =
      millis();

    sendPacket();
  }
}
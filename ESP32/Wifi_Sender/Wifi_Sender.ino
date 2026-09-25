#include <WiFi.h>
#include <WiFiUdp.h>

// ============================================================
// Wi-Fi configuration
// ============================================================
const char* WIFI_SSID = "IoT Lab";
const char* WIFI_PASSWORD = "iot108lab";

// Receiver ESP32 IP
IPAddress RECEIVER_IP(192, 168, 12, 93);
const uint16_t RECEIVER_PORT = 5005;
const uint16_t LOCAL_PORT = 5006;

// ============================================================
// Network / ACK configuration
// ============================================================
const uint32_t ACK_TIMEOUT_MS = 1000;
const size_t MAX_PENDING = 32;

// ============================================================
// ACS712 CURRENT SENSOR CONFIGURATION
// ============================================================
const int ACS712_PIN = 34;                  // ADC1, safe with Wi-Fi
const float ACS_SENSITIVITY_MV_PER_A = 185.0f; // ACS712 5A variant
const float ACS_ZERO_MV = 2500.0f;          // Calibrate this for your module
const uint16_t ACS_SAMPLES = 16;
const uint32_t POWER_SAMPLE_INTERVAL_MS = 20;
const float LOAD_VOLTAGE_V = 3.3f;

// ============================================================
// Runtime experiment configuration
// Python sends: CONFIG,<payload_bytes>,<packet_interval_ms>
// ============================================================
const size_t MAX_PAYLOAD_SIZE = 2048;
uint16_t payloadSize = 16;
uint32_t sendIntervalMs = 1000;

// ============================================================
// Global objects
// ============================================================
WiFiUDP udp;
uint32_t packetId = 0;
uint8_t payload[MAX_PAYLOAD_SIZE];

uint32_t nextSendAtMs = 0;
uint32_t nextPowerSampleAtMs = 0;

// ============================================================
// Packet structures
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

struct PendingPacket {
  bool active;
  uint32_t packet_id;
  uint32_t send_time_ms;
  uint16_t payload_bytes;
  int rssi_dbm;
};

PendingPacket pending[MAX_PENDING];

// ============================================================
// Helpers
// ============================================================
bool timeReached(uint32_t now, uint32_t target) {
  return static_cast<int32_t>(now - target) >= 0;
}

void connectWiFi() {
  Serial.print("Connecting to Wi-Fi");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("Wi-Fi connected");
  Serial.print("Sender IP: ");
  Serial.println(WiFi.localIP());
  Serial.print("RSSI: ");
  Serial.print(WiFi.RSSI());
  Serial.println(" dBm");
  Serial.print("Wi-Fi channel: ");
  Serial.println(WiFi.channel());
}

void preparePayload(uint16_t size) {
  if (size > MAX_PAYLOAD_SIZE) {
    size = MAX_PAYLOAD_SIZE;
  }

  for (uint16_t i = 0; i < size; i++) {
    payload[i] = static_cast<uint8_t>(i & 0xFF);
  }
}

float readCurrentMa() {
  uint32_t totalMv = 0;

  for (uint16_t i = 0; i < ACS_SAMPLES; i++) {
    totalMv += analogReadMilliVolts(ACS712_PIN);
    delayMicroseconds(100);
  }

  float averageMv = static_cast<float>(totalMv) / ACS_SAMPLES;
  float currentA = fabsf(averageMv - ACS_ZERO_MV) / ACS_SENSITIVITY_MV_PER_A;
  return currentA * 1000.0f;
}

void printPowerSample(uint32_t timestampMs, float currentMa) {
  // PWR,timestamp_ms,current_ma
  Serial.print("PWR,");
  Serial.print(timestampMs);
  Serial.print(",");
  Serial.println(currentMa, 2);
}

void printPacketTelemetry(
    uint32_t id,
    uint16_t payloadBytes,
    int rssi,
    float rttMs,
    bool successful,
    uint16_t retries,
    uint32_t timestampMs
) {
  // PKT,id,payload,rssi,rtt,success,retries,timestamp
  Serial.print("PKT,");
  Serial.print(id);
  Serial.print(",");
  Serial.print(payloadBytes);
  Serial.print(",");
  Serial.print(rssi);
  Serial.print(",");
  Serial.print(rttMs, 2);
  Serial.print(",");
  Serial.print(successful ? 1 : 0);
  Serial.print(",");
  Serial.print(retries);
  Serial.print(",");
  Serial.println(timestampMs);
}

void handleSerialConfig() {
  if (!Serial.available()) {
    return;
  }

  String command = Serial.readStringUntil('\n');
  command.trim();

  if (!command.startsWith("CONFIG,")) {
    return;
  }

  int firstComma = command.indexOf(',');
  int secondComma = command.indexOf(',', firstComma + 1);

  if (firstComma == -1 || secondComma == -1) {
    Serial.println("CONFIG_ERROR_FORMAT");
    return;
  }

  long newPayload = command.substring(firstComma + 1, secondComma).toInt();
  long newInterval = command.substring(secondComma + 1).toInt();

  if (newPayload <= 0 || newPayload > MAX_PAYLOAD_SIZE) {
    Serial.print("CONFIG_ERROR_PAYLOAD,");
    Serial.println(newPayload);
    return;
  }

  if (newInterval <= 0) {
    Serial.print("CONFIG_ERROR_INTERVAL,");
    Serial.println(newInterval);
    return;
  }

  payloadSize = static_cast<uint16_t>(newPayload);
  sendIntervalMs = static_cast<uint32_t>(newInterval);
  preparePayload(payloadSize);

  // Restart cadence from the new configuration time.
  nextSendAtMs = millis();

  Serial.print("CONFIG_OK,");
  Serial.print(payloadSize);
  Serial.print(",");
  Serial.print(sendIntervalMs);
  Serial.print(",");
  Serial.println(WiFi.channel());
}

int findFreePendingSlot() {
  for (size_t i = 0; i < MAX_PENDING; i++) {
    if (!pending[i].active) {
      return static_cast<int>(i);
    }
  }
  return -1;
}

int findPendingById(uint32_t id) {
  for (size_t i = 0; i < MAX_PENDING; i++) {
    if (pending[i].active && pending[i].packet_id == id) {
      return static_cast<int>(i);
    }
  }
  return -1;
}

void processIncomingAcks() {
  while (true) {
    int incomingSize = udp.parsePacket();
    if (incomingSize <= 0) {
      break;
    }

    if (incomingSize >= static_cast<int>(sizeof(AckPacket))) {
      AckPacket ack;
      int bytesRead = udp.read(reinterpret_cast<uint8_t*>(&ack), sizeof(AckPacket));

      if (bytesRead == sizeof(AckPacket)) {
        int slot = findPendingById(ack.packet_id);

        if (slot >= 0) {
          uint32_t now = millis();
          float rttMs = static_cast<float>(now - pending[slot].send_time_ms);
          bool ok = ack.success == 1;

          printPacketTelemetry(
            pending[slot].packet_id,
            pending[slot].payload_bytes,
            pending[slot].rssi_dbm,
            ok ? rttMs : -1.0f,
            ok,
            0,
            now
          );

          pending[slot].active = false;
        }
      }
    }

    while (udp.available() > 0) {
      udp.read();
    }
  }
}

void processAckTimeouts() {
  uint32_t now = millis();

  for (size_t i = 0; i < MAX_PENDING; i++) {
    if (!pending[i].active) {
      continue;
    }

    if (now - pending[i].send_time_ms >= ACK_TIMEOUT_MS) {
      printPacketTelemetry(
        pending[i].packet_id,
        pending[i].payload_bytes,
        pending[i].rssi_dbm,
        -1.0f,
        false,
        0,
        now
      );

      pending[i].active = false;
    }
  }
}

void sendScheduledPacket() {
  int slot = findFreePendingSlot();

  if (slot < 0) {
    Serial.println("WARN_PENDING_QUEUE_FULL");
    return;
  }

  packetId++;

  TestHeader header;
  header.packet_id = packetId;
  header.timestamp_ms = millis();
  header.payload_size = payloadSize;

  uint32_t sendStart = millis();
  int rssi = WiFi.RSSI();

  bool packetStarted = udp.beginPacket(RECEIVER_IP, RECEIVER_PORT);
  bool sendOk = false;

  if (packetStarted) {
    size_t headerWritten = udp.write(
      reinterpret_cast<const uint8_t*>(&header),
      sizeof(TestHeader)
    );

    size_t payloadWritten = udp.write(payload, payloadSize);

    if (headerWritten == sizeof(TestHeader) && payloadWritten == payloadSize) {
      sendOk = udp.endPacket();
    } else {
      udp.endPacket();
    }
  }

  if (sendOk) {
    pending[slot].active = true;
    pending[slot].packet_id = packetId;
    pending[slot].send_time_ms = sendStart;
    pending[slot].payload_bytes = payloadSize;
    pending[slot].rssi_dbm = rssi;
  } else {
    printPacketTelemetry(
      packetId,
      payloadSize,
      rssi,
      -1.0f,
      false,
      0,
      millis()
    );
  }
}

// ============================================================
// Setup
// ============================================================
void setup() {
  Serial.begin(115200);
  Serial.setTimeout(50);

  analogReadResolution(12);
  analogSetPinAttenuation(ACS712_PIN, ADC_11db);

  delay(1000);

  Serial.println();
  Serial.println("======================================");
  Serial.println("Adaptive IoT Wi-Fi Sender");
  Serial.println("NON-BLOCKING FIXED-CADENCE VERSION");
  Serial.println("======================================");

  preparePayload(payloadSize);
  connectWiFi();

  if (udp.begin(LOCAL_PORT)) {
    Serial.print("Listening for ACK on UDP port: ");
    Serial.println(LOCAL_PORT);
  } else {
    Serial.println("ERROR: UDP start failed");
  }

  for (size_t i = 0; i < MAX_PENDING; i++) {
    pending[i].active = false;
  }

  nextSendAtMs = millis();
  nextPowerSampleAtMs = millis();

  Serial.print("ACS712 ADC pin: GPIO");
  Serial.println(ACS712_PIN);
  Serial.print("ACS712 zero-current voltage: ");
  Serial.print(ACS_ZERO_MV, 1);
  Serial.println(" mV");
  Serial.print("Power sample interval: ");
  Serial.print(POWER_SAMPLE_INTERVAL_MS);
  Serial.println(" ms");
  Serial.print("Load voltage: ");
  Serial.print(LOAD_VOLTAGE_V, 2);
  Serial.println(" V");
  Serial.println("Sender ready");
  Serial.println("Waiting for CONFIG command...");
}

// ============================================================
// Main loop
// ============================================================
void loop() {
  handleSerialConfig();

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi disconnected. Reconnecting...");
    connectWiFi();
    udp.stop();
    udp.begin(LOCAL_PORT);
  }

  // Never block waiting for an ACK.
  processIncomingAcks();
  processAckTimeouts();

  uint32_t now = millis();

  // Fixed packet cadence. A 100 ms interval means one send every 100 ms,
  // independent of RTT. This fixes the old RTT + interval behaviour.
  if (timeReached(now, nextSendAtMs)) {
    sendScheduledPacket();

    // Advance from the previous schedule instead of "now" so small loop
    // delays do not accumulate as timing drift.
    nextSendAtMs += sendIntervalMs;

    // If the MCU was stalled for a long time, do not burst many packets.
    if (timeReached(millis(), nextSendAtMs + sendIntervalMs)) {
      nextSendAtMs = millis() + sendIntervalMs;
    }
  }

  // Current is sampled independently of packet/ACK timing so Wi-Fi, BT and
  // BLE energy measurements are not biased by where the code happened to
  // take a sample.
  now = millis();
  if (timeReached(now, nextPowerSampleAtMs)) {
    float currentMa = readCurrentMa();
    printPowerSample(now, currentMa);
    nextPowerSampleAtMs += POWER_SAMPLE_INTERVAL_MS;

    if (timeReached(millis(), nextPowerSampleAtMs + POWER_SAMPLE_INTERVAL_MS)) {
      nextPowerSampleAtMs = millis() + POWER_SAMPLE_INTERVAL_MS;
    }
  }

  delay(1);
}

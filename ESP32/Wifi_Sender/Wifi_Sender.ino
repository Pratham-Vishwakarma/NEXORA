#include <WiFi.h>
#include <WiFiUdp.h>

// ============================================================
// Wi-Fi configuration
// ============================================================
const char* WIFI_SSID = "OneplusNord3";
const char* WIFI_PASSWORD = "Thisismyhotspotpasskey@125940";

// Receiver ESP32 IP
IPAddress RECEIVER_IP(10, 51, 202, 223);
const uint16_t RECEIVER_PORT = 5005;
const uint16_t LOCAL_PORT = 5006;

// ============================================================
// Network / ACK configuration
// ============================================================
const uint32_t ACK_TIMEOUT_MS = 1000;

// ============================================================
// Runtime experiment configuration
// Python sends:
// CONFIG,<payload_bytes>,<packet_interval_ms>
// Example:
// CONFIG,128,500
// ESP32 responds:
// CONFIG_OK,128,500,6
// where 6 is the current Wi-Fi channel.
// ============================================================
const size_t MAX_PAYLOAD_SIZE = 2048;

// Default values used until Python sends CONFIG
uint16_t payloadSize = 16;
uint32_t sendIntervalMs = 1000;

// ============================================================
// Global objects
// ============================================================
WiFiUDP udp;
uint32_t packetId = 0;

// Application payload buffer
uint8_t payload[MAX_PAYLOAD_SIZE];

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

// ============================================================
// Connect to Wi-Fi
// ============================================================
void connectWiFi() {
  Serial.print("Connecting to Wi-Fi");
  WiFi.mode(WIFI_STA);
  WiFi.begin(
    WIFI_SSID,
    WIFI_PASSWORD
  );
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

// ============================================================
// Prepare application payload
// ============================================================
void preparePayload(uint16_t size) {
  if (size > MAX_PAYLOAD_SIZE) {
    size = MAX_PAYLOAD_SIZE;
  }

  for (uint16_t i = 0;i < size;i++) {
    payload[i] = static_cast<uint8_t>(i & 0xFF);
  }
}

// ============================================================
// Handle configuration from Python
// Expected command:
// CONFIG,128,500
// Meaning:
// payload  = 128 bytes
// interval = 500 ms
// ============================================================
void handleSerialConfig() {
  if (!Serial.available()) {
    return;
  }

  String command = Serial.readStringUntil('\n');
  command.trim();

  // Ignore anything except CONFIG messages
  if (!command.startsWith("CONFIG,")) {
    return;
  }

  // ----------------------------------------------------------
  // Locate command separators
  // ----------------------------------------------------------
  int firstComma = command.indexOf(',');
  int secondComma = command.indexOf(',', firstComma + 1);
  if (firstComma == -1 || secondComma == -1) {
    Serial.println("CONFIG_ERROR_FORMAT");
    return;
  }

  // ----------------------------------------------------------
  // Extract parameters
  // ----------------------------------------------------------
  String payloadString = command.substring(firstComma + 1, secondComma);
  String intervalString = command.substring(secondComma + 1);
  long newPayload = payloadString.toInt();
  long newInterval = intervalString.toInt();

  // ----------------------------------------------------------
  // Validate payload
  // ----------------------------------------------------------
  if (newPayload <= 0 || newPayload > MAX_PAYLOAD_SIZE) {
    Serial.print("CONFIG_ERROR_PAYLOAD,");
    Serial.println(newPayload);
    return;
  }

  // ----------------------------------------------------------
  // Validate packet interval
  // ----------------------------------------------------------
  if (newInterval <= 0) {
    Serial.print("CONFIG_ERROR_INTERVAL,");
    Serial.println(newInterval);
    return;
  }

  // ----------------------------------------------------------
  // Apply new configuration
  // ----------------------------------------------------------
  payloadSize = static_cast<uint16_t>(newPayload);
  sendIntervalMs = static_cast<uint32_t>(newInterval);

  // Rebuild payload for new size
  preparePayload(payloadSize);

  // ----------------------------------------------------------
  // Confirm configuration back to Python
  //
  // Format:
  //
  // CONFIG_OK,
  // payload,
  // interval,
  // wifi_channel
  //
  // Example:
  //
  // CONFIG_OK,128,500,6
  // ----------------------------------------------------------
  Serial.print("CONFIG_OK,");
  Serial.print(payloadSize);
  Serial.print(",");
  Serial.print(sendIntervalMs);
  Serial.print(",");
  Serial.println(WiFi.channel());
}

// ============================================================
// Print packet telemetry
//
// Format:
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
// PKT,42,128,-63,6.00,1,0,49381
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
  Serial.print("PKT,");
  Serial.print(packetId);
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

// ============================================================
// Setup
// ============================================================
void setup() {
  Serial.begin(115200);
  // Reduce readStringUntil() blocking time
  Serial.setTimeout(100);
  delay(1000);
  Serial.println();
  Serial.println("======================================");
  Serial.println("Adaptive IoT Wi-Fi Sender");
  Serial.println("======================================");

  // ----------------------------------------------------------
  // Prepare default payload
  // ----------------------------------------------------------
  preparePayload(payloadSize);

  // ----------------------------------------------------------
  // Connect Wi-Fi
  // ----------------------------------------------------------
  connectWiFi();

  // ----------------------------------------------------------
  // Start UDP socket
  // ----------------------------------------------------------
  bool udpStarted = udp.begin(LOCAL_PORT);
  if (udpStarted) {
    Serial.print("Listening for ACK on UDP port: ");
    Serial.println(LOCAL_PORT);
  } else {
    Serial.println("ERROR: UDP start failed");
  }

  // ----------------------------------------------------------
  // Print initial configuration
  // ----------------------------------------------------------
  Serial.print("Default payload size: ");
  Serial.print(payloadSize);
  Serial.println(" bytes");
  Serial.print("Default packet interval: ");
  Serial.print(sendIntervalMs);
  Serial.println(" ms");
  Serial.print("Maximum payload size: ");
  Serial.print(MAX_PAYLOAD_SIZE);
  Serial.println(" bytes");
  Serial.println("Sender ready");
  Serial.println("Waiting for CONFIG command...");
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
  // Restore Wi-Fi if connection drops
  // ----------------------------------------------------------
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi disconnected. Reconnecting...");
    connectWiFi();
    udp.stop();
    udp.begin(LOCAL_PORT);
  }

  // ----------------------------------------------------------
  // New packet
  // ----------------------------------------------------------
  packetId++;

  // ----------------------------------------------------------
  // Construct packet header
  // ----------------------------------------------------------
  TestHeader header;
  header.packet_id = packetId;
  header.timestamp_ms = millis();
  header.payload_size = payloadSize;

  // ----------------------------------------------------------
  // RTT timer
  // ----------------------------------------------------------
  uint32_t sendStart = millis();

  // ----------------------------------------------------------
  // Send UDP datagram
  //
  // Datagram:
  //
  // [TestHeader]
  // [application payload]
  //
  // Header = 10 bytes
  //
  // Total UDP application data =
  // 10 + payloadSize
  // ----------------------------------------------------------
  bool packetStarted = udp.beginPacket(RECEIVER_IP, RECEIVER_PORT);
  bool sendOk = false;
  if (packetStarted) {
    size_t headerWritten = udp.write(reinterpret_cast<const uint8_t*>(&header), sizeof(TestHeader));
    size_t payloadWritten = udp.write(payload, payloadSize);
    if (headerWritten == sizeof(TestHeader) && payloadWritten == payloadSize) {
      sendOk = udp.endPacket();
    } else {
      udp.endPacket();
      sendOk = false;
    }
  }

  // ----------------------------------------------------------
  // Wait for receiver ACK
  // ----------------------------------------------------------
  bool ackReceived = false;
  float rttMs = -1.0;
  uint16_t retryCount = 0;
  if (sendOk) {
    uint32_t timeoutStart = millis();
    while (millis() - timeoutStart < ACK_TIMEOUT_MS) {
      // Allow Python configuration changes
      // even while waiting for an ACK.
      handleSerialConfig();
      int incomingSize = udp.parsePacket();
      if (incomingSize >= static_cast<int>(sizeof(AckPacket))) {
        AckPacket ack;
        int bytesRead = udp.read(reinterpret_cast<uint8_t*>(&ack), sizeof(AckPacket));
        if (bytesRead == sizeof(AckPacket) && ack.packet_id == packetId && ack.success == 1) {
          ackReceived = true;
          rttMs = static_cast<float>(millis() - sendStart);
          break;
        }
      }
      delay(1);
    }
  }

  // ----------------------------------------------------------
  // Get current Wi-Fi RSSI
  // ----------------------------------------------------------
  int rssi = WiFi.RSSI();

  // ----------------------------------------------------------
  // Output raw telemetry to Python
  // ----------------------------------------------------------
  printPacketTelemetry(
    packetId,
    payloadSize,
    rssi,
    ackReceived ? rttMs : -1.0,
    ackReceived,
    retryCount,
    millis()
  );

  // ----------------------------------------------------------
  // Wait for next transmission
  //
  // Do not use one large delay() because Python may send
  // another CONFIG message during this period.
  // ----------------------------------------------------------
  uint32_t waitStart = millis();
  while (millis() - waitStart < sendIntervalMs) {
    handleSerialConfig();
    delay(5);
  }
}
#include <WiFi.h>
#include <WiFiUdp.h>

// ============================================================
// WIFI CONFIGURATION
// ============================================================
const char* WIFI_SSID = "OneplusNord3";
const char* WIFI_PASSWORD = "Thisismyhotspotpasskey@125940";
const uint16_t LISTEN_PORT = 5005;

// ============================================================
// PAYLOAD CONFIGURATION
// ============================================================
const size_t MAX_PAYLOAD_SIZE = 2048;

// ============================================================
// GLOBAL OBJECTS
// ============================================================
WiFiUDP udp;
uint8_t payload[MAX_PAYLOAD_SIZE];

// ============================================================
// PACKET STRUCTURES
//
// Must exactly match wifi_sender.ino
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
// CONNECT TO WIFI
// ============================================================
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
    Serial.print("Receiver IP: ");
    Serial.println(WiFi.localIP());
    Serial.print("RSSI: ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm");
    Serial.print("Wi-Fi channel: ");
    Serial.println(WiFi.channel());
}

// ============================================================
// CLEAR REMAINING UDP DATA
// ============================================================
void clearUdpBuffer() {
    while (udp.available() > 0) {
        udp.read();
    }
}

// ============================================================
// SEND ACK
// ============================================================
void sendAck(
    IPAddress senderIP,
    uint16_t senderPort,
    uint32_t packetId,
    bool success
) {
    AckPacket ack;
    ack.packet_id = packetId;
    ack.receiver_timestamp_ms = millis();
    ack.success = success ? 1 : 0;
    bool packetStarted = udp.beginPacket(senderIP, senderPort);
    if (!packetStarted) {
        Serial.println("ERROR: Could not begin ACK packet");
        return;
    }

    size_t written = udp.write(reinterpret_cast<const uint8_t*>(&ack), sizeof(AckPacket));
    bool sent = udp.endPacket();
    Serial.print("ACK bytes written: ");
    Serial.println(written);
    Serial.print("ACK status: ");
    if (sent && written == sizeof(AckPacket)) {
        Serial.println("SENT");
    } else {
        Serial.println("FAILED");
    }
}

// ============================================================
// SETUP
// ============================================================
void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println();
    Serial.println("======================================");
    Serial.println("Adaptive IoT Wi-Fi Receiver");
    Serial.println("======================================");
    connectWiFi();
    bool udpStarted = udp.begin(LISTEN_PORT);
    if (udpStarted) {
        Serial.print("Listening on UDP port: ");
        Serial.println(LISTEN_PORT);
    } else {
        Serial.println("ERROR: UDP start failed");
    }

    Serial.print("Maximum payload size: ");
    Serial.print(MAX_PAYLOAD_SIZE);
    Serial.println(" bytes");
    Serial.println("Receiver ready");
}

// ============================================================
// MAIN LOOP
// ============================================================
void loop() {
    // --------------------------------------------------------
    // Reconnect Wi-Fi if needed
    // --------------------------------------------------------
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("Wi-Fi disconnected. Reconnecting...");
        connectWiFi();
        udp.stop();
        udp.begin(LISTEN_PORT);
    }

    // --------------------------------------------------------
    // Check for incoming UDP packet
    // --------------------------------------------------------
    int incomingPacketSize = udp.parsePacket();
    if (incomingPacketSize <= 0) {
        delay(1);
        return;
    }

    // --------------------------------------------------------
    // Save sender information BEFORE reading packet
    // --------------------------------------------------------
    IPAddress senderIP = udp.remoteIP();
    uint16_t senderPort = udp.remotePort();
    Serial.println();
    Serial.println("--------------------------------------");
    Serial.print("Incoming UDP datagram: ");
    Serial.print(incomingPacketSize);
    Serial.println(" bytes");
    Serial.print("From: ");
    Serial.print(senderIP);
    Serial.print(":");
    Serial.println(senderPort);

    // --------------------------------------------------------
    // Validate minimum packet size
    // --------------------------------------------------------
    if (incomingPacketSize < static_cast<int>(sizeof(TestHeader))) {
        Serial.println("ERROR: Datagram smaller than TestHeader");
        clearUdpBuffer();
        return;
    }

    // --------------------------------------------------------
    // Read packet header
    // --------------------------------------------------------
    TestHeader header;
    int headerBytesRead = udp.read(reinterpret_cast<uint8_t*>(&header), sizeof(TestHeader));
    if (headerBytesRead != sizeof(TestHeader)) {
        Serial.println("ERROR: Incomplete header");
        clearUdpBuffer();
        return;
    }

    // --------------------------------------------------------
    // Display header information
    // --------------------------------------------------------
    Serial.print("Packet ID: ");
    Serial.println(header.packet_id);
    Serial.print("Sender timestamp: ");
    Serial.println(header.timestamp_ms);
    Serial.print("Declared payload: ");
    Serial.print(header.payload_size);
    Serial.println(" bytes");

    // --------------------------------------------------------
    // Validate payload size
    // --------------------------------------------------------
    if (header.payload_size > MAX_PAYLOAD_SIZE) {
        Serial.println("ERROR: Payload exceeds MAX_PAYLOAD_SIZE");
        clearUdpBuffer();
        sendAck(
            senderIP,
            senderPort,
            header.packet_id,
            false
        );
        return;
    }

    // --------------------------------------------------------
    // Expected UDP datagram size
    //
    // TestHeader = 10 bytes
    //
    // Total =
    // 10 + application payload
    // --------------------------------------------------------
    size_t expectedDatagramSize = sizeof(TestHeader) + header.payload_size;
    Serial.print("Expected UDP size: ");
    Serial.print(expectedDatagramSize);
    Serial.println(" bytes");
    bool sizeValid = incomingPacketSize == static_cast<int>(expectedDatagramSize);
    if (!sizeValid) {
        Serial.println("WARNING: Datagram size mismatch");
    }

    // --------------------------------------------------------
    // Read application payload
    // --------------------------------------------------------
    int payloadBytesRead = 0;
    if (header.payload_size > 0) {
        payloadBytesRead = udp.read(payload, header.payload_size);
    }
    
    Serial.print("Payload bytes read: ");
    Serial.println(payloadBytesRead);

    // --------------------------------------------------------
    // Validate payload length
    // --------------------------------------------------------
    bool payloadValid = payloadBytesRead == header.payload_size;

    // --------------------------------------------------------
    // Validate payload contents
    //
    // Sender generates:
    //
    // payload[i] = i & 0xFF
    // --------------------------------------------------------
    bool payloadContentValid = true;
    if (payloadValid) {
        for (uint16_t i = 0; i < header.payload_size; i++) {
            uint8_t expected = static_cast<uint8_t>(i & 0xFF);
            if (payload[i] != expected) {
                payloadContentValid = false;
                Serial.print("Payload mismatch at byte ");
                Serial.println(i);
                break;
            }
        }
    } else {
        payloadContentValid = false;
    }

    // --------------------------------------------------------
    // Final packet validation
    // --------------------------------------------------------
    bool packetValid = sizeValid && payloadValid && payloadContentValid;
    Serial.print("Size validation: ");
    Serial.println(sizeValid ? "OK" : "FAILED");
    Serial.print("Payload length validation: ");
    Serial.println(payloadValid ? "OK" : "FAILED");
    Serial.print("Payload content validation: ");
    Serial.println(payloadContentValid ? "OK" : "FAILED");    
    Serial.print("Packet validation: ");
    Serial.println(packetValid ? "OK" : "FAILED");

    // --------------------------------------------------------
    // Receiver-side Wi-Fi metrics
    // --------------------------------------------------------
    Serial.print("Receiver RSSI: ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm");
    Serial.print("Wi-Fi channel: ");
    Serial.println(WiFi.channel());

    // --------------------------------------------------------
    // Send ACK back to sender's actual IP and port
    // --------------------------------------------------------
    Serial.print("Sending ACK to ");
    Serial.print(senderIP);
    Serial.print(":");
    Serial.println(senderPort);
    sendAck(
        senderIP,
        senderPort,
        header.packet_id,
        packetValid
    );

    // --------------------------------------------------------
    // Clear any unexpected remaining bytes
    // --------------------------------------------------------
    clearUdpBuffer();
    Serial.println("--------------------------------------");
}
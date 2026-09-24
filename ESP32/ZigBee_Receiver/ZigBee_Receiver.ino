#include <Arduino.h>

#define ZIGBEE_RX_PIN 16
#define ZIGBEE_TX_PIN 17
#define ZIGBEE_BAUD 9600

HardwareSerial ZigbeeSerial(2);

void setup() {

  Serial.begin(115200);

  ZigbeeSerial.begin(
      ZIGBEE_BAUD,
      SERIAL_8N1,
      ZIGBEE_RX_PIN,
      ZIGBEE_TX_PIN
  );

  delay(1000);

  Serial.println("ZIGBEE SIMPLE RECEIVER READY");
}

void loop() {

  while (ZigbeeSerial.available()) {

    char c = ZigbeeSerial.read();

    Serial.write(c);
  }
}
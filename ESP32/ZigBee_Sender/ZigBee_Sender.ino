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

  Serial.println("ZIGBEE SIMPLE SENDER READY");
}

void loop() {

  static uint32_t counter = 0;

  ZigbeeSerial.print("HELLO_ZIGBEE,");
  ZigbeeSerial.println(counter);

  Serial.print("SENT: HELLO_ZIGBEE,");
  Serial.println(counter);

  counter++;

  delay(1000);
}
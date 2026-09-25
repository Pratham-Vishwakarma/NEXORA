#define ACS712_PIN A1

void setup() {
  Serial.begin(115200);
}

void loop() {
  int raw = analogRead(ACS712_PIN);

  float voltage =
    raw * 5.0 / 1023.0;

  Serial.print("RAW=");
  Serial.print(raw);

  Serial.print(", VOLTAGE=");
  Serial.println(voltage, 4);

  delay(250);
}
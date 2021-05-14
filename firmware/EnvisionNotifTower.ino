/*
 | Envision Notification Towers
 | Georges Troulis  <gtroulis@ucsd.edu>
 |
 | This firmware runs on the ESP32 boards that drive the Notification Tower Lamps
 | in response to sign-in attempts from the EnVision Kiosk.
 |
 | Connects to EnVision-Local network with static IP address (determined by solder
 | jumpers), subscribes to the 'envision/sign_in' MQTT topic, and responds to messages
 | received from that topic (placed there by the Kiosk).
 |
 | Library Dependencies (needed to compile):
 |  - PubSubClient (MQTT Client):
 |
 | ------------------------------------------------------------
 | Revision Log (Updated 12/04/2019):
 | 0.4: Changed bug in static IP assignment giving incorrect range
 | 0.3: Changed Server IP from George's Laptop to EnVision Server
 | 0.2: Implemented MQTT, successfully actuates tower lamps to MQTT commands
 | 0.1: First pre-release rev, initializes all GPIOs and has basic
 |      test routine
 |
 | ------------------------------------------------------------
 | TODO list:
 |  [ ] Store WiFi credentials in hashed form
 |  [ ] Implement better failure mechanisms for WiFi failures
*/

// The firmware revision
#define FIRMWARE_REV  F("0.4")

// WiFi and MQTT libraries for ESP32
#include <WiFi.h>
#include <PubSubClient.h>

/******************************************************************************/
/*  GPIO Defs                                                                 */
/******************************************************************************/

// On-Board Pushbutton/LEDs for general purpose
// LEDs: active if output HIGH
// BTN:  pushed if read LOW
#define LED1 32
#define BTN1 33

// Signals for 24V Tower Lamp
// Active if set HIGH
#define SIG_RED 27
#define SIG_GRN 26
#define SIG_BUZ 25

// Address Solder Jumpers, to give each board a unique address
// Soldered: Reads 1
// Unsoldered: Reads 0
#define ADDR0 14
#define ADDR1 12
#define ADDR2 22
#define ADDR3 23

// Generic IO pins from breakout
#define D16  16
#define D17  17
#define D5    5
#define D18  18

/******************************************************************************/
/*  Const Defs                                                                */
/******************************************************************************/

// Local EnVision Network Credentials
#define SSID "EnVision-Local"
#define PSWD "thinkmakebreak"
#define MQTT_SERV_IP "192.168.111.111"
#define MQTT_PORT 1883

#define MQTT_NOTIF_TOWER_TOPIC "envision/front_desk/sign_in"

// Network Config Options
IPAddress gateway(192, 168, 111, 1);
IPAddress subnet(255, 255, 255, 0);

/******************************************************************************/
/*  Global Vars                                                               */
/******************************************************************************/

// The unique address of the device, determined by the solder jumpers
byte deviceAddr;

// The static IP Address of this device, determined by the solder jumpers
IPAddress deviceIP;

// Keep track of button state to react to changing states only
int btnPrev = 0;

// The MQTT Client objects
WiFiClient espClient;
PubSubClient mqttClient(espClient);

/******************************************************************************/
/*  Main Functions                                                            */
/******************************************************************************/

void setup() {

  // Init all the IO Pins
  initIO();

  // Read the address jumpers to determine the address of this device
  initDeviceAddr();

  // Enable default serial UART for USB debugging/printing
  Serial.begin(115200);

  // Print some startup stats like firmware rev and device address
  printBootStats();

  // Connect to the local EnVision network
  initWifi();

}

void loop() {

  // Wait for MQTT Messages on subscribed topics, and reconnect if necessary
  if (!mqttClient.connected()) {
    reconnect();
  }
  mqttClient.loop();
}

/******************************************************************************/
/*  Init Functions                                                            */
/******************************************************************************/

/*
 *  Initialize all the IO pins and set default output states
 */
void initIO() {
  // General Purpose LED/Button
  pinMode(LED1, OUTPUT);
  pinMode(BTN1, INPUT);

  // Tower Lamp signals
  pinMode(SIG_RED, OUTPUT);
  pinMode(SIG_GRN, OUTPUT);
  pinMode(SIG_BUZ, OUTPUT);

  // Default Output States
  digitalWrite(LED1, LOW);
  digitalWrite(SIG_RED, LOW);
  digitalWrite(SIG_GRN, LOW);
  digitalWrite(SIG_BUZ, LOW);
}

/*
 *  Initialize the Addr Jumpers to inputs, then read them to
 *  determine the device address
 */
void initDeviceAddr() {

  // Init Address Jumpers as inputs
  pinMode(ADDR0, INPUT);
  pinMode(ADDR1, INPUT);
  pinMode(ADDR2, INPUT);
  pinMode(ADDR3, INPUT);

  // Read the address jumpers to determine the device address (4-bits)
  deviceAddr = 0;
  deviceAddr =                     (digitalRead(ADDR3) & 0x1);
  deviceAddr = (deviceAddr << 1) | (digitalRead(ADDR2) & 0x1);
  deviceAddr = (deviceAddr << 1) | (digitalRead(ADDR1) & 0x1);
  deviceAddr = (deviceAddr << 1) | (digitalRead(ADDR0) & 0x1);

  // Set the Static IP variable of this device (don't init address yet)
  // Static IP Ranges: 192.168.111.X
  // X in range [221, 229] U [231, 238]
  // 192.168.111.239 reserved for testing MQTT server
  uint8_t addr[4] = {192, 168, 111, 221};
  if (deviceAddr < 9) {
    addr[3] += deviceAddr;
  }
  else {
    // The value 230 is reserved for the last octet for another machine
    addr[3] += 1 + deviceAddr;
  }
  deviceIP = addr;
}

/*
 *  Attempt to connect to the EnVision-Local network with a
 *  static IP address determined by the device's unique address
 *
 *  Keep retrying until success
 */
void initWifi() {
  Serial.print(F("Connecting to network "));
  Serial.println(SSID);

  // Static IP Address configured during initDeviceAddr
  if (!WiFi.config(deviceIP, gateway, subnet)) {
    Serial.println("Static IP Failed to configure");
  }

  WiFi.begin(SSID, PSWD);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("");
  Serial.println("WiFi connected");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());

  mqttClient.setServer(MQTT_SERV_IP, MQTT_PORT);
  mqttClient.setCallback(mqttMsgRecvCallback);
}

/*
 *  Print some stats to main UART for debugging purposes
 */
void printBootStats() {
  Serial.println();
  Serial.println(F("----------------------------------------"));
  Serial.println(F("EnVision Notification Tower"));

  Serial.print(F("Firmware Version: "));
  Serial.println(FIRMWARE_REV);

  Serial.print(F("Device Address: "));
  Serial.println(deviceAddr);
  Serial.println();
}

/******************************************************************************/
/*  Other Helper Functions                                                    */
/******************************************************************************/

/*
 *  MQTT callback function, called whenever a message is received on
 *  a subscribed topic
 */
void mqttMsgRecvCallback(char* topic, byte* msgRaw, unsigned int length) {
  #define SUCCESS_DELAY 200
  #define FAIL_DELAY 100

  // Only respond to messages from "envision/sign_in"
  if (String(topic) != MQTT_NOTIF_TOWER_TOPIC)
    return;

  // Convert to String for easier parsing
  String message;
  for (int i = 0; i < length; i++) {
    message += (char) msgRaw[i];
  }

  Serial.print("[");
  Serial.print(topic);
  Serial.print("]: ");
  Serial.println(message);

  if (message == "<OK>") {
    // Beep the buzzer once but blink the green light thrice
    digitalWrite(SIG_BUZ, HIGH);
    digitalWrite(SIG_GRN, HIGH);
    delay(SUCCESS_DELAY);
    digitalWrite(SIG_BUZ, LOW);
    digitalWrite(SIG_GRN, LOW);
    delay(SUCCESS_DELAY);
    for (int i = 0; i < 2; i++) {
      digitalWrite(SIG_GRN, HIGH);
      delay(SUCCESS_DELAY);
      digitalWrite(SIG_GRN, LOW);
      delay(SUCCESS_DELAY);
    }
  }
  else if (message == "<DENY>") {
    // Beep the buzzer and blink the red light 4 times
    for (int i = 0; i < 4; i++) {
      digitalWrite(SIG_RED, HIGH);
      digitalWrite(SIG_BUZ, HIGH);
      delay(FAIL_DELAY);
      digitalWrite(SIG_RED, LOW);
      digitalWrite(SIG_BUZ, LOW);
      delay(FAIL_DELAY);
    }
  }
}

/*
 *  Connect to the MQTT server and subscribe to relevant topics
 */
void reconnect() {
  // Construct the MQTT Device ID string
  char deviceID[] = "NotifTower_00\0";
  deviceID[11] = '0' + deviceAddr / 10;
  deviceID[12] = '0' + deviceAddr % 10;

  // Loop until we're reconnected
  while (!mqttClient.connected()) {
    Serial.print("Attempting MQTT connection to ");
    Serial.print(MQTT_SERV_IP);
    Serial.print(" on port ");
    Serial.print(MQTT_PORT);
    Serial.print(" with client ID ");
    Serial.println(deviceID);

    // Attempt to connect
    if (mqttClient.connect(deviceID)) {
      Serial.println("MQTT Connected Successfully");
      // Subscribe
      mqttClient.subscribe(MQTT_NOTIF_TOWER_TOPIC);
    } else {
      Serial.print("failed, rc=");
      Serial.print(mqttClient.state());
      Serial.println(" try again in 5 seconds");
      // Wait 5 seconds before retrying
      delay(5000);
    }
  }
}

/*
 * Cycle all tower lamp signals for testing
 */
void cycleLights() {
  Serial.println(F("---------------"));
  Serial.println(F("Cycling all lamp signals ..."));

  Serial.println(F("Cycle Red ..."));
  for (int i = 0; i < 3; i++) {
    digitalWrite(SIG_RED, HIGH);
    delay(100);
    digitalWrite(SIG_RED, LOW);
    delay(100);
  }
  Serial.println(F("Red done!\n"));
  delay(300);

  Serial.println(F("Cycle Green ..."));
  for (int i = 0; i < 3; i++) {
    digitalWrite(SIG_GRN, HIGH);
    delay(100);
    digitalWrite(SIG_GRN, LOW);
    delay(100);
  }
  Serial.println(F("Green done!\n"));
  delay(300);

  Serial.println(F("Cycle Buzzer ..."));
  for (int i = 0; i < 3; i++) {
    digitalWrite(SIG_BUZ, HIGH);
    delay(100);
    digitalWrite(SIG_BUZ, LOW);
    delay(100);
  }
  Serial.println(F("Buzzer done!\n"));

  Serial.println(F("Cycle complete!"));
  Serial.println(F("---------------"));
  Serial.println();
}

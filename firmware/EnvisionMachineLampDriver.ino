/*
 | Envision Machine Lamp Driver
 | Georges Troulis  <gtroulis@ucsd.edu>
 |
 | This firmware runs on the ESP32 boards that drive the Notification Tower Lamps
 | in response to the RPi controller on the Laser Cutter or other machines
 |
 | ------------------------------------------------------------
 | Revision Log (Updated 12/07/2019):
 | 0.2: Moved Heartbeat pulsing to separate thread, changed thread stack depth to 1024 words
 | 0.1: First pre-release rev, basic functionality
 |
 | ------------------------------------------------------------
 | TODO list:
 |  [ ] Give states to control signals that make more sense (make them all consistent)
*/

/*
 *  Truth Table:
 *  
 *  Signals from RPi w/o Pull Ups:
 *
 *             RED_CNST | RED_PULS | GRN_CNST | BUZ_PULS | Want Behaviour
 *  Timer OFF:     0    |    0     |    0     |    0     |  Grn Off, Red Steady, Buzz off (Note, need pull-ups)
 *  Timer ON:      0    |    1     |    0     |    1     |  Grn Steady, Red Off, Buzz off
 *  Time <30s:     0    |    0     |    0     |    1     |  Grn Steady, Red Pulsing, Buzz off
 *  Time <15s:     0    |    0     |    0     |    0     |  Grn Steady, Red Pulsing, Buzz Pulsing
 *  Ideal OFF:     1    |    1     |    1     |    1     |  Grn Off, Red Steady, Buzz off (Use PULLUP to achieve this)
 */

// The firmware revision
#define FIRMWARE_REV  F("0.2")

/******************************************************************************/
/*  GPIO Defs                                                                 */
/******************************************************************************/

// On-Board Pushbutton/LEDs for general purpose
// LED: active if output HIGH
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

// Use the Generic IO pins to receive control signals from the main RPi
// used to flash the tower lamp appropriately
#define RX_RED_CNST_SIG  D16  // (Active LOW)  Red Lamp Steady
#define RX_GRN_CNST_SIG  D17  // (Active HIGH) Green Lamp Steady
#define RX_BUZ_PULS_SIG  D5   // (Active LOW)  Buzzer Pulse
#define RX_RED_PULS_SIG  D18  // (Active LOW)  Red Lamp Pulse (overrides steady

// Enable the Heartbeat LED (can be useful to see if application has frozen)
#define ENABLE_HEARTBEAT

/******************************************************************************/
/*  Global Vars                                                               */
/******************************************************************************/

// The unique address of the device, determined by the solder jumpers
byte deviceAddr;

/******************************************************************************/
/*  RTOS Task Handles                                                         */
/******************************************************************************/

TaskHandle_t thRedPulser = NULL;  // Pulses the Red Lamp
TaskHandle_t thBuzPulser = NULL;  // Pulses the Buzzer

/******************************************************************************/
/*  Main Functions                                                            */
/******************************************************************************/

void setup() {

  // Init all the IO Pins
  initIO();

  // Read the address jumpers to determine the address of this device
  initDeviceAddr();

  // Init any RTOS tasks that need to run
  initRTOSTasks();

  // Enable default serial UART for USB debugging/printing
  Serial.begin(115200);

  // Print some startup stats like firmware rev and device address
  printBootStats();
}

void loop() {
  // Forward the signals from the RPi to the tower lamp

  // logic for red lamp, either pulsing, constant, or off
  // PulseRed signal takes priority over ConstantRed signal
  if (!digitalRead(RX_RED_PULS_SIG)) {
    if (thRedPulser == NULL) {
      spawnRedPulser();
    }
  }
  else if (digitalRead(RX_RED_CNST_SIG)) {
    if (thRedPulser != NULL) {
      vTaskDelete(thRedPulser);
      thRedPulser = NULL;
    }

    // Not pulsing, but enabled
    digitalWrite(SIG_RED, HIGH);
  }
  else {
    if (thRedPulser != NULL) {
      vTaskDelete(thRedPulser);
      thRedPulser = NULL;
    }
    digitalWrite(SIG_RED, LOW);
  }

  // logic for buzzer, pulsing or not
  if (!digitalRead(RX_BUZ_PULS_SIG)) {
    if (thBuzPulser == NULL) {
      spawnBuzPulser();
    }
  }
  else {
    if (thBuzPulser != NULL) {
      vTaskDelete(thBuzPulser);
      thBuzPulser = NULL;
    }
    digitalWrite(SIG_BUZ, LOW);
  }

  // Green lamp is constant-on or off
  digitalWrite(SIG_GRN, !digitalRead(RX_GRN_CNST_SIG));

  // Debug: If any character received, print state of inputs
  if (Serial.available()) {
    Serial.read();
    Serial.println("----------");
    Serial.print("RED_CNST [D16]: ");
    Serial.println(digitalRead(D16));

    Serial.print("GRN_CNST [D17]: ");
    Serial.println(digitalRead(D17));

    Serial.print("BUZ_PULS [ D5]: ");
    Serial.println(digitalRead(D5));

    Serial.print("RED_PULS [D18]: ");
    Serial.println(digitalRead(D18));
  }

  // Allow the idle task to run and perform cleanup
  delay(10);
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

  // Control inputs from RPi for tower lamp
  pinMode(RX_RED_PULS_SIG, INPUT_PULLUP);
  pinMode(RX_RED_CNST_SIG, INPUT_PULLUP);
  pinMode(RX_GRN_CNST_SIG, INPUT_PULLUP);
  pinMode(RX_BUZ_PULS_SIG, INPUT_PULLUP);

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
}

/*
 *  Init any RTOS Tasks that need to be initialized before loop
 */
void initRTOSTasks() { 

  // Create the Heartbeak task (note: doesn't need task handle because we don't
  // care about keeping track of this once it's created)
  #ifdef ENABLE_HEARTBEAT
    xTaskCreate(
          Task_Heartbeat,    // Task Function Body
          "Task_Heartbeat",  // Task Name
          1024,              // Stack Size (32-bit word)
          NULL,              // No Arguments
          1,                 // Lowest Priority
          NULL               // No Task Handle
    );
  #endif
}

/*
 *  Print some stats to main UART for debugging purposes
 */
void printBootStats() {
  Serial.println();
  Serial.println(F("----------------------------------------"));
  Serial.println(F("EnVision Laser Client"));

  Serial.print(F("Firmware Version: "));
  Serial.println(FIRMWARE_REV);

  Serial.print(F("Device Address: "));
  Serial.println(deviceAddr);
  Serial.println();
}

/******************************************************************************/
/*  RTOS Task Functions                                                       */
/******************************************************************************/

/*
 *  Creates an instance of the task that pulses the Red Lamp
 *
 *  Note: This will create multiple instances of the same task if called
 *         multiple times. This should be avoided by the caller by checking
 *         if the task handle is null
 *        
 */
inline void spawnRedPulser() {
  xTaskCreate(
        Task_RedPulser,    // Task Function Body
        "Task_RedPulser",  // Task Name
        1024,              // Stack Size (32-bit word)
        NULL,              // No Arguments
        1,                 // Lowest Priority
        &thRedPulser       // Task Handle
  );
}

/*
 *  Creates an instance of the task that pulses the Buzzer
 *
 *  Note: This will create multiple instances of the same task if called
 *         multiple times. This should be avoided by the caller by checking
 *         if the task handle is null
 *        
 */
inline void spawnBuzPulser() {
  xTaskCreate(
        Task_BuzPulser,    // Task Function Body
        "Task_BuzPulser",  // Task Name
        1024,              // Stack Size (32-bit word)
        NULL,              // No Arguments
        1,                 // Lowest Priority
        &thBuzPulser       // Task Handle
  );
}

/*
 *  Task that pulses the Red Lamp. Runs forever until deleted or blocked
 *  by kernel.
 *
 *  This task is spawned every time the applications wants to pulse the
 *  red lamp, and is deleted when the applications wants to stop the pulsing
 */
void Task_RedPulser(void* param) {
  #define RED_PULSE_DELAY 500

  while(true) {
    digitalWrite(SIG_RED, HIGH);
    delay(RED_PULSE_DELAY);
    digitalWrite(SIG_RED, LOW);
    delay(RED_PULSE_DELAY);
  }
}

/*
 *  Task that pulses the Buzzer. Runs forever until deleted or blocked
 *  by kernel.
 *
 *  This task is spawned every time the applications wants to pulse the
 *  buzzer, and is deleted when the applications wants to stop the pulsing
 */
void Task_BuzPulser(void* param) {
  #define BUZ_ON_DELAY 100
  #define BUZ_OFF_DELAY 400

  while(true) {
    digitalWrite(SIG_BUZ, HIGH);
    delay(BUZ_ON_DELAY);
    digitalWrite(SIG_BUZ, LOW);
    delay(BUZ_OFF_DELAY);
  }
}

/*
 *  Task that pulses the built-in LED in a heartbeat pattern to indicate
 *  that the device is running.
 *
 *  If the heartbeat LED is not pulsing, then the application has encountered
 *  some error and has halted. Resetting the MCU may resolve this
 */
void Task_Heartbeat(void* param) {
  #define HB_PULSE_ON    100
  #define HB_PULSE_OFF_1 200
  #define HB_PULSE_OFF_2 1000

  // Heartbeat has 2 pulses, a short one and a long one
  while(true) {
    // Pulse 1
    digitalWrite(LED1, HIGH);
    delay(HB_PULSE_ON);
    digitalWrite(LED1, LOW);
    delay(HB_PULSE_OFF_1);

    // Pulse 2
    digitalWrite(LED1, HIGH);
    delay(HB_PULSE_ON);
    digitalWrite(LED1, LOW);
    delay(HB_PULSE_OFF_2);
  }
}

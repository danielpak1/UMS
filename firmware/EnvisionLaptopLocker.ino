/*
 | Locker Control
 | J. DeWald, EnVision, JSOE, UCSD
 | 8/20/2017
 |
 | This sketch reads a nibble from serial input to drive two 16 channel multiplexers (MUX)
 | Mux Truth Table is available at https://www.sparkfun.com/datasheets/IC/cd74hc4067.pdf
 |
 | ------------------------------------------------------------
 | Modified by Georges Troulis, Summer 2019
 | gtroulis@ucsd.edu
 | ------------------------------------------------------------
 |
 | Library Dependencies (needed to compile):
 |  - Adafruit_SSD1306: https://learn.adafruit.com/monochrome-oled-breakouts/arduino-library-and-examples
 |  - PaulStoffregen's Encoder Library: https://www.pjrc.com/teensy/td_libs_Encoder.html
 |
 |
 | ------------------------------------------------------------
 | Revision Log:
 | 1.7: OLEDs now show adjusted laptop range (locker 1 range [1-15], locker 2 range [16-31] etc)
 | 1.6: Added nice display when encoder override is used
 | 1.5: Changed delay of door back to 4.5 seconds
 | 1.4: Rotary Encoder now used to "override" opening locker doors
 | 1.3: Added nicer print-out for OLED
 | 1.2: Added support for settings in EEPROM. Currently cannot
 |      be set
 | 1.1: Support for Buzzer, Rotary Encoder, and OLED display.
 |      Each board has unique address set by solder jumpers
 |
 | ------------------------------------------------------------
 | TODO list:
 |  [ ] Add user interface menu
 |  [ ] Use encoder library that Jesse recommended
 |  [ ] Add reed switch functionality and beep when doors aren't closed
*/

// The firmware revision
#define FIRMWARE_REV  F("1.7")

// OLED Display Library
#include <Adafruit_SSD1306.h>

#include <EEPROM.h>

/******************************************************************************/
/*      EEPROM Settings (to store settings over reboots)                      */
/******************************************************************************/

// Comment this out during normal functionality
// When uncommented, the EEPROM will be written default values on boot
// If left uncommented, device won't remember settings across reboots
// Uncomment this once per device, upload code, then comment and re-upload, keep commented
//#define EEPROM_RESET

#define DFLT_SCREEN_INV     ((bool) 0)
#define DFLT_ENC_INV        ((bool) 1)

// Indices of settings in EEPROM (4-byte aligned for future-proofing)

#define IND_SCREEN_INV      0 // (bool) Invert Screen
#define IND_ENC_INV         4 // (bool) Invert Encoder

// Actual values of settings (init with default values, then init from EEPROM)
bool encoderInvert = DFLT_ENC_INV;
bool screenInvert  = DFLT_SCREEN_INV;

/******************************************************************************/
/*      GPIO Pin Defs                                                         */
/******************************************************************************/

// Buzzer
#define buzzer        2

// Encoder input signals
#define enc_1         4
#define enc_2         3
#define enc_btn       5

// Mux Signal In/Out pins
#define sig_sen       6
#define sig_sol       7

// Mux address pins
#define S0            8
#define S1            9
#define S2            10
#define S3            11

// Mux Enable pins
#define en_sol        12
#define en_sen        13

// Address Solder Jumpers, to give each board a unique address
#define ADDR0         A1
#define ADDR1         A2
#define ADDR2         A3

/******************************************************************************/
/*      Global Constants                                                      */
/******************************************************************************/

#define DISP_ADDR     0x3C  // I2C Address of the OLED Display

#define BUZ_FREQ      4000  // 4 kHz Piezo speaker (warning, very annoying)

#define DOOR_DELAY     4500 // Door delay when opening through RPi command
#define OVR_DOOR_DELAY 2000 // Override delay when using encoder override

// OLED Display for user interface
Adafruit_SSD1306 disp(128, 64, &Wire, 4);

/******************************************************************************/
/*      Global Variables                                                      */
/******************************************************************************/

// The unique address of the device, determined by the solder jumpers
byte deviceAddr;

// Absolute position of the rotary encoder
// Modified by the ISR_EncoderChanged() callback
volatile byte encoderVal = 1;

// Encoder boundary values. The value of encoderVal always stays in this range
byte encoderMin =  1;
byte encoderMax = 15;

// Keep track of changes in the button state
byte lastBtnState = 0;

// Keep track of encoder val changes
byte lastEncoderVal = encoderVal;


/******************************************************************************/
/*      Main Code                                                             */
/******************************************************************************/

void setup() {
  // initialize serial:
  Serial.begin(9600);

  // Initialize the OLED Display
  if(!disp.begin(SSD1306_SWITCHCAPVCC, DISP_ADDR)) {
    Serial.println(F("SSD1306 allocation failed"));
    for(;;); // Don't proceed, loop forever
  }

  // Initialize all I/O Pins
  initIOPins();

  // Read the address jumpers to determine the device address (3-bits)
  initDeviceAddress();

  // If this is defined, write default values to the settings
  #ifdef EEPROM_RESET
    resetEEPROM();
  #endif

  // Read the settings stored in EEPROM and initialize global settings variables
  initSettingsFromEEPROM();

  // Enable the interrupt that connects to the encoder pin
  attachInterrupt(digitalPinToInterrupt(enc_2), ISR_EncoderChanged, RISING);

  // By default, show the selected door on the OLED
  showSelDoor();

  // Init done, ready to receive instructions
  Serial.println("READY");
}

void loop() {

  // TEMP encoder testing output
  if (lastEncoderVal != encoderVal) {
    Serial.print(F("Encoder Value: "));
    Serial.println(encoderVal);
    lastEncoderVal = encoderVal;

    // Update the OLED
    showSelDoor();
  }

  // Manual override switch: If encoder button pushed, then open
  // the door that is selected
  if (!digitalRead(enc_btn)) {
    if (lastBtnState) {

      byte door = encoderVal;

      // Show "opening door" message on OLED, then open the door,
      // wait for solenoid to deactivate, and show the selected door again

      openLockerDoor(door - 1);

      resetDisplay();
      // Show the progress bar over a given time interval
      for (int i = 0; i < 100; i += 3) {
        showOpeningDoorProg(door + (16 * deviceAddr), i);

        // Note that writing to the display takes a while,
        // so delay is divided by 300 instead of 100
        delay(OVR_DOOR_DELAY / 300);
      }

      deactivateDoorSol(door - 1);

      showSelDoor();

      // Make sure this executes on a falling edge of the pushbutton only
      lastBtnState = 0;
    }
  }
  else {
    lastBtnState = 1;
  }

  // If there's no serial data pending, skip to beginning of loop
  // Doing 'return' will actually make the loop() call itself again
  if (!Serial.available())
    return;

  // look for the next valid integer in the incoming serial stream:
  byte solenoid = Serial.parseInt(); //receive solenoid number 0-15, parseInt discards negative numbers
  // look for the newline. That's the end of your sentence:
  if (Serial.read() == '\n') {
    //verify the solenoid number is within a valid range
    if (solenoid < 48) {

      // Note, solenoids are 1-indexed instead of 0-indexed
      // (i.e. PCB solenoid 2 connects to locker solenoid 1)
      // RPi software takes this into account when sending data
      solenoid = solenoid % 16;

      // Open the given locker door, wait some amount, then deactivate the solenoid
      openLockerDoor(solenoid);
      delay(DOOR_DELAY);
      deactivateDoorSol(solenoid);

      //code not currently used for reed switches
      bool doorClosed = false;
      Serial.print("Waiting for door close");
      digitalWrite(en_sen, LOW);//enable the reed mux
      //solenoid mux is disabled, reed mux is enabled
      //this while loop will wait for a high signal on sig_sen pin
      while (!doorClosed) {
        //commented out because not being used
        //doorClosed = digitalRead(sig_sen);
        doorClosed = true; //obviously this is for testing
        Serial.print("."); //debug printing, we'd need something more valuable for the kiosk
        delay(1000);
      }
      Serial.print("\n");

      Serial.println("READY");//alert the kiosk that ready for input
    }
  }
}

/******************************************************************************/
/*      General Hardware Helper Functions                                     */
/******************************************************************************/

/*
 * Interrupt Service Routine, triggered when Encoder is rotated.
 * Determine the direction of change and update global
 * encoder position value
 */
void ISR_EncoderChanged() {

  // We know encoder updates on rising edge so enc_2 is always HIGH
  // Encoder may or may not need inverting, hence this setting
  // encoderInvert can be modified via user interface
  if (encoderInvert) {
    digitalRead(enc_1) ? encoderVal-- : encoderVal++;
  }
  else {
    digitalRead(enc_1) ? encoderVal++ : encoderVal--;
  }

  // Keep the new value within the boundaries
  if (encoderVal > encoderMax) encoderVal = encoderMin;
  if (encoderVal < encoderMin) encoderVal = encoderMax;
}

/*
 * Opens the locker door specified.
 *
 * Sets the door mux address, and enables the solenoid signal
 */
void openLockerDoor(byte door) {

  bool solenoidByte[] = {0, 0, 0, 0}; //empty nibble

  //convert the integer to a four bit nibble
  for (int i = 0; i <= 3; i++)
  {
    //Serial.println(bitRead(door, i));
    solenoidByte[i] = bitRead(door, i); //read the bits of solenoid, 0 is LSB (rightmost)
    Serial.print(solenoidByte[i]);//print each bit to Serial
    Serial.print("-");
  }
  Serial.print("\n");
  Serial.println (door, BIN);//terminate the data print with a newline
  //Format is 0-0-0-0\n
  //can be used later in kiosk if needed

  //enable pin is still high (disabled)
  //set each bit first, then set the signal, then enable the mux
  digitalWrite(S0, solenoidByte[0]);
  digitalWrite(S1, solenoidByte[1]);
  digitalWrite(S2, solenoidByte[2]);
  digitalWrite(S3, solenoidByte[3]);
  digitalWrite(sig_sol, HIGH);//set signal high
  digitalWrite(en_sol, LOW);//enable solenoid mux
}

/*
 * Deactivates the solenoid for the locker door specified.
 *
 * Sets the door mux address, and disables the solenoid signal. Should be called very
 * soon after openLockerDoor
 */
void deactivateDoorSol(byte door) {

  bool solenoidByte[] = {0, 0, 0, 0}; //empty nibble

  //convert the integer to a four bit nibble
  for (int i = 0; i <= 3; i++)
  {
    //Serial.println(bitRead(door, i));
    solenoidByte[i] = bitRead(door, i); //read the bits of solenoid, 0 is LSB (rightmost)
  }

  //enable pin is still high (disabled)
  //set each bit first, then set the signal, then enable the mux
  digitalWrite(S0, solenoidByte[0]);
  digitalWrite(S1, solenoidByte[1]);
  digitalWrite(S2, solenoidByte[2]);
  digitalWrite(S3, solenoidByte[3]);

  digitalWrite(en_sol, LOW);//enable solenoid mux
  digitalWrite(sig_sol, LOW); //send a default-low signal to the mux to release the solenoid
  digitalWrite(en_sol, HIGH); //disable the solenoid mux
}


/*
 *  Sets the settings in the EEPROM to default values. Does not update
 *  global settings variables, call initSettingsFromEEPROM() for that.
 */
void resetEEPROM() {
    EEPROM.put(IND_SCREEN_INV, DFLT_SCREEN_INV);
    EEPROM.put(IND_ENC_INV, DFLT_ENC_INV);
}


/******************************************************************************/
/*      OLED Helper Functions                                                 */
/******************************************************************************/

/*
 * Resets the display and sets some default settings
 */
void resetDisplay() {
    disp.clearDisplay();
    disp.setCursor(0, 0);
    disp.setTextSize(1);
    disp.setTextColor(WHITE);

    // This can be set via the user interface, stored across boots
    if (screenInvert) disp.setRotation(2);
    else              disp.setRotation(0);
}

/*
 * Shows the door that is currently selected by the user interface
 * on the OLED display
 */
void showSelDoor() {
  resetDisplay();

  #define NUM_TXT_SZ 4

  // Device address determines numeric range of laptops
  // Addr 0: Laptops [ 1-15]
  // Addr 1: Laptops [16-31]
  // Addr 2: Laptops [32-47]
  int selectedLaptop = encoderVal + (16 * deviceAddr);

  // Prepare to display the encoder value, large number
  disp.setTextSize(NUM_TXT_SZ);

  // Center the number; using 5x7 font
  if (selectedLaptop < 10) {
    disp.setCursor((disp.width() - 5*NUM_TXT_SZ)/2,
                   (disp.height()- 7*NUM_TXT_SZ)/2);
  }
  else {
    disp.setCursor((disp.width() - 11*NUM_TXT_SZ)/2,
                   (disp.height()- 7*NUM_TXT_SZ)/2);
  }
  disp.println(selectedLaptop);

  // Display a nice rectangle around the number
  disp.drawRect(0, 0, disp.width(), disp.height(), 1);
  disp.drawRect(1, 1, disp.width()-2, disp.height()-2, 1);

  disp.display();
}

/*
 * Shows the message 'opening door' on the OLED with
 * a progress bar of how long the door has been open for
 *
 * Note: display must be erased before calling this function
 *       (not done here for optimization purposes)
 */
void showOpeningDoorProg(unsigned int door, unsigned int progress) {

  // Display the "Opening Door XX" text
  // This is roughly centered on a 128x64 display
  disp.setTextSize(2);
  disp.setCursor(20, 10);
  disp.print(F("Opening"));
  disp.setCursor(20, 30);
  disp.print(F("Door "));
  disp.print(door);

  // Draw the progress bar
  #define BAR_WIDTH  100
  #define BAR_HEIGHT 2
  const int barX = (disp.width() - 100)/2;
  const int barY = 51;
  disp.drawRect(barX, barY, BAR_WIDTH+4, BAR_HEIGHT+4, WHITE);
  disp.fillRect(barX+2, barY+2, progress, 2, WHITE);

  // Display a nice rectangle around the screen border
  disp.drawRect(0, 0, disp.width(), disp.height(), 1);
  disp.drawRect(1, 1, disp.width()-2, disp.height()-2, 1);
  disp.display();
}

/******************************************************************************/
/*      Buzzer Helper Functions                                               */
/******************************************************************************/

/*
 * Beeps the buzzer once for minor alerts
 */
void beepOnce() {
  tone(buzzer, BUZ_FREQ);
  delay(200);
  noTone(buzzer);
}

/*
 * Pulses the buzzer thrice to alert the user
 * of something more urgent than a single beep
 */
void beepAlert() {
  for (int i = 0; i < 3; i++) {
    tone(buzzer, BUZ_FREQ);
    delay(100);
    noTone(buzzer);
    delay(100);
  }
}

/******************************************************************************/
/*      Init Functions, called once during setup()                            */
/******************************************************************************/

/*
 * Initialize the I/O pins and set default states for the outputs
 * Should be called once during setup()
 */
void initIOPins() {
  // Inputs
  pinMode(sig_sen, INPUT);
  pinMode(enc_1, INPUT);
  pinMode(enc_2, INPUT);
  pinMode(enc_btn, INPUT);

  // Outputs
  pinMode(S0, OUTPUT);
  pinMode(S1, OUTPUT);
  pinMode(S2, OUTPUT);
  pinMode(S3, OUTPUT);
  pinMode(buzzer, OUTPUT);
  pinMode(en_sol, OUTPUT);
  pinMode(en_sen, OUTPUT);
  pinMode(sig_sol, OUTPUT);

  // The Address Jumpers
  pinMode(ADDR0, INPUT);
  pinMode(ADDR1, INPUT);
  pinMode(ADDR2, INPUT);

  // Set default values to outputs
  digitalWrite(en_sol, HIGH); //disable solenoid mux
  digitalWrite(en_sen, HIGH); //disable reed mux
  digitalWrite(sig_sol, LOW); //default the solenoid signal out to LOW
  digitalWrite(S0, LOW);
  digitalWrite(S1, LOW);
  digitalWrite(S2, LOW);
  digitalWrite(S3, LOW);
  digitalWrite(buzzer, LOW);
}

/*
 * Read the address jumpers to determine the device address (3-bits)
 * Should be called once during setup()
 */
void initDeviceAddress() {
  deviceAddr = 0;
  deviceAddr =                     (digitalRead(ADDR2) & 0x1);
  deviceAddr = (deviceAddr << 1) | (digitalRead(ADDR1) & 0x1);
  deviceAddr = (deviceAddr << 1) | (digitalRead(ADDR0) & 0x1);
}

/*
 * Read the settings stored in EEPROM and initialize global settings variables.
 * Called once during setup(), and when prompted to reset settings to default
 *
 * Note: EEPROM.get updates the variables by reference, see Arduino documentation
 *       for details
 */
void initSettingsFromEEPROM() {
  EEPROM.get(IND_ENC_INV, encoderInvert);
  EEPROM.get(IND_SCREEN_INV, screenInvert);
}

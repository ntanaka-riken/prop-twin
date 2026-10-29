// blink_ota_esp8266 — SERIAL-ONLY DC motor controller for the Switch Science
// ESPr Developer (ESP-WROOM-02 / ESP8266). Wi-Fi/OTA-free build (v36):
// the attached devices are the L293D dual-bridge DC motor driver and one
// sync LED that marks each command for video-based identification. The
// Wi-Fi/OTA/UDP control plane, provisioning, and multi-device history
// (matrix, OLED, BME280, MPU-6050, NeoPixel, servo, stepper, DHT) live in the
// original repo (~/Documents/esp32/blink_ota_esp8266, GitHub:
// ntanaka-riken/blink-ota-esp8266) and can be restored from its git log.
//
// Hardware:
//   - L293D dual-bridge parallel (1A+3A, 2A+4A, EN1,2+EN3,4 shorted):
//     INA=IO12, INB=IO13, EN=IO15 (PWM speed 0-255).
//   - Sync LED: IO14 -> resistor -> LED -> GND; 100 ms flash per dcm:* ACK.
//   - Back-EMF probe: motor terminal A (L293D pin 3) -> 10k -> TOUT -> 2k -> GND,
//     terminal B (pin 6) -> 6.8k -> GND (reference while coasting). Ratio 0.167.
//   - Measured cold-start threshold (binary search): 40% no / 45% marginal
//     (delayed breakaway) / 50% yes — use 50%+ to actually start the motor.
//
// Operation:
//   - Serial 115200, 1 line = 1 command:
//       stat | dcm:ramp <pct> <ms> | dcm:ramp-step <pct> <ms> <inc%>
//       | dcm:speed <-255..255> | dcm:brake | dcm:off | dcm:auto <0|1>
//       | adc:read | adc:cap <interval_us> <n> <pre> [command] | adc:emf [settle_us] [n]
//       | adc:zero | rpm:set <rpm> | rpm:off | tel:on | tel:off
//   - Boot sequence: 5 s after boot, jump to 50% (the lowest duty that starts
//     the motor), ramp 50->100% over 5 s, hold 100% for 1 s, then coast.
//     Any motion command cancels it; dcm:auto 0 disables it (RAM-held,
//     resets on reboot) and stops the motor if the sequence is running.

const char* FW_VERSION = "blink_ota_esp8266 v36 serial-only (L293D + sync LED)";
unsigned long blinkInterval = 500;   // ms between [HB] serial heartbeats

// --- DC motor: L293D dual-bridge parallel (1A+3A, 2A+4A, EN1,2+EN3,4 shorted) ---
// Measured cold-start threshold (binary search, this motor + driver):
//   20% no / 40% no / 45% marginal (delayed breakaway) / 50% yes
// Reliable start = 50%+, steady running 55%+.
const int DCM_INA = 12;              // 1A + 3A (direction A = forward)
const int DCM_INB = 13;              // 2A + 4A (direction B = reverse)
const int DCM_EN = 15;               // 1,2EN + 3,4EN (PWM speed 0-255)

// --- sync LED: IO14 -> resistor -> LED -> GND (active HIGH) ---
// Flashes for SYNC_FLASH_MS on every accepted dcm:* command, so a camera can
// time-stamp each command to the frame (see twin/README.md).
const int SYNC_LED = 14;
const unsigned long SYNC_FLASH_MS = 100;
unsigned long syncLedOnAt = 0;
bool syncLedOn = false;
int dcmDuty = 0;                     // current PWM duty 0-255
int dcmDir = 1;                      // +1 forward, -1 reverse
bool dcmOn = false;                  // false = coast (EN low)
bool dcmRampActive = false;
int dcmRampFrom = 0, dcmRampTo = 0;
long dcmRampMs = 0;
unsigned long dcmRampStart = 0;
// boot sequence: BOOT_START_MS after boot jump to BOOT_FROM_PCT, ramp to
// BOOT_TO_PCT over BOOT_RAMP_MS, hold BOOT_HOLD_MS, then coast
bool dcmAutoBoot = true;
const unsigned long BOOT_START_MS = 5000;
const int BOOT_FROM_PCT = 50;        // lowest duty that starts the motor from rest
const int BOOT_TO_PCT = 100;
const long BOOT_RAMP_MS = 5000;
const unsigned long BOOT_HOLD_MS = 1000;
int bootStage = 0;                   // 0 armed, 1 running, 2 done/cancelled
unsigned long bootAt = 0;
// discrete (staircase) ramp: every dcmStepIntervalMs, duty += dcmStepInc
bool dcmStepRampActive = false;
int dcmStepTarget = 0;               // target duty 0-255
int dcmStepInc = 25;                 // duty increment per step (10% of 255)
long dcmStepIntervalMs = 1000;       // ms per step
unsigned long dcmStepLast = 0;

// --- ADC (TOUT, 0-1 V, 10 bit): back-EMF of motor terminal A through 6.8k/2k ---
const float ADC_DIVIDER = 2.0f / (10.0f + 2.0f); // TOUT = V_A * 0.167
const int ADC_CAP_MAX = 4000;                    // samples (8 KB)
const float MOTOR_K = 6.06e-3f;                  // back-EMF constant V*s/rad (twin/README.md)
const float EMF_SCALE = 12280.0f / 12000.0f;     // 270 ohm reference drop while coasting
float adcZero = 21.0f;                           // raw ADC at 0 V, re-measured in setup()

// --- closed-loop speed control (constants tuned on the twin, twin/motor_twin.py) ---
// Every CTL_MS: EN low ~2 ms to read the back-EMF (tachometer), EMA filter, then
// duty = feedforward(ref) + Kp*e + I, floored at 40 % so the motor never stalls.
const unsigned long CTL_MS = 50;
const float CTL_KP = 0.04f, CTL_KI = 0.25f, CTL_ALPHA = 0.5f;
const float RPM_MIN = 750.0f, RPM_MAX = 3200.0f, KICK_FRAC = 0.4f;
const int DUTY_FLOOR = 102;
const float FF_RPM[] = {0, 700, 1227, 1629, 2169, 3057};
const float FF_DUTY[] = {0, 102, 127, 153, 204, 255};
bool rpmCtl = false, telOn = false;
float rpmRef = 0, rpmFilt = 0, rpmMeas = 0, ctlI = 0;
unsigned long ctlLast = 0, kickUntil = 0;

void syncFlash() {
  digitalWrite(SYNC_LED, HIGH);
  syncLedOn = true;
  syncLedOnAt = millis();
}

// back-EMF probe: EN low for settle_us, n reads, bridge restored. Returns mean raw.
float emfProbe(long settle, long n, int* mn, int* mx, unsigned long* coastUs) {
  unsigned long t0 = micros();
  if (dcmOn) analogWrite(DCM_EN, 0);
  while ((long)(micros() - (t0 + settle)) < 0) {}
  long sum = 0; int lo = 1023, hi = 0;
  for (long k = 0; k < n; k++) {
    int r = analogRead(A0); sum += r;
    if (r < lo) lo = r;
    if (r > hi) hi = r;
  }
  if (coastUs) *coastUs = micros() - t0;
  if (dcmOn) dcmApply();
  if (mn) *mn = lo;
  if (mx) *mx = hi;
  return (float)sum / n;
}

float rawToRpm(float raw) {
  float v = (raw - adcZero) / 1023.0f / ADC_DIVIDER * EMF_SCALE;
  if (v < 0) v = 0;
  return v / MOTOR_K * 30.0f / PI;
}

float ffDuty(float rpm) {
  for (int k = 1; k < 6; k++)
    if (rpm <= FF_RPM[k])
      return FF_DUTY[k - 1] + (FF_DUTY[k] - FF_DUTY[k - 1]) * (rpm - FF_RPM[k - 1]) / (FF_RPM[k] - FF_RPM[k - 1]);
  return 255;
}

void dcmApply() {
  if (!dcmOn) return;
  if (dcmDir >= 0) { digitalWrite(DCM_INA, HIGH); digitalWrite(DCM_INB, LOW); }
  else             { digitalWrite(DCM_INA, LOW);  digitalWrite(DCM_INB, HIGH); }
  analogWrite(DCM_EN, dcmDuty);
}
void dcmOff() {                  // coast: EN low, inputs low; cancels ramps
  dcmOn = false;
  dcmRampActive = false;
  dcmStepRampActive = false;
  dcmDuty = 0;                   // stopped motor: next ramp starts from 0
  digitalWrite(DCM_INA, LOW);
  digitalWrite(DCM_INB, LOW);
  analogWrite(DCM_EN, 0);
}
void dcmRampToPct(int targetPct, long ms) {   // soft-start ramp, % of 255
  if (targetPct < 0) targetPct = 0;
  if (targetPct > 100) targetPct = 100;
  if (ms < 0) ms = 0;
  if (ms > 30000) ms = 30000;
  dcmRampFrom = dcmDuty;
  dcmRampTo = targetPct * 255 / 100;
  dcmRampMs = ms;
  dcmRampStart = millis();
  dcmRampActive = true;
  dcmOn = true;
  dcmApply();
}

// --- command dispatcher (serial only, 1 line = 1 command) ---
void dispatchCommand(const char* buf) {
  if (!strncmp(buf, "dcm:", 4) && strncmp(buf, "dcm:auto ", 9)) {
    bootStage = 2;                    // manual control cancels the boot sequence
    rpmCtl = false;                   // ... and the speed controller
  }
  if (!strcmp(buf, "stat")) {
    Serial.printf("STAT %s heap=%u maxfree=%u frag=%u\n",
                  FW_VERSION,
                  (unsigned)ESP.getFreeHeap(),
                  (unsigned)ESP.getMaxFreeBlockSize(),
                  (unsigned)ESP.getHeapFragmentation());
  } else if (!strncmp(buf, "dcm:ramp ", 9)) {
    int pct = 0, ms = 0;
    if (sscanf(buf + 9, "%d %d", &pct, &ms) != 2) {
      Serial.printf("ERR dcm:ramp usage: <target%%> <ms>\n");
    } else {
      dcmStepRampActive = false;      // continuous and step ramps are exclusive
      dcmRampToPct(pct, ms);
      syncFlash();                    // video sync marker
      Serial.printf("ACK dcm:ramp %d%% over %ldms (duty %d->%d)\n",
                    pct, dcmRampMs, dcmRampFrom, dcmRampTo);
    }
  } else if (!strncmp(buf, "dcm:ramp-step ", 14)) {
    // usage: dcm:ramp-step <target%> <interval_ms> <inc%>  — staircase
    int pct = 0, ms = 0, inc = 0;
    if (sscanf(buf + 14, "%d %d %d", &pct, &ms, &inc) != 3) {
      Serial.printf("ERR dcm:ramp-step usage: <target%%> <interval_ms> <inc%%>\n");
    } else {
      dcmRampActive = false;          // continuous and step ramps are exclusive
      if (pct < 0) pct = 0;
      if (pct > 100) pct = 100;
      if (ms < 50) ms = 50;
      if (ms > 10000) ms = 10000;
      if (inc < 1) inc = 1;
      if (inc > 51) inc = 51;
      dcmStepTarget = pct * 255 / 100;
      dcmStepInc = inc * 255 / 100;   // inc is in % of full scale
      if (dcmStepInc < 1) dcmStepInc = 1;
      dcmStepIntervalMs = ms;
      dcmStepLast = millis();
      dcmStepRampActive = true;
      dcmOn = true;
      dcmApply();
      syncFlash();                    // video sync marker
      Serial.printf("ACK dcm:ramp-step target=%d%% every=%ldms inc=%d%% (duty %d->%d)\n",
                    pct, dcmStepIntervalMs, inc, dcmDuty, dcmStepTarget);
    }
  } else if (!strncmp(buf, "dcm:speed ", 10)) {
    long v = atol(buf + 10);          // -255..255; sign = direction, 0 = coast
    dcmRampActive = false;
    dcmStepRampActive = false;
    if (v == 0) {
      dcmOff();
    } else {
      dcmDir = (v > 0) ? 1 : -1;
      dcmDuty = (int)constrain((v > 0 ? v : -v), 0, 255);
      dcmOn = true;
      dcmApply();
    }
    syncFlash();                    // video sync marker
    Serial.printf("ACK dcm:speed dir=%d duty=%d\n", dcmDir, dcmDuty);
  } else if (!strcmp(buf, "dcm:brake")) {
    dcmRampActive = false;
    dcmStepRampActive = false;
    dcmOn = true;
    dcmDuty = 0;                      // braked motor: next ramp starts from 0
    digitalWrite(DCM_INA, HIGH);      // both inputs HIGH = short brake
    digitalWrite(DCM_INB, HIGH);
    analogWrite(DCM_EN, 255);
    syncFlash();                    // video sync marker
    Serial.printf("ACK dcm:brake\n");
  } else if (!strcmp(buf, "dcm:off")) {
    dcmOff();                         // coast: EN low, freewheel
    syncFlash();                    // video sync marker
    Serial.printf("ACK dcm:off\n");
  } else if (!strcmp(buf, "adc:read")) {
    int raw = analogRead(A0);
    Serial.printf("ADC raw=%d tout_mV=%d terminalA_mV=%d\n", raw, raw * 1000 / 1023,
                  (int)(raw * 1000.0f / 1023 / ADC_DIVIDER));
  } else if (!strncmp(buf, "adc:cap ", 8)) {
    // usage: adc:cap <interval_us> <n> <pre> [command] — blocking capture into RAM; the
    // command (e.g. dcm:off) is dispatched at sample index <pre>; data printed afterwards.
    // Ramp engines do not advance during the capture (keep n * interval <= 3 s).
    long us = 0, n = 0, pre = 0; int used = 0;
    if (sscanf(buf + 8, "%ld %ld %ld %n", &us, &n, &pre, &used) < 3) {
      Serial.printf("ERR adc:cap usage: <interval_us> <n> <pre> [command]\n");
    } else {
      if (us < 10) us = 10;            // analogRead takes ~10 us; check total_us
      if (n < 1) n = 1;
      if (n > ADC_CAP_MAX) n = ADC_CAP_MAX;
      if (n * us > 3000000L) n = 3000000L / us;
      if (pre < 0) pre = 0;
      const char* cmd = used ? buf + 8 + used : "";
      uint16_t* cap = (uint16_t*)malloc(n * sizeof(uint16_t));
      if (!cap) {
        Serial.printf("ERR adc:cap out of memory\n");
      } else {
        unsigned long t0 = micros(), tCmd = 0;
        for (long k = 0; k < n; k++) {
          while ((long)(micros() - (t0 + (unsigned long)(k * us))) < 0) {}
          if (k == pre && *cmd) { tCmd = micros() - t0; dispatchCommand(cmd); }
          cap[k] = analogRead(A0);
          if (syncLedOn && millis() - syncLedOnAt >= SYNC_FLASH_MS) {
            digitalWrite(SYNC_LED, LOW);
            syncLedOn = false;
          }
          if ((k & 63) == 0) ESP.wdtFeed();
        }
        unsigned long tEnd = micros() - t0;
        Serial.printf("ADC cap n=%ld interval_us=%ld pre=%ld cmd_us=%lu total_us=%lu divider=%.4f\n",
                      n, us, pre, tCmd, tEnd, ADC_DIVIDER);
        for (long k = 0; k < n; k += 32) {
          Serial.print("ADC ");
          for (long j = k; j < n && j < k + 32; j++) {
            Serial.print(cap[j]);
            Serial.print(j + 1 < n && j + 1 < k + 32 ? ',' : '\n');
          }
          yield();
        }
        Serial.printf("ADC end\n");
        free(cap);
      }
    }
  } else if (!strncmp(buf, "rpm:set ", 8)) {
    // usage: rpm:set <rpm> — closed-loop speed (750..3200 rpm); 0 = off. Kicks at 100 % if stopped.
    float ref = atof(buf + 8);
    bootStage = 2;
    if (ref <= 0) {
      rpmCtl = false;
      dcmOff();
    } else {
      rpmRef = constrain(ref, RPM_MIN, RPM_MAX);
      if (!rpmCtl) {                  // fresh reading: rpmFilt may be stale when idle
        ctlI = 0;
        rpmFilt = rpmMeas = rawToRpm(emfProbe(1500, 16, NULL, NULL, NULL));
      }
      rpmCtl = true;
      dcmRampActive = dcmStepRampActive = false;
      dcmOn = true; dcmDir = 1;
      if (rpmFilt < 300) { kickUntil = millis() + 300; dcmDuty = 255; }
      dcmApply();
    }
    syncFlash();                    // video sync marker
    Serial.printf("ACK rpm:set ref=%d\n", (int)(rpmCtl ? rpmRef : 0));
  } else if (!strcmp(buf, "rpm:off")) {
    rpmCtl = false;
    dcmOff();
    syncFlash();                    // video sync marker
    Serial.printf("ACK rpm:off\n");
  } else if (!strcmp(buf, "tel:on")) {
    telOn = true;                     // one TEL line per CTL_MS probe
    Serial.printf("ACK tel:on period_ms=%lu\n", CTL_MS);
  } else if (!strcmp(buf, "tel:off")) {
    telOn = false;
    Serial.printf("ACK tel:off\n");
  } else if (!strcmp(buf, "adc:zero")) {
    adcZero = emfProbe(200, 64, NULL, NULL, NULL);   // call with the motor stopped
    Serial.printf("ACK adc:zero raw=%.1f\n", adcZero);
  } else if (!strncmp(buf, "adc:emf", 7)) {
    // usage: adc:emf [settle_us] [n] — tachometer at any duty: EN low for settle_us so the
    // winding current dies, then n ADC reads of the open-circuit terminal (= back-EMF), then
    // the PWM is restored. ~2 ms of coast: the speed drops < 0.5 %.
    long settle = 1500, n = 8;
    sscanf(buf + 7, "%ld %ld", &settle, &n);
    if (settle < 200) settle = 200;
    if (settle > 20000) settle = 20000;
    if (n < 1) n = 1;
    if (n > 64) n = 64;
    bool driving = dcmOn && !dcmRampActive && !dcmStepRampActive;
    int mn, mx; unsigned long tOff;
    float raw = emfProbe(settle, n, &mn, &mx, &tOff);
    float mv = raw * 1000.0f / 1023 / ADC_DIVIDER;
    long sum = (long)(raw * n);
    Serial.printf("EMF terminalA_mV=%d raw_mean=%.1f raw_min=%d raw_max=%d coast_us=%lu duty=%d rpm=%d %s\n",
                  (int)mv, raw, mn, mx, tOff, dcmDuty, (int)rawToRpm(raw), driving ? "drive" : "idle");
    (void)sum;
  } else if (!strncmp(buf, "dcm:auto ", 9)) {
    dcmAutoBoot = (atoi(buf + 9) != 0);   // boot sequence flag (RAM-held)
    if (!dcmAutoBoot && bootStage == 1) {  // disabled mid-sequence: stop now
      dcmOff();
      bootStage = 2;
    }
    syncFlash();                    // video sync marker
    Serial.printf("ACK dcm:auto boot-soft-start=%s\n", dcmAutoBoot ? "ON" : "OFF");
  } else {
    Serial.printf("ERR unknown cmd '%s' (stat|dcm:*|adc:*|rpm:*|tel:*)\n", buf);
  }
}

void setup() {
  Serial.begin(115200);
  Serial.printf("[RESET] %s\n", ESP.getResetReason().c_str());
  Serial.printf("[FW] %s\n", FW_VERSION);

  // DC motor (L293D dual-bridge parallel)
  pinMode(DCM_INA, OUTPUT);
  pinMode(DCM_INB, OUTPUT);
  pinMode(DCM_EN, OUTPUT);
  pinMode(SYNC_LED, OUTPUT);
  digitalWrite(SYNC_LED, LOW);       // sync LED off until the first command
  dcmOff();                          // idle: EN low (motor freewheels)
  delay(20);
  adcZero = emfProbe(200, 64, NULL, NULL, NULL);   // motor at rest after reset
  bootAt = millis();                 // boot sequence starts BOOT_START_MS from now
  Serial.printf("[DCM] L293D ready (EN=IO15 PWM, 1A+3A=IO12, 2A+4A=IO13)\n");
  Serial.printf("[DCM] boot sequence armed: in %lus, %d->%d%% over %lds, hold %lus,"
                " coast (dcm:auto 0 to disable)\n", BOOT_START_MS / 1000,
                BOOT_FROM_PCT, BOOT_TO_PCT, BOOT_RAMP_MS / 1000, BOOT_HOLD_MS / 1000);
  Serial.println("Ready. Type a command (stat | dcm:speed 255 | dcm:ramp 80 5000 | adc:read | ...)");
}

unsigned long lastHb = 0;

void loop() {
  // serial command reader (non-blocking, 1 line = 1 command)
  static char cmdBuf[132];
  static int cmdLen = 0;
  while (Serial.available()) {
    char ch = (char)Serial.read();
    if (ch == '\n' || ch == '\r') {
      if (cmdLen > 0) {
        cmdBuf[cmdLen] = '\0';
        dispatchCommand(cmdBuf);
        cmdLen = 0;
      }
    } else if (cmdLen < 128) {
      cmdBuf[cmdLen++] = ch;
    } else {
      cmdLen = 0;                     // overlong line: drop it
    }
  }

  unsigned long now = millis();

  // sync LED: end the flash started by syncFlash()
  if (syncLedOn && now - syncLedOnAt >= SYNC_FLASH_MS) {
    digitalWrite(SYNC_LED, LOW);
    syncLedOn = false;
  }

  // heartbeat over serial (500 ms) — proves the loop is alive
  if (now - lastHb >= blinkInterval) {
    lastHb = now;
    Serial.printf("[HB] %lu\n", (unsigned long)now);
  }

  // tachometer probe + closed-loop speed control (see CTL_* above)
  if ((rpmCtl || telOn) && now - ctlLast >= CTL_MS) {
    ctlLast = now;
    rpmMeas = rawToRpm(emfProbe(1500, 16, NULL, NULL, NULL));
    rpmFilt += CTL_ALPHA * (rpmMeas - rpmFilt);
    if (rpmCtl) {
      if ((long)(kickUntil - now) > 0 && rpmFilt < KICK_FRAC * rpmRef) {
        dcmDuty = 255;
      } else {
        float e = rpmRef - rpmFilt, ff = ffDuty(rpmRef);
        float u = ff + CTL_KP * e + ctlI;
        if ((u > DUTY_FLOOR && u < 255) || (u >= 255 && e < 0) || (u <= DUTY_FLOOR && e > 0))
          ctlI += CTL_KI * e * CTL_MS / 1000.0f;          // anti-windup
        u = ff + CTL_KP * e + ctlI;
        dcmDuty = (int)constrain(u, (float)DUTY_FLOOR, 255.0f);
      }
      dcmOn = true; dcmDir = 1;
      dcmApply();
    }
    if (telOn)
      Serial.printf("TEL t=%lu duty=%d rpm=%d filt=%d ref=%d\n", now, dcmOn && dcmDuty ? dcmDuty : 0,
                    (int)rpmMeas, (int)rpmFilt, (int)(rpmCtl ? rpmRef : 0));
  }

  // DC motor boot sequence: runs once, BOOT_START_MS after boot
  if (dcmAutoBoot && bootStage == 0 && now - bootAt >= BOOT_START_MS) {
    bootStage = 1;
    Serial.printf("[DCM] boot sequence: %d%% -> %d%% over %lds\n",
                  BOOT_FROM_PCT, BOOT_TO_PCT, BOOT_RAMP_MS / 1000);
    dcmStepRampActive = false;
    dcmDir = 1;
    dcmDuty = BOOT_FROM_PCT * 255 / 100;   // start the ramp from 50%, not 0
    dcmRampToPct(BOOT_TO_PCT, BOOT_RAMP_MS);
  }
  if (bootStage == 1 && now - bootAt >= BOOT_START_MS + BOOT_RAMP_MS + BOOT_HOLD_MS) {
    bootStage = 2;
    dcmOff();
    Serial.println("[DCM] boot sequence done: coast");
  }
  // DC motor continuous ramp engine (recomputes duty every loop pass)
  if (dcmRampActive) {
    long el = (long)(now - dcmRampStart);
    if (el >= dcmRampMs) {
      dcmDuty = dcmRampTo;
      dcmRampActive = false;
    } else if (dcmRampMs > 0) {
      dcmDuty = dcmRampFrom + (dcmRampTo - dcmRampFrom) * (int)el / dcmRampMs;
    }
    dcmApply();
  }
  // DC motor discrete (staircase) ramp: +/-inc every interval until target
  if (dcmStepRampActive && now - dcmStepLast >= dcmStepIntervalMs) {
    dcmStepLast = now;
    if (dcmDuty < dcmStepTarget) dcmDuty = min(dcmDuty + dcmStepInc, dcmStepTarget);
    else                         dcmDuty = max(dcmDuty - dcmStepInc, dcmStepTarget);
    dcmApply();
    if (dcmDuty == dcmStepTarget) dcmStepRampActive = false;  // reached
  }
  delay(5);
}

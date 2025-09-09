#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>
#include <Adafruit_MCP23X17.h>

// ===================== PCA9685 (4块 0x40~0x43: 原64通道) =====================
Adafruit_PWMServoDriver pwmBoards[4] = {
  Adafruit_PWMServoDriver(0x40), Adafruit_PWMServoDriver(0x41),
  Adafruit_PWMServoDriver(0x42), Adafruit_PWMServoDriver(0x43)
};
// 另外一块用于24V外设的 PCA9685，地址 0x44
Adafruit_PWMServoDriver pwm24V = Adafruit_PWMServoDriver(0x44);
bool pwm24VReady = false;
// 硬件为高电平有效，关闭反相
const bool PWM24V_INVERT = false;

// 辅助：按百分比设置 0x44 通道占空比（0~100）
void pwm24vWritePercent(uint8_t channel, int percent) {
  if (!pwm24VReady) return;
  if (percent < 0) percent = 0;
  if (percent > 100) percent = 100;
  int duty = map(percent, 0, 100, 0, 4095);
  if (PWM24V_INVERT) duty = 4095 - duty;
  pwm24V.setPWM(channel, 0, duty);
}

// I2C 设备存在性探测
bool i2cPresent(uint8_t address) {
  Wire.beginTransmission(address);
  return (Wire.endTransmission() == 0);
}

// ===================== MCP23017 (4块, 方向控制) =====================
Adafruit_MCP23X17 dirBoards[4];

// ===================== 继电器引脚 =====================
#define RELAY_POWER 2   // 电磁铁电源继电器
#define RELAY_HEAT  3   // 热控板电源继电器（必须在电磁铁电源开后才能开）

// ===================== 状态标记 =====================
bool powerOn = false;
bool heatOn = false;

void setup() {
  Serial.begin(115200);
  Wire.begin();
  Wire.setClock(400000); // 400kHz I2C 提高稳定性

  // 初始化 PWM 驱动器
  for (int i = 0; i < 4; i++) {
    pwmBoards[i].begin();
    pwmBoards[i].setPWMFreq(1000); // 1kHz
  }

  // 24V PCA9685 (0x44)
  // 启动时扫描一次 I2C，辅助诊断
  Serial.print("I2C scan: ");
  bool any = false;
  for (uint8_t a = 1; a < 127; a++) {
    if (i2cPresent(a)) {
      any = true;
      Serial.print("0x");
      if (a < 16) Serial.print('0');
      Serial.print(a, HEX);
      Serial.print(' ');
    }
  }
  if (!any) Serial.print("<none>");
  Serial.println();

  if (i2cPresent(0x44)) {
    pwm24V.begin();
    pwm24V.setPWMFreq(1000); // 1kHz
    pwm24VReady = true;
    Serial.println("PCA9685 0x44 OK");
  } else {
    pwm24VReady = false;
    Serial.println("ERR: PCA9685 0x44 init fail");
  }

  // 初始化 MCP23017
  for (int i = 0; i < 4; i++) {
    if (!dirBoards[i].begin_I2C(0x20 + i)) {
      Serial.print("MCP23017 ");
      Serial.print(i);
      Serial.println(" 初始化失败");
    }
    for (int pin = 0; pin < 16; pin++) {
      dirBoards[i].pinMode(pin, OUTPUT);
      dirBoards[i].digitalWrite(pin, LOW);
    }
  }

  // 继电器初始化
  pinMode(RELAY_POWER, OUTPUT);
  pinMode(RELAY_HEAT, OUTPUT);
  digitalWrite(RELAY_POWER, LOW);
  digitalWrite(RELAY_HEAT, LOW);
}

void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    // ===================== 电源控制 =====================
    if (cmd == "POWER ON") {
      digitalWrite(RELAY_POWER, HIGH);
      powerOn = true;
      Serial.println("POWER ON OK");
    }
    else if (cmd == "POWER OFF") {
      digitalWrite(RELAY_POWER, LOW);
      digitalWrite(RELAY_HEAT, LOW); // 强制热控关闭
      powerOn = false;
      heatOn = false;
      Serial.println("POWER OFF OK");
    }
    // ===================== 热控控制（继电器上电） =====================
    else if (cmd == "HEAT ON") {
      if (powerOn) { // 必须先开电源
        digitalWrite(RELAY_HEAT, HIGH);
        heatOn = true;
        Serial.println("HEAT ON OK");
      } else {
        Serial.println("ERR: POWER must be ON first");
      }
    }
    else if (cmd == "HEAT OFF") {
      digitalWrite(RELAY_HEAT, LOW);
      heatOn = false;
      Serial.println("HEAT OFF OK");
    }
    // ===================== 24V 外设：制冷凝固 =====================
    else if (cmd == "COOL_SOLID ON") {
      // 通道: 3 泵, 0/2 制冷片，仅0或100%
      // 启动时：先开泵，0.5s后开制冷片
      pwm24vWritePercent(3, 100);
      delay(500);
      pwm24vWritePercent(0, 100);
      pwm24vWritePercent(2, 100);
      Serial.println("COOL_SOLID ON OK");
    }
    else if (cmd == "COOL_SOLID OFF") {
      // 关闭时：先关制冷片，0.5s后关泵
      pwm24vWritePercent(0, 0);
      pwm24vWritePercent(2, 0);
      delay(500);
      pwm24vWritePercent(3, 0);
      Serial.println("COOL_SOLID OFF OK");
    }
    // ===================== 24V 外设：电磁铁散热 =====================
    else if (cmd == "EM_COOL ON") {
      pwm24vWritePercent(4, 100);
      pwm24vWritePercent(14, 100);
      Serial.println("EM_COOL ON OK");
    }
    else if (cmd == "EM_COOL OFF") {
      pwm24vWritePercent(4, 0);
      pwm24vWritePercent(14, 0);
      Serial.println("EM_COOL OFF OK");
    }
    // ===================== 24V 外设：电阻加热片（ch1: 0/15/100%） =====================
    else if (cmd.startsWith("HEATER ")) {
      int val = cmd.substring(7).toInt();
      int pwm = 0;
      if (val <= 0) pwm = 0;
      else if (val < 50) pwm = 15; // 兼容传入任意中间值，<50 视为15
      else pwm = 100;
      pwm24vWritePercent(1, pwm);
      Serial.print("HEATER SET "); Serial.print(pwm); Serial.println("% OK");
    }
    // ===================== 24V 外设：溶剂加入泵（ch5: 30%） =====================
    else if (cmd == "SOLVENT START") {
      pwm24vWritePercent(5, 30);
      Serial.println("SOLVENT START OK");
    }
    else if (cmd == "SOLVENT STOP") {
      pwm24vWritePercent(5, 0);
      Serial.println("SOLVENT STOP OK");
    }
    // ===================== 通道控制 =====================
    else {
      int ch, duty, dir;
      if (sscanf(cmd.c_str(), "SET %d %d %d", &ch, &duty, &dir) == 3) {
        int boardIndex = ch / 16;
        int channelIndex = ch % 16;
        if (boardIndex < 4) {
          int dutyVal = map(duty, 0, 100, 0, 4095);
          pwmBoards[boardIndex].setPWM(channelIndex, 0, dutyVal);
          dirBoards[boardIndex].digitalWrite(channelIndex, dir);
          Serial.print("SET OK CH=");
          Serial.print(ch);
          Serial.print(" Duty=");
          Serial.print(duty);
          Serial.print(" Dir=");
          Serial.println(dir);
        } else {
          Serial.println("ERR: Invalid channel");
        }
      }
      // ===================== SEQ 脚本执行 =====================
      else if (cmd.startsWith("SEQ")) {
        runSequence(cmd.substring(3));
      }
    }
  }
}

// ===================== 简易 SEQ 脚本解释器 =====================
void runSequence(String seq) {
  Serial.println("SEQ START");
  // 格式示例: "POWER ON; SET 0 50 1; WAIT 5000; HEAT ON; WAIT 10000; HEAT OFF; POWER OFF;"
  int idx = 0;
  while (idx < seq.length()) {
    int next = seq.indexOf(';', idx);
    if (next == -1) break;
    String token = seq.substring(idx, next);
    token.trim();
    if (token.length() > 0) {
      Serial.print("SEQ CMD: ");
      Serial.println(token);
      if (token.startsWith("WAIT")) {
        int ms = token.substring(4).toInt();
        delay(ms);
      } else {
        Serial.println(token);
        Serial.write(token.c_str(), token.length());
        Serial.write('\n');
      }
    }
    idx = next + 1;
  }
  Serial.println("SEQ END");
}

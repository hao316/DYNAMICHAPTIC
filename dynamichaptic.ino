#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>
#include <Adafruit_MCP23X17.h>

// 四块 PCA9685 用于PWM控制
Adafruit_PWMServoDriver pwmBoards[4] = {
  Adafruit_PWMServoDriver(0x40), Adafruit_PWMServoDriver(0x41),
  Adafruit_PWMServoDriver(0x42), Adafruit_PWMServoDriver(0x43)
};

// 四块 MCP23017 用于方向控制
Adafruit_MCP23X17 dirBoards[4];

#define RELAY_PIN 8  // 继电器控制引脚

void setup() {
  Serial.begin(115200);
  Wire.begin();

  // 初始化 PWM 驱动器
  for (int i = 0; i < 4; i++) {
    pwmBoards[i].begin();
    pwmBoards[i].setPWMFreq(1000); // 1kHz
  }
  
  // 初始化 MCP23017 方向控制
  for (int i = 0; i < 4; i++) {
    if (!dirBoards[i].begin_I2C(0x20 + i)) {
      Serial.print("MCP23017 ");
      Serial.print(i);
      Serial.println(" 初始化失败");
    }
    // 设置所有引脚为输出
    for (int pin = 0; pin < 16; pin++) {
      dirBoards[i].pinMode(pin, OUTPUT);
    }
  }

  // 继电器控制初始化
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, LOW); // 默认关闭电源
}

void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    // 电源开关指令
    if (cmd == "POWER ON") {
      digitalWrite(RELAY_PIN, HIGH);
      Serial.println("POWER ON OK");
    } 
    else if (cmd == "POWER OFF") {
      digitalWrite(RELAY_PIN, LOW);
      Serial.println("POWER OFF OK");
    } 
    else {
      // 格式: "SET ch duty dir"
      int ch, duty, dir;
      if (sscanf(cmd.c_str(), "SET %d %d %d", &ch, &duty, &dir) == 3) {
        int boardIndex = ch / 16;
        int channelIndex = ch % 16;

        int dutyVal = map(duty, 0, 100, 0, 4095);

        // 调试信息
        Serial.print("CH:");
        Serial.print(ch);
        Serial.print(" Board:");
        Serial.print(boardIndex);
        Serial.print(" Channel:");
        Serial.print(channelIndex);
        Serial.print(" Duty:");
        Serial.print(duty);
        Serial.print(" Dir:");
        Serial.println(dir);

        // 设置 PWM 占空比
        pwmBoards[boardIndex].setPWM(channelIndex, 0, dutyVal);

        // 方向控制：数字信号（1=正向，0=反向）
        dirBoards[boardIndex].digitalWrite(channelIndex, dir);

        Serial.println("SET OK");
      }
    }
  }
}

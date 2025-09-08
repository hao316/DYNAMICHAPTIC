import sys
from PySide6.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QLabel, QDialog, QComboBox, QGridLayout
)
from PySide6.QtGui import QColor, QPixmap, QPainter, QLinearGradient, QFont
from PySide6.QtCore import Qt
import serial

# 串口设置
SERIAL_PORT = "COM3"  # 修改为实际端口
BAUD_RATE = 115200
ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)

# 占空比选项
PWM_LEVELS = [0, 25, 50, 75, 100]

# 占空比颜色映射（可改为其他渐变）
COLORMAP = {
    0: (68, 1, 84),
    25: (59, 82, 139),
    50: (33, 145, 140),
    75: (94, 201, 98),
    100: (253, 231, 37),
}

def get_color_for_pwm(pwm):
    return COLORMAP.get(pwm, (200, 200, 200))

def get_text_color(r, g, b):
    yiq = ((r*299)+(g*587)+(b*114))/1000
    return QColor(0, 0, 0) if yiq > 128 else QColor(255, 255, 255)

# ------------------ 通道设置弹窗 ------------------
class ChannelDialog(QDialog):
    def __init__(self, idx, current_pwm, current_dir, parent=None):
        super().__init__(parent)
        self.idx = idx
        self.setWindowTitle(f"设置通道 {idx}")

        layout = QVBoxLayout()

        # 占空比选择
        self.pwm_selector = QComboBox()
        for level in PWM_LEVELS:
            self.pwm_selector.addItem(f"{level}%", level)
        self.pwm_selector.setCurrentText(f"{current_pwm}%")

        # 方向选择
        self.dir_selector = QComboBox()
        self.dir_selector.addItem("N", 0)
        self.dir_selector.addItem("S", 1)
        self.dir_selector.setCurrentIndex(current_dir)

        layout.addWidget(QLabel("占空比:"))
        layout.addWidget(self.pwm_selector)
        layout.addWidget(QLabel("方向:"))
        layout.addWidget(self.dir_selector)

        # 确认按钮
        ok_button = QPushButton("确定")
        ok_button.clicked.connect(self.accept)
        layout.addWidget(ok_button)

        self.setLayout(layout)

    def get_values(self):
        return (self.pwm_selector.currentData(), self.dir_selector.currentData())

# ------------------ 主控制面板 ------------------
class ControlPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("64通道 PWM 控制面板")
        self.resize(950, 700)

        # 每个通道状态字典
        self.channel_states = {i: {"pwm":0, "dir":0} for i in range(64)}
        self.power_on = False

        # 主布局
        main_layout = QHBoxLayout()
        left_layout = QVBoxLayout()
        self.grid_layout = QGridLayout()

        # 电源按钮
        self.power_btn = QPushButton("电源 OFF")
        self.power_btn.setCheckable(True)
        self.power_btn.clicked.connect(self.toggle_power)
        left_layout.addWidget(self.power_btn, alignment=Qt.AlignCenter)

        # 64 通道按钮
        self.buttons = {}
        for row in range(8):
            for col in range(8):
                idx = self.snake_index(row, col)
                btn = QPushButton()
                btn.setFixedSize(60, 60)
                btn.clicked.connect(lambda _, i=idx: self.open_channel_dialog(i))
                self.grid_layout.addWidget(btn, row, col)
                self.buttons[idx] = btn

        left_layout.addLayout(self.grid_layout)
        main_layout.addLayout(left_layout)

        # 右侧 scalebar
        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel("占空比颜色标尺"), alignment=Qt.AlignHCenter)
        
        # 创建标尺容器
        scalebar_widget = QWidget()
        scalebar_layout = QVBoxLayout(scalebar_widget)
        scalebar_layout.setSpacing(0)
        
        # 从上到下创建标尺条和标签
        for i, level in enumerate(reversed(PWM_LEVELS)):
            # 标签
            label = QLabel(f"{level}%")
            label.setAlignment(Qt.AlignCenter)
            label.setFixedHeight(20)
            scalebar_layout.addWidget(label)
            
            # 颜色条
            color_bar = QLabel()
            color_bar.setFixedSize(60, 30)
            r, g, b = COLORMAP[level]
            color_bar.setStyleSheet(f"background-color: rgb({r},{g},{b}); border: 1px solid black;")
            scalebar_layout.addWidget(color_bar)
        
        right_layout.addWidget(scalebar_widget, alignment=Qt.AlignHCenter)

        main_layout.addLayout(right_layout)
        self.setLayout(main_layout)

        self.update_buttons()

    def snake_index(self, row, col):
        """蛇形走线映射"""
        if row % 2 == 0:
            return row*8 + col
        else:
            return row*8 + (7-col)

    def toggle_power(self):
        if self.power_btn.isChecked():
            ser.write(b"POWER ON\n")
            self.power_on = True
            self.power_btn.setText("电源 ON")
        else:
            ser.write(b"POWER OFF\n")
            self.power_on = False
            self.power_btn.setText("电源 OFF")
        self.update_buttons()

    def open_channel_dialog(self, idx):
        if not self.power_on:
            return
        state = self.channel_states[idx]
        dlg = ChannelDialog(idx, state["pwm"], state["dir"], self)
        if dlg.exec() == QDialog.Accepted:
            pwm, direction = dlg.get_values()
            self.channel_states[idx]["pwm"] = pwm
            self.channel_states[idx]["dir"] = direction
            self.update_buttons()
            # 串口发送
            cmd = f"SET {idx} {pwm} {direction}\n"
            ser.write(cmd.encode())

    def update_buttons(self):
        for idx, btn in self.buttons.items():
            state = self.channel_states[idx]
            if not self.power_on:
                btn.setEnabled(False)
                btn.setStyleSheet("background-color: gray; color: white;")
                btn.setText(f"{idx}\nOFF")
                continue
            btn.setEnabled(True)
            pwm = state["pwm"]
            direction = state["dir"]
            r, g, b = get_color_for_pwm(pwm)
            text_color = get_text_color(r, g, b)
            btn.setStyleSheet(f"background-color: rgb({r},{g},{b}); color: {text_color.name()};")
            btn.setFont(QFont("Arial", 10, QFont.Bold))
            direction_text = "N" if direction==0 else "S"
            btn.setText(f"{idx}\n{direction_text}")



# ------------------ 程序入口 ------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ControlPanel()
    window.show()
    sys.exit(app.exec())

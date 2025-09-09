# control_gui.py
import sys
import time
import serial
import serial.tools.list_ports
from functools import partial
from PySide6.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QLabel, QDialog, QComboBox, QGridLayout, QTextEdit, QMessageBox,
    QSpinBox, QFileDialog
)
from PySide6.QtGui import QColor, QFont, QPixmap, QPainter, QLinearGradient
from PySide6.QtCore import Qt, Slot

# ----------------- 配置 -----------------
SERIAL_PORT = "COM3"   # <-- 修改为你实际串口，或留空使用 port 自动发现
BAUD_RATE = 115200
PWM_LEVELS = [0, 25, 50, 75, 100]

# 离散颜色映射（你可以改为更平滑的插值）
COLORMAP = {
    0: (68, 1, 84),
    25: (59, 82, 139),
    50: (33, 145, 140),
    75: (94, 201, 98),
    100: (253, 231, 37),
}

def get_color_for_pwm(p):
    return COLORMAP.get(p, (200,200,200))

def get_text_color(r,g,b):
    yiq = ((r*299)+(g*587)+(b*114))/1000
    return QColor(0,0,0) if yiq > 128 else QColor(255,255,255)

# ----------------- 串口辅助 -----------------
def find_arduino_port():
    ports = list(serial.tools.list_ports.comports())
    for p in ports:
        desc = (p.description or "").lower()
        if "arduino" in desc or "ch340" in desc or "usb-serial" in desc:
            return p.device
    return None

class SerialWrapper:
    def __init__(self, port=None, baud=115200):
        self.ser = None
        self.port = port
        self.baud = baud
        if not port:
            port = find_arduino_port()
        if port:
            try:
                self.ser = serial.Serial(port, baud, timeout=0.5)
                time.sleep(0.1)
            except Exception as e:
                self.ser = None
                print("Serial open error:", e)

    def is_open(self):
        return self.ser is not None and self.ser.is_open

    def write(self, s: str):
        if not self.is_open():
            raise RuntimeError("Serial not open")
        self.ser.write((s + "\n").encode("utf-8"))

    def close(self):
        if self.is_open():
            self.ser.close()

# ----------------- 通道设置对话框 -----------------
class ChannelDialog(QDialog):
    def __init__(self, idx, cur_pwm, cur_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"设置通道 {idx}")
        self.idx = idx
        self.resize(220, 120)
        layout = QVBoxLayout(self)

        self.pwm_combo = QComboBox()
        for v in PWM_LEVELS:
            self.pwm_combo.addItem(f"{v}%", v)
        self.pwm_combo.setCurrentText(f"{cur_pwm}%")

        self.dir_combo = QComboBox()
        self.dir_combo.addItem("N", 0)
        self.dir_combo.addItem("S", 1)
        self.dir_combo.setCurrentIndex(cur_dir)

        layout.addWidget(QLabel("占空比:"))
        layout.addWidget(self.pwm_combo)
        layout.addWidget(QLabel("方向:"))
        layout.addWidget(self.dir_combo)

        btn_ok = QPushButton("确定")
        btn_ok.clicked.connect(self.accept)
        layout.addWidget(btn_ok)

    def values(self):
        return self.pwm_combo.currentData(), self.dir_combo.currentData()

# ----------------- 主窗口 -----------------
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("64ch + Heat Control GUI (PySide6)")
        self.resize(1200, 720)

        # 串口
        port = SERIAL_PORT if SERIAL_PORT else find_arduino_port()
        if not port:
            QMessageBox.warning(self, "串口", "未指定串口且未自动检测到 Arduino，启动时请手动指定串口。")
        try:
            self.serial = SerialWrapper(port, BAUD_RATE)
        except Exception as e:
            self.serial = SerialWrapper(None, BAUD_RATE)
        if not self.serial.is_open():
            print("串口未打开，GUI 仍可本地操作，但无法下发指令。")

        # 设备逻辑状态（GUI 端缓存）
        self.channel_states = {i: {"pwm":0, "dir":0} for i in range(64)}
        self.power_on = False
        self.heat_on = False
        self.cool_solid_on = False
        self.em_cool_on = False
        self.solvent_on = False

        # 布局：三列
        root = QHBoxLayout(self)

        # 左列：8x8 矩阵
        left_col = QVBoxLayout()
        left_col.addWidget(QLabel("64 通道（蛇形排列）"), alignment=Qt.AlignHCenter)
        grid = QGridLayout()
        self.btns = {}
        for r in range(8):
            for c in range(8):
                idx = self.snake_index(r, c)
                btn = QPushButton()
                btn.setFixedSize(72, 72)
                btn.clicked.connect(partial(self.on_channel_clicked, idx))
                grid.addWidget(btn, r, c)
                self.btns[idx] = btn
        left_col.addLayout(grid)

        # scalebar
        left_col.addWidget(QLabel("颜色标尺"), alignment=Qt.AlignHCenter)
        left_col.addWidget(self.make_scalebar_widget(), alignment=Qt.AlignHCenter)
        root.addLayout(left_col, 3)

        # 中列：热控及手动按钮
        mid_col = QVBoxLayout()
        mid_col.addWidget(QLabel("手动控制"), alignment=Qt.AlignHCenter)

        # POWER 按钮
        self.btn_power = QPushButton("POWER OFF")
        self.btn_power.setCheckable(True)
        self.btn_power.clicked.connect(self.on_power_toggled)
        mid_col.addWidget(self.btn_power)

        # HEAT 控制（ON/OFF）
        self.btn_heat = QPushButton("HEAT OFF")
        self.btn_heat.setCheckable(True)
        self.btn_heat.clicked.connect(self.on_heat_toggled)
        mid_col.addWidget(self.btn_heat)

        # 电阻加热片模式（0/15/100）
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Heater Mode:"))
        self.heater_mode = QComboBox()
        self.heater_mode.addItem("0% (OFF)", 0)
        self.heater_mode.addItem("15% (Keep Warm)", 15)
        self.heater_mode.addItem("100% (Melt)", 100)
        self.heater_mode.currentIndexChanged.connect(self.on_heater_mode_changed)
        mode_row.addWidget(self.heater_mode)
        mid_col.addLayout(mode_row)

        # 制冷凝固（ON/OFF）
        self.btn_coolsolid = QPushButton("COOL_SOLID OFF")
        self.btn_coolsolid.setCheckable(True)
        self.btn_coolsolid.clicked.connect(self.on_coolsolid_toggled)
        mid_col.addWidget(self.btn_coolsolid)

        # 电磁铁散热（ON/OFF）
        self.btn_emcool = QPushButton("EM_COOL OFF")
        self.btn_emcool.setCheckable(True)
        self.btn_emcool.clicked.connect(self.on_emcool_toggled)
        mid_col.addWidget(self.btn_emcool)

        # 溶剂泵（ON/OFF）
        self.btn_solvent = QPushButton("SOLVENT OFF")
        self.btn_solvent.setCheckable(True)
        self.btn_solvent.clicked.connect(self.on_solvent_toggled)
        mid_col.addWidget(self.btn_solvent)

        mid_col.addSpacing(10)
        mid_col.addWidget(QLabel("快速命令（示例）"))
        # quick command examples
        ex_btns = [
            ("All CH 0", self.quick_all_zero),
            ("All CH 50%", self.quick_all_50),
            ("Turn OFF All", self.quick_all_off),
        ]
        for text, cb in ex_btns:
            b = QPushButton(text)
            b.clicked.connect(cb)
            mid_col.addWidget(b)

        root.addLayout(mid_col, 1)

        # 右列：SEQ 输入 + 日志
        right_col = QVBoxLayout()
        right_col.addWidget(QLabel("SEQ 脚本输入（用 ; 分隔命令，命令末尾可选 ; ）"))
        self.seq_edit = QTextEdit()
        self.seq_edit.setAcceptRichText(False)
        right_col.addWidget(self.seq_edit)

        hbox = QHBoxLayout()
        btn_send_seq = QPushButton("发送 SEQ")
        btn_send_seq.clicked.connect(self.on_send_seq)
        btn_load = QPushButton("加载 .seq 文件")
        btn_load.clicked.connect(self.on_load_seq_file)
        hbox.addWidget(btn_send_seq)
        hbox.addWidget(btn_load)
        right_col.addLayout(hbox)

        right_col.addWidget(QLabel("日志"))
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        right_col.addWidget(self.log)

        root.addLayout(right_col, 2)

        self.update_all_buttons()

    # ---------- UI helpers ----------
    def make_scalebar_widget(self, w=40, h=200):
        pm = QPixmap(w, h)
        p = QPainter(pm)
        grad = QLinearGradient(0,0,0,h)
        lvls = sorted(COLORMAP.keys())
        for i,l in enumerate(lvls):
            r,g,b = COLORMAP[l]
            grad.setColorAt(i/(len(lvls)-1), QColor(r,g,b))
        p.fillRect(0,0,w,h,grad)
        p.end()
        lbl = QLabel()
        lbl.setPixmap(pm)
        return lbl

    def snake_index(self, row, col):
        return row*8 + (col if row % 2 == 0 else (7-col))

    def log_msg(self, text):
        ts = time.strftime("%H:%M:%S")
        self.log.append(f"[{ts}] {text}")
        # auto scroll
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def send_serial(self, s: str):
        try:
            if not self.serial.is_open():
                raise RuntimeError("串口未打开")
            self.serial.write(s)
            self.log_msg("TX: " + s)
            # 非阻塞读取一行回显（短超时）
            time.sleep(0.03)
            # Try to read available bytes if any (best-effort)
            if self.serial.ser and self.serial.ser.in_waiting:
                resp = self.serial.ser.read(self.serial.ser.in_waiting).decode(errors='ignore')
                for line in resp.splitlines():
                    self.log_msg("RX: " + line)
        except Exception as e:
            self.log_msg("ERR: " + str(e))
            QMessageBox.critical(self, "串口错误", str(e))

    # ---------- channel UI ----------
    def update_all_buttons(self):
        for idx, btn in self.btns.items():
            st = self.channel_states[idx]
            pwm = st["pwm"]; d = st["dir"]
            r,g,b = get_color_for_pwm(pwm)
            tc = get_text_color(r,g,b)
            btn.setStyleSheet(f"background-color: rgb({r},{g},{b}); color: {tc.name()};")
            btn.setFont(QFont("Arial", 10, QFont.Bold))
            btn.setText(f"{idx}\n{pwm}% {'N' if d==0 else 'S'}")
            btn.setEnabled(True if self.power_on else False)

        # update mid buttons text
        self.btn_power.setText("POWER ON" if self.power_on else "POWER OFF")
        self.btn_heat.setText("HEAT ON" if self.heat_on else "HEAT OFF")
        self.btn_coolsolid.setText("COOL_SOLID ON" if self.cool_solid_on else "COOL_SOLID OFF")
        self.btn_emcool.setText("EM_COOL ON" if self.em_cool_on else "EM_COOL OFF")
        self.btn_solvent.setText("SOLVENT ON" if self.solvent_on else "SOLVENT OFF")

    # ---------- user actions ----------
    def on_channel_clicked(self, idx):
        if not self.power_on:
            QMessageBox.information(self, "提示", "请先打开主电源（POWER ON）")
            return
        st = self.channel_states[idx]
        dlg = ChannelDialog(idx, st["pwm"], st["dir"], self)
        if dlg.exec():
            pwm, dirv = dlg.values()
            self.channel_states[idx]["pwm"] = pwm
            self.channel_states[idx]["dir"] = dirv
            self.update_all_buttons()
            self.send_serial(f"SET {idx} {pwm} {dirv}")

    def on_power_toggled(self):
        new = self.btn_power.isChecked()
        # decide sending logic: our Arduino expects "POWER ON"/"POWER OFF"
        if new:
            self.send_serial("POWER ON")
            self.power_on = True
        else:
            self.send_serial("POWER OFF")
            # also clear heat etc flags
            self.power_on = False
            self.heat_on = False
            self.cool_solid_on = False
            self.em_cool_on = False
            self.solvent_on = False
        self.update_all_buttons()

    def on_heat_toggled(self):
        new = self.btn_heat.isChecked()
        if new:
            self.send_serial("HEAT ON")
            # Arduino may reply ERR if POWER not on; still update local flag optimistically
            self.heat_on = True
        else:
            self.send_serial("HEAT OFF")
            self.heat_on = False
        self.update_all_buttons()

    def on_heater_mode_changed(self):
        # 发送 HEATER <0|15|100>
        val = self.heater_mode.currentData()
        self.send_serial(f"HEATER {val}")

    def on_coolsolid_toggled(self):
        new = self.btn_coolsolid.isChecked()
        if new:
            self.send_serial("COOL_SOLID ON")
            self.cool_solid_on = True
        else:
            self.send_serial("COOL_SOLID OFF")
            self.cool_solid_on = False
        self.update_all_buttons()

    def on_emcool_toggled(self):
        new = self.btn_emcool.isChecked()
        if new:
            self.send_serial("EM_COOL ON")
            self.em_cool_on = True
        else:
            self.send_serial("EM_COOL OFF")
            self.em_cool_on = False
        self.update_all_buttons()

    def on_solvent_toggled(self):
        new = self.btn_solvent.isChecked()
        if new:
            # start without duration (Arduino supports optional duration)
            self.send_serial("SOLVENT START")
            self.solvent_on = True
        else:
            self.send_serial("SOLVENT STOP")
            self.solvent_on = False
        self.update_all_buttons()

    # quick examples
    def quick_all_zero(self):
        for i in range(64):
            self.channel_states[i]["pwm"] = 0
            self.channel_states[i]["dir"] = 0
            self.send_serial(f"SET {i} 0 0")
        self.update_all_buttons()

    def quick_all_50(self):
        for i in range(64):
            self.channel_states[i]["pwm"] = 50
            self.channel_states[i]["dir"] = 0
            self.send_serial(f"SET {i} 50 0")
        self.update_all_buttons()

    def quick_all_off(self):
        for i in range(64):
            self.channel_states[i]["pwm"] = 0
            self.channel_states[i]["dir"] = 0
            self.send_serial(f"SET {i} 0 0")
        self.update_all_buttons()

    # ---------- SEQ handling ----------
    def on_send_seq(self):
        raw = self.seq_edit.toPlainText().strip()
        if not raw:
            QMessageBox.information(self, "SEQ", "脚本为空")
            return
        # Normalize: ensure all commands end with ';' and put in one line after 'SEQ '
        # Accept both ';' separated or newline separated inputs; convert newlines to ';'
        lines = []
        for ln in raw.splitlines():
            ln = ln.strip()
            if not ln: 
                continue
            # if user already used ';' inside a line, split it
            parts = [p.strip() for p in ln.split(';') if p.strip()]
            lines.extend(parts)
        # join with '; ' and append trailing ';'
        seq_body = '; '.join(lines) + ';'
        send_str = "SEQ " + seq_body
        self.send_serial(send_str)
        self.log_msg("Sent SEQ (len={}): {}".format(len(seq_body), seq_body))

    def on_load_seq_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "打开 SEQ 文件", ".", "SEQ Files (*.seq);;All Files (*)")
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    txt = f.read()
                    self.seq_edit.setPlainText(txt)
                    self.log_msg(f"Loaded {path}")
            except Exception as e:
                QMessageBox.critical(self, "文件错误", str(e))

    def closeEvent(self, event):
        try:
            if self.serial and self.serial.is_open():
                self.serial.close()
        except:
            pass
        event.accept()

# ----------------- run -----------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

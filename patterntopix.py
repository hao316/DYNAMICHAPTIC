import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageFont, ImageDraw
import os

def to_8bytes(input_data, font_path="C:/Windows/Fonts/Corbel/corbel.ttf", threshold=128):
    """支持字符或图片路径，返回8字节数组"""
    if len(input_data) == 1 and not os.path.exists(input_data):
        # 字符 → 8x8 图像
        img = Image.new("1", (8, 8), 0)
        draw = ImageDraw.Draw(img)
        font = ImageFont.truetype(font_path, 8)
        draw.text((0, -1), input_data, font=font, fill=1)
    elif os.path.exists(input_data):
        # 图片 → 灰度 → 二值化
        img = Image.open(input_data).convert("L")
        img = img.resize((8, 8))
        img = img.point(lambda p: 255 if p > threshold else 0, '1')
    else:
        raise ValueError("输入必须是单个字符或图片路径")

    # 转换为字节数组
    bytes_array = []
    for y in range(8):
        row = 0
        for x in range(8):
            pixel = img.getpixel((x, y))
            bit = 1 if pixel > 0 else 0
            row = (row << 1) | bit
        bytes_array.append(row)
    return bytes_array


def print_matrix(byte_array):
    """返回点阵可视化字符串"""
    lines = []
    for row in byte_array:
        line = "".join("█" if row & (1 << (7 - col)) else " " for col in range(8))
        lines.append(line)
    return "\n".join(lines)


# ================= GUI =================
def generate_from_char():
    ch = entry_char.get().strip()
    if not ch:
        messagebox.showwarning("提示", "请输入一个字符")
        return
    try:
        bytes_array = to_8bytes(ch)
        text_output.delete("1.0", tk.END)
        text_output.insert(tk.END, f"字节数组: {bytes_array}\n\n")
        text_output.insert(tk.END, print_matrix(bytes_array))
    except Exception as e:
        messagebox.showerror("错误", str(e))


def generate_from_image():
    file_path = filedialog.askopenfilename(
        title="选择图片",
        filetypes=[("Image files", "*.png;*.jpg;*.bmp;*.gif")]
    )
    if not file_path:
        return
    try:
        bytes_array = to_8bytes(file_path)
        text_output.delete("1.0", tk.END)
        text_output.insert(tk.END, f"字节数组: {bytes_array}\n\n")
        text_output.insert(tk.END, print_matrix(bytes_array))
    except Exception as e:
        messagebox.showerror("错误", str(e))


def bytes_to_pwm_code(byte_array, duty_n=0, duty_s=0):
    """
    把8字节数组转换为PWM驱动代码
    蛇形编号: 偶数行左→右，奇数行右→左
    """
    commands = []
    for row in range(8):
        for col in range(8):
            bit = (byte_array[row] >> (7 - col)) & 1
            if bit:
                # 计算蛇形编号
                if row % 2 == 0:  
                    idx = row * 8 + col   # 偶数行
                else:
                    idx = row * 8 + (7 - col)  # 奇数行

                # 偶数行 → N极，奇数行 → S极
                if row % 2 == 0:
                    cmd = f"SET {idx} {duty_n} 0;"
                else:
                    cmd = f"SET {idx} {duty_s} 1;"
                commands.append(cmd)
    return " ".join(commands)


# 在 GUI 里调用
def generate_from_char():
    ch = entry_char.get().strip()
    if not ch:
        messagebox.showwarning("提示", "请输入一个字符")
        return
    try:
        bytes_array = to_8bytes(ch)
        pwm_code = bytes_to_pwm_code(bytes_array)

        text_output.delete("1.0", tk.END)
        text_output.insert(tk.END, f"字节数组: {bytes_array}\n\n")
        text_output.insert(tk.END, print_matrix(bytes_array) + "\n\n")
        text_output.insert(tk.END, "PWM代码:\n" + pwm_code)
    except Exception as e:
        messagebox.showerror("错误", str(e))


def generate_from_image():
    file_path = filedialog.askopenfilename(
        title="选择图片",
        filetypes=[("Image files", "*.png;*.jpg;*.bmp;*.gif")]
    )
    if not file_path:
        return
    try:
        bytes_array = to_8bytes(file_path)
        pwm_code = bytes_to_pwm_code(bytes_array)

        text_output.delete("1.0", tk.END)
        text_output.insert(tk.END, f"字节数组: {bytes_array}\n\n")
        text_output.insert(tk.END, print_matrix(bytes_array) + "\n\n")
        text_output.insert(tk.END, "PWM代码:\n" + pwm_code)
    except Exception as e:
        messagebox.showerror("错误", str(e))


# 主窗口
root = tk.Tk()
root.title("字符/图片转8x8点阵")

frame_input = tk.Frame(root)
frame_input.pack(pady=10)

tk.Label(frame_input, text="输入字符:").grid(row=0, column=0, padx=5)
entry_char = tk.Entry(frame_input, width=5, font=("Consolas", 14))
entry_char.grid(row=0, column=1, padx=5)

btn_char = tk.Button(frame_input, text="生成点阵", command=generate_from_char)
btn_char.grid(row=0, column=2, padx=5)

btn_img = tk.Button(frame_input, text="选择图片", command=generate_from_image)
btn_img.grid(row=0, column=3, padx=5)

text_output = tk.Text(root, width=30, height=15, font=("Consolas", 12))
text_output.pack(pady=10)

root.mainloop()

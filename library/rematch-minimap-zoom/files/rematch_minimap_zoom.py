"""
Rematch Minimap Zoom - an overlay that magnifies the minimap image.

Установка:   pip install mss pillow keyboard
Первый запуск / перенастройка области:   python rematch_minimap_zoom.py --setup
Обычный запуск:                          python rematch_minimap_zoom.py

Клавиши (можно поменять в minimap_config.json):
  ]   - приблизить
  [   - отдалить
  F8  - включить/выключить оверлей
  F9  - выход

Игра должна быть в режиме "Окно без рамки" (Borderless), иначе оверлей не будет виден.
Скрипт только читает картинку экрана и рисует поверх, память игры не трогает.
"""
import ctypes
import json
import os
import sys
import time
import tkinter as tk

try:
    import keyboard
except ImportError:
    keyboard = None
    print("The keyboard library is not installed, keyboard hotkeys are disabled "
          "(pip install keyboard). Gamepad still works.")
import mss
from PIL import Image, ImageTk

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "minimap_config.json")
MANAGED_PATH = os.environ.get("REMATCH_CONFIG")   # set when started from the Rematch Scripts app
MANAGED = bool(MANAGED_PATH)

DEFAULT_CONFIG = {
    "region": None,          # {"left":..., "top":..., "width":..., "height":...}
    "zoom": 1.5,
    "zoom_step": 0.25,
    "zoom_min": 1.0,
    "zoom_max": 4.0,
    "fps": 30,
    "focus_x": 0.5,          # точка приближения по горизонтали (0 = левый край, 1 = правый)
    "focus_y": 0.5,          # точка приближения по вертикали (0 = верх, 1 = низ)
    "key_zoom_in": "]",
    "key_zoom_out": "[",
    "key_toggle": "f8",
    "key_exit": "f9",
    # Геймпад: удерживай модификатор и жми кнопку (чтобы не мешать игре)
    "pad_enabled": True,
    "pad_modifier": "BACK",      # кнопка View/Select
    "pad_zoom_in": "UP",         # BACK + крестовина вверх
    "pad_zoom_out": "DOWN",      # BACK + крестовина вниз
    "pad_toggle": "LEFT",        # BACK + крестовина влево
    "pad_exit": "START",         # BACK + Start
}

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass


# ---------- Геймпад (XInput, ставить ничего не нужно) ----------
class _XGamepad(ctypes.Structure):
    _fields_ = [("wButtons", ctypes.c_ushort), ("bLeftTrigger", ctypes.c_ubyte),
                ("bRightTrigger", ctypes.c_ubyte), ("sThumbLX", ctypes.c_short),
                ("sThumbLY", ctypes.c_short), ("sThumbRX", ctypes.c_short),
                ("sThumbRY", ctypes.c_short)]


class _XState(ctypes.Structure):
    _fields_ = [("dwPacketNumber", ctypes.c_ulong), ("Gamepad", _XGamepad)]


PAD_BUTTONS = {
    "UP": 0x0001, "DOWN": 0x0002, "LEFT": 0x0004, "RIGHT": 0x0008,
    "START": 0x0010, "BACK": 0x0020, "LB": 0x0100, "RB": 0x0200,
    "A": 0x1000, "B": 0x2000, "X": 0x4000, "Y": 0x8000,
}

_xinput = None
for _name in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
    try:
        _xinput = getattr(ctypes.windll, _name)
        break
    except Exception:
        pass


def read_pad_buttons():
    """Маска нажатых кнопок первого подключённого геймпада (0, если нет)."""
    if _xinput is None:
        return 0
    state = _XState()
    for i in range(4):
        if _xinput.XInputGetState(i, ctypes.byref(state)) == 0:
            return state.Gamepad.wButtons
    return 0


def read_managed():
    try:
        with open(MANAGED_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def apply_managed_live(cfg, v):
    """Settings that can change while running."""
    cfg["zoom_step"] = float(v.get("zoom_step", cfg["zoom_step"]))
    cfg["focus_x"] = float(v.get("focus_x", cfg["focus_x"]))
    cfg["focus_y"] = float(v.get("focus_y", cfg["focus_y"]))
    cfg["fps"] = int(v.get("fps", cfg["fps"]))
    cfg["pad_enabled"] = bool(v.get("pad_enabled", cfg["pad_enabled"]))


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if MANAGED:
        v = read_managed()
        cfg["region"] = {"left": int(v.get("rg_left", 1517)), "top": int(v.get("rg_top", 677)),
                         "width": int(v.get("rg_width", 352)), "height": int(v.get("rg_height", 352))}
        cfg["zoom"] = float(v.get("zoom", cfg["zoom"]))
        cfg["key_toggle"] = str(v.get("key_toggle", cfg["key_toggle"]))
        apply_managed_live(cfg, v)
        return cfg
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def select_region():
    """Полупрозрачный экран: обведи мышкой миникарту."""
    root = tk.Tk()
    root.attributes("-fullscreen", True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.3)
    root.configure(bg="black", cursor="cross")
    canvas = tk.Canvas(root, bg="black", highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    canvas.create_text(
        root.winfo_screenwidth() // 2, 40, fill="white", font=("Arial", 20),
        text="Drag a box around the minimap with the mouse (Esc to cancel)",
    )
    state = {"start": None, "rect": None, "result": None}

    def press(e):
        state["start"] = (e.x, e.y)
        state["rect"] = canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="red", width=2)

    def drag(e):
        if state["rect"]:
            x0, y0 = state["start"]
            canvas.coords(state["rect"], x0, y0, e.x, e.y)

    def release(e):
        x0, y0 = state["start"]
        left, top = min(x0, e.x), min(y0, e.y)
        w, h = abs(e.x - x0), abs(e.y - y0)
        if w > 10 and h > 10:
            state["result"] = {"left": left, "top": top, "width": w, "height": h}
        root.destroy()

    canvas.bind("<ButtonPress-1>", press)
    canvas.bind("<B1-Motion>", drag)
    canvas.bind("<ButtonRelease-1>", release)
    root.bind("<Escape>", lambda e: root.destroy())
    root.mainloop()
    return state["result"]


def make_overlay_special(root):
    """Клик сквозь окно + не попадает в захват экрана (чтобы не было эффекта 'зеркала')."""
    try:
        user32 = ctypes.windll.user32
        root.update_idletasks()
        hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_NOACTIVATE = 0x08000000
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(
            hwnd, GWL_EXSTYLE,
            style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
        )
        WDA_EXCLUDEFROMCAPTURE = 0x11
        user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
    except Exception as e:
        print("Could not set up the overlay window:", e)


def run_overlay(cfg):
    region = cfg["region"]
    w, h = region["width"], region["height"]
    state = {"zoom": float(cfg["zoom"]), "visible": True, "quit": False}

    def zoom_in():
        state["zoom"] = min(cfg["zoom_max"], state["zoom"] + cfg["zoom_step"])
        print(f"Zoom: x{state['zoom']:.2f}")

    def zoom_out():
        state["zoom"] = max(cfg["zoom_min"], state["zoom"] - cfg["zoom_step"])
        print(f"Zoom: x{state['zoom']:.2f}")

    def toggle():
        state["visible"] = not state["visible"]

    def quit_():
        state["quit"] = True

    if keyboard is not None:
        keyboard.add_hotkey(cfg["key_zoom_in"], zoom_in)
        keyboard.add_hotkey(cfg["key_zoom_out"], zoom_out)
        keyboard.add_hotkey(cfg["key_toggle"], toggle)
        if not MANAGED:
            keyboard.add_hotkey(cfg["key_exit"], quit_)

    pad_prev = {"mask": 0}

    def poll_pad():
        if not cfg["pad_enabled"]:
            return
        mask = read_pad_buttons()
        pressed = mask & ~pad_prev["mask"]
        pad_prev["mask"] = mask
        if not (mask & PAD_BUTTONS[cfg["pad_modifier"]]):
            return
        if pressed & PAD_BUTTONS[cfg["pad_zoom_in"]]:
            zoom_in()
        if pressed & PAD_BUTTONS[cfg["pad_zoom_out"]]:
            zoom_out()
        if pressed & PAD_BUTTONS[cfg["pad_toggle"]]:
            toggle()
        if pressed & PAD_BUTTONS[cfg["pad_exit"]]:
            quit_()

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.geometry(f"{w}x{h}+{region['left']}+{region['top']}")
    label = tk.Label(root, bd=0, highlightthickness=0, bg="black")
    label.pack(fill="both", expand=True)
    make_overlay_special(root)

    sct = mss.mss()
    delay_box = [max(1, int(1000 / max(5, cfg["fps"])))]
    live = {"mtime": 0.0, "checked": 0.0, "show": None}

    def reload_live():
        """Re-read the menu settings twice a second (zoom, focus, FPS, show/hide)."""
        try:
            mt = os.path.getmtime(MANAGED_PATH)
        except OSError:
            return
        if mt == live["mtime"]:
            return
        live["mtime"] = mt
        v = read_managed()
        apply_managed_live(cfg, v)
        delay_box[0] = max(1, int(1000 / max(5, cfg["fps"])))
        state["zoom"] = max(cfg["zoom_min"], min(cfg["zoom_max"], float(v.get("zoom", state["zoom"]))))
        show = bool(v.get("show", True))
        if show != live["show"]:
            live["show"] = show
            state["visible"] = show

    def tick():
        poll_pad()
        if MANAGED:
            now = time.time()
            if now - live["checked"] > 0.5:
                live["checked"] = now
                reload_live()
        if state["quit"]:
            if not MANAGED:
                cfg["zoom"] = state["zoom"]
                save_config(cfg)
            root.destroy()
            return
        if state["visible"]:
            root.attributes("-alpha", 1.0)
            shot = sct.grab(region)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            z = state["zoom"]
            if z > 1.0:
                cw, ch = int(w / z), int(h / z)
                fx, fy = cfg["focus_x"], cfg["focus_y"]
                left = int(fx * w - cw / 2)
                top = int(fy * h - ch / 2)
                left = max(0, min(w - cw, left))
                top = max(0, min(h - ch, top))
                img = img.crop((left, top, left + cw, top + ch)).resize((w, h), Image.BILINEAR)
            photo = ImageTk.PhotoImage(img)
            label.configure(image=photo)
            label.image = photo
        else:
            root.attributes("-alpha", 0.0)
        root.after(delay_box[0], tick)

    print(f"Running. {cfg['key_zoom_in']} / {cfg['key_zoom_out']} - zoom, "
          f"{cfg['key_toggle']} - show/hide." + ("" if MANAGED else f" {cfg['key_exit']} - exit."))
    tick()
    root.mainloop()


def main():
    cfg = load_config()
    if "--setup" in sys.argv or not cfg["region"]:
        print("Drag a box around the minimap (the game must be open).")
        region = select_region()
        if not region:
            print("Cancelled.")
            return
        cfg["region"] = region
        save_config(cfg)
        print("Region saved:", region)
    run_overlay(cfg)


if __name__ == "__main__":
    main()

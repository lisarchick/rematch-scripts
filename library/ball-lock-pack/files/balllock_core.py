"""
Общее ядро: быстрый захват экрана, поиск мяча по цвету, ПД-регулятор.
Оптимизации против лагов:
  * захват через dxcam (GPU, Desktop Duplication) с автоматическим откатом на mss в отдельном потоке
  * даунсэмплинг срезом (без дорогого resize), HSV считается на маленькой картинке
  * фиксированная частота цикла (TARGET_FPS) и поправка на реальный dt
  * hotkeys через события, без опроса клавиатуры в цикле
  * окна OpenCV и waitKey только в режиме калибровки
  * SendInput со структурой, созданной один раз
  * таймер Windows 1 мс и повышенный приоритет процесса
"""
import ctypes
import json
import math
import os
import threading
import time
from ctypes import wintypes

import cv2
import keyboard
import numpy as np

# ----------------------------- НАСТРОЙКИ -----------------------------
CFG = {
    "lower": [20, 100, 100],   # HSV нижняя граница цвета мяча
    "upper": [35, 255, 255],   # HSV верхняя граница
    "step": 3,                 # во сколько раз уменьшать кадр (3 = 1/3). Больше = быстрее, меньше точность
    "target_fps": 120,         # частота цикла управления
    "min_area": 20,            # минимальная площадь контура (на уменьшенном кадре)
    "min_circularity": 0.50,
    "memory_frames": 25,       # сколько кадров "помнить" мяч после потери
    "decay": 0.92,
    "smooth": 0.7,             # сглаживание позиции цели (1.0 = без сглаживания)
}

MOUSE_GAINS = {
    "kp": 0.28, "edge": 0.45, "kd": 0.09,
    "deadzone": 4, "max_out": 120.0, "per_frame": True,
}
GAMEPAD_GAINS = {
    "kp": 0.0018, "edge": 0.0025, "kd": 0.0006,
    "deadzone": 8, "max_out": 1.0, "per_frame": False,
}

# ----------------------------- СИСТЕМНОЕ -----------------------------
def tune_system():
    try:
        ctypes.windll.winmm.timeBeginPeriod(1)
        ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000
        h = ctypes.windll.kernel32.GetCurrentProcess()
        ctypes.windll.kernel32.SetPriorityClass(h, ABOVE_NORMAL_PRIORITY_CLASS)
    except Exception:
        pass
    cv2.setNumThreads(2)
    cv2.setUseOptimized(True)


# ----------------------------- ЗАХВАТ ЭКРАНА -----------------------------
class Capture:
    def __init__(self, fps):
        self.backend = None
        self.frame = None
        self.lock = threading.Lock()
        self.running = True
        try:
            import dxcam
            self.cam = dxcam.create(output_color="BGR")
            self.cam.start(target_fps=fps, video_mode=True)
            self.backend = "dxcam"
        except Exception as e:
            print(f"[CAPTURE] dxcam недоступен ({e}), использую mss")
            self.backend = "mss"
            self.thread = threading.Thread(target=self._mss_loop, daemon=True)
            self.thread.start()
        print(f"[CAPTURE] Бэкенд захвата: {self.backend}")

    def _mss_loop(self):
        import mss
        with mss.mss() as sct:
            mon = sct.monitors[1]
            while self.running:
                img = np.asarray(sct.grab(mon))[:, :, :3]
                with self.lock:
                    self.frame = img

    def grab(self):
        if self.backend == "dxcam":
            return self.cam.get_latest_frame()
        with self.lock:
            return self.frame

    def stop(self):
        self.running = False
        if self.backend == "dxcam":
            try:
                self.cam.stop()
            except Exception:
                pass


# ----------------------------- ВЫВОД: МЫШЬ -----------------------------
class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("ii", _INPUT_UNION)]


class MouseOutput:
    name = "Mouse"

    def __init__(self):
        self.rx = 0.0
        self.ry = 0.0
        self._inp = _INPUT(0, _INPUT_UNION(_MOUSEINPUT(0, 0, 0, 0x0001, 0, 0)))
        self._size = ctypes.sizeof(_INPUT)
        self._send = ctypes.windll.user32.SendInput

    def move(self, cx, cy):
        cx += self.rx
        cy += self.ry
        ix, iy = int(cx), int(cy)
        self.rx, self.ry = cx - ix, cy - iy
        if ix or iy:
            mi = self._inp.ii.mi
            mi.dx, mi.dy = ix, iy
            self._send(1, ctypes.byref(self._inp), self._size)

    def stop(self):
        self.rx = self.ry = 0.0

    def close(self):
        self.stop()


# ----------------------------- ВЫВОД: ГЕЙМПАД -----------------------------
class GamepadOutput:
    name = "Gamepad"

    def __init__(self):
        import vgamepad as vg
        self.pad = vg.VX360Gamepad()
        self.lx = 0.0
        self.ly = 0.0

    def _set(self, x, y):
        x = max(-1.0, min(1.0, x))
        y = max(-1.0, min(1.0, -y))  # экранная Y инвертирована относительно стика
        if abs(x - self.lx) < 1e-3 and abs(y - self.ly) < 1e-3:
            return  # ничего не изменилось, не дёргаем драйвер
        self.lx, self.ly = x, y
        self.pad.right_joystick_float(x_value_float=x, y_value_float=y)
        self.pad.update()

    def move(self, cx, cy):
        self._set(cx, cy)

    def stop(self):
        self._set(0.0, 0.0)

    def close(self):
        self.stop()


# ----------------------------- ПОИСК МЯЧА -----------------------------
def find_ball(mask, min_area, min_circ):
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best, best_score = None, 0.0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue
        per = cv2.arcLength(cnt, True)
        if per == 0:
            continue
        circ = 4 * math.pi * area / (per * per)
        if circ < min_circ:
            continue
        score = area * circ
        if score > best_score:
            best_score = score
            (bx, by), r = cv2.minEnclosingCircle(cnt)
            best = (bx, by, r)
    return best


# ----------------------------- ГЛАВНЫЙ ЦИКЛ -----------------------------
class State:
    locked = False
    debug = False
    running = True


def run(output, gains, title, config_path=None):
    tune_system()
    st = State()
    managed = bool(config_path)   # запущен из меню Rematch Scripts: настройки берутся из файла
    base_gains = dict(gains)
    if managed:
        st.locked = True

    def toggle_lock():
        st.locked = not st.locked
        if not st.locked:
            output.stop()
        print(f"[LOCK] {'АКТИВЕН' if st.locked else 'ОТКЛЮЧЕН'}")

    def toggle_debug():
        st.debug = not st.debug
        print(f"[DEBUG] {'ВКЛ' if st.debug else 'ВЫКЛ'}")

    def quit_():
        st.running = False

    print("=" * 60)
    print(title)
    if managed:
        print("  Управление и настройки: меню Rematch Scripts")
    else:
        print("  [F6] ВКЛ/ВЫКЛ лок на мяче | [F7] калибровка цвета | [F8] выход")
    print("=" * 60)
    if not managed:
        keyboard.add_hotkey("f6", toggle_lock)
        keyboard.add_hotkey("f7", toggle_debug)
        keyboard.add_hotkey("f8", quit_)

    step = max(1, int(CFG["step"]))
    kernel = np.ones((3, 3), np.uint8)
    period = 1.0 / CFG["target_fps"]
    lower = np.array(CFG["lower"], dtype=np.uint8)
    upper = np.array(CFG["upper"], dtype=np.uint8)

    cfg_state = {"mtime": 0.0, "checked": 0.0}

    def reload_cfg():
        """Читает настройки из меню (раз в 0.4 с, только если файл изменился)."""
        nonlocal step, period, lower, upper
        try:
            mt = os.path.getmtime(config_path)
            if mt == cfg_state["mtime"]:
                return
            cfg_state["mtime"] = mt
            with open(config_path, "r", encoding="utf-8") as f:
                v = json.load(f)
        except Exception:
            return
        g = lambda k, d: v.get(k, d)
        CFG["smooth"] = float(g("smooth", CFG["smooth"]))
        CFG["target_fps"] = int(g("fps", CFG["target_fps"]))
        period = 1.0 / max(10, CFG["target_fps"])
        step = max(1, int(g("step", step)))
        sens, damp = float(g("sens", 1.0)), float(g("damping", 1.0))
        gains["kp"] = base_gains["kp"] * sens
        gains["edge"] = base_gains["edge"] * sens
        gains["kd"] = base_gains["kd"] * damp
        gains["deadzone"] = float(g("deadzone", base_gains["deadzone"]))
        if not st.debug:
            lower = np.array([int(g("h_min", lower[0])), int(g("s_min", lower[1])), int(g("v_min", lower[2]))], dtype=np.uint8)
            upper = np.array([int(g("h_max", upper[0])), int(g("s_max", upper[1])), int(g("v_max", upper[2]))], dtype=np.uint8)
        st.debug = bool(g("debug", False))

    cap = Capture(CFG["target_fps"])
    trackbars = False
    if managed:
        reload_cfg()

    prev_ex = prev_ey = 0.0
    sx = sy = None            # сглаженная позиция цели (в пикселях полного экрана)
    last_cx = last_cy = 0.0
    lost = 0
    last_t = time.perf_counter()
    next_t = last_t

    try:
        while st.running:
            frame = cap.grab()
            if frame is None:
                time.sleep(0.005)
                continue

            now = time.perf_counter()
            if managed and now - cfg_state["checked"] > 0.4:
                cfg_state["checked"] = now
                reload_cfg()
            dt = max(now - last_t, 1e-4)
            last_t = now
            dt60 = min(dt * 60.0, 3.0)

            h, w = frame.shape[:2]
            center_x, center_y = w / 2.0, h / 2.0
            max_dist = math.hypot(center_x, center_y)

            small = np.ascontiguousarray(frame[::step, ::step])
            hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)

            if st.debug:
                if not trackbars:
                    cv2.namedWindow("Calibration", cv2.WINDOW_NORMAL)
                    cv2.resizeWindow("Calibration", 350, 260)
                    for i, n in enumerate(("H Min", "S Min", "V Min")):
                        cv2.createTrackbar(n, "Calibration", int(lower[i]), 255 if i else 179, lambda x: None)
                    for i, n in enumerate(("H Max", "S Max", "V Max")):
                        cv2.createTrackbar(n, "Calibration", int(upper[i]), 255 if i else 179, lambda x: None)
                    trackbars = True
                lower = np.array([cv2.getTrackbarPos(n, "Calibration") for n in ("H Min", "S Min", "V Min")], dtype=np.uint8)
                upper = np.array([cv2.getTrackbarPos(n, "Calibration") for n in ("H Max", "S Max", "V Max")], dtype=np.uint8)

            mask = cv2.inRange(hsv, lower, upper)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            ball = find_ball(mask, CFG["min_area"], CFG["min_circularity"])

            if ball is not None:
                lost = 0
                tx, ty = ball[0] * step, ball[1] * step
                a = CFG["smooth"]
                if sx is None:
                    sx, sy = tx, ty
                else:
                    sx = a * tx + (1 - a) * sx
                    sy = a * ty + (1 - a) * sy

                ex, ey = sx - center_x, sy - center_y
                dist = math.hypot(ex, ey)

                if st.locked:
                    if dist > gains["deadzone"]:
                        ratio = min(dist / (max_dist * 0.6), 1.0)
                        kp = gains["kp"] + gains["edge"] * ratio * ratio
                        ux = kp * ex + gains["kd"] * (ex - prev_ex) / dt60
                        uy = kp * ey + gains["kd"] * (ey - prev_ey) / dt60
                        if gains["per_frame"]:
                            ux *= dt60
                            uy *= dt60
                        m = gains["max_out"]
                        ux = max(-m, min(m, ux))
                        uy = max(-m, min(m, uy))
                        output.move(ux, uy)
                        last_cx = 0.6 * ux + 0.4 * last_cx
                        last_cy = 0.6 * uy + 0.4 * last_cy
                    else:
                        output.stop()
                        last_cx = last_cy = 0.0
                prev_ex, prev_ey = ex, ey
            else:
                if st.locked and lost < CFG["memory_frames"]:
                    lost += 1
                    last_cx *= CFG["decay"]
                    last_cy *= CFG["decay"]
                    output.move(last_cx, last_cy * 0.5)
                else:
                    if st.locked:
                        output.stop()
                    prev_ex = prev_ey = 0.0
                    last_cx = last_cy = 0.0
                    sx = sy = None

            if st.debug:
                view = small.copy()
                c = (int(center_x / step), int(center_y / step))
                cv2.circle(view, c, 5, (255, 255, 255), 1)
                if ball is not None:
                    b = (int(ball[0]), int(ball[1]))
                    cv2.circle(view, b, max(int(ball[2]), 4), (0, 255, 0), 2)
                    cv2.line(view, c, b, (0, 0, 255), 2)
                cv2.imshow(f"{title} (F7 hide)", view)
                cv2.imshow("Mask", mask)
                cv2.waitKey(1)
            elif trackbars:
                cv2.destroyAllWindows()
                trackbars = False

            # фиксированная частота цикла
            next_t += period
            delay = next_t - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            else:
                next_t = time.perf_counter()
    finally:
        output.close()
        cap.stop()
        cv2.destroyAllWindows()
        try:
            ctypes.windll.winmm.timeEndPeriod(1)
        except Exception:
            pass

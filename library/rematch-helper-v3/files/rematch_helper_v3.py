"""
REMATCH Helper v3 (most accurate): shows where a shot is heading, read from the minimap.

Что делает:
  * Берёт кадр миникарты (приоритет: dxcam / DXGI, запасной: mss).
  * Находит МЯЧ: золотое кольцо с белой серединой (мяч свободен).
    Если кольцо надето на игрока (чёрная середина) — мяч у игрока, это не удар.
  * Находит ПУНКТИРНЫЙ ЖЁЛТЫЙ КРУГ (отметка, куда летит мяч) и подгоняет под него окружность.
  * Строит прогноз пересечения линии ворот:
        метод B: мяч -> центр пунктирного круга (и дальше по прямой),
        метод A: линия полёта по последним кадрам (если круга нет).
  * Показывает: ВЛЕВО / ЦЕНТР / ВПРАВО / ПРОМАХ — только когда несколько кадров подряд согласны.

Клавиши (работают из игры): F7 — сменить способ захвата, F8 — снимок миникарты в calib/,
F9 — окно отладки вкл/выкл, F10 — выход.

Установка:   pip install opencv-python numpy mss dxcam
"""
import ctypes
import json
import os
import queue
import threading
import time
from collections import deque

import numpy as np

try:  # DPI-awareness до создания окон (Windows)
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


# ======================= REMATCH SCRIPTS MENU INTEGRATION =======================
# When started from the Rematch Scripts app, settings come from the menu (REMATCH_CONFIG file).
MANAGED_PATH = os.environ.get("REMATCH_CONFIG")
MANAGED = bool(MANAGED_PATH)
VERDICT_EN = {"left": "LEFT", "right": "RIGHT", "center": "CENTER", "miss": "MISS"}
VERDICT_RU = {"left": "ВЛЕВО", "right": "ВПРАВО", "center": "ЦЕНТР", "miss": "ПРОМАХ"}
LANG = {"v": "ru"}
_focus = {"t": 0.0, "ok": True}


def is_game_focused():
    """True if the active window looks like the game (title contains 'rematch', not this app)."""
    now = time.perf_counter()
    if now - _focus["t"] < 0.3:
        return _focus["ok"]
    _focus["t"] = now
    try:
        u = ctypes.windll.user32
        hwnd = u.GetForegroundWindow()
        n = u.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(hwnd, buf, n + 1)
        t = buf.value.lower()
        _focus["ok"] = "rematch" in t and "scripts" not in t and "github" not in t
    except Exception:
        _focus["ok"] = True
    return _focus["ok"]


def apply_managed(cfg):
    """Override defaults with values chosen in the Rematch Scripts menu."""
    try:
        with open(MANAGED_PATH, "r", encoding="utf-8") as f:
            v = json.load(f)
    except Exception as e:
        print("Menu settings could not be read:", e)
        return cfg
    g = v.get
    cfg["capture"] = g("capture", cfg["capture"])
    cfg["debug"] = bool(g("debug", False))
    cfg["monitor_index"] = int(g("monitor_index", cfg["monitor_index"]))
    m = cfg["minimap"]
    cfg["minimap"] = {"left": int(g("mm_left", m["left"])), "top": int(g("mm_top", m["top"])),
                      "width": int(g("mm_width", m["width"])), "height": int(g("mm_height", m["height"]))}
    fs = int(g("font_size", 30))
    cfg["font_size"] = fs
    cfg["text_color"] = str(g("text_color", "#ff2d2d"))
    cfg["overlay_geometry"] = "620x%d+%d+%d" % (max(80, int(fs * 2.2)), int(g("text_x", 650)), int(g("text_y", 180)))
    cfg["only_in_game"] = bool(g("only_in_game", False))
    LANG["v"] = str(g("verdict_lang", "en"))
    for k in ("hold_sec", "center_band", "goal_margin", "goal_left_x", "goal_right_x", "goal_y",
              "wall_left_x", "wall_right_x", "min_speed", "max_eta"):
        cfg[k] = float(g(k, cfg[k]))
    cfg["vote_window"] = max(1, int(g("vote_window", cfg["vote_window"])))
    cfg["vote_need"] = max(1, min(cfg["vote_window"], int(g("vote_need", cfg["vote_need"]))))
    for name in ("ring", "marker"):
        cfg[name + "_hsv_lower"] = [int(g(name + "_h_min", cfg[name + "_hsv_lower"][0])),
                                    int(g(name + "_s_min", cfg[name + "_hsv_lower"][1])),
                                    int(g(name + "_v_min", cfg[name + "_hsv_lower"][2]))]
        cfg[name + "_hsv_upper"] = [int(g(name + "_h_max", cfg[name + "_hsv_upper"][0])),
                                    int(g(name + "_s_max", cfg[name + "_hsv_upper"][1])),
                                    int(g(name + "_v_max", cfg[name + "_hsv_upper"][2]))]
    return cfg

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "rematch_config_v3.json")
CALIB_DIR = os.path.join(HERE, "calib")
LOG_PATH = os.path.join(HERE, "shots_log.jsonl")

# ======================= КОНФИГ =======================
# Все координаты ворот — внутри кадра миникарты (в пикселях ROI).
DEFAULT_CONFIG = {
    # Круглая миникарта (1920x1080): круг ~352 px, левый верхний угол (1517, 677)
    "minimap": {"left": 1517, "top": 677, "width": 352, "height": 352},
    "monitor_index": 0,          # номер монитора для dxcam
    "capture": "auto",           # auto | dxcam | mss
    "overlay_geometry": "620x80+650+180",
    "debug": True,
    # Ворота на миникарте (ROI px): створ — маленький прямоугольник под штрафной
    "goal_left_x": 155.5,
    "goal_right_x": 197.5,
    "goal_y": 177.0,             # линия ворот (нижняя линия поля)
    "wall_left_x": 49.0,
    "wall_right_x": 300.0,
    "goal_margin": 4.0,          # допуск на штанги/радиус мяча
    "center_band": 6.0,          # |x - центр| <= band  =>  ЦЕНТР
    # Цвета (HSV, OpenCV: H 0..179)
    "ring_hsv_lower": [21, 190, 190],     # золотое кольцо мяча (H~24)
    "ring_hsv_upper": [27, 255, 255],
    "marker_hsv_lower": [28, 190, 190],   # жёлтый пунктир (H~29)
    "marker_hsv_upper": [34, 255, 255],
    "ring_size_min": 20,
    "ring_size_max": 38,
    "marker_min_pixels": 120,
    # Трекер мяча
    "track_window": 0.40,        # сек: окно для оценки скорости
    "track_gap": 0.30,           # сек без мяча — трек сбрасывается
    "max_jump_px": 70,
    "min_samples": 3,
    "min_speed": 25.0,           # px/сек: медленнее — не удар
    "max_eta": 2.5,              # сек до линии ворот
    "marker_min_dist": 18.0,     # ближе к центру круга — считаем по линии полёта (метод A)
    # Стабилизация
    "vote_window": 5,
    "vote_need": 3,
    "hold_sec": 1.5,
    # Клавиши (VK): F7, F8, F9, F10
    "key_backend": 0x76,
    "key_snapshot": 0x77,
    "key_debug": 0x78,
    "key_exit": 0x79,
}


def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user = json.load(f)
            for k, v in user.items():
                if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                    cfg[k].update(v)
                else:
                    cfg[k] = v
        except Exception as e:
            print("Config not read, using defaults:", e)
    else:
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
    if MANAGED:
        cfg = apply_managed(cfg)
    return cfg


# ======================= ДЕТЕКЦИЯ =======================
class Ball:
    def __init__(self, x, y, free):
        self.x, self.y, self.free = float(x), float(y), bool(free)


class Marker:
    def __init__(self, x, y, r):
        self.x, self.y, self.r = float(x), float(y), float(r)


def circle_fit(xs, ys):
    """Алгебраическая подгонка окружности (работает и по дугам)."""
    xs = xs.astype(np.float64)
    ys = ys.astype(np.float64)
    A = np.column_stack([xs, ys, np.ones_like(xs)])
    b = xs * xs + ys * ys
    sol = np.linalg.lstsq(A, b, rcond=None)[0]
    cx, cy = sol[0] / 2.0, sol[1] / 2.0
    r = float(np.sqrt(max(sol[2] + cx * cx + cy * cy, 0.0)))
    return cx, cy, r


def normalize_brightness(frame, cv2):
    """Если кадр тусклый (например, захват с неверной яркостью) — растягиваем яркость."""
    p = float(np.percentile(frame, 99.5))
    if 40.0 < p < 215.0:
        k = 255.0 / p
        return np.clip(frame.astype(np.float32) * k, 0, 255).astype(np.uint8)
    return frame


def detect(frame, cfg, cv2):
    """Возвращает (ball|None, marker|None)."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # ---- мяч: золотое кольцо ----
    ring = cv2.inRange(hsv, np.array(cfg["ring_hsv_lower"], np.uint8), np.array(cfg["ring_hsv_upper"], np.uint8))
    ring = cv2.morphologyEx(ring, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    n, _, st, cen = cv2.connectedComponentsWithStats(ring)
    white = cv2.inRange(hsv, np.array([0, 0, 225], np.uint8), np.array([180, 70, 255], np.uint8))
    smin, smax = cfg["ring_size_min"], cfg["ring_size_max"]
    ball = None
    best_area = 0
    for k in range(1, n):
        x, y, w, h, a = [int(v) for v in st[k]]
        if smin <= w <= smax and smin <= h <= smax and a >= 100 and a > best_area:
            cx, cy = float(cen[k][0]), float(cen[k][1])
            ix, iy = int(round(cx)), int(round(cy))
            patch = white[max(iy - 4, 0): iy + 5, max(ix - 4, 0): ix + 5]
            free = bool(patch.size and (patch > 0).mean() >= 0.5)
            ball = Ball(cx, cy, free)
            best_area = a

    # ---- пунктирный круг ----
    mk = cv2.inRange(hsv, np.array(cfg["marker_hsv_lower"], np.uint8), np.array(cfg["marker_hsv_upper"], np.uint8))
    n2, lab2, st2, _ = cv2.connectedComponentsWithStats(mk)
    keep = np.zeros_like(mk)
    for k in range(1, n2):
        if st2[k][4] >= 20:
            keep[lab2 == k] = 255
    ys, xs = np.nonzero(keep)
    marker = None
    if len(xs) >= cfg["marker_min_pixels"]:
        cx, cy, r = circle_fit(xs, ys)
        if 7.0 <= r <= 40.0:
            marker = Marker(cx, cy, r)
    return ball, marker


# ======================= ГЕОМЕТРИЯ / ПРОГНОЗ =======================
def reflect_x(x, lo, hi):
    if lo <= x <= hi:
        return x, False
    width = hi - lo
    p = (x - lo) % (2.0 * width)
    if p > width:
        p = 2.0 * width - p
    return lo + p, True


class ShotPredictor:
    """Чистая логика (без tkinter/mss) — тестируется отдельно."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.track = deque()           # (t, x, y) только свободный мяч
        self.votes = deque(maxlen=cfg["vote_window"])
        self.shown = None              # (key, bounced)
        self.last_confirm = 0.0
        self.last_ball = None          # (t, x, y)
        self.last_marker = None        # (t, Marker)
        self.debug = {}

    # --- трек ---
    def _push(self, t, ball, marker):
        cfg = self.cfg
        if marker is not None:
            self.last_marker = (t, marker)
        if ball is not None and ball.free:
            if self.track:
                t0, x0, y0 = self.track[-1]
                if t - t0 > cfg["track_gap"] or np.hypot(ball.x - x0, ball.y - y0) > cfg["max_jump_px"]:
                    self.track.clear()
            self.track.append((t, ball.x, ball.y))
            self.last_ball = (t, ball.x, ball.y)
        else:
            if self.track and t - self.track[-1][0] > cfg["track_gap"]:
                self.track.clear()
        while self.track and t - self.track[0][0] > cfg["track_window"]:
            self.track.popleft()

    def _velocity(self):
        """Скорость мяча (vx, vy) и сглаженная позиция по последним кадрам."""
        if len(self.track) < self.cfg["min_samples"]:
            return None
        arr = np.array(self.track, dtype=np.float64)
        ts = arr[:, 0] - arr[-1, 0]
        if np.ptp(ts) < 0.04:
            return None
        kx, bx = np.polyfit(ts, arr[:, 1], 1)
        ky, by = np.polyfit(ts, arr[:, 2], 1)
        return float(kx), float(ky), float(bx), float(by)

    def _cross(self, x, y, dx, dy):
        """Пересечение линии ворот лучом из (x,y) направлением (dx,dy). -> x или None."""
        gy = self.cfg["goal_y"]
        if dy <= 1e-6 or y >= gy:
            return None
        t = (gy - y) / dy
        return x + dx * t

    # --- основной шаг ---
    def update(self, t, ball, marker):
        cfg = self.cfg
        gl, gr = cfg["goal_left_x"], cfg["goal_right_x"]
        gc = (gl + gr) / 2.0
        lo, hi = cfg["wall_left_x"], cfg["wall_right_x"]
        gy = cfg["goal_y"]

        self._push(t, ball, marker)
        vel = self._velocity()
        moving = vel is not None and np.hypot(vel[0], vel[1]) >= cfg["min_speed"] and vel[1] > 0

        xa = xb = None
        if vel is not None and moving:
            vx, vy, px, py = vel
            eta = (gy - py) / vy if vy > 1e-6 else None
            if eta is not None and 0.0 < eta <= cfg["max_eta"]:
                xa = px + vx * eta

            # метод B: мяч -> центр пунктирного круга
            mk = self.last_marker
            if mk is not None and t - mk[0] <= 0.25:
                m = mk[1]
                bx_, by_ = px, py
                ddx, ddy = m.x - bx_, m.y - by_
                if np.hypot(ddx, ddy) >= cfg["marker_min_dist"]:
                    xb = self._cross(bx_, by_, ddx, ddy)

        x = xb if xb is not None else xa
        method = "B" if xb is not None else ("A" if xa is not None else None)

        self.debug = {"xa": xa, "xb": xb, "vel": vel, "moving": moving}

        if x is None:
            self.votes.append(None)
            return self._current(t, None, None)

        x, bounced = reflect_x(x, lo, hi)
        mg = cfg["goal_margin"]
        if x < gl - mg or x > gr + mg:
            key = "miss"
        elif abs(x - gc) <= cfg["center_band"]:
            key = "center"
        elif x < gc:
            key = "left"
        else:
            key = "right"
        self.votes.append((key, bounced))
        return self._current(t, x, method)

    def _current(self, t, x, method):
        valid = [v for v in self.votes if v is not None]
        if valid:
            keys = [v[0] for v in valid]
            top = max(set(keys), key=keys.count)
            if keys.count(top) >= self.cfg["vote_need"]:
                bounced = any(v[1] for v in valid if v[0] == top)
                self.shown = (top, bounced)
                self.last_confirm = t
        if self.shown and t - self.last_confirm > self.cfg["hold_sec"]:
            self.shown = None
            self.votes.clear()
        return {"verdict": self.shown, "x": x, "method": method}


VERDICT_TEXT = {"left": "ВЛЕВО", "right": "ВПРАВО", "center": "ЦЕНТР", "miss": "ПРОМАХ"}


def verdict_text(v):
    if not v:
        return ""
    if LANG["v"] == "en":
        return VERDICT_EN[v[0]] + (" (bounce)" if v[1] else "")
    return VERDICT_TEXT[v[0]] + (" (отскок)" if v[1] else "")


# ======================= ЗАХВАТ ЭКРАНА =======================
class Grabber:
    """dxcam (DXGI Desktop Duplication) -> запасной mss. Создаётся и используется в одном потоке."""

    def __init__(self, cfg):
        self.cfg = cfg
        r = cfg["minimap"]
        self.l, self.t, self.w, self.h = r["left"], r["top"], r["width"], r["height"]
        self.region = (self.l, self.t, self.l + self.w, self.t + self.h)
        order = {"auto": ["dxcam", "mss"], "dxcam": ["dxcam", "mss"], "mss": ["mss", "dxcam"]}.get(
            cfg["capture"], ["dxcam", "mss"])
        self.order = order
        self.mode = None
        self.cam = None
        self.sct = None
        self.last = None
        self.frames = 0
        self._open_first(order)

    def _open_first(self, names):
        for name in names:
            if self._open(name):
                return
        raise RuntimeError("Could not open any screen capture method")

    def _open(self, name):
        self.close()
        try:
            if name == "dxcam":
                import dxcam
                last_err = None
                for dev in range(4):
                    try:
                        cam = dxcam.create(device_idx=dev, output_idx=self.cfg["monitor_index"], output_color="BGR")
                    except Exception as e:  # нет такого адаптера
                        last_err = e
                        continue
                    frame = None
                    for _ in range(40):
                        frame = cam.grab(region=self.region)
                        if frame is not None:
                            break
                        time.sleep(0.03)
                    if frame is not None and frame.mean() > 2.0:
                        self.cam = cam
                        self.mode = "dxcam"
                        self.last = frame
                        print(f"Capture: dxcam (adapter {dev})")
                        return True
                    try:
                        cam.release()
                    except Exception:
                        pass
                print("dxcam did not work:", last_err)
                return False
            else:
                import mss
                self.sct = mss.mss()
                self.mode = "mss"
                print("Capture: mss")
                return True
        except Exception as e:
            print(f"Capture method {name} unavailable:", e)
            return False

    def switch(self):
        nxt = "mss" if self.mode == "dxcam" else "dxcam"
        if not self._open(nxt):
            self._open(self.mode or "mss")

    def grab(self):
        """Возвращает (кадр BGR, новый_ли_кадр)."""
        if self.mode == "dxcam":
            f = self.cam.grab(region=self.region)
            if f is None:
                return self.last, False
            self.last = np.ascontiguousarray(f[:, :, :3])
            self.frames += 1
            return self.last, True
        img = self.sct.grab({"left": self.l, "top": self.t, "width": self.w, "height": self.h})
        f = np.ascontiguousarray(np.asarray(img, dtype=np.uint8)[:, :, :3])
        self.frames += 1
        self.last = f
        return f, True

    def close(self):
        try:
            if self.cam is not None:
                self.cam.release()
        except Exception:
            pass
        self.cam = None
        self.sct = None


# ======================= ПРИЛОЖЕНИЕ =======================
class App:
    def __init__(self):
        import tkinter as tk
        import cv2
        self.tk, self.cv2 = tk, cv2
        self.cfg = load_config()
        self.running = True
        self.debug = bool(self.cfg["debug"])
        self.text_q = queue.Queue()
        self.dbg_lock = threading.Lock()
        self.dbg_frame = None
        self.flags = {"snapshot": threading.Event(), "backend": threading.Event()}

        TR = "#010101"
        self.root = tk.Tk()
        self.root.title("REMATCH Helper v3")
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)
        self.root.config(bg=TR)
        self.root.attributes("-transparentcolor", TR)
        self.root.geometry(self.cfg["overlay_geometry"])
        self.label = tk.Label(self.root, text="", font=("Arial", int(self.cfg.get("font_size", 30)), "bold"), fg=self.cfg.get("text_color", "#ff2d2d"), bg=TR)
        self.label.pack(expand=True)
        self.root.update_idletasks()
        self._click_through()
        self._shown_text = ""
        self._key_prev = {}

        threading.Thread(target=self._capture_loop, daemon=True).start()
        self.root.after(30, self._poll)

    def _click_through(self):
        try:
            u = ctypes.windll.user32
            hwnd = u.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            u.SetWindowLongW(hwnd, -20, u.GetWindowLongW(hwnd, -20) | 0x80000 | 0x20)
        except Exception:
            pass

    def _key_pressed(self, vk):
        if MANAGED:
            return False  # hotkeys are handled by the Rematch Scripts app
        try:
            down = bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
        except Exception:
            return False
        was = self._key_prev.get(vk, False)
        self._key_prev[vk] = down
        return down and not was

    def _poll(self):
        if not self.running:
            return
        latest = None
        try:
            while True:
                latest = self.text_q.get_nowait()
        except queue.Empty:
            pass
        if latest is not None and latest != self._shown_text:
            self._shown_text = latest
            self.label.config(text=latest)

        if self._key_pressed(self.cfg["key_snapshot"]):
            self.flags["snapshot"].set()
        if self._key_pressed(self.cfg["key_backend"]):
            self.flags["backend"].set()
        if self._key_pressed(self.cfg["key_debug"]):
            self.debug = not self.debug
            if not self.debug:
                self.cv2.destroyAllWindows()
        if self._key_pressed(self.cfg["key_exit"]):
            return self.shutdown()

        if self.debug:
            with self.dbg_lock:
                vis, self.dbg_frame = self.dbg_frame, None
            if vis is not None:
                self.cv2.imshow("REMATCH debug (Q - quit)", vis)
            if self.cv2.waitKey(1) & 0xFF == ord("q"):
                return self.shutdown()
        self.root.after(15, self._poll)

    def shutdown(self):
        self.running = False
        try:
            self.cv2.destroyAllWindows()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    # ---- поток захвата ----
    def _save(self, frame, name):
        os.makedirs(CALIB_DIR, exist_ok=True)
        path = os.path.join(CALIB_DIR, name)
        self.cv2.imwrite(path, frame)
        print("Snapshot saved:", path)

    def _capture_loop(self):
        cv2 = self.cv2
        cfg = self.cfg
        try:
            grab = Grabber(cfg)
        except Exception as e:
            print("CAPTURE ERROR:", e)
            return
        pred = ShotPredictor(cfg)
        last_sent = None
        first_saved = False
        prev_frame = None
        fps_t, fps_n, fps = time.perf_counter(), 0, 0.0
        seg = []            # лог текущего удара
        seg_last = 0.0

        def send(text):
            nonlocal last_sent
            if text != last_sent:
                last_sent = text
                self.text_q.put(text)

        while self.running:
            if MANAGED and cfg.get("only_in_game") and not is_game_focused():
                send("")
                time.sleep(0.2)
                continue
            if self.flags["backend"].is_set():
                self.flags["backend"].clear()
                grab.switch()
                pred = ShotPredictor(cfg)
            frame, new = grab.grab()
            if frame is None:
                time.sleep(0.005)
                continue
            if not first_saved:
                self._save(frame, "first_frame.png")
                first_saved = True
            if self.flags["snapshot"].is_set():
                self.flags["snapshot"].clear()
                self._save(frame, f"minimap_{int(time.time())}.png")

            if not new or (prev_frame is not None and np.array_equal(prev_frame, frame)):
                time.sleep(0.002)
                continue
            prev_frame = frame
            t = time.perf_counter()
            fps_n += 1
            if t - fps_t >= 1.0:
                fps, fps_n, fps_t = fps_n / (t - fps_t), 0, t

            work = normalize_brightness(frame, cv2)
            ball, marker = detect(work, cfg, cv2)
            info = pred.update(t, ball, marker)
            send(verdict_text(info["verdict"]))

            # лог ударов для настройки
            moving = pred.debug.get("moving")
            if moving and ball is not None:
                seg.append([round(t, 3), round(ball.x, 1), round(ball.y, 1),
                            None if marker is None else round(marker.x, 1),
                            None if marker is None else round(marker.y, 1)])
                seg_last = t
            elif seg and t - seg_last > 0.6:
                try:
                    with open(LOG_PATH, "a", encoding="utf-8") as f:
                        f.write(json.dumps({"samples": seg, "goal": [cfg["goal_left_x"], cfg["goal_right_x"], cfg["goal_y"]],
                                            "verdict": pred.shown}, ensure_ascii=False) + "\n")
                except Exception:
                    pass
                seg = []

            if self.debug:
                vis = frame.copy()
                gl, gr, gy = cfg["goal_left_x"], cfg["goal_right_x"], cfg["goal_y"]
                cv2.line(vis, (int(gl), int(gy)), (int(gr), int(gy)), (0, 255, 0), 2)
                if marker is not None:
                    cv2.circle(vis, (int(marker.x), int(marker.y)), int(marker.r), (255, 0, 255), 1)
                    cv2.circle(vis, (int(marker.x), int(marker.y)), 2, (255, 0, 255), -1)
                if ball is not None:
                    col = (0, 255, 0) if ball.free else (0, 0, 255)
                    cv2.circle(vis, (int(ball.x), int(ball.y)), 15, col, 1)
                dbg = pred.debug
                for key, col in (("xa", (255, 255, 0)), ("xb", (255, 0, 255))):
                    xv = dbg.get(key)
                    if xv is not None:
                        cv2.circle(vis, (int(np.clip(xv, 0, vis.shape[1] - 1)), int(gy)), 5, col, -1)
                cv2.putText(vis, f"{grab.mode} {fps:.0f}fps", (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
                cv2.putText(vis, verdict_text(info["verdict"]) or "-", (4, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
                with self.dbg_lock:
                    self.dbg_frame = vis

        grab.close()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()

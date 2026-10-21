"""Точка входа для меню Rematch Scripts. Режим (мышь/геймпад) и все параметры берутся из меню."""
import json
import os

from balllock_core import run, MouseOutput, GamepadOutput, MOUSE_GAINS, GAMEPAD_GAINS

if __name__ == "__main__":
    path = os.environ.get("REMATCH_CONFIG")
    mode = "mouse"
    if path:
        try:
            with open(path, "r", encoding="utf-8") as f:
                mode = json.load(f).get("mode", "mouse")
        except Exception:
            pass
    if mode == "gamepad":
        run(GamepadOutput(), dict(GAMEPAD_GAINS), "REMATCH BALL LOCK - GAMEPAD", path)
    else:
        run(MouseOutput(), dict(MOUSE_GAINS), "REMATCH BALL LOCK - MOUSE", path)

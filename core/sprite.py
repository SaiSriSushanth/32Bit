# core/sprite.py
# Sprite sheet animator using Pillow + tkinter PhotoImage.
# Each ROW in the sheet = one animation state.
# Each column = one frame. Config drives everything — no hardcoded values.

from PIL import Image, ImageTk
import tkinter as tk
from core.events import bus


class SpriteAnimator:
    def __init__(self, canvas: tk.Canvas, config: dict):
        self.canvas = canvas
        cfg = config["sprite"]
        self.fw = cfg["frame_width"]
        self.fh = cfg["frame_height"]
        self.scale = cfg["display_scale"]
        self.fps = cfg["fps"]
        self.states = cfg["states"]
        self.sheet = Image.open(cfg["sheet_path"]).convert("RGBA")
        self.current_state = "idle"
        self.current_frame = 0
        self.frames_cache: dict[str, list] = {}
        self._preload_frames()
        self.image_id = self.canvas.create_image(0, 0, anchor="nw")
        bus.on("sprite_state_change", self._on_state_change)
        self._animate()

    def _preload_frames(self):
        for state, cfg in self.states.items():
            row = cfg["row"]
            frames = []
            for col in range(cfg["frames"]):
                box = (
                    col * self.fw, row * self.fh,
                    (col + 1) * self.fw, (row + 1) * self.fh
                )
                frame = self.sheet.crop(box).resize(
                    (self.fw * self.scale, self.fh * self.scale),
                    Image.NEAREST  # pixel-perfect upscaling — no blurring
                )
                frames.append(ImageTk.PhotoImage(frame))
            self.frames_cache[state] = frames

    def _on_state_change(self, state: str, **kwargs):
        if state in self.states:
            self.current_state = state
            self.current_frame = 0

    def _animate(self):
        frames = self.frames_cache.get(self.current_state, [])
        if frames:
            self.canvas.itemconfig(self.image_id, image=frames[self.current_frame])
            state_cfg = self.states[self.current_state]
            next_frame = self.current_frame + 1
            if next_frame >= len(frames):
                if state_cfg.get("loop", True):
                    self.current_frame = 0
                else:
                    bus.emit("sprite_state_change", state="idle")
            else:
                self.current_frame = next_frame
        self.canvas.after(int(1000 / self.fps), self._animate)

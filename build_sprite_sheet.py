# build_sprite_sheet.py
# Stitches Trader_3 individual PNGs into a single sprite sheet for Buddy.
# Run once: python build_sprite_sheet.py

from PIL import Image
import os

SRC = "Free-City-Trader-Character-Sprite-Sheets-Pixel-Art/Trader_1"
OUT = "assets/sprite_sheet.png"
FRAME_W, FRAME_H = 128, 128

rows = [
    ("Idle.png",      6),   # row 0 — idle
    ("Idle_2.png",    6),   # row 1 — listening  (first 6 of 11)
    ("Idle_3.png",    7),   # row 2 — thinking
    ("Dialogue.png",  8),   # row 3 — speaking   (first 8 of 16)
    ("Approval.png",  8),   # row 4 — wakeup
]

FRAMES_PER_ROW = max(frames for _, frames in rows)

sheet_w = FRAME_W * FRAMES_PER_ROW
sheet_h = FRAME_H * len(rows)
sheet = Image.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 0))

for row_idx, (filename, num_frames) in enumerate(rows):
    src = Image.open(os.path.join(SRC, filename)).convert("RGBA")
    for col in range(num_frames):
        box = (col * FRAME_W, 0, (col + 1) * FRAME_W, FRAME_H)
        frame = src.crop(box)
        sheet.paste(frame, (col * FRAME_W, row_idx * FRAME_H))

os.makedirs("assets", exist_ok=True)
sheet.save(OUT)
print(f"Saved {sheet_w}x{sheet_h} sprite sheet to {OUT}")

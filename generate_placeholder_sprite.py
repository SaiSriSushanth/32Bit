# generate_placeholder_sprite.py
# Generates a simple coloured-circle spritesheet for testing.

from PIL import Image, ImageDraw
import os

os.makedirs("assets", exist_ok=True)
sheet = Image.new("RGBA", (192, 160), (0, 0, 0, 0))
draw  = ImageDraw.Draw(sheet)
colors = [
    (100, 180, 255, 255),  # row 0 — idle      (blue)
    (100, 255, 180, 255),  # row 1 — listening  (green)
    (255, 200, 100, 255),  # row 2 — thinking   (amber)
    (255, 100, 180, 255),  # row 3 — speaking   (pink)
    (180, 100, 255, 255),  # row 4 — wakeup     (purple)
]
for row, color in enumerate(colors):
    num_frames = 6 if row == 4 else 4
    for col in range(num_frames):
        x, y = col * 32, row * 32
        draw.ellipse([x + 4, y + 4, x + 28, y + 28], fill=color)
sheet.save("assets/sprite_sheet.png")
print("Placeholder sprite sheet saved to assets/sprite_sheet.png")

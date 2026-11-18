"""Generates the original placeholder costume art. Replace the PNGs any time; the code does not care."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

out = Path(__file__).resolve().parents[1] / "frontend" / "effects" / "mario-cap"
out.mkdir(parents=True, exist_ok=True)
W, H = 400, 260
im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
d = ImageDraw.Draw(im)
d.pieslice((40, 20, 360, 340), 180, 360, fill=(214, 40, 40, 255), outline=(120, 10, 10, 255), width=6)  # dome
d.rounded_rectangle((20, 170, 380, 235), 30, fill=(190, 30, 30, 255), outline=(120, 10, 10, 255), width=6)  # brim
d.ellipse((150, 60, 250, 150), fill=(255, 255, 255, 255), outline=(120, 10, 10, 255), width=4)  # badge
try:
    f = ImageFont.truetype("DejaVuSans-Bold.ttf", 72)
except OSError:
    f = ImageFont.load_default()
d.text((200, 106), "N", fill=(214, 40, 40, 255), font=f, anchor="mm")
im.save(out / "cap.png")
th = im.resize((120, 78)); th.save(out / "thumb.png")
print("wrote", out)

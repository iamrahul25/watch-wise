"""Generates the Play Store graphics for Watch Wise into play-store/.

    python tools/gen_store_assets.py icon         # icon-512.png (same design as the launcher icon)
    python tools/gen_store_assets.py feature      # feature-graphic.png (1024x500)
    python tools/gen_store_assets.py phone <raw dir>   # frames raw phone screencaps -> screenshots/
    python tools/gen_store_assets.py wear <raw dir>    # raw round-watch screencaps -> wear-screenshots/

Raw phone captures are 1080x2424 (too tall for Play's 2:1 limit), so each is placed on a
1080x1920 canvas with a caption. The caption comes from the file name: 01_Pick-a-face.png.
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "play-store"

INK = (7, 8, 11)
BG = (14, 17, 24)
SURFACE = (24, 27, 35)
HAIRLINE = (38, 43, 54)
MUTED = (141, 149, 167)
WHITE = (244, 246, 250)
MINT = (94, 230, 168)
CYAN = (87, 199, 255)
AMBER = (255, 194, 87)


def font(size, bold=True):
    for name in (("segoeuib.ttf", "arialbd.ttf") if bold else ("segoeui.ttf", "arial.ttf")):
        try:
            return ImageFont.truetype(f"C:/Windows/Fonts/{name}", size)
        except OSError:
            continue
    return ImageFont.load_default()


def gradient(size, start, end, horizontal=False):
    w, h = size
    g = Image.new("RGB", (w, h))
    px = g.load()
    for i in range(w if horizontal else h):
        t = i / max(1, (w if horizontal else h) - 1)
        c = tuple(round(a + (b - a) * t) for a, b in zip(start, end))
        for j in range(h if horizontal else w):
            px[(i, j) if horizontal else (j, i)] = c
    return g


def draw_watch(size, background=True):
    """The launcher-icon design (108-unit viewport) rendered at `size` px, supersampled."""
    s = size * 4
    u = s / 108
    img = Image.new("RGBA", (s, s), BG + (255,) if background else (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Straps
    for y0, y1 in ((22, 36), (72, 86)):
        d.rounded_rectangle([44 * u, y0 * u, 64 * u, y1 * u], radius=4 * u, fill=HAIRLINE)
    # Case
    d.ellipse([30 * u, 30 * u, 78 * u, 78 * u], fill=SURFACE)
    # Gradient ring: draw the ring as a mask over a mint -> cyan gradient
    ring = Image.new("L", (s, s), 0)
    rd = ImageDraw.Draw(ring)
    rd.ellipse([30 * u, 30 * u, 78 * u, 78 * u], outline=255, width=round(4.5 * u))
    img.paste(gradient((s, s), MINT, CYAN, horizontal=True), (0, 0), ring)
    # Ticks at 12 / 3 / 6 / 9
    for cx, cy in ((54, 37), (71, 54), (54, 71), (37, 54)):
        d.ellipse([(cx - 1.6) * u, (cy - 1.6) * u, (cx + 1.6) * u, (cy + 1.6) * u], fill=MUTED)
    # Hands (round caps)
    def hand(x1, y1, color, width):
        d.line([54 * u, 54 * u, x1 * u, y1 * u], fill=color, width=round(width * u))
        r = width / 2
        d.ellipse([(x1 - r) * u, (y1 - r) * u, (x1 + r) * u, (y1 + r) * u], fill=color)
    hand(54, 41, WHITE, 4.5)
    hand(65, 60, MINT, 4.5)
    d.ellipse([51 * u, 51 * u, 57 * u, 57 * u], fill=AMBER)
    return img.resize((size, size), Image.LANCZOS)


def icon():
    OUT.mkdir(exist_ok=True)
    draw_watch(512).save(OUT / "icon-512.png")
    print("icon-512.png")


def feature():
    w, h = 1024, 500
    img = gradient((w, h), (10, 12, 18), (22, 30, 44), horizontal=True).convert("RGBA")
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([40, 20, 500, 480], fill=MINT + (60,))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(90)))
    watch = draw_watch(380, background=False)
    img.alpha_composite(watch, (80, 60))
    d = ImageDraw.Draw(img)
    d.text((500, 150), "Watch Wise", font=font(84), fill=WHITE)
    d.text((504, 258), "Bold watch faces for Wear OS", font=font(36, bold=False), fill=MUTED)
    d.text((504, 318), "Pick on your phone. Set in one tap.", font=font(30, bold=False), fill=MINT)
    img.convert("RGB").save(OUT / "feature-graphic.png")
    print("feature-graphic.png")


def phone(raw_dir):
    dest = OUT / "screenshots"
    dest.mkdir(parents=True, exist_ok=True)
    for old in dest.glob("*.png"):
        old.unlink()
    for i, raw in enumerate(sorted(Path(raw_dir).glob("*.png")), 1):
        caption = raw.stem.split("_", 1)[-1].replace("-", " ")
        canvas = gradient((1080, 1920), (16, 20, 30), INK).convert("RGBA")
        d = ImageDraw.Draw(canvas)
        f = font(64)
        tw = d.textlength(caption, font=f)
        d.text(((1080 - tw) / 2, 90), caption, font=f, fill=WHITE)
        shot = Image.open(raw).convert("RGBA")
        scale = 1560 / shot.height
        shot = shot.resize((round(shot.width * scale), 1560), Image.LANCZOS)
        mask = Image.new("L", shot.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, *shot.size], radius=48, fill=255)
        x = (1080 - shot.width) // 2
        ImageDraw.Draw(canvas).rounded_rectangle([x - 6, 254, x + shot.width + 6, 254 + 1572], radius=54, fill=HAIRLINE)
        canvas.paste(shot, (x, 260), mask)
        canvas.convert("RGB").save(dest / f"{i:02d}.png")
        print(f"screenshots/{i:02d}.png  {caption}")


def wear(raw_dir):
    """Play wants square Wear OS screenshots of the app UI, no device frame or mask."""
    dest = OUT / "wear-screenshots"
    dest.mkdir(parents=True, exist_ok=True)
    for old in dest.glob("*.png"):
        old.unlink()
    for i, raw in enumerate(sorted(Path(raw_dir).glob("*.png")), 1):
        shot = Image.open(raw).convert("RGB")
        side = min(shot.size)
        shot = shot.crop((0, 0, side, side))
        if side < 384:
            shot = shot.resize((384, 384), Image.LANCZOS)
        shot.save(dest / f"{i:02d}.png")
        print(f"wear-screenshots/{i:02d}.png")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"icon": icon, "feature": feature}.get(cmd, lambda: None)()
    if cmd in ("phone", "wear"):
        (phone if cmd == "phone" else wear)(sys.argv[2])
    elif cmd not in ("icon", "feature"):
        sys.exit(__doc__)

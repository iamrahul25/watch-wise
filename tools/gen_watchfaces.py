"""Generate the Watch Face Format (WFF) sources for the pushed watch faces.

Writes, for each face module under watchfaces/<face>/src:
  main/res/font/*.ttf             static font weights cut from the variable fonts in
                                  app/src/main/assets/fonts (WFF has no variable-axis support)
  main/res/drawable-nodpi/*.png   icons / dot grid images
  main/res/values/strings.xml     labels for the face and its accent options
  main/res/xml/watch_face_info.xml
  <accent>/res/raw/watchface.xml  one per accent flavour; identical except for the
                                  default accent, so the pushed face starts in the
                                  colour picked in the app (still changeable in the
                                  watch's own Customise screen)

Layout follows the "AMOLED Watch Faces" design artboards (450 x 450 px), using the real
font metrics so text sits where the browser (and the app's Kotlin previews) put it.

Needs: fonttools, pillow  (pip install fonttools pillow)
Run:   python tools/gen_watchfaces.py
"""

import math
import os
import re
from xml.sax.saxutils import escape

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_SRC = os.path.join(ROOT, "app", "src", "main", "assets", "fonts")
SIZE = 450
CX = CY = SIZE / 2

# Characters the faces can show (digits, names of days/months, symbols).
CHARSET = "".join(chr(c) for c in range(0x20, 0x7F)) + "°·"


def argb(hex_rgb, alpha=0xFF):
    return f"#{alpha:02x}{hex_rgb.lstrip('#').lower()}"


def fmt(v):
    """Float attributes (shapes, sizes): ints where possible, else 2 decimals."""
    r = round(v, 2)
    return str(int(r)) if r == int(r) else f"{r:.2f}".rstrip("0")


def ifmt(v):
    """Integer attributes (x/y/width/height of Part* / clock elements)."""
    return str(int(round(v)))


# ---------------------------------------------------------------- fonts

class Font:
    """A static font instance written to res/font, plus its metrics for layout."""

    def __init__(self, src, out_dir, name, axes):
        self.name = name
        path = os.path.join(out_dir, name + ".ttf")
        tt = TTFont(os.path.join(FONT_SRC, src))
        tt = instancer.instantiateVariableFont(tt, axes)
        opts = subset.Options()
        opts.layout_features = ["*"]
        opts.name_IDs = ["*"]
        sub = subset.Subsetter(opts)
        sub.populate(text=CHARSET)
        sub.subset(tt)
        os.makedirs(out_dir, exist_ok=True)
        tt.save(path)
        self.upm = tt["head"].unitsPerEm
        hhea = tt["hhea"]
        self.asc, self.desc, self.gap = hhea.ascent, -hhea.descent, hhea.lineGap
        self.cmap = tt.getBestCmap()
        self.hmtx = tt["hmtx"]

    def line_h(self, size):
        """CSS 'normal' line height."""
        return (self.asc + self.desc + self.gap) / self.upm * size

    def width(self, text, size, letter_spacing=0.0):
        adv = sum(self.hmtx[self.cmap[ord(ch)]][0] for ch in text)
        return adv / self.upm * size + letter_spacing * size * len(text)


# ---------------------------------------------------------------- images

def svg_polylines(d):
    """Tiny SVG path parser (M/L/H/V/C/Z, absolute + relative) -> list of point lists."""
    tokens = re.findall(r"[MLHVCZmlhvcz]|-?\d*\.?\d+", d)
    lines, cur, start = [], [], (0.0, 0.0)
    x = y = 0.0
    cmd = None
    i = 0

    def num():
        nonlocal i
        v = float(tokens[i])
        i += 1
        return v

    while i < len(tokens):
        t = tokens[i]
        if re.match(r"[A-Za-z]", t):
            cmd = t
            i += 1
            if cmd in "Zz":
                cur.append(start)
                lines.append(cur)
                cur = []
                x, y = start
                continue
        rel = cmd.islower()
        c = cmd.upper()
        if c == "M":
            nx, ny = num(), num()
            x, y = (x + nx, y + ny) if rel else (nx, ny)
            if cur:
                lines.append(cur)
            cur, start = [(x, y)], (x, y)
            cmd = "l" if rel else "L"
        elif c == "L":
            nx, ny = num(), num()
            x, y = (x + nx, y + ny) if rel else (nx, ny)
            cur.append((x, y))
        elif c == "H":
            nx = num()
            x = x + nx if rel else nx
            cur.append((x, y))
        elif c == "V":
            ny = num()
            y = y + ny if rel else ny
            cur.append((x, y))
        elif c == "C":
            pts = [num() for _ in range(6)]
            if rel:
                pts = [pts[k] + (x if k % 2 == 0 else y) for k in range(6)]
            x0, y0 = x, y
            x1, y1, x2, y2, x3, y3 = pts
            for s in range(1, 17):
                t_ = s / 16
                mt = 1 - t_
                cur.append((
                    mt ** 3 * x0 + 3 * mt * mt * t_ * x1 + 3 * mt * t_ * t_ * x2 + t_ ** 3 * x3,
                    mt ** 3 * y0 + 3 * mt * mt * t_ * y1 + 3 * mt * t_ * t_ * y2 + t_ ** 3 * y3,
                ))
            x, y = x3, y3
    if cur:
        lines.append(cur)
    return lines


def icon_png(path, paths, circles=(), out=64):
    """White 24x24 line icon (stroke 2, round caps/joins), supersampled."""
    ss = 16
    k = out * ss / 24
    img = Image.new("RGBA", (out * ss, out * ss), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    w = 2 * k
    for d in paths:
        for line in svg_polylines(d):
            pts = [(px * k, py * k) for px, py in line]
            dr.line(pts, fill="white", width=int(w), joint="curve")
            for px, py in pts:  # round caps / joins
                dr.ellipse([px - w / 2, py - w / 2, px + w / 2, py + w / 2], fill="white")
    for cx, cy, r in circles:
        dr.ellipse([(cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k], outline="white", width=int(w))
    img.resize((out, out), Image.LANCZOS).save(path)


def dot_grid_png(path):
    """radial-gradient(#1c1c1c 1.2px, transparent 1.6px) on a 9px grid, 450x450."""
    ss = 4
    img = Image.new("RGBA", (SIZE * ss, SIZE * ss), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    r = 1.4 * ss
    for gy in range(SIZE // 9 + 1):
        for gx in range(SIZE // 9 + 1):
            cx, cy = (gx * 9 + 4.5) * ss, (gy * 9 + 4.5) * ss
            dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(0x1C, 0x1C, 0x1C, 255))
    img.resize((SIZE, SIZE), Image.LANCZOS).save(path, optimize=True)


def preview_png(path, title):
    """Placeholder preview (replaced by a real screenshot of the face)."""
    img = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    dr.ellipse([0, 0, 299, 299], fill="black", outline=(60, 60, 60, 255), width=3)
    dr.text((150, 150), title, fill="white", anchor="mm")
    img.save(path)


# ---------------------------------------------------------------- WFF XML helpers

def part_text(x, y, w, h, font, size, color, body, align="CENTER", letter_spacing=None,
              alpha=255, ambient_alpha=None, tint=None):
    ls = f' letterSpacing="{fmt(letter_spacing)}"' if letter_spacing else ""
    tint_attr = f' tintColor="{tint}"' if tint else ""
    variant = f'\n    <Variant mode="AMBIENT" target="alpha" value="{ambient_alpha}"/>' if ambient_alpha is not None else ""
    return f"""<PartText x="{ifmt(x)}" y="{ifmt(y)}" width="{ifmt(w)}" height="{ifmt(h)}" alpha="{alpha}"{tint_attr}>{variant}
  <Text align="{align}">
    <Font family="{font.name}" size="{fmt(size)}" color="{color}"{ls}>{body}</Font>
  </Text>
</PartText>"""


def template(fmt_str, *exprs):
    params = "".join(f'<Parameter expression="{escape(e)}"/>' for e in exprs)
    return f"<Template>{escape(fmt_str)}{params}</Template>"


_time_ids = iter(range(10_000))


def time_text(x, y, w, h, fmt_str, font, size, color, align="CENTER", letter_spacing=None,
              alpha=255, ambient_alpha=None, tint=None):
    """Time as a PartText built from time sources.

    Not a DigitalClock/TimeText: TimeText's Font has no letterSpacing in any WFF version,
    and the design needs tracking. Hours follow the watch's 12/24-hour setting.
    fmt_str: "hh", "mm", "hh:mm" or "ss".
    """
    def make(hour):
        parts = {"hh": ("%s", [hour]), "mm": ("%s", ["[MINUTE_Z]"]),
                 "hh:mm": ("%s:%s", [hour, "[MINUTE_Z]"]), "ss": ("%s", ["[SECOND_Z]"])}[fmt_str]
        return part_text(x, y, w, h, font, size, color, template(parts[0], *parts[1]), align=align,
                         letter_spacing=letter_spacing, alpha=alpha, ambient_alpha=ambient_alpha, tint=tint)

    if "hh" not in fmt_str:
        return make(None)
    return condition(f"h24_{next(_time_ids)}", "[IS_24_HOUR_MODE]", make("[HOUR_0_23_Z]"), make("[HOUR_1_12_Z]"))


def dot(x, y, d, color, tint=None):
    """Filled circle of diameter d centred on (x, y); integer part box, exact ellipse inside."""
    tint_attr = f' tintColor="{tint}"' if tint else ""
    px, py = math.floor(x - d / 2) - 1, math.floor(y - d / 2) - 1
    size = math.ceil(d) + 3
    return f"""<PartDraw x="{px}" y="{py}" width="{size}" height="{size}"{tint_attr}>
  <Ellipse x="{fmt(x - d / 2 - px)}" y="{fmt(y - d / 2 - py)}" width="{fmt(d)}" height="{fmt(d)}"><Fill color="{color}"/></Ellipse>
</PartDraw>"""


def rect(x, y, w, h, color):
    px, py = math.floor(x), math.floor(y)
    return f"""<PartDraw x="{px}" y="{py}" width="{math.ceil(w) + 1}" height="{math.ceil(h) + 1}">
  <Rectangle x="{fmt(x - px)}" y="{fmt(y - py)}" width="{fmt(w)}" height="{fmt(h)}"><Fill color="{color}"/></Rectangle>
</PartDraw>"""


def condition(name, expr, then_xml, else_xml=None):
    default = f"""
  <Default>
{indent(else_xml, 4)}
  </Default>""" if else_xml else ""
    return f"""<Condition>
  <Expressions><Expression name="{name}"><![CDATA[{expr}]]></Expression></Expressions>
  <Compare expression="{name}">
{indent(then_xml, 4)}
  </Compare>{default}
</Condition>"""


def group(name, children, alpha=255, ambient_alpha=None):
    variant = f'\n  <Variant mode="AMBIENT" target="alpha" value="{ambient_alpha}"/>' if ambient_alpha is not None else ""
    body = "\n".join(indent(c, 2) for c in children)
    return f"""<Group name="{name}" x="0" y="0" width="{SIZE}" height="{SIZE}" alpha="{alpha}">{variant}
{body}
</Group>"""


def indent(text, n):
    pad = " " * n
    return "\n".join(pad + line if line else line for line in text.splitlines())


def color_config(accents, default_index):
    options = "\n".join(
        f'    <ColorOption id="{i}" displayName="accent_{name}" colors="{argb(hex_)}"/>'
        for i, (name, hex_) in enumerate(accents)
    )
    return f"""  <UserConfigurations>
    <ColorConfiguration id="accent" displayName="accent_label" defaultValue="{default_index}">
{options}
    </ColorConfiguration>
  </UserConfigurations>"""


def watchface_xml(accents, default_index, scene_children, user_config=True, extra=""):
    scene = "\n".join(indent(c, 4) for c in scene_children)
    config = color_config(accents, default_index) + "\n" if user_config else ""
    extra = indent(extra, 2) + "\n" if extra else ""
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!-- Generated by tools/gen_watchfaces.py - edit the generator, not this file. -->
<WatchFace width="{SIZE}" height="{SIZE}" clipShape="CIRCLE">
  <Metadata key="CLOCK_TYPE" value="DIGITAL"/>
  <Metadata key="PREVIEW_TIME" value="10:08:32"/>
{config}{extra}  <Scene backgroundColor="#ff000000">
{scene}
  </Scene>
</WatchFace>
"""


ACCENT = "[CONFIGURATION.accent]"


# ---------------------------------------------------------------- Mono Stack

def mono_stack():
    face = "monostack"
    base = os.path.join(ROOT, "watchfaces", face, "src")
    res = os.path.join(base, "main", "res")
    fdir = os.path.join(res, "font")
    medium = Font("spacegrotesk.ttf", fdir, "spacegrotesk_medium", {"wght": 500})
    bold = Font("spacegrotesk.ttf", fdir, "spacegrotesk_bold", {"wght": 700})
    light = Font("spacegrotesk.ttf", fdir, "spacegrotesk_light", {"wght": 300})

    grey, minutes_grey = argb("8c8c8c"), argb("6f6f6f")

    # 60-dot seconds ring (radius 208): passed seconds white, current second big + accent.
    ring = []
    for i in range(60):
        a = i * math.pi / 30
        x, y = CX + 208 * math.sin(a), CY - 208 * math.cos(a)
        base_d = 5 if i % 5 == 0 else 3
        ring.append(condition(
            f"now{i}", f"[SECOND] == {i}",
            dot(x, y, 9, "#ffffffff", tint=ACCENT),
            condition(f"past{i}", f"[SECOND] > {i}",
                      dot(x, y, base_d, "#ffffffff"),
                      dot(x, y, base_d, argb("2a2a2a"))),
        ))
    markers = [dot(CX + 208 * math.sin(i * math.pi / 30), CY - 208 * math.cos(i * math.pi / 30), 4, argb("333333"))
               for i in range(0, 60, 5)]

    # Vertical stack: date, HH, MM, stats (CSS flex column, centred).
    date_h = medium.line_h(15)
    big_h = 150 * 0.86
    stat_h = medium.line_h(14)
    total = date_h + 14 + big_h * 2 + 16 + stat_h
    top = CY - total / 2
    date_y = top
    hh_y = date_y + date_h + 14
    mm_y = hh_y + big_h
    stat_y = mm_y + big_h + 16

    date = part_text(0, date_y, SIZE, date_h, medium, 15, grey,
                     "<Upper>" + template("%s %s %s", "[DAY_OF_WEEK_S]", "[DAY]", "[MONTH_S]") + "</Upper>",
                     letter_spacing=0.22, ambient_alpha=190)

    hours = time_text(0, hh_y, SIZE, big_h, "hh", bold, 150, "#ffffffff", letter_spacing=-0.05, ambient_alpha=0)
    minutes = time_text(0, mm_y, SIZE, big_h, "mm", bold, 150, minutes_grey, letter_spacing=-0.05, ambient_alpha=0)
    hours_amb = time_text(0, hh_y, SIZE, big_h, "hh", light, 150, argb("d0d0d0"), letter_spacing=-0.05,
                          alpha=0, ambient_alpha=255)
    minutes_amb = time_text(0, mm_y, SIZE, big_h, "mm", light, 150, argb("7a7a7a"), letter_spacing=-0.05,
                            alpha=0, ambient_alpha=255)

    # "84%  •  24°C": battery right-aligned before the dot, temperature left-aligned after it.
    gap, dot_d = 14, 4
    left_w = CX - dot_d / 2 - gap
    battery = part_text(0, stat_y, left_w, stat_h, medium, 14, grey,
                        template("%d%%", "[BATTERY_PERCENT]"), align="END", letter_spacing=0.08, ambient_alpha=190)
    sep = group("sep", [dot(CX, stat_y + stat_h / 2, dot_d, "#ffffffff", tint=ACCENT)], ambient_alpha=120)
    tx = CX + dot_d / 2 + gap

    def temp(body):
        return part_text(tx, stat_y, SIZE - tx, stat_h, medium, 14, grey, body, align="START",
                         letter_spacing=0.08, ambient_alpha=190)

    temperature = condition(
        "weather", "[WEATHER.IS_AVAILABLE]",
        condition("fahrenheit", "[WEATHER.TEMPERATURE_UNIT] == 2",
                  temp(template("%d°F", "[WEATHER.TEMPERATURE]")),
                  temp(template("%d°C", "[WEATHER.TEMPERATURE]"))),
        temp("--°C"),
    )

    scene = [
        group("seconds_ring", ring, ambient_alpha=0),
        group("ambient_markers", markers, alpha=0, ambient_alpha=255),
        date, hours, minutes, hours_amb, minutes_amb, battery, sep, temperature,
    ]
    accents = [("red", "FF3B30"), ("orange", "FF8A00"), ("cyan", "3BD8FF"), ("white", "FFFFFF")]
    write_module(face, "Mono Stack", accents, scene, res, base)


# ---------------------------------------------------------------- Dot Matrix

def dot_matrix():
    face = "dotmatrix"
    base = os.path.join(ROOT, "watchfaces", face, "src")
    res = os.path.join(base, "main", "res")
    fdir = os.path.join(res, "font")
    bold = Font("doto.ttf", fdir, "doto_bold", {"wght": 700, "ROND": 0})
    black = Font("doto.ttf", fdir, "doto_black", {"wght": 900, "ROND": 0})
    medium = Font("doto.ttf", fdir, "doto_medium", {"wght": 500, "ROND": 0})

    drawables = os.path.join(res, "drawable-nodpi")
    os.makedirs(drawables, exist_ok=True)
    dot_grid_png(os.path.join(drawables, "dot_grid.png"))
    icon_png(os.path.join(drawables, "icon_steps.png"), ["M7 21l3-6 3 2v5", "M6 12l3-4 4 1 3 4"], circles=[(13, 4, 2)])
    icon_png(os.path.join(drawables, "icon_flame.png"),
             ["M12 22c4 0 7-3 7-7 0-4-3-6-4-10-2 2-3 4-3 6-1-1-2-2-2-4-2 2-5 5-5 8 0 4 3 7 7 7z"])
    icon_png(os.path.join(drawables, "icon_pulse.png"), ["M3 12h4l2-5 4 10 2-5h6"])

    grey, white = argb("8c8c8c"), "#ffffffff"

    # Vertical stack (gap 10): date, time row, stats (+6), battery (+10).
    date_h = bold.line_h(20)
    time_h = 104 * 0.95
    value_h = black.line_h(22)
    label_h = bold.line_h(13)
    stats_h = 20 + 4 + value_h + 4 + label_h
    total = date_h + 10 + time_h + 10 + 6 + stats_h + 10 + 10 + 8
    top = CY - total / 2
    date_y = top
    time_y = date_y + date_h + 10
    stats_y = time_y + time_h + 10 + 6
    bat_y = stats_y + stats_h + 10 + 10

    background = f"""<PartImage x="0" y="0" width="{SIZE}" height="{SIZE}">
  <Variant mode="AMBIENT" target="alpha" value="0"/>
  <Image resource="dot_grid"/>
</PartImage>"""

    date = part_text(0, date_y, SIZE, date_h, bold, 20, grey,
                     "<Upper>" + template("%s · %s %s", "[DAY_OF_WEEK_S]", "[MONTH_S]", "[DAY]") + "</Upper>",
                     letter_spacing=0.08, ambient_alpha=190)

    # Time row: HH:MM + small accent seconds, bottom-aligned (margin-bottom 12), centred as a unit.
    hm_w = black.width("00:00", 104, -0.02)
    ss_w = black.width("00", 28)
    ss_h = black.line_h(28)
    x0 = CX - (hm_w + 4 + ss_w) / 2
    pad = 6  # slack so glyph overhang is not clipped
    hm = time_text(x0 - pad, time_y, hm_w + 2 * pad, time_h, "hh:mm", black, 104, white,
                   letter_spacing=-0.02, ambient_alpha=0)
    ss = time_text(x0 + hm_w + 4 - pad, time_y + time_h - 12 - ss_h, ss_w + 2 * pad, ss_h, "ss", black, 28, white,
                   tint=ACCENT, ambient_alpha=0)
    hm_amb = time_text(0, time_y, SIZE, time_h, "hh:mm", medium, 104, argb("c8c8c8"),
                       letter_spacing=-0.02, alpha=0, ambient_alpha=255)

    # Stats: 3 columns, gap 18, sized for the widest sample value ("8,412").
    col_w = max(black.width("8,412", 22), bold.width("STEPS", 13), 20)
    stats = []
    columns = [
        ("icon_steps", template("%d", "[STEP_COUNT]"), "STEPS"),
        ("icon_flame", template("%d", "floor([STEP_COUNT] * 0.04)"), "KCAL"),
        ("icon_pulse", None, "BPM"),
    ]
    for i, (icon, value, label) in enumerate(columns):
        ccx = CX + (i - 1) * (col_w + 18)
        stats.append(f"""<PartImage x="{ifmt(ccx - 10)}" y="{ifmt(stats_y)}" width="20" height="20" tintColor="{ACCENT}">
  <Image resource="{icon}"/>
</PartImage>""")
        vy = stats_y + 24
        vx, vw = ccx - col_w / 2 - 10, col_w + 20
        if value is None:  # heart rate: "--" until there is a reading
            stats.append(condition(
                "has_hr", "[HEART_RATE] > 0",
                part_text(vx, vy, vw, value_h, black, 22, white, template("%d", "round([HEART_RATE])")),
                part_text(vx, vy, vw, value_h, black, 22, white, "--"),
            ))
        else:
            stats.append(part_text(vx, vy, vw, value_h, black, 22, white, value))
        stats.append(part_text(vx, vy + value_h + 4, vw, label_h, bold, 13, grey, label))

    # Battery: 10 blocks of 8px, gap 4; block i is lit when round(battery / 10) > i.
    blocks = []
    bx = CX - (10 * 8 + 9 * 4) / 2
    for i in range(10):
        x = bx + i * 12
        blocks.append(condition(f"bat{i}", f"[BATTERY_PERCENT] >= {i * 10 + 5}",
                                rect(x, bat_y, 8, 8, white), rect(x, bat_y, 8, 8, argb("2a2a2a"))))

    scene = [
        background, date, hm, ss, hm_amb,
        group("stats", stats, ambient_alpha=150),
        group("battery", blocks, ambient_alpha=110),
    ]
    accents = [("lime", "B6FF3B"), ("white", "FFFFFF"), ("cyan", "3BD8FF"), ("orange", "FF8A00")]
    write_module(face, "Dot Matrix", accents, scene, res, base)


# ---------------------------------------------------------------- Ember Forest
#
# "05 · Ember Forest" from the "Pixel Art AMOLED Watch Faces" design: a 150 x 150 pixel
# grid (3 screen px per pixel) with a campfire, pines, tent and a camper. WFF can't run the
# design's per-pixel code, so this is a port of it that renders:
#   ember_bg.png         the still scene (pines, tent, camper, logs, fire glow)
#   ember_fire.webp      the flame, smoke and embers as a seamless 5.2 s loop at 10 fps
#                        (one per flame colour, cropped to the box where anything moves)
#   ember_ambient.png    the always-on embers and log
#   ef_*.png             the design's 3x5 / 5x7 pixel fonts as WFF bitmap fonts
# Differences from the design: the glow doesn't flicker (the still scene and the loop must
# match at the loop's edges), stars blink on whole seconds, and the animation frequencies
# are rounded to fit the 5.2 s loop. The app preview (EmberForestPainter.kt) mirrors this.

EF_N, EF_FX, EF_FB, EF_PX = 150, 75, 112, SIZE // 150
EF_LOOP, EF_FPS = 5.2, 10
EF_W = 2 * math.pi / EF_LOOP  # base angular frequency of the loop

EF_SMALL = {
    'A': '.#. #.# ### #.# #.#', 'B': '##. #.# ##. #.# ##.', 'C': '.## #.. #.. #.. .##', 'D': '##. #.# #.# #.# ##.',
    'E': '### #.. ##. #.. ###', 'F': '### #.. ##. #.. #..', 'G': '.## #.. #.# #.# .##', 'H': '#.# #.# ### #.# #.#',
    'I': '### .#. .#. .#. ###', 'J': '..# ..# ..# #.# .#.', 'K': '#.# #.# ##. #.# #.#', 'L': '#.. #.. #.. #.. ###',
    'M': '#.# ### ### #.# #.#', 'N': '##. #.# #.# #.# #.#', 'O': '.#. #.# #.# #.# .#.', 'P': '##. #.# ##. #.. #..',
    'Q': '.#. #.# #.# ##. .##', 'R': '##. #.# ##. #.# #.#', 'S': '.## #.. .#. ..# ##.', 'T': '### .#. .#. .#. .#.',
    'U': '#.# #.# #.# #.# ###', 'V': '#.# #.# #.# #.# .#.', 'W': '#.# #.# ### ### #.#', 'X': '#.# #.# .#. #.# #.#',
    'Y': '#.# #.# .#. .#. .#.', 'Z': '### ..# .#. #.. ###',
    '0': '### #.# #.# #.# ###', '1': '.#. ##. .#. .#. ###', '2': '##. ..# .#. #.. ###', '3': '##. ..# .#. ..# ##.',
    '4': '#.# #.# ### ..# ..#', '5': '### #.. ##. ..# ##.', '6': '.## #.. ### #.# ###', '7': '### ..# .#. .#. .#.',
    '8': '### #.# ### #.# ###', '9': '### #.# ### ..# ##.',
    ':': '. # . # .', '%': '#.# ..# .#. #.. #.#', '/': '..# ..# .#. #.. #..', '.': '. . . . #',
    '-': '... ... ### ... ...', ' ': '.. .. .. .. ..', '·': '. . # . .', '°': '##. ##. ... ... ...',
}
EF_BIG = {
    '0': '.###. #...# #..## #.#.# ##..# #...# .###.', '1': '..#.. .##.. ..#.. ..#.. ..#.. ..#.. .###.',
    '2': '.###. #...# ....# ..##. .#... #.... #####', '3': '####. ....# ....# .###. ....# ....# ####.',
    '4': '...#. ..##. .#.#. #..#. ##### ...#. ...#.', '5': '##### #.... ####. ....# ....# #...# .###.',
    '6': '..##. .#... #.... ####. #...# #...# .###.', '7': '##### ....# ...#. ..#.. .#... .#... .#...',
    '8': '.###. #...# #...# .###. #...# #...# .###.', '9': '.###. #...# #...# .#### ....# ...#. .##..',
    ':': '. . # . # . .',
}
EF_GLYPH_NAMES = {':': 'colon', '%': 'pct', '/': 'slash', '.': 'dot', '-': 'dash', ' ': 'space',
                  '·': 'middot', '°': 'deg'}


def ef_palette(flame):
    return ['000000', 'ffe2b8', 'd9925a', '2a1206', '160703', '2e1004', '521c06', 'ff3d00', flame, 'ffd23f',
            'fff4c8', '7a4a22', '3e220e', 'c9773a', '050a08', '7a3010', '1f1c1b', 'b9b2a0', '1e2a3c', 'a84c22',
            '0c0806', 'd06a2a', '2a1408']


def jround(v):
    """JavaScript Math.round."""
    return math.floor(v + 0.5)


def ef_hash(a, b):
    v = math.sin(a * 127.1 + b * 311.7) * 43758.5453
    return v - math.floor(v)


def ef_glyph(ch, big=False):
    return ((big and EF_BIG.get(ch)) or EF_SMALL.get(ch) or EF_SMALL[' ']).split(' ')


def ef_text_width(text, s=1, big=False):
    return sum((len(ef_glyph(ch, big)[0]) + 1) * s for ch in text) - s


class Pixels:
    """The design's pixel buffer (palette indices), same drawing rules as its JS engine."""

    _BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5]

    def __init__(self, n=EF_N):
        self.n = n
        self.b = bytearray(n * n)

    def set(self, x, y, c):
        x, y = jround(x), jround(y)
        if 0 <= x < self.n and 0 <= y < self.n:
            self.b[y * self.n + x] = c

    def get(self, x, y):
        x, y = jround(x), jround(y)
        return self.b[y * self.n + x] if 0 <= x < self.n and 0 <= y < self.n else 0

    def rect(self, x, y, w, h, c):
        for j in range(h):
            for i in range(w):
                self.set(x + i, y + j, c)

    def line(self, x0, y0, x1, y1, c):
        s = max(abs(x1 - x0), abs(y1 - y0)) or 1
        for i in range(s + 1):
            self.set(x0 + (x1 - x0) * i / s, y0 + (y1 - y0) * i / s, c)

    def dith(self, x, y, t):
        return t * 16 > self._BAYER[(y & 3) * 4 + (x & 3)]

    def text(self, text, x, y, c, s=1, big=False):
        for ch in text:
            rows = ef_glyph(ch, big)
            for j, r in enumerate(rows):
                for i, p in enumerate(r):
                    if p == '#':
                        self.rect(x + i * s, y + j * s, s, s, c)
            x += (len(rows[0]) + 1) * s

    def ctext(self, text, y, c, s=1, big=False):
        self.text(text, jround((self.n - ef_text_width(text, s, big)) / 2), y, c, s, big)

    def image(self, flame, transparent_zero=False):
        """3x nearest-neighbour RGBA image, clipped to the round screen like the design."""
        pal = [tuple(int(h[k:k + 2], 16) for k in (0, 2, 4)) for h in ef_palette(flame)]
        n, r = self.n, self.n / 2
        img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
        px = img.load()
        for y in range(n):
            dy = y + 0.5 - r
            hw = math.sqrt(max(0, r * r - dy * dy))
            x0, x1 = math.ceil(r - hw - 0.5), math.floor(r + hw - 0.5)
            for x in range(n):
                c = self.b[y * n + x]
                if (c == 0 and transparent_zero) or not (x0 <= x <= x1):
                    continue
                px[x, y] = pal[c] + (255,)
        return img.resize((n * EF_PX, n * EF_PX), Image.NEAREST)


def ef_stars():
    """(x, y, phase) of the design's 30 stars, minus the ones behind the time."""
    stars = []
    for i in range(30):
        x, y = math.floor(ef_hash(i, 1) * EF_N), math.floor(ef_hash(i, 2) * 70)
        if 14 < y < 52 and 28 < x < 122:
            continue
        stars.append((x, y, jround(i * 2.1 / 1.5) % 4))
    return stars


def ef_scene(e):
    """The still scene: glow (no flicker), pines, tent, camper, logs."""
    FX, FB = EF_FX, EF_FB
    for y in range(78, EF_N):
        for x in range(EF_N):
            ground = y >= 106
            d = math.hypot((x - FX) / 1.9, (y - FB) * 1.2) if ground else math.hypot(x - FX, (y - FB) * 0.9) * 1.6
            v = max(0.0, 3 - d / 12)
            base = math.floor(v)
            lvl = min(3, base + (1 if e.dith(x, y, v - base) else 0))
            if lvl > 0:
                e.set(x, y, 3 + lvl)

    def pine(bx, by, h):
        for j in range(h):
            w = math.floor((j % 6) * 0.7 + j * 0.22)
            e.rect(bx - w, by - h + j, w * 2 + 1, 1, 14)
            ex = bx + w if bx < FX else bx - w
            if abs(ex - FX) < 58 and j > 2:
                e.set(ex, by - h + j, 15)
        e.rect(bx, by, 2, 3, 14)

    for x, y, h in [(6, 104, 30), (16, 106, 42), (27, 104, 26), (124, 104, 28), (134, 106, 44), (145, 105, 30),
                    (3, 108, 22), (148, 108, 20)]:
        pine(x, y, h)
    for j in range(23):
        hw = math.floor(j * 0.7)
        for i in range(-hw, hw + 1):
            door = j > 10 and abs(i) < (j - 10) * 0.45
            e.set(114 + i, 90 + j, 0 if door else (19 if i < 0 else 18))
    e.line(114, 88, 114, 90, 18)
    camper = ['...###....', '..#####...', '..#####...', '...###....', '..#####...', '.#######..', '.########.',
              '.#######..', '..######..', '..#####...', '..######..', '..##..###.', '..##...##.', '.###..###.']
    for j, r in enumerate(camper):
        last = r.rfind('#')
        for i, p in enumerate(r):
            if p == '#':
                e.set(36 + i, 96 + j, 21 if i >= last - (1 if 4 < j < 9 else 0) else 20)
    e.rect(32, 110, 18, 3, 12)
    e.rect(32, 110, 18, 1, 13)
    for w in range(3):
        e.line(62, 115 + w, 86, 109 + w, 13 if w == 0 else 11)
        e.line(64, 108 + w, 88, 114 + w, 13 if w == 0 else 11)
    e.rect(61, 115, 2, 3, 12)
    e.rect(87, 114, 2, 3, 12)


def ef_fire(e, t):
    """Smoke, flame, flame bits and embers at time t (seconds, loops every EF_LOOP)."""
    FX, FB, W = EF_FX, EF_FB, EF_W
    for i in range(6):
        age = (t / EF_LOOP + i / 6) % 1
        cx = FX + math.sin(age * 4 + i) * 6 + age * 12
        cy = FB - 28 - age * 52
        r = 2 + age * 7
        yy = -r
        while yy <= r:
            xx = -r
            while xx <= r:
                if xx * xx + yy * yy <= r * r:
                    px, py = jround(cx + xx), jround(cy + yy)
                    if e.get(px, py) == 0 and e.dith(px, py, 0.32 * (1 - age)):
                        e.set(px, py, 16)
                xx += 1
            yy += 1
    for x in range(-11, 12):
        H = 24 * max(0.0, 1 - abs(x) / 12) ** 1.2
        h = H * (0.72 + 0.22 * math.sin(t * 9 * W + x * 1.7) + 0.16 * math.sin(t * 14 * W + x * 0.6))
        y = 0
        while y < h:
            rel = y / h
            px = FX + x + jround(math.sin(t * 5 * W + y * 0.35) * rel * 2)
            py = FB - 2 - y
            y += 1
            if rel > 0.86 and not e.dith(px, py, 0.5):
                continue
            core = 5 * (1 - rel * 1.1)
            c = 7
            if abs(x) < core * 0.55 and rel < 0.4:
                c = 10
            elif abs(x) < core and rel < 0.6:
                c = 9
            elif rel < 0.78:
                c = 8
            e.set(px, py, c)
    for k in range(3):
        a = (t * 8 / EF_LOOP + k * 0.33) % 1
        bx = FX + [-4, 2, 6][k] + jround(math.sin(t * 4 * W + k) * 2)
        if a < 0.7:
            e.rect(bx, jround(FB - 22 - a * 12), 2, 3, 8 if a < 0.35 else 7)
    for i in range(18):
        age = (t * 2 / EF_LOOP + ef_hash(i, 4)) % 1
        x = FX + (ef_hash(i, 7) - 0.5) * 10 + math.sin(age * 7 + i) * 5 * age + age * 8 * (ef_hash(i, 8) - 0.3)
        y = FB - 10 - age * 78
        c = 10 if age < 0.25 else 9 if age < 0.45 else 8 if age < 0.7 else 7 if age < 0.9 else 0
        if c:
            e.set(x, y, c)
            if i % 4 == 0:
                e.set(x, y + 1, 7)


def ef_ambient(e):
    for i in range(-6, 7):
        if math.sin(i * 1.3) > 0:
            e.set(EF_FX + i, EF_FB - 1 - (1 if i % 2 == 0 else 0), 8 if i % 3 == 0 else 7)
    e.line(64, 113, 86, 110, 12)


EF_TIME_X = jround((EF_N - ef_text_width("00:00", 3, True)) / 2)


def ef_preview(flame):
    """Preview image: the design at 10:08 with sample date and stats."""
    e = Pixels()
    for x, y, phase in ef_stars():
        if phase < 2:
            e.set(x, y, 17)
    ef_scene(e)
    ef_fire(e, 1.3)
    e.text("10:08", EF_TIME_X + 1, 22, 3, 3, True)
    e.text("10:08", EF_TIME_X, 21, 1, 3, True)
    e.ctext("THURSDAY 26 NOV", 46, 2)
    e.rect(36, 125, 78, 16, 0)
    for s in range(10):
        e.rect(46 + s * 6, 127, 4, 2, 8 if s < 7 else 22)
    e.ctext("MOVE 7/10 · 82%", 132, 2)
    return e.image(flame, transparent_zero=False)


def ef_glyph_png(path, ch, big, s, hex_rgb):
    """One bitmap-font character: its pixels plus the 1-pixel gap after it."""
    rows = ef_glyph(ch, big)
    k = s * EF_PX
    w, h = (len(rows[0]) + 1) * k, len(rows) * k
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    rgb = tuple(int(hex_rgb[i:i + 2], 16) for i in (0, 2, 4))
    for j, r in enumerate(rows):
        for i, p in enumerate(r):
            if p == '#':
                dr.rectangle([i * k, j * k, i * k + k - 1, j * k + k - 1], fill=rgb + (255,))
    img.save(path, optimize=True)
    return w, h


def ember_forest():
    face = "emberforest"
    base = os.path.join(ROOT, "watchfaces", face, "src")
    res = os.path.join(base, "main", "res")
    drawables = os.path.join(res, "drawable-nodpi")
    os.makedirs(drawables, exist_ok=True)
    accents = [("orange", "FF8A00"), ("cyan", "3DD6FF"), ("violet", "B469FF"), ("green", "5CFF7A")]
    P = EF_PX

    # Still scene, plus the black box behind the stats bar.
    bg = Pixels()
    ef_scene(bg)
    bg.rect(36, 125, 78, 16, 0)
    bg.image("000000").save(os.path.join(drawables, "ember_bg.png"), optimize=True)

    # Box (in pixels) where the loop changes anything.
    times = [i / EF_FPS for i in range(round(EF_LOOP * EF_FPS))]
    frames = []
    bx0 = by0 = EF_N
    bx1 = by1 = -1
    for t in times:
        e = Pixels()
        ef_scene(e)
        e.rect(36, 125, 78, 16, 0)
        ef_fire(e, t)
        frames.append(e)
        for idx, (a, b) in enumerate(zip(e.b, bg.b)):
            if a != b:
                x, y = idx % EF_N, idx // EF_N
                bx0, by0, bx1, by1 = min(bx0, x), min(by0, y), max(bx1, x), max(by1, y)
    box = (bx0 * P, by0 * P, (bx1 + 1) * P, (by1 + 1) * P)

    for name, hex_ in accents:
        flavour = os.path.join(base, name, "res", "drawable-nodpi")
        os.makedirs(flavour, exist_ok=True)
        imgs = [f.image(hex_).crop(box).convert("RGB") for f in frames]
        imgs[0].save(os.path.join(flavour, "ember_fire.webp"), save_all=True, append_images=imgs[1:],
                     duration=1000 // EF_FPS, loop=0, lossless=True, quality=100, method=6)
        amb = Pixels()
        ef_ambient(amb)
        amb.image(hex_, transparent_zero=True).save(os.path.join(flavour, "ember_ambient.png"), optimize=True)
        ef_preview(hex_).save(os.path.join(flavour, "preview.png"), optimize=True)

    # Bitmap fonts: each in its colour (bitmap glyphs aren't tinted).
    fonts = {
        "ember_time": (True, 3, "ffe2b8", "0123456789:"),
        "ember_shadow": (True, 3, "2a1206", "0123456789:"),
        "ember_time_amb": (True, 3, "d9925a", "0123456789:"),
        "ember_small": (False, 1, "d9925a", "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:%/.- ·°"),
    }
    font_xml = []
    for fname, (big, s, color, chars) in fonts.items():
        entries = []
        for ch in chars:
            rname = f"ef_{fname.removeprefix('ember_')}_{EF_GLYPH_NAMES.get(ch, ch.lower())}"
            w, h = ef_glyph_png(os.path.join(drawables, rname + ".png"), ch, big, s, color)
            entries.append(f'  <Character name="{escape(ch, {chr(34): "&quot;"})}" resource="{rname}" width="{w}" height="{h}"/>')
        font_xml.append(f'<BitmapFont name="{fname}">\n' + "\n".join(entries) + "\n</BitmapFont>")
    bitmap_fonts = "<BitmapFonts>\n" + "\n".join(indent(x, 2) for x in font_xml) + "\n</BitmapFonts>"
    big_h, small_h = 7 * 3 * P, 5 * P

    def btext(x, y, w, h, family, size, body, align="START", alpha=255, ambient_alpha=None):
        variant = f'\n  <Variant mode="AMBIENT" target="alpha" value="{ambient_alpha}"/>' if ambient_alpha is not None else ""
        return f"""<PartText x="{x}" y="{y}" width="{w}" height="{h}" alpha="{alpha}">{variant}
  <Text align="{align}">
    <BitmapFont family="{family}" size="{size}">{body}</BitmapFont>
  </Text>
</PartText>"""

    def time_part(x, y, family, alpha=255, ambient_alpha=None):
        w = (ef_text_width("00:00", 3, True) + 3) * P

        def make(hour):
            return btext(x, y, w, big_h, family, big_h, template("%s:%s", hour, "[MINUTE_Z]"),
                         alpha=alpha, ambient_alpha=ambient_alpha)
        return condition(f"h24_{next(_time_ids)}", "[IS_24_HOUR_MODE]", make("[HOUR_0_23_Z]"), make("[HOUR_1_12_Z]"))

    def scene(index):
        flame = argb(accents[index][1])
        stars = [condition(f"star{i}", f"([SECOND] + {phase}) % 4 < 2",
                           rect(x * P, y * P, P, P, argb("b9b2a0")))
                 for i, (x, y, phase) in enumerate(ef_stars())]
        fire = f"""<PartAnimatedImage x="{box[0]}" y="{box[1]}" width="{box[2] - box[0]}" height="{box[3] - box[1]}">
  <AnimationController play="ON_VISIBLE" repeat="TRUE" beforePlaying="FIRST_FRAME" afterPlaying="FIRST_FRAME"/>
  <AnimatedImage resource="ember_fire" format="WEBP"/>
</PartAnimatedImage>"""
        background = f"""<PartImage x="0" y="0" width="{SIZE}" height="{SIZE}">
  <Image resource="ember_bg"/>
</PartImage>"""
        ambient = f"""<PartImage x="0" y="0" width="{SIZE}" height="{SIZE}">
  <Image resource="ember_ambient"/>
</PartImage>"""
        # Centred text: glyph images carry a trailing 1-pixel gap, so nudge right to
        # land where the design's ctext puts it.
        date = btext(4, 46 * P, SIZE - 4, small_h, "ember_small",
                     small_h, "<Upper>" + template("%s %s %s", "[DAY_OF_WEEK_F]", "[DAY_Z]", "[MONTH_S]") + "</Upper>",
                     align="CENTER")
        segments = [condition(f"move{s}", f"[STEP_COUNT] >= {(s + 1) * 1000}",
                              rect((46 + s * 6) * P, 127 * P, 4 * P, 2 * P, flame),
                              rect((46 + s * 6) * P, 127 * P, 4 * P, 2 * P, argb("2a1408")))
                   for s in range(10)]
        stats = btext(4, 132 * P, SIZE - 4, small_h, "ember_small", small_h,
                      template("MOVE %d/10 · %d%%", "clamp(floor([STEP_COUNT] / 1000), 0, 10)", "[BATTERY_PERCENT]"),
                      align="CENTER")
        return [
            group("scene", [background, fire, *stars], ambient_alpha=0),
            group("ambient", [ambient], alpha=0, ambient_alpha=255),
            time_part((EF_TIME_X + 1) * P, 22 * P, "ember_shadow", ambient_alpha=0),
            time_part(EF_TIME_X * P, 21 * P, "ember_time", ambient_alpha=0),
            time_part(EF_TIME_X * P, 21 * P, "ember_time_amb", alpha=0, ambient_alpha=255),
            date,
            group("stats", [*segments, stats], ambient_alpha=0),
        ]

    write_module(face, "Ember Forest", accents, scene, res, base, user_config=False, extra=bitmap_fonts,
                 editable=False)
    print(f"[gen] {face}: fire box {box}, {len(frames)} frames")


# ---------------------------------------------------------------- module files

def write_module(face, title, accents, scene, res, base, user_config=True, extra="", editable=True):
    """scene: list of scene XML children, or a function accent index -> list (per-flavour scenes)."""
    for d in ("values", "xml", "drawable-nodpi"):
        os.makedirs(os.path.join(res, d), exist_ok=True)
    labels = "\n".join(f'    <string name="accent_{n}">{n.capitalize()}</string>' for n, _ in accents)
    with open(os.path.join(res, "values", "strings.xml"), "w", encoding="utf-8") as f:
        f.write(f"""<?xml version="1.0" encoding="utf-8"?>
<!-- Generated by tools/gen_watchfaces.py -->
<resources>
    <string name="app_name">{title}</string>
    <string name="accent_label">Accent</string>
{labels}
</resources>
""")
    with open(os.path.join(res, "xml", "watch_face_info.xml"), "w", encoding="utf-8") as f:
        f.write(f"""<?xml version="1.0" encoding="utf-8"?>
<!-- Generated by tools/gen_watchfaces.py -->
<WatchFaceInfo>
    <Preview value="@drawable/preview" />
    <MultipleInstancesAllowed value="false" />
    <Editable value="{"true" if editable else "false"}" />
</WatchFaceInfo>
""")
    preview = os.path.join(res, "drawable-nodpi", "preview.png")
    if not os.path.exists(preview):
        preview_png(preview, title)
    for index, (name, _) in enumerate(accents):
        raw = os.path.join(base, name, "res", "raw")
        os.makedirs(raw, exist_ok=True)
        with open(os.path.join(raw, "watchface.xml"), "w", encoding="utf-8") as f:
            children = scene(index) if callable(scene) else scene
            f.write(watchface_xml(accents, index, children, user_config=user_config, extra=extra))
    print(f"[gen] {face}: {len(accents)} accent variants")


if __name__ == "__main__":
    mono_stack()
    dot_matrix()
    ember_forest()

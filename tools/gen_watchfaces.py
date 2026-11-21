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


def condition(name, expr, then_xml, else_xml):
    return f"""<Condition>
  <Expressions><Expression name="{name}"><![CDATA[{expr}]]></Expression></Expressions>
  <Compare expression="{name}">
{indent(then_xml, 4)}
  </Compare>
  <Default>
{indent(else_xml, 4)}
  </Default>
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


def watchface_xml(accents, default_index, scene_children):
    scene = "\n".join(indent(c, 4) for c in scene_children)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!-- Generated by tools/gen_watchfaces.py - edit the generator, not this file. -->
<WatchFace width="{SIZE}" height="{SIZE}" clipShape="CIRCLE">
  <Metadata key="CLOCK_TYPE" value="DIGITAL"/>
  <Metadata key="PREVIEW_TIME" value="10:08:32"/>
{color_config(accents, default_index)}
  <Scene backgroundColor="#ff000000">
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


# ---------------------------------------------------------------- module files

def write_module(face, title, accents, scene, res, base):
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
        f.write("""<?xml version="1.0" encoding="utf-8"?>
<!-- Generated by tools/gen_watchfaces.py -->
<WatchFaceInfo>
    <Preview value="@drawable/preview" />
    <MultipleInstancesAllowed value="false" />
    <Editable value="true" />
</WatchFaceInfo>
""")
    preview = os.path.join(res, "drawable-nodpi", "preview.png")
    if not os.path.exists(preview):
        preview_png(preview, title)
    for index, (name, _) in enumerate(accents):
        raw = os.path.join(base, name, "res", "raw")
        os.makedirs(raw, exist_ok=True)
        with open(os.path.join(raw, "watchface.xml"), "w", encoding="utf-8") as f:
            f.write(watchface_xml(accents, index, scene))
    print(f"[gen] {face}: {len(accents)} accent variants")


if __name__ == "__main__":
    mono_stack()
    dot_matrix()

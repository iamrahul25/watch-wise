"""Generate the Watch Face Format (WFF) sources for the pushed watch faces.

Writes, for each face module under watchfaces/<face>/src:
  main/res/font/*.ttf             static font weights cut from the variable fonts in
                                  shared/src/main/assets/fonts (WFF has no variable-axis support)
  main/res/drawable-nodpi/*.png   icons / dot grid images / pictures (from shared/src/main/assets/photos)
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

import io
import json
import math
import os
import re
from xml.sax.saxutils import escape

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from PIL import Image, ImageDraw

import pixel_art as art
import pixel_motion as motion

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_SRC = os.path.join(ROOT, "shared", "src", "main", "assets", "fonts")
PHOTO_SRC = os.path.join(ROOT, "shared", "src", "main", "assets", "photos")
PIXEL_ASSETS = os.path.join(ROOT, "shared", "src", "main", "assets", "pixel")
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

    def __init__(self, src, out_dir, name, axes, extra_chars="", digits=None, ligatures=True):
        """axes: variable-font axis values, or None for a static font.
        digits: (x_scale, advance) to give 0-9 one advance width, condensed by x_scale.
        ligatures: False drops the OpenType features, so "//" or "---" stay separate glyphs."""
        self.name = name
        self.src = os.path.join(FONT_SRC, src)
        path = os.path.join(out_dir, name + ".ttf")
        tt = TTFont(self.src)
        if axes is not None:
            tt = instancer.instantiateVariableFont(tt, axes)
        opts = subset.Options()
        opts.layout_features = ["*"] if ligatures else []
        opts.name_IDs = ["*"]
        sub = subset.Subsetter(opts)
        sub.populate(text=CHARSET + extra_chars)
        sub.subset(tt)
        if digits:
            equal_digits(tt, *digits)
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


def equal_digits(tt, x_scale, advance):
    """Scale the digit outlines horizontally and centre each in the same advance width."""
    glyf, cmap = tt["glyf"], tt.getBestCmap()
    for ch in "0123456789":
        name = cmap[ord(ch)]
        g = glyf[name]
        g.expand(glyf)
        g.coordinates.scale((x_scale, 1))
        g.recalcBounds(glyf)
        g.coordinates.translate((round((advance - g.xMin - g.xMax) / 2), 0))
        g.coordinates.toInt()
        g.recalcBounds(glyf)
        tt["hmtx"][name] = (advance, g.xMin)


# ---------------------------------------------------------------- images

def svg_polylines(d):
    """Tiny SVG path parser (M/L/H/V/C/S/A/Z, absolute + relative) -> list of point lists."""
    tokens = re.findall(r"[MLHVCSAZmlhvcsaz]|-?\d*\.?\d+", d)
    lines, cur, start = [], [], (0.0, 0.0)
    x = y = 0.0
    cmd = None
    ctrl2 = None  # second control point of the previous C/S segment
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
        elif c == "A":
            rx, ry, rot, large, sweep, nx, ny = (num() for _ in range(7))
            nx, ny = (x + nx, y + ny) if rel else (nx, ny)
            cur.extend(svg_arc(x, y, rx, ry, rot, large, sweep, nx, ny))
            x, y = nx, ny
        elif c in "CS":
            pts = [num() for _ in range(6 if c == "C" else 4)]
            if rel:
                pts = [pts[k] + (x if k % 2 == 0 else y) for k in range(len(pts))]
            if c == "S":  # first control point mirrors the previous one
                mirrored = (2 * x - ctrl2[0], 2 * y - ctrl2[1]) if ctrl2 else (x, y)
                pts = [*mirrored, *pts]
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
        ctrl2 = (x2, y2) if c in "CS" else None
    if cur:
        lines.append(cur)
    return lines


def svg_arc(x0, y0, rx, ry, rot, large, sweep, x1, y1, steps=24):
    """Points along an SVG arc (endpoint form), excluding the start point."""
    phi = math.radians(rot)
    cp, sp = math.cos(phi), math.sin(phi)
    dx, dy = (x0 - x1) / 2, (y0 - y1) / 2
    px, py = cp * dx + sp * dy, -sp * dx + cp * dy
    grow = max(1.0, math.sqrt((px / rx) ** 2 + (py / ry) ** 2))
    rx, ry = rx * grow, ry * grow
    den = (rx * py) ** 2 + (ry * px) ** 2
    f = math.sqrt(max(0.0, (rx * ry) ** 2 - den) / den) * (-1 if large == sweep else 1)
    qx, qy = f * rx * py / ry, -f * ry * px / rx
    cx, cy = cp * qx - sp * qy + (x0 + x1) / 2, sp * qx + cp * qy + (y0 + y1) / 2
    a0 = math.atan2((py - qy) / ry, (px - qx) / rx)
    da = math.atan2((-py - qy) / ry, (-px - qx) / rx) - a0
    if sweep and da < 0:
        da += 2 * math.pi
    elif not sweep and da > 0:
        da -= 2 * math.pi
    out = []
    for s in range(1, steps + 1):
        a = a0 + da * s / steps
        out.append((cx + rx * math.cos(a) * cp - ry * math.sin(a) * sp,
                    cy + rx * math.cos(a) * sp + ry * math.sin(a) * cp))
    return out


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
    """extra: XML before the scene, or a function accent index -> XML."""
    if callable(extra):
        extra = extra(default_index)
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
#
# An LED board centred on the screen: HH:MM in big 5 x 7 dot digits (hours white, minutes in
# the accent) over their unlit dots, a ring of 60 dots counting the seconds, the battery and
# date above and steps, calories and heart rate below. Everything is mirrored about the
# centre. The digits are a font of round dots made here (dm_dot_font), so they stay sharp and
# the colour follows the accent. Always-on keeps thinner dots, the date and the battery.
# The app preview (DotMatrixPainter.kt) uses the same positions.

DM_DIGITS = {  # 5 x 7
    "0": ".###. #...# #...# #...# #...# #...# .###.", "1": "..#.. .##.. ..#.. ..#.. ..#.. ..#.. .###.",
    "2": ".###. #...# ....# ...#. ..#.. .#... #####", "3": "####. ....# ....# .###. ....# ....# ####.",
    "4": "...#. ..##. .#.#. #..#. ##### ...#. ...#.", "5": "##### #.... ####. ....# ....# #...# .###.",
    "6": "..##. .#... #.... ####. #...# #...# .###.", "7": "##### ....# ...#. ..#.. .#... .#... .#...",
    "8": ".###. #...# #...# .###. #...# #...# .###.", "9": ".###. #...# #...# .#### ....# ...#. .##..",
    "-": "..... ..... ..... .###. ..... ..... .....",
}
DM_VALUE_P = 3  # dot pitch of the step, calorie and heart rate numbers
DM_ICONS = {  # 7 x 7
    "steps": "...##.. ...##.. ..###.. .#.##.. ...###. ..#..#. .#...#.",
    "flame": "...#... ..##... ..###.. .####.# ##.#### ##..### .#####.",
    "heart": ".##.##. ####### ####### ####### .#####. ..###.. ...#...",
}
DM_P = 15  # dot pitch of the time
DM_COLS = 25  # HH (11) + gap + colon + gap + MM (11)
DM_LEFT = CX - DM_COLS * DM_P / 2  # left edge of the time
DM_DOT, DM_DOT_AMBIENT = 12.6, 8.0  # lit dot diameters
DM_UNLIT = "161616"
DM_RING_R, DM_RING_DOT = 213, (5, 7.5, 10)  # radius; normal, five-second and current dots
DM_BATTERY_Y, DM_PERCENT_Y, DM_DATE_Y = 58, 83, 122  # centres
DM_ICON_Y, DM_VALUE_Y, DM_LABEL_Y = 318, 354, 386
DM_COLUMNS = (127, 225, 323)  # steps, kcal, heart rate
DM_ICON_P = 4.4  # dot pitch of the icons
DM_ACCENTS = [("lime", "B6FF3B"), ("white", "FFFFFF"), ("cyan", "3BD8FF"), ("orange", "FF8A00")]


def dm_centre(col, row):
    """Centre of a time dot; row 3 is the middle of the screen."""
    return DM_LEFT + (col + 0.5) * DM_P, CY + (row - 3) * DM_P


def dm_dot_font(path, name, diameter):
    """A TrueType font of the 5 x 7 dot digits: one dot pitch is 100 units, a digit advances
    six pitches (five dots and the gap), and the baseline is the bottom of the lowest dots."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    radius = diameter / DM_P * 50
    # The text starts on a whole pixel; this puts the dots back on their exact centres.
    nudge = (DM_LEFT - math.floor(DM_LEFT)) / DM_P * 100
    glyphs, metrics = {".notdef": TTGlyphPen(None).glyph()}, {".notdef": (600, 0)}
    for ch, art_ in DM_DIGITS.items():
        pen = TTGlyphPen(None)
        for row, line in enumerate(art_.split()):
            for col, cell in enumerate(line):
                if cell != "#":
                    continue
                x, y = col * 100 + 50 + nudge, (6 - row) * 100 + 50
                # A circle from eight quadratic arcs, clockwise as TrueType outlines are.
                pts = []
                for k in range(8):
                    a, mid = -2 * math.pi * k / 8, -2 * math.pi * (k + 0.5) / 8
                    c = radius / math.cos(math.pi / 8)
                    pts.append(((x + radius * math.cos(a), y + radius * math.sin(a)),
                                (x + c * math.cos(mid), y + c * math.sin(mid))))
                round_ = lambda p: (round(p[0]), round(p[1]))
                pen.moveTo(round_(pts[0][0]))
                for k in range(8):
                    pen.qCurveTo(round_(pts[k][1]), round_(pts[(k + 1) % 8][0]))
                pen.closePath()
        gname = f"d{ch}"
        glyphs[gname] = pen.glyph()
        metrics[gname] = (600, 0)
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(list(glyphs))
    fb.setupCharacterMap({ord(ch): f"d{ch}" for ch in DM_DIGITS})
    fb.setupGlyf(glyphs)
    glyf = fb.font["glyf"]
    fb.setupHorizontalMetrics({g: (adv, getattr(glyf[g], "xMin", 0)) for g, (adv, _) in metrics.items()})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": name, "styleName": "Regular"})
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    fb.setupPost()
    fb.font["head"].created = fb.font["head"].modified = 0  # identical files on every run
    fb.font.recalcTimestamp = False
    fb.save(path)

    class DotFont:
        pass
    f = DotFont()
    f.name, f.asc, f.upm = name, 800, 1000
    return f


def dm_dots(draw, dots, colour, ss):
    for x, y, d in dots:
        draw.ellipse([(x - d / 2) * ss, (y - d / 2) * ss, (x + d / 2) * ss, (y + d / 2) * ss], fill=colour)


def dm_time_dots(text, diameter):
    """(x, y, diameter) of the lit dots of "hhmm" digits."""
    dots = []
    for k, ch in enumerate(text):
        first = (0, 6, 14, 20)[k]
        for row, line in enumerate(DM_DIGITS[ch].split()):
            for col, cell in enumerate(line):
                if cell == "#":
                    dots.append((*dm_centre(first + col, row), diameter))
    return dots


def dm_icon_dots(name, cx, cy):
    rows = DM_ICONS[name].split()
    return [(cx + (col - 3) * DM_ICON_P, cy + (row - 3) * DM_ICON_P, DM_ICON_P * 0.92)
            for row, line in enumerate(rows) for col, cell in enumerate(line) if cell == "#"]


def dot_matrix():
    face = "dotmatrix"
    base = os.path.join(ROOT, "watchfaces", face, "src")
    res = os.path.join(base, "main", "res")
    fdir = os.path.join(res, "font")
    drawables = os.path.join(res, "drawable-nodpi")
    import shutil
    for d in (fdir, drawables):  # generated folders: start empty
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
    black = Font("doto.ttf", fdir, "doto_black", {"wght": 900, "ROND": 0})
    bold = Font("doto.ttf", fdir, "doto_bold", {"wght": 700, "ROND": 0})
    lit = dm_dot_font(os.path.join(fdir, "dotclock.ttf"), "dotclock", DM_DOT)
    thin = dm_dot_font(os.path.join(fdir, "dotclock_thin.ttf"), "dotclock_thin", DM_DOT_AMBIENT)
    ss = 4

    def picture(path, dots, colour):
        img = Image.new("RGBA", (SIZE * ss, SIZE * ss), (0, 0, 0, 0))
        dm_dots(ImageDraw.Draw(img), dots, colour, ss)
        img.resize((SIZE, SIZE), Image.LANCZOS).save(path, optimize=True)

    # The unlit dots behind the time.
    unlit = [(*dm_centre(first + col, row), DM_DOT) for first in (0, 6, 14, 20)
             for col in range(5) for row in range(7)]
    picture(os.path.join(drawables, "unlit.png"), unlit, "#" + DM_UNLIT)
    icon_size = 32
    for name in DM_ICONS:
        img = Image.new("RGBA", (icon_size * ss, icon_size * ss), (0, 0, 0, 0))
        dm_dots(ImageDraw.Draw(img), dm_icon_dots(name, icon_size / 2, icon_size / 2), "white", ss)
        img.resize((icon_size, icon_size), Image.LANCZOS).save(os.path.join(drawables, f"icon_{name}.png"))

    white, grey = "#ffffffff", argb("8c8c8c")

    def text(cx, cy, width, font, size, color, body, tint=None, ambient_alpha=None):
        """Centred on (cx, cy), measured on the capital height."""
        top = cy + 0.35 * size - font.asc / font.upm * size
        return part_text(cx - width / 2, top, width, 1.2 * size + 2, font, size, color, body,
                         tint=tint, ambient_alpha=ambient_alpha)

    # Seconds ring: passed seconds in the accent, the current one white and larger.
    ring = []
    for i in range(60):
        a = i * math.pi / 30
        x, y = CX + DM_RING_R * math.sin(a), CY - DM_RING_R * math.cos(a)
        d = DM_RING_DOT[1] if i % 5 == 0 else DM_RING_DOT[0]
        ring.append(condition(
            f"now{i}", f"[SECOND] == {i}",
            dot(x, y, DM_RING_DOT[2], white),
            condition(f"past{i}", f"[SECOND] > {i}",
                      dot(x, y, d, white, tint=ACCENT),
                      dot(x, y, d, argb("242424"))),
        ))

    # The time: hours and minutes as two texts in the dot font, each starting at its column.
    size = DM_P * 10
    top = CY + 3.5 * DM_P - lit.asc / lit.upm * size

    def number(kind, col, font, color, tint=None):
        x = math.floor(DM_LEFT) + col * DM_P
        return time_text(x, top, 12 * DM_P, size, kind, font, size, color, align="START", tint=tint)

    def colon(diameter, color):
        return "\n".join(dot(*dm_centre(12, row), diameter, color) for row in (2, 4))

    # Date: "SUN 22 NOV", the day name in the accent. Doto is monospaced, so columns are fixed.
    date_size = 29
    column = 0.6 * date_size
    left = CX - 10 * column / 2

    def date_part(col, chars, color, body, tint=None):
        x = left + col * column
        return part_text(x, DM_DATE_Y + 0.35 * date_size - black.asc / black.upm * date_size,
                         (chars + 1) * column, 1.2 * date_size + 2, black, date_size, color, body,
                         align="START", tint=tint)
    date = [date_part(0, 3, white, "<Upper>" + template("%s", "[DAY_OF_WEEK_S]") + "</Upper>", tint=ACCENT),
            date_part(4, 6, white, "<Upper>" + template("%s %s", "[DAY_Z]", "[MONTH_S]") + "</Upper>")]

    # Battery: ten dots, lit from the left, and the percentage under them.
    pitch = 13
    battery = []
    for i in range(10):
        x = CX + (i - 4.5) * pitch
        battery.append(condition(f"bat{i}", f"[BATTERY_PERCENT] >= {i * 10 + 5}",
                                 dot(x, DM_BATTERY_Y, 8, white, tint=ACCENT),
                                 dot(x, DM_BATTERY_Y, 8, argb("262626"))))
    percent = text(CX, DM_PERCENT_Y, 100, black, 21, argb("c4c4c4"), template("%d%%", "[BATTERY_PERCENT]"))

    steps_x, kcal_x, heart_x = DM_COLUMNS
    stats = []
    for x, icon, label in ((steps_x, "steps", "STEPS"), (kcal_x, "flame", "KCAL"), (heart_x, "heart", "BPM")):
        stats.append(f"""<PartImage x="{x - icon_size // 2}" y="{DM_ICON_Y - icon_size // 2}" width="{icon_size}" height="{icon_size}" tintColor="{ACCENT}">
  <Image resource="icon_{icon}"/>
</PartImage>""")
        stats.append(text(x, DM_LABEL_Y, 80, black, 17, grey, label))

    def value(x, body):
        # The dot font again. A digit's advance includes its gap, so nudge half a pitch right.
        size = DM_VALUE_P * 10
        top = DM_VALUE_Y + 3.5 * DM_VALUE_P - lit.asc / lit.upm * size
        return part_text(x - 48 + DM_VALUE_P / 2, top, 96, size, lit, size, white, body)
    stats.append(value(steps_x, template("%d", "[STEP_COUNT]")))
    stats.append(value(kcal_x, template("%d", "floor([STEP_COUNT] * 0.04)")))
    stats.append(condition("has_hr", "[HEART_RATE] > 0",
                           value(heart_x, template("%d", "round([HEART_RATE])")), value(heart_x, "--")))

    unlit_part = f"""<PartImage x="0" y="0" width="{SIZE}" height="{SIZE}">
  <Image resource="unlit"/>
</PartImage>"""
    scene = [
        group("board", [unlit_part, *ring], ambient_alpha=0),
        group("time", [number("hh", 0, lit, white), colon(DM_DOT, argb("8c8c8c")),
                       number("mm", 14, lit, white, tint=ACCENT)], ambient_alpha=0),
        group("time_ambient", [number("hh", 0, thin, argb("b4b4b4")), colon(DM_DOT_AMBIENT, argb("5a5a5a")),
                               number("mm", 14, thin, argb("8a8a8a"))], alpha=0, ambient_alpha=255),
        group("date", date, ambient_alpha=150),
        group("battery", [percent], ambient_alpha=120),
        group("details", [*battery, *stats], ambient_alpha=0),
    ]
    dm_preview_images(base, res)
    write_module(face, "Dot Matrix", DM_ACCENTS, scene, res, base)


def dm_preview_images(base, res):
    """Preview at SAT 28 NOV, 10:08:32 with sample data, one per accent."""
    from PIL import ImageFont
    ss = 3
    fonts = os.path.join(res, "font")
    for name, hex_ in DM_ACCENTS:
        accent = "#" + hex_
        img = Image.new("RGBA", (SIZE * ss, SIZE * ss), (0, 0, 0, 255))
        dr = ImageDraw.Draw(img)
        for first in (0, 6, 14, 20):
            dm_dots(dr, [(*dm_centre(first + c, r), DM_DOT) for c in range(5) for r in range(7)],
                    "#" + DM_UNLIT, ss)
        dots = dm_time_dots("1008", DM_DOT)
        split = len(dm_time_dots("10", DM_DOT))
        dm_dots(dr, dots[:split], "white", ss)
        dm_dots(dr, dots[split:], accent, ss)
        dm_dots(dr, [(*dm_centre(12, r), DM_DOT) for r in (2, 4)], "#8c8c8c", ss)
        for i in range(60):
            a = i * math.pi / 30
            d = DM_RING_DOT[2] if i == 32 else DM_RING_DOT[1] if i % 5 == 0 else DM_RING_DOT[0]
            colour = "white" if i == 32 else accent if i < 32 else "#242424"
            dm_dots(dr, [(CX + DM_RING_R * math.sin(a), CY - DM_RING_R * math.cos(a), d)], colour, ss)
        dm_dots(dr, [(CX + (i - 4.5) * 13, DM_BATTERY_Y, 8) for i in range(8)], accent, ss)
        dm_dots(dr, [(CX + (i - 4.5) * 13, DM_BATTERY_Y, 8) for i in range(8, 10)], "#262626", ss)

        def words(x, y, s, size, colour, anchor="ms"):
            font = ImageFont.truetype(os.path.join(fonts, "doto_black.ttf"), size * ss)
            dr.text((x * ss, (y + 0.35 * size) * ss), s, font=font, fill=colour, anchor=anchor)

        words(CX, DM_PERCENT_Y, "82%", 21, "#c4c4c4")
        left = CX - 10 * 0.6 * 29 / 2
        words(left, DM_DATE_Y, "SAT", 29, accent, "ls")
        words(left + 4 * 0.6 * 29, DM_DATE_Y, "28 NOV", 29, "white", "ls")
        for x, icon, value, label in zip(DM_COLUMNS, ("steps", "flame", "heart"), ("7038", "281", "72"),
                                         ("STEPS", "KCAL", "BPM")):
            dm_dots(dr, dm_icon_dots(icon, x, DM_ICON_Y), accent, ss)
            left = x - (len(value) * 6 - 1) * DM_VALUE_P / 2
            dm_dots(dr, [(left + (k * 6 + col + 0.5) * DM_VALUE_P, DM_VALUE_Y + (row - 3) * DM_VALUE_P,
                          DM_VALUE_P * DM_DOT / DM_P)
                         for k, ch in enumerate(value) for row, line in enumerate(DM_DIGITS[ch].split())
                         for col, cell in enumerate(line) if cell == "#"], "white", ss)
            words(x, DM_LABEL_Y, label, 17, "#8c8c8c")
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).ellipse([0, 0, img.size[0] - 1, img.size[1] - 1], fill=255)
        out = Image.new("RGBA", img.size, (0, 0, 0, 0))
        out.paste(img, (0, 0), mask)
        d = os.path.join(base, name, "res", "drawable-nodpi")
        os.makedirs(d, exist_ok=True)
        out.resize((SIZE, SIZE), Image.LANCZOS).save(os.path.join(d, "preview.png"), optimize=True)


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


# ---------------------------------------------------------------- Shell Window
#
# "05 · Shell Window" from the "AMOLED Watch Faces — 4 Designs" canvas: a macOS-style
# terminal window running `date`, `status` and `next`. The design is drawn on a 480 x 480
# artboard, so everything is scaled by SW_K. JetBrains Mono is monospaced (600 units per
# glyph), so coloured spans on one line are separate PartTexts placed by column.
# Differences from the design (no WFF data for them): no "BT on" or SpO2, distance is
# estimated from steps (0.762 m stride), and the next event comes from a complication slot
# (system "next event" provider by default) with the unread-notification count after it.

SW_K = SIZE / 480
SW_WIN_X, SW_WIN_Y, SW_WIN_W = 68, 92, 344  # window frame (design px)
SW_TITLE_H, SW_PAD_X, SW_PAD_T, SW_PAD_B = 30, 14, 10, 12
SW_LINE, SW_BODY = 19, 13  # line height / body font size
SW_TIME, SW_SECS = 46, 20
SW_COL = 0.6 * SW_BODY  # one monospace column at body size (design px)
SW_LEFT = SW_WIN_X + 1 + SW_PAD_X  # content left
SW_RIGHT = SW_WIN_X + SW_WIN_W - 1 - SW_PAD_X  # content right
SW_TOP = SW_WIN_Y + 1 + SW_TITLE_H + SW_PAD_T  # first line top
SW_TIME_ROW = SW_TOP + SW_LINE + 4  # time row top (margin 4px, height 46, margin 2px)
SW_ROWS = {name: SW_TIME_ROW + SW_TIME + 2 + i * SW_LINE for i, name in enumerate(
    ["date", "p_status", "battery", "hr", "steps", "energy", "weather", "p_next", "next", "p_npm"])}
SW_WIN_H = SW_ROWS["p_npm"] + SW_LINE + SW_PAD_B + 1 - SW_WIN_Y

SW_TEXT, SW_DIM, SW_DATE = "e6e6e6", "9a9a9a", "b5b5b5"
SW_GREEN, SW_RED, SW_AMBER = "5fd77a", "ff6b81", "febc2e"
SW_ACCENTS = [("blue", "4EA1FF"), ("green", "5FD77A"), ("amber", "FEBC2E"), ("purple", "C792EA")]


def sw_grouped(expr):
    """(condition, format, params) options printing an integer with a thousands comma."""
    hi, lo = f"floor(({expr}) / 1000)", f"(({expr}) % 1000)"
    return [(f"{expr} < 1000", "%d", [expr]),
            (f"{lo} < 10", "%d,00%d", [hi, lo]),
            (f"{lo} < 100", "%d,0%d", [hi, lo]),
            (None, "%d,%d", [hi, lo])]


def sw_choose(name, options, render):
    """Nested Conditions picking the first option whose condition holds."""
    cond, f, params = options[0]
    if cond is None:
        return render(f, params)
    return condition(f"{name}{next(_time_ids)}", cond, render(f, params), sw_choose(name, options[1:], render))


def round_rect(x, y, w, h, r, fill=None, stroke=None):
    """Rounded rectangle (design px), filled and/or with a 1px stroke inside its edge."""
    k = SW_K
    px, py = math.floor(x * k), math.floor(y * k)
    inner = ""
    if fill:
        inner += f'<RoundRectangle x="{fmt(x * k - px)}" y="{fmt(y * k - py)}" width="{fmt(w * k)}" height="{fmt(h * k)}" ' \
                 f'cornerRadiusX="{fmt(r * k)}" cornerRadiusY="{fmt(r * k)}"><Fill color="{fill}"/></RoundRectangle>'
    if stroke:
        t = 1.0
        inner += f'<RoundRectangle x="{fmt(x * k - px + t / 2)}" y="{fmt(y * k - py + t / 2)}" ' \
                 f'width="{fmt(w * k - t)}" height="{fmt(h * k - t)}" cornerRadiusX="{fmt(r * k - t / 2)}" ' \
                 f'cornerRadiusY="{fmt(r * k - t / 2)}"><Stroke color="{stroke}" thickness="{fmt(t)}"/></RoundRectangle>'
    return f"""<PartDraw x="{px}" y="{py}" width="{math.ceil(w * k) + 2}" height="{math.ceil(h * k) + 2}">
  {inner}
</PartDraw>"""


def shell_window():
    face = "shellwindow"
    base = os.path.join(ROOT, "watchfaces", face, "src")
    res = os.path.join(base, "main", "res")
    fdir = os.path.join(res, "font")
    reg = Font("jetbrainsmono_regular.ttf", fdir, "jetbrainsmono_regular", None, extra_chars="✓→—")
    xb = Font("jetbrainsmono_extrabold.ttf", fdir, "jetbrainsmono_extrabold", None)
    k = SW_K
    preview = []  # (kind, ...) draw ops in design px, for the preview image

    def baseline_top(font, size, baseline):
        """Top of a centred, content-high PartText box whose baseline lands at `baseline`."""
        return baseline - font.asc / font.upm * size

    def line_baseline(font, row_top, size=SW_BODY):
        content = (font.asc + font.desc + font.gap) / font.upm * size
        return row_top + (SW_LINE - content) / 2 + font.asc / font.upm * size

    def text_at(x, row_top, w, body, color, sample, font=reg, size=SW_BODY, align="START", tint=None):
        b = line_baseline(font, row_top, size)
        top = baseline_top(font, size, b)
        h = font.line_h(size)
        preview.append(("text", x, b, w, font, size, "ACCENT" if tint else color, sample, align, 0))
        return part_text(x * k, top * k, w * k, h * k, font, size * k, argb(color), body, align=align,
                         tint=tint)

    def col(row, c, body, color, sample, width_cols=None, align="START", tint=None):
        x = SW_LEFT + c * SW_COL
        w = width_cols * SW_COL if width_cols else SW_RIGHT - x
        return text_at(x, SW_ROWS.get(row, row), w, body, color, sample, align=align, tint=tint)

    def prompt(row, cmd):
        return [col(row, 0, "watch:~$", "ffffff", "watch:~$", tint=ACCENT),
                col(row, 9, cmd, SW_GREEN, cmd)]

    # Window: title bar colour behind everything, body below it (square top corners), border.
    wx, wy, ww, wh = SW_WIN_X, SW_WIN_Y, SW_WIN_W, SW_WIN_H
    body_y = wy + 1 + SW_TITLE_H
    chrome = [
        round_rect(wx, wy, ww, wh, 12, fill=argb("232323")),
        round_rect(wx + 1, body_y, ww - 2, wy + wh - 1 - body_y, 11, fill=argb("161616")),
        round_rect(wx + 1, body_y, ww - 2, 12, 0, fill=argb("161616")),
    ]
    preview += [("rrect", wx, wy, ww, wh, 12, "232323"), ("rrect", wx + 1, body_y, ww - 2, wy + wh - 1 - body_y, 11, "161616"),
                ("rrect", wx + 1, body_y, ww - 2, 12, 0, "161616")]
    border = round_rect(wx, wy, ww, wh, 12, stroke=argb("2c2c2c"))
    preview.append(("stroke", wx, wy, ww, wh, 12, "2c2c2c"))
    lights = []
    for i, c in enumerate(["ff5f57", "febc2e", "28c840"]):
        cx, cy = wx + 1 + 12 + 5.5 + i * 18, wy + 1 + SW_TITLE_H / 2
        lights.append(dot(cx * k, cy * k, 11 * k, argb(c)))
        preview.append(("dot", cx, cy, 11, c))
    title_row = wy + 1 + (SW_TITLE_H - SW_LINE) / 2
    title_b = line_baseline(reg, title_row, 11)
    title = part_text((wx + 1) * k, baseline_top(reg, 11, title_b) * k, (ww - 2) * k, reg.line_h(11) * k, reg, 11 * k,
                      argb("a8a8a8"), "watch — bash")
    preview.append(("text", wx + 1, title_b, ww - 2, reg, 11, "a8a8a8", "watch — bash", "CENTER", 0))

    # Time row: HH:MM (ExtraBold 46) then :SS (20, grey) on the same baseline. The design's
    # -2px tracking is left out: WFF doesn't apply negative letterSpacing to PartText, so
    # :SS would overlap the minutes.
    ls = 0
    hm_w = xb.width("00:00", SW_TIME, ls)
    time_b = SW_TIME_ROW + SW_TIME * (1 - (xb.asc + xb.desc) / xb.upm) / 2 + xb.asc / xb.upm * SW_TIME
    hm = time_text(SW_LEFT * k, baseline_top(xb, SW_TIME, time_b) * k, (hm_w + 8) * k, xb.line_h(SW_TIME) * k, "hh:mm",
                   xb, SW_TIME * k, argb("f2f2f2"), align="START", letter_spacing=ls)
    ss_x = SW_LEFT + hm_w + 3
    ss = part_text(ss_x * k, baseline_top(xb, SW_SECS, time_b) * k, (xb.width(":00", SW_SECS) + 6) * k,
                   xb.line_h(SW_SECS) * k, xb, SW_SECS * k, argb(SW_DIM), template(":%s", "[SECOND_Z]"), align="START")
    preview += [("text", SW_LEFT, time_b, hm_w + 8, xb, SW_TIME, "f2f2f2", "10:08", "START", ls),
                ("text", ss_x, time_b, 60, xb, SW_SECS, SW_DIM, ":32", "START", 0)]

    date = col("date", 0, template("%s, %s %s %s · %s", "[DAY_OF_WEEK_S]", "[DAY]", "[MONTH_S]", "[YEAR]",
                                   "[TIMEZONE_ABB]"), SW_DATE, "Thu, 26 Nov 2026 · IST")

    battery = [col("battery", 0, "✓ Battery", SW_TEXT, "✓ Battery"),
               col("battery", 10, template("%d%%", "[BATTERY_PERCENT]"), SW_GREEN, "68%")]
    hr = [col("hr", 0, "✓ HR", SW_TEXT, "✓ HR"),
          condition("has_hr", "[HEART_RATE] > 0",
                    col("hr", 5, template("%d bpm", "round([HEART_RATE])"), SW_RED, "72 bpm"),
                    col("hr", 5, "-- bpm", SW_RED, ""))]

    def steps_render(f1, p1):
        return sw_choose("goal", sw_grouped("[STEP_GOAL]"),
                         lambda f2, p2: col("steps", 0, template(f"✓ Steps {f1} / {f2}", *p1, *p2), SW_TEXT, ""))
    # No step goal set (0): just the count.
    steps = condition("has_goal", "[STEP_GOAL] > 0",
                      sw_choose("steps", sw_grouped("[STEP_COUNT]"), steps_render),
                      sw_choose("steps", sw_grouped("[STEP_COUNT]"),
                                lambda f, p: col("steps", 0, template(f"✓ Steps {f}", *p), SW_TEXT, "")))
    preview.append(("text", SW_LEFT, line_baseline(reg, SW_ROWS["steps"]), 300, reg, SW_BODY, SW_TEXT,
                    "✓ Steps 7,842 / 10,000", "START", 0))
    energy = col("energy", 0, template("✓ %d kcal · %d.%d km", "floor([STEP_COUNT] * 0.04)",
                                       "floor([STEP_COUNT] * 0.000762)", "floor([STEP_COUNT] * 0.00762) % 10"),
                 SW_TEXT, "✓ 313 kcal · 5.9 km")

    def weather_line(unit):
        return col("weather", 0, template(f"✓ %d°{unit} %s · H%d L%d · UV %d", "[WEATHER.TEMPERATURE]",
                                          "[WEATHER.CONDITION_NAME]", "[WEATHER.DAY_TEMPERATURE_HIGH]",
                                          "[WEATHER.DAY_TEMPERATURE_LOW]", "[WEATHER.UV_INDEX]"), SW_TEXT, "")
    weather = condition("weather", "[WEATHER.IS_AVAILABLE]",
                        condition("fahrenheit", "[WEATHER.TEMPERATURE_UNIT] == 2", weather_line("F"), weather_line("C")),
                        col("weather", 0, "✓ Weather --", SW_TEXT, ""))
    preview.append(("text", SW_LEFT, line_baseline(reg, SW_ROWS["weather"]), 300, reg, SW_BODY, SW_TEXT,
                    "✓ 24°C Haze · H28 L19 · UV 3", "START", 0))

    # Next event: a complication slot (LONG_TEXT / SHORT_TEXT), unread notifications at the right.
    msgs_cols = 8
    nx = SW_LEFT + 2 * SW_COL
    nw = SW_RIGHT - msgs_cols * SW_COL - nx
    n_b = line_baseline(reg, SW_ROWS["next"])
    n_top, n_h = baseline_top(reg, SW_BODY, n_b), reg.line_h(SW_BODY)
    sx, sy, sw_, sh = (math.floor(v) for v in (nx * k, n_top * k, nw * k, n_h * k + 1))

    def slot_text(body):
        return part_text(0, 0, sw_, sh, reg, SW_BODY * k, argb(SW_TEXT), body, align="START")
    next_event = f"""<ComplicationSlot slotId="0" x="{sx}" y="{sy}" width="{sw_}" height="{sh}" displayName="next_label"
    supportedTypes="LONG_TEXT SHORT_TEXT EMPTY" isCustomizable="TRUE">
  <DefaultProviderPolicy defaultSystemProvider="NEXT_EVENT" defaultSystemProviderType="LONG_TEXT"/>
  <BoundingBox x="0" y="0" width="{sw_}" height="{sh}"/>
  <Complication type="LONG_TEXT">
{indent(slot_text(template("%s %s", "[COMPLICATION.TITLE]", "[COMPLICATION.TEXT]")), 4)}
  </Complication>
  <Complication type="SHORT_TEXT">
{indent(slot_text(template("%s", "[COMPLICATION.TEXT]")), 4)}
  </Complication>
  <Complication type="EMPTY">
{indent(slot_text("no events"), 4)}
  </Complication>
</ComplicationSlot>"""
    preview.append(("text", nx, n_b, nw, reg, SW_BODY, SW_TEXT, "21:00 Standup", "START", 0))
    msgs_x = SW_RIGHT - msgs_cols * SW_COL
    msgs = condition("msgs", "[UNREAD_NOTIFICATION_COUNT] > 0",
                     condition("one_msg", "[UNREAD_NOTIFICATION_COUNT] == 1",
                               text_at(msgs_x, SW_ROWS["next"], msgs_cols * SW_COL, "1 msg", SW_AMBER, "", align="END"),
                               text_at(msgs_x, SW_ROWS["next"], msgs_cols * SW_COL,
                                       template("%d msgs", "[UNREAD_NOTIFICATION_COUNT]"), SW_AMBER, "", align="END")))
    preview.append(("text", msgs_x, n_b, msgs_cols * SW_COL, reg, SW_BODY, SW_AMBER, "3 msgs", "END", 0))
    arrow = col("next", 0, "→", SW_TEXT, "→")

    # Blinking block cursor after "npm ": 8 x 15, its bottom 3px below the baseline.
    cur_x = SW_LEFT + 13 * SW_COL
    cur_y = line_baseline(reg, SW_ROWS["p_npm"]) + 3 - 15
    cursor = condition("cursor", "[SECOND] % 2 == 0", rect(cur_x * k, cur_y * k, 8 * k, 15 * k, argb("d0d0d0")))
    preview.append(("box", cur_x, cur_y, 8, 15, "d0d0d0"))

    first_prompt = prompt(SW_TOP, "date")
    for name in ("p_status", "p_next", "p_npm"):
        first_prompt += prompt(name, {"p_status": "status", "p_next": "next", "p_npm": "npm"}[name])
    text_lines = [*first_prompt, date, *battery, *hr, steps, energy, weather, arrow, msgs]

    scene = [
        group("chrome", chrome, ambient_alpha=0),
        group("frame", [border, *lights, title], ambient_alpha=110),
        group("lines", text_lines, ambient_alpha=170),
        next_event,
        group("time", [hm], ambient_alpha=230),
        group("live", [ss, cursor], ambient_alpha=0),
    ]
    sw_preview_images(base, preview)
    write_module(face, "Shell Window", SW_ACCENTS, scene, res, base, strings={"next_label": "Next event"})


def sw_preview_images(base, ops, k=SW_K, accents=SW_ACCENTS):
    """Preview at 10:08:32 with sample data, one per accent, from the same layout as the XML."""
    from PIL import ImageFont
    ss = 3
    k = k * ss
    for name, hex_ in accents:
        img = Image.new("RGBA", (SIZE * ss, SIZE * ss), (0, 0, 0, 255))
        dr = ImageDraw.Draw(img)
        for op in ops:
            kind = op[0]
            if kind in ("rrect", "stroke"):
                _, x, y, w, h, r, c = op
                box = [x * k, y * k, (x + w) * k - 1, (y + h) * k - 1]
                if kind == "rrect":
                    dr.rounded_rectangle(box, r * k, fill="#" + c)
                else:
                    dr.rounded_rectangle(box, r * k, outline="#" + c, width=ss)
            elif kind == "dot":
                _, x, y, d, c = op
                dr.ellipse([(x - d / 2) * k, (y - d / 2) * k, (x + d / 2) * k, (y + d / 2) * k], fill="#" + c)
            elif kind == "box":
                _, x, y, w, h, c = op
                dr.rectangle([x * k, y * k, (x + w) * k - 1, (y + h) * k - 1], fill="#" + c)
            elif kind == "text":
                _, x, b, w, font, size, c, sample, align, ls = op
                if not sample:
                    continue
                pil = ImageFont.truetype(font.src, round(size * k))
                adv = (0.6 + ls) * size * k
                total = adv * len(sample)
                x0 = x * k + {"START": 0, "CENTER": (w * k - total) / 2, "END": w * k - total}[align]
                fill = "#" + (hex_ if c == "ACCENT" else c)
                for i, ch in enumerate(sample):
                    dr.text((x0 + i * adv, b * k), ch, font=pil, fill=fill, anchor="ls")
        # Round screen, then downsample.
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).ellipse([0, 0, img.size[0] - 1, img.size[1] - 1], fill=255)
        out = Image.new("RGBA", img.size, (0, 0, 0, 0))
        out.paste(img, (0, 0), mask)
        d = os.path.join(base, name, "res", "drawable-nodpi")
        os.makedirs(d, exist_ok=True)
        out.resize((SIZE, SIZE), Image.LANCZOS).save(os.path.join(d, "preview.png"), optimize=True)


# ---------------------------------------------------------------- Shell Full
#
# A redesign of Shell Window for the whole round screen: no window box, just the terminal
# text, as large as fits. Every line
# starts at one left margin (stepped in where the bezel curves, on the first and last
# rows) and is clipped at the circle on the right. JetBrains Mono is monospaced (600
# units per glyph), so coloured spans on one line are separate PartTexts placed by column.
# Same data as Shell Window (see there); shares its colours, accents and helpers.

SF_K = 1  # laid out directly on the 450 x 450 face
SF_BODY, SF_LINE = 19, 25  # body font size / line pitch
SF_TIME, SF_SECS = 80, 30
SF_COL = 0.6 * SF_BODY  # one monospace column at body size
SF_LEFT = 82  # common left margin
SF_EDGE = 8  # gap kept from the bezel
SF_ROW_NAMES = ["p_date", "time", "date", "p_status", "battery", "hr", "steps", "energy", "weather", "p_next",
                "next", "p_npm"]


def _sf_rows():
    rows, y = {}, (SIZE - (len(SF_ROW_NAMES) - 1) * SF_LINE - (SF_TIME + 4)) / 2
    for name in SF_ROW_NAMES:
        rows[name] = y
        y += SF_TIME + 4 if name == "time" else SF_LINE
    return rows


SF_ROWS = _sf_rows()


def sf_row_bounds(top, h=SF_LINE):
    """(left, right) for a row: the common margin, kept SF_EDGE inside the circle."""
    worst = max(abs(top - CY), abs(top + h - CY))
    half = math.sqrt(max(0.0, CX * CX - worst * worst))
    return max(SF_LEFT, CX - half + SF_EDGE), CX + half - SF_EDGE


def shell_full():
    face = "shellfull"
    base = os.path.join(ROOT, "watchfaces", face, "src")
    res = os.path.join(base, "main", "res")
    fdir = os.path.join(res, "font")
    reg = Font("jetbrainsmono_regular.ttf", fdir, "jetbrainsmono_regular", None, extra_chars="✓→—")
    xb = Font("jetbrainsmono_extrabold.ttf", fdir, "jetbrainsmono_extrabold", None)
    k = SF_K
    preview = []  # (kind, ...) draw ops in design px, for the preview image

    def baseline_top(font, size, baseline):
        """Top of a centred, content-high PartText box whose baseline lands at `baseline`."""
        return baseline - font.asc / font.upm * size

    def line_baseline(font, row_top, size=SF_BODY):
        content = (font.asc + font.desc + font.gap) / font.upm * size
        return row_top + (SF_LINE - content) / 2 + font.asc / font.upm * size

    def text_at(x, row_top, w, body, color, sample, font=reg, size=SF_BODY, align="START", tint=None):
        b = line_baseline(font, row_top, size)
        top = baseline_top(font, size, b)
        h = font.line_h(size)
        preview.append(("text", x, b, w, font, size, "ACCENT" if tint else color, sample, align, 0))
        return part_text(x * k, top * k, w * k, h * k, font, size * k, argb(color), body, align=align,
                         tint=tint)

    def col(row, c, body, color, sample, width_cols=None, align="START", tint=None):
        left, right = sf_row_bounds(SF_ROWS[row])
        x = left + c * SF_COL
        w = width_cols * SF_COL if width_cols else right - x
        return text_at(x, SF_ROWS[row], w, body, color, sample, align=align, tint=tint)

    def prompt(row, cmd):
        return [col(row, 0, "watch:~$", "ffffff", "watch:~$", tint=ACCENT),
                col(row, 9, cmd, SW_GREEN, cmd)]

    # Time row: HH:MM (ExtraBold) then :SS (grey) on the same baseline. The design's
    # -2px tracking is left out: WFF doesn't apply negative letterSpacing to PartText, so
    # :SS would overlap the minutes.
    ls = 0
    hm_w = xb.width("00:00", SF_TIME, ls)
    time_row = SF_ROWS["time"] + 2
    time_b = time_row + SF_TIME * (1 - (xb.asc + xb.desc) / xb.upm) / 2 + xb.asc / xb.upm * SF_TIME
    hm = time_text(SF_LEFT * k, baseline_top(xb, SF_TIME, time_b) * k, (hm_w + 8) * k, xb.line_h(SF_TIME) * k, "hh:mm",
                   xb, SF_TIME * k, argb("f2f2f2"), align="START", letter_spacing=ls)
    ss_x = SF_LEFT + hm_w + 3
    ss = part_text(ss_x * k, baseline_top(xb, SF_SECS, time_b) * k, (xb.width(":00", SF_SECS) + 6) * k,
                   xb.line_h(SF_SECS) * k, xb, SF_SECS * k, argb(SW_DIM), template(":%s", "[SECOND_Z]"), align="START")
    preview += [("text", SF_LEFT, time_b, hm_w + 8, xb, SF_TIME, "f2f2f2", "10:08", "START", ls),
                ("text", ss_x, time_b, 60, xb, SF_SECS, SW_DIM, ":32", "START", 0)]

    date = col("date", 0, template("%s, %s %s %s · %s", "[DAY_OF_WEEK_S]", "[DAY]", "[MONTH_S]", "[YEAR]",
                                   "[TIMEZONE_ABB]"), SW_DATE, "Thu, 26 Nov 2026 · IST")

    battery = [col("battery", 0, "✓ Battery", SW_TEXT, "✓ Battery"),
               col("battery", 10, template("%d%%", "[BATTERY_PERCENT]"), SW_GREEN, "68%")]
    hr = [col("hr", 0, "✓ HR", SW_TEXT, "✓ HR"),
          condition("has_hr", "[HEART_RATE] > 0",
                    col("hr", 5, template("%d bpm", "round([HEART_RATE])"), SW_RED, "72 bpm"),
                    col("hr", 5, "-- bpm", SW_RED, ""))]

    def steps_render(f1, p1):
        return sw_choose("goal", sw_grouped("[STEP_GOAL]"),
                         lambda f2, p2: col("steps", 0, template(f"✓ Steps {f1} / {f2}", *p1, *p2), SW_TEXT, ""))
    # No step goal set (0): just the count.
    steps = condition("has_goal", "[STEP_GOAL] > 0",
                      sw_choose("steps", sw_grouped("[STEP_COUNT]"), steps_render),
                      sw_choose("steps", sw_grouped("[STEP_COUNT]"),
                                lambda f, p: col("steps", 0, template(f"✓ Steps {f}", *p), SW_TEXT, "")))
    preview.append(("text", SF_LEFT, line_baseline(reg, SF_ROWS["steps"]), 300, reg, SF_BODY, SW_TEXT,
                    "✓ Steps 7,842 / 10,000", "START", 0))
    energy = col("energy", 0, template("✓ %d kcal · %d.%d km", "floor([STEP_COUNT] * 0.04)",
                                       "floor([STEP_COUNT] * 0.000762)", "floor([STEP_COUNT] * 0.00762) % 10"),
                 SW_TEXT, "✓ 313 kcal · 5.9 km")

    def weather_line(unit):
        return col("weather", 0, template(f"✓ %d°{unit} %s · H%d L%d · UV %d", "[WEATHER.TEMPERATURE]",
                                          "[WEATHER.CONDITION_NAME]", "[WEATHER.DAY_TEMPERATURE_HIGH]",
                                          "[WEATHER.DAY_TEMPERATURE_LOW]", "[WEATHER.UV_INDEX]"), SW_TEXT, "")
    weather = condition("weather", "[WEATHER.IS_AVAILABLE]",
                        condition("fahrenheit", "[WEATHER.TEMPERATURE_UNIT] == 2", weather_line("F"), weather_line("C")),
                        col("weather", 0, "✓ Weather --", SW_TEXT, ""))
    preview.append(("text", SF_LEFT, line_baseline(reg, SF_ROWS["weather"]), 300, reg, SF_BODY, SW_TEXT,
                    "✓ 24°C Haze · H28 L19 · UV 3", "START", 0))

    # Next event: a complication slot (LONG_TEXT / SHORT_TEXT), unread notifications at the right.
    msgs_cols = 7
    n_left, n_right = sf_row_bounds(SF_ROWS["next"])
    nx = n_left + 2 * SF_COL
    nw = n_right - msgs_cols * SF_COL - nx
    n_b = line_baseline(reg, SF_ROWS["next"])
    n_top, n_h = baseline_top(reg, SF_BODY, n_b), reg.line_h(SF_BODY)
    sx, sy, sw_, sh = (math.floor(v) for v in (nx * k, n_top * k, nw * k, n_h * k + 1))

    def slot_text(body):
        return part_text(0, 0, sw_, sh, reg, SF_BODY * k, argb(SW_TEXT), body, align="START")
    next_event = f"""<ComplicationSlot slotId="0" x="{sx}" y="{sy}" width="{sw_}" height="{sh}" displayName="next_label"
    supportedTypes="LONG_TEXT SHORT_TEXT EMPTY" isCustomizable="TRUE">
  <DefaultProviderPolicy defaultSystemProvider="NEXT_EVENT" defaultSystemProviderType="LONG_TEXT"/>
  <BoundingBox x="0" y="0" width="{sw_}" height="{sh}"/>
  <Complication type="LONG_TEXT">
{indent(slot_text(template("%s %s", "[COMPLICATION.TITLE]", "[COMPLICATION.TEXT]")), 4)}
  </Complication>
  <Complication type="SHORT_TEXT">
{indent(slot_text(template("%s", "[COMPLICATION.TEXT]")), 4)}
  </Complication>
  <Complication type="EMPTY">
{indent(slot_text("no events"), 4)}
  </Complication>
</ComplicationSlot>"""
    preview.append(("text", nx, n_b, nw, reg, SF_BODY, SW_TEXT, "21:00 Standup", "START", 0))
    msgs_x = n_right - msgs_cols * SF_COL
    msgs = condition("msgs", "[UNREAD_NOTIFICATION_COUNT] > 0",
                     condition("one_msg", "[UNREAD_NOTIFICATION_COUNT] == 1",
                               text_at(msgs_x, SF_ROWS["next"], msgs_cols * SF_COL, "1 msg", SW_AMBER, "", align="END"),
                               text_at(msgs_x, SF_ROWS["next"], msgs_cols * SF_COL,
                                       template("%d msgs", "[UNREAD_NOTIFICATION_COUNT]"), SW_AMBER, "", align="END")))
    preview.append(("text", msgs_x, n_b, msgs_cols * SF_COL, reg, SF_BODY, SW_AMBER, "3 msgs", "END", 0))
    arrow = col("next", 0, "→", SW_TEXT, "→")

    # Blinking block cursor after "npm " (design: 8 x 15 at 13px, bottom 3px below the baseline).
    cur_w, cur_h, cur_drop = SF_BODY * 8 / 13, SF_BODY * 15 / 13, SF_BODY * 3 / 13
    cur_x = sf_row_bounds(SF_ROWS["p_npm"])[0] + 13 * SF_COL
    cur_y = line_baseline(reg, SF_ROWS["p_npm"]) + cur_drop - cur_h
    cursor = condition("cursor", "[SECOND] % 2 == 0", rect(cur_x * k, cur_y * k, cur_w * k, cur_h * k, argb("d0d0d0")))
    preview.append(("box", cur_x, cur_y, cur_w, cur_h, "d0d0d0"))

    first_prompt = []
    for name, cmd in (("p_date", "date"), ("p_status", "status"), ("p_next", "next"), ("p_npm", "npm")):
        first_prompt += prompt(name, cmd)
    text_lines = [*first_prompt, date, *battery, *hr, steps, energy, weather, arrow, msgs]

    scene = [
        group("lines", text_lines, ambient_alpha=170),
        next_event,
        group("time", [hm], ambient_alpha=230),
        group("live", [ss, cursor], ambient_alpha=0),
    ]
    sw_preview_images(base, preview, k=SF_K)
    write_module(face, "Shell Full", SW_ACCENTS, scene, res, base, strings={"next_label": "Next event"})


# ---------------------------------------------------------------- Stack
#
# "04 · Stack" from the "AMOLED Watch Faces — 4 Designs" canvas: condensed hours over
# accent minutes on the left, a column of date and stats on the right, a seconds ring, a
# sunrise / sunset line on top and a notification pill at the bottom. Drawn on a 480 x 480
# artboard, so everything is scaled by ST_K.
# Differences from the design: Space Grotesk stands in for Anton and Inter (the time is a
# horizontally condensed cut of it). WFF has no sunrise data, so the top line is a
# complication slot (system sunrise / sunset provider, which shows only the next of the two).
# The pill has a fixed width, and its event is a second complication slot.

ST_K = SIZE / 480
ST_TIME = 194.3  # digit font size: 136 px tall digits
ST_DIGIT_SCALE, ST_DIGIT_ADV = 0.70, 440  # condensing, advance (font units)
ST_TIME_CX = 177
ST_BASELINES = (230, 378)  # hours, minutes
ST_COL_X = 276
ST_WHITE, ST_GREY = "f2f2f2", "9a9a9a"
ST_ACCENTS = [("violet", "B79CFF"), ("cyan", "4FD1FF"), ("orange", "FF6B2C"), ("lime", "B6F35B")]

ST_ICONS = {  # 24 x 24 line icons: (paths, circles, colour or None for the accent)
    "sun": (["M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5"],
            [(12, 12, 5)], "FFC24D"),
    "heart": (["M12 20s-7-4.4-9.2-8.7A5.2 5.2 0 0 1 12 6.4a5.2 5.2 0 0 1 9.2 4.9C19 15.6 12 20 12 20z"],
              [], "FF4D6D"),
    "steps": (["M5 16c0-3 .8-7 2.8-7S10 12 10 14s-1 4-2.5 4S5 17 5 16z"
               "M14 10c0-3 .8-7 2.8-7S19 6 19 8s-1 4-2.5 4S14 11 14 10z"], [], None),
    "battery": (["M4 7H17C18.1 7 19 7.9 19 9V15C19 16.1 18.1 17 17 17H4C2.9 17 2 16.1 2 15V9C2 7.9 2.9 7 4 7Z"
                 "M22 11v2M5 10v4M8 10v4M11 10v4"], [], "B6F35B"),
    "bell": (["M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.9 1.9 0 0 0 3.4 0"], [], None),
}


def stack():
    face = "stack"
    base = os.path.join(ROOT, "watchfaces", face, "src")
    res = os.path.join(base, "main", "res")
    fdir = os.path.join(res, "font")
    drawables = os.path.join(res, "drawable-nodpi")
    os.makedirs(drawables, exist_ok=True)
    src = "spacegrotesk.ttf"
    digits = (ST_DIGIT_SCALE, ST_DIGIT_ADV)
    time_bold = Font(src, fdir, "stack_digits_bold", {"wght": 700}, digits=digits)
    time_light = Font(src, fdir, "stack_digits_light", {"wght": 300}, digits=digits)
    medium = Font(src, fdir, "spacegrotesk_medium", {"wght": 500})
    semi = Font(src, fdir, "spacegrotesk_semibold", {"wght": 600})
    bold = Font(src, fdir, "spacegrotesk_bold", {"wght": 700}, digits=(1, 620))
    k = ST_K
    preview = []  # draw ops in design px, for the preview image
    for name, (paths, circles, _) in ST_ICONS.items():
        icon_png(os.path.join(drawables, f"icon_{name}.png"), paths, circles)

    def text(x, top, box, w, font, size, color, body, sample="", align="START", ls=0, tint=None):
        """PartText for a CSS line box (x, top, w x box) in design px; ls in design px.
        A non-empty sample also goes into the preview image."""
        content = (font.asc + font.desc + font.gap) / font.upm * size
        y = top + (box - content) / 2
        if sample:
            preview.append(("text", x, y + font.asc / font.upm * size, w, font, size,
                            "ACCENT" if tint else color, sample, align, ls))
        return part_text(x * k, y * k, w * k, font.line_h(size) * k + 1, font, size * k, argb(color), body,
                         align=align, letter_spacing=ls / size, tint=tint)

    def icon(name, x, cy, d):
        color = ST_ICONS[name][2]
        preview.append(("icon", name, x, cy - d / 2, d, color))
        tint = argb(color) if color else ACCENT
        return f"""<PartImage x="{ifmt(x * k)}" y="{ifmt((cy - d / 2) * k)}" width="{ifmt(d * k)}" height="{ifmt(d * k)}" tintColor="{tint}">
  <Image resource="icon_{name}"/>
</PartImage>"""

    # Seconds ring: dim track plus an accent arc from 12 o'clock.
    r, sw = 234 * k, 4 * k
    arc = f'centerX="{fmt(CX)}" centerY="{fmt(CY)}" width="{fmt(2 * r)}" height="{fmt(2 * r)}" startAngle="0"'
    ring = [f"""<PartDraw x="0" y="0" width="{SIZE}" height="{SIZE}">
  <Arc {arc} endAngle="360" direction="CLOCKWISE"><Stroke color="#ff161616" thickness="{fmt(sw)}"/></Arc>
</PartDraw>""", f"""<PartDraw x="0" y="0" width="{SIZE}" height="{SIZE}" tintColor="{ACCENT}">
  <Arc {arc} endAngle="1.2" direction="CLOCKWISE">
    <Transform target="endAngle" value="clamp([SECOND], 0.2, 60) * 6"/>
    <Stroke color="#ffffffff" thickness="{fmt(sw)}" cap="ROUND"/>
  </Arc>
</PartDraw>"""]
    preview.append(("ring", 234, 4, 32))

    # Time.
    tw = 2 * ST_DIGIT_ADV / 1000 * ST_TIME + 24

    def digits_part(which, font, color, tint=None, alpha=255, ambient_alpha=None):
        baseline = ST_BASELINES[0 if which == "hh" else 1]
        top = baseline - font.asc / font.upm * ST_TIME
        return time_text((ST_TIME_CX - tw / 2) * k, top * k, tw * k, font.line_h(ST_TIME) * k + 1, which, font,
                         ST_TIME * k, color, tint=tint, alpha=alpha, ambient_alpha=ambient_alpha)

    time_on = [digits_part("hh", time_bold, argb(ST_WHITE), ambient_alpha=0),
               digits_part("mm", time_bold, "#ffffffff", tint=ACCENT, ambient_alpha=0)]
    time_amb = [digits_part("hh", time_light, argb("d0d0d0"), alpha=0, ambient_alpha=255),
                digits_part("mm", time_light, argb("7a7a7a"), alpha=0, ambient_alpha=255)]
    for baseline, sample, color in zip(ST_BASELINES, ("10", "08"), (ST_WHITE, "ACCENT")):
        preview.append(("text", ST_TIME_CX - tw / 2, baseline, tw, time_bold, ST_TIME, color, sample, "CENTER", 0))

    # Date block.
    date = [
        text(ST_COL_X, 112, 15, 170, semi, 12, ST_GREY,
             "<Upper>" + template("%s", "[DAY_OF_WEEK_F]") + "</Upper>", "THURSDAY", ls=3),
        text(ST_COL_X, 127, 27, 170, bold, 22, ST_WHITE, template("%s %s", "[DAY]", "[MONTH_S]"), "26 Nov"),
    ]
    divider = rect(ST_COL_X * k, 167 * k, 100 * k, 1, argb("262626"))
    preview.append(("box", ST_COL_X, 167, 100, 1, "262626"))

    # Stats column: icon (20) + gap 8 + text.
    tx = ST_COL_X + 28

    def value(top, body, sample="", box=22):
        return text(tx, top, box, 140, bold, 18, ST_WHITE, body, sample)

    def sky(body, sample=""):
        return text(tx, 203, 13, 146, medium, 11, ST_GREY, body, sample)

    # Preview samples are added on their own, so the XML branches below add none.
    preview.append(("text", tx, 198.5, 140, bold, 18, ST_WHITE, "24°", "START", 0))
    preview.append(("text", tx, 213.5, 146, medium, 11, ST_GREY, "Haze · UV 3", "START", 0))
    weather = condition(
        "weather", "[WEATHER.IS_AVAILABLE]",
        "\n".join([value(182, template("%d°", "[WEATHER.TEMPERATURE]"), box=21),
                   sky(template("%s · UV %d", "[WEATHER.CONDITION_NAME]", "[WEATHER.UV_INDEX]"))]),
        "\n".join([value(182, "--°", box=21), sky("No weather")]))

    def hr_case(body, n_digits):
        """Heart rate followed by a small BPM, placed after n_digits equal-width digits."""
        x = tx + n_digits * 0.62 * 18 + 5
        return "\n".join([value(229.5, body), text(x, 235, 14, 50, medium, 11, ST_GREY, "BPM")])

    preview.append(("text", tx, 246.5, 60, bold, 18, ST_WHITE, "72", "START", 0))
    preview.append(("text", tx + 2 * 0.62 * 18 + 5, 245.5, 50, medium, 11, ST_GREY, "BPM", "START", 0))
    bpm = template("%d", "round([HEART_RATE])")
    heart = condition("has_hr", "[HEART_RATE] > 0",
                      condition("hr3", "[HEART_RATE] >= 99.5", hr_case(bpm, 3), hr_case(bpm, 2)),
                      hr_case("--", 2))

    preview.append(("text", tx, 282.5, 140, bold, 18, ST_WHITE, "7,842", "START", 0))
    steps = sw_choose("st_steps", sw_grouped("[STEP_COUNT]"), lambda f, p: value(265.5, template(f, *p)))
    battery = value(301, template("%d%%", "[BATTERY_PERCENT]"), "68%")

    stats = [icon("sun", ST_COL_X, 199, 20), weather, icon("heart", ST_COL_X, 240.5, 20), heart,
             icon("steps", ST_COL_X, 276.5, 20), steps, icon("battery", ST_COL_X, 312, 20), battery]

    def slot(slot_id, x, y, w, h, label, provider, kind, types, body):
        """Complication slot in design px; body(type, width, height) draws each type."""
        sx, sy, sw_, sh = (int(round(v * k)) for v in (x, y, w, h))
        parts = "\n".join(f'  <Complication type="{t}">\n{indent(body(t, sw_, sh), 4)}\n  </Complication>'
                          for t in types.split())
        return f"""<ComplicationSlot slotId="{slot_id}" x="{sx}" y="{sy}" width="{sw_}" height="{sh}" displayName="{label}"
    supportedTypes="{types}" isCustomizable="TRUE">
  <Variant mode="AMBIENT" target="alpha" value="0"/>
  <DefaultProviderPolicy defaultSystemProvider="{provider}" defaultSystemProviderType="{kind}"/>
  <BoundingBox x="0" y="0" width="{sw_}" height="{sh}"/>
{parts}
</ComplicationSlot>"""

    # Sunrise / sunset: the provider's icon (which tells them apart) and time, at the top.
    def sun_body(kind, w, h):
        def line(body, color=ST_WHITE):
            return part_text(w / 2 - 40, 0, w / 2 + 40, h, medium, 13 * k, argb(color), body, align="START",
                             letter_spacing=1.5 / 13)

        def image(resource):
            d = int(round(16 * k))
            return f"""<PartImage x="{int(w / 2) - 40 - d - 6}" y="{(h - d) // 2}" width="{d}" height="{d}" tintColor="#ffffc24d">
  <Image resource="{resource}"/>
</PartImage>"""
        if kind == "EMPTY":
            return "\n".join([image("icon_sun"), line("--:--", ST_GREY)])
        return "\n".join([image("[COMPLICATION.MONOCHROMATIC_IMAGE]"), line(template("%s", "[COMPLICATION.TEXT]"))])

    sun = slot(0, 120, 53, 240, 19, "sun_label", "SUNRISE_SUNSET", "SHORT_TEXT", "SHORT_TEXT EMPTY", sun_body)
    preview.extend([("icon", "sun", 190, 54.5, 16, "FFC24D"),
                    ("text", 214, 66.5, 120, medium, 13, ST_WHITE, "06:28", "START", 1.5)])

    # Notification pill: bell, unread count, dot, next event.
    px, py, pw, ph = 138, 396, 204, 28
    to_sw = k / SW_K  # round_rect takes Shell Window design px
    pill = [round_rect(px * to_sw, py * to_sw, pw * to_sw, ph * to_sw, ph / 2 * to_sw, stroke=argb("2a2a2a")),
            icon("bell", px + 13, py + ph / 2, 14),
            text(px + 31, py + 6, 16, 22, medium, 12, "ffffff",
                 template("%d", "clamp([UNREAD_NOTIFICATION_COUNT], 0, 99)"), "3", align="CENTER", tint=ACCENT),
            dot((px + 59) * k, (py + ph / 2) * k, 2.5 * k, argb(ST_GREY))]
    preview.extend([("pill", px, py, pw, ph, "2a2a2a"), ("dot", px + 59, py + ph / 2, 2.5, ST_GREY)])
    ex, ew = px + 66, pw - 78

    def event_body(kind, w, h):
        def line(body):
            return part_text(0, 0, w, h, medium, 12 * k, argb(ST_WHITE), body, align="START")
        if kind == "LONG_TEXT":
            return line(template("%s %s", "[COMPLICATION.TITLE]", "[COMPLICATION.TEXT]"))
        return line(template("%s", "[COMPLICATION.TEXT]") if kind == "SHORT_TEXT" else "No events")

    event = slot(1, ex, py + 6.5, ew, 16, "next_label", "NEXT_EVENT", "LONG_TEXT",
                 "LONG_TEXT SHORT_TEXT EMPTY", event_body)
    preview.append(("text", ex, py + 18.5, ew, medium, 12, ST_WHITE, "21:00 Standup", "START", 0))

    scene = [
        group("seconds_ring", ring, ambient_alpha=0),
        *time_on, *time_amb,
        group("date", date, ambient_alpha=160),
        group("stats", [divider, *stats], ambient_alpha=0),
        group("pill", pill, ambient_alpha=0),
        sun, event,
    ]
    st_preview_images(base, res, preview)
    write_module(face, "Stack", ST_ACCENTS, scene, res, base,
                 strings={"sun_label": "Sunrise / sunset", "next_label": "Next event"})


def st_preview_images(base, res, ops):
    """Preview at 10:08:32 with sample data, one per accent, from the same layout as the XML."""
    from PIL import ImageFont
    ss = 3
    k = ST_K * ss
    for name, hex_ in ST_ACCENTS:
        img = Image.new("RGBA", (SIZE * ss, SIZE * ss), (0, 0, 0, 255))
        dr = ImageDraw.Draw(img)

        def colour(c):
            return "#" + (hex_ if c in ("ACCENT", None) else c)

        for op in ops:
            kind = op[0]
            if kind == "ring":
                _, r, w, second = op
                edge = r + w / 2
                box = [(240 - edge) * k, (240 - edge) * k, (240 + edge) * k, (240 + edge) * k]
                dr.arc(box, 0, 360, fill="#161616", width=round(w * k))
                dr.arc(box, -90, -90 + second * 6, fill=colour(None), width=round(w * k))
            elif kind == "box":
                _, x, y, w, h, c = op
                dr.rectangle([x * k, y * k, (x + w) * k - 1, (y + h) * k - 1], fill="#" + c)
            elif kind == "pill":
                _, x, y, w, h, c = op
                dr.rounded_rectangle([x * k, y * k, (x + w) * k, (y + h) * k], h / 2 * k, outline="#" + c, width=ss)
            elif kind == "dot":
                _, x, y, d, c = op
                dr.ellipse([(x - d / 2) * k, (y - d / 2) * k, (x + d / 2) * k, (y + d / 2) * k], fill="#" + c)
            elif kind == "icon":
                _, icon_name, x, y, d, c = op
                size = round(d * k)
                alpha = Image.open(os.path.join(res, "drawable-nodpi", f"icon_{icon_name}.png")).getchannel("A")
                img.paste(colour(c), (round(x * k), round(y * k)), alpha.resize((size, size), Image.LANCZOS))
            elif kind == "text":
                _, x, b, w, font, size, c, sample, align, ls = op
                pil = ImageFont.truetype(os.path.join(res, "font", font.name + ".ttf"), round(size * k))
                total = sum(pil.getlength(ch) for ch in sample) + ls * k * len(sample)
                cx = x * k + {"START": 0, "CENTER": (w * k - total) / 2, "END": w * k - total}[align]
                for ch in sample:
                    dr.text((cx, b * k), ch, font=pil, fill=colour(c), anchor="ls")
                    cx += pil.getlength(ch) + ls * k
        # Round screen, then downsample.
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).ellipse([0, 0, img.size[0] - 1, img.size[1] - 1], fill=255)
        out = Image.new("RGBA", img.size, (0, 0, 0, 0))
        out.paste(img, (0, 0), mask)
        d = os.path.join(base, name, "res", "drawable-nodpi")
        os.makedirs(d, exist_ok=True)
        out.resize((SIZE, SIZE), Image.LANCZOS).save(os.path.join(d, "preview.png"), optimize=True)


# ---------------------------------------------------------------- Terminal
#
# "04 · Terminal" from the "AMOLED Watch Faces" (450 x 450) canvas: solid hours over outlined
# minutes, a column of four labelled readings, the date on top and a prompt line with the next
# event at the bottom. The digits are bitmap fonts (WFF cannot track text tighter, and this
# keeps solid and outlined digits identical in shape), one PartText per digit.
# Differences from the design: WFF has no sunrise data, so that reading is a complication slot
# (system sunrise / sunset provider, which shows whichever comes next, so it is labelled SUN
# with the provider's icon). The next event is a second complication slot.

TM_ACCENTS = [("orange", "FF8A3D"), ("cyan", "3DE0FF"), ("lime", "C6FF3D"), ("violet", "B69CFF")]
TM_WHITE, TM_GREY, TM_SOFT = "f2f4f7", "9aa0a8", "c9ced4"
TM_HEART, TM_BATTERY = "ff6b7a", "c6ff3d"
TM_DIGIT = 132  # digit font size
TM_LINE = 0.82 * TM_DIGIT  # line height of one digit row
TM_PAD = 8  # transparent side margin of a digit image (the tracking makes cells overlap)
TM_COL_W, TM_COL_GAP = 85.6, 22  # reading column ("24° HAZE") and its gap from the digits
TM_TOP = 89.6  # top of the centred date / digits / prompt stack
TM_MID = TM_TOP + 15.84 + 12  # top of the digits rows
TM_BOTTOM = TM_MID + 2 * TM_LINE + 12  # top of the prompt row
TM_CHAR = 11 * 0.6 + 11 * 0.12  # prompt row: one tracked character
TM_MAX_CHARS = 34


def tm_digit_images(drawables):
    """Tabular Space Grotesk Bold digits as solid and 2px-outline images.
    Returns (digit cell width after the design's -0.06em tracking, image width, height)."""
    from PIL import ImageChops, ImageFilter, ImageFont
    tt = instancer.instantiateVariableFont(TTFont(os.path.join(FONT_SRC, "spacegrotesk.ttf")), {"wght": 700})
    for table in tt["cmap"].tables:
        for ch in "0123456789":
            if ord(ch) in table.cmap:
                table.cmap[ord(ch)] = table.cmap[ord(ch)].split(".")[0] + ".tf"
    upm = tt["head"].unitsPerEm
    asc, desc = tt["hhea"].ascent, -tt["hhea"].descent
    adv = tt["hmtx"]["zero.tf"][0] / upm * TM_DIGIT
    data = io.BytesIO()
    tt.save(data)
    ss = 4
    data.seek(0)
    font = ImageFont.truetype(data, TM_DIGIT * ss)
    w, h = math.ceil(adv) + 2 * TM_PAD, math.ceil(TM_LINE)
    baseline = (TM_LINE - (asc + desc) / upm * TM_DIGIT) / 2 + asc / upm * TM_DIGIT
    for ch in "0123456789":
        mask = Image.new("L", (w * ss, h * ss), 0)
        ImageDraw.Draw(mask).text((TM_PAD * ss, baseline * ss), ch, font=font, fill=255, anchor="ls")
        # 2px stroke centred on the glyph edge: grown by 1px minus shrunk by 1px.
        outline = ImageChops.subtract(mask.filter(ImageFilter.MaxFilter(2 * ss + 1)),
                                      mask.filter(ImageFilter.MinFilter(2 * ss + 1)))
        for style, m in (("solid", mask), ("line", outline)):
            img = Image.new("RGBA", (w, h), (255, 255, 255, 0))
            img.putalpha(m.resize((w, h), Image.LANCZOS))
            img.save(os.path.join(drawables, f"tm_{style}_{ch}.png"), optimize=True)
    return adv - 0.06 * TM_DIGIT, w, h


def terminal():
    face = "terminal"
    base = os.path.join(ROOT, "watchfaces", face, "src")
    res = os.path.join(base, "main", "res")
    fdir = os.path.join(res, "font")
    drawables = os.path.join(res, "drawable-nodpi")
    os.makedirs(drawables, exist_ok=True)
    mono = Font("jetbrainsmono_regular.ttf", fdir, "jetbrainsmono_regular", None)
    adv, dw, dh = tm_digit_images(drawables)
    digits_x = CX - (2 * adv + TM_COL_GAP + TM_COL_W) / 2
    col_x = digits_x + 2 * adv + TM_COL_GAP
    col_w = 430 - col_x
    preview = []  # draw ops for the preview image

    bitmap_fonts = ["<BitmapFonts>"]
    for style in ("solid", "line"):
        bitmap_fonts.append(f'  <BitmapFont name="tm_{style}">')
        bitmap_fonts += [f'    <Character name="{d}" resource="tm_{style}_{d}" width="{dw}" height="{dh}"/>'
                         for d in range(10)]
        bitmap_fonts.append("  </BitmapFont>")
    bitmap_fonts = "\n".join(bitmap_fonts + ["</BitmapFonts>"])

    def digit(x, y, style, expr, tint, alpha, ambient_alpha):
        variant = (f'\n  <Variant mode="AMBIENT" target="alpha" value="{ambient_alpha}"/>'
                   if ambient_alpha is not None else "")
        return f"""<PartText x="{ifmt(x)}" y="{ifmt(y)}" width="{dw}" height="{dh}" alpha="{alpha}" tintColor="{tint}">{variant}
  <Text align="START">
    <BitmapFont family="tm_{style}" size="{dh}" color="#ffffffff">{template("%d", expr)}</BitmapFont>
  </Text>
</PartText>"""

    def digit_row(row, which, style, tint, alpha=255, ambient_alpha=None):
        def pair(value):
            return "\n".join(
                digit(digits_x + i * adv - TM_PAD, TM_MID + row * TM_LINE, style, e, tint, alpha, ambient_alpha)
                for i, e in enumerate((f"floor({value} / 10)", f"{value} % 10")))
        if which == "mm":
            return pair("[MINUTE]")
        return condition(f"h24_{next(_time_ids)}", "[IS_24_HOUR_MODE]", pair("[HOUR_0_23]"), pair("[HOUR_1_12]"))

    time_on = [digit_row(0, "hh", "solid", argb(TM_WHITE), ambient_alpha=0),
               digit_row(1, "mm", "line", ACCENT, ambient_alpha=0)]
    time_amb = [digit_row(0, "hh", "line", argb("d0d0d0"), alpha=0, ambient_alpha=255),
                digit_row(1, "mm", "line", argb("7a7a7a"), alpha=0, ambient_alpha=255)]
    for row, (sample, style, color) in enumerate((("10", "solid", TM_WHITE), ("08", "line", None))):
        for i, ch in enumerate(sample):
            preview.append(("image", f"tm_{style}_{ch}", digits_x + i * adv - TM_PAD, TM_MID + row * TM_LINE, color))

    def text(x, top, w, size, color, body, sample="", align="START", ls=0.0):
        """PartText whose CSS 'normal' line box starts at `top`; ls in px."""
        if sample:
            preview.append(("text", x, top + mono.asc / mono.upm * size, w, size, color, sample, align, ls))
        return part_text(x, top, w, mono.line_h(size) + 1, mono, size, argb(color), body, align=align,
                         letter_spacing=ls / size)

    date = text(0, TM_TOP, SIZE, 12, TM_GREY,
                "<Upper>" + template("%s %s %s %s", "[DAY_OF_WEEK_S]", "[DAY_Z]", "[MONTH_S]", "[YEAR]") + "</Upper>",
                "THU 26 NOV 2026", align="CENTER", ls=2.64)

    # Reading column: label (11px) over value (16px), four blocks, centred on the digits.
    block_h = mono.line_h(11) + 2 + mono.line_h(16)
    col_top = TM_MID + (2 * TM_LINE - (4 * block_h + 3 * 13)) / 2
    tops = [col_top + i * (block_h + 13) for i in range(4)]
    value_dy = mono.line_h(11) + 2

    def label(i, name):
        return text(col_x, tops[i], col_w, 11, TM_GREY, name, name, ls=1.1)

    def value(i, body, color=TM_WHITE, sample=""):
        return text(col_x, tops[i] + value_dy, col_w, 16, color, body, sample, ls=1.1)

    def sample_value(i, color, sample):
        """Preview-only text for a value whose XML has several branches."""
        preview.append(("text", col_x, tops[i] + value_dy + mono.asc / mono.upm * 16, col_w, 16, color,
                        sample, "START", 1.1))

    weather = condition(
        "weather", "[WEATHER.IS_AVAILABLE]",
        value(0, "<Upper>" + template("%d° %s", "[WEATHER.TEMPERATURE]", "[WEATHER.CONDITION_NAME]") + "</Upper>"),
        value(0, "--°"))
    # Long condition names end in an ellipsis instead of running off the screen.
    weather = weather.replace('<Text align="START">', '<Text align="START" ellipsis="TRUE">')
    sample_value(0, TM_WHITE, "24° HAZE")
    heart = condition("has_hr", "[HEART_RATE] > 0",
                      value(2, template("%d BPM", "round([HEART_RATE])"), TM_HEART),
                      value(2, "-- BPM", TM_HEART))
    sample_value(2, TM_HEART, "68 BPM")
    readings = [label(0, "WEATHER"), weather, label(2, "HEART"), heart, label(3, "BATTERY"),
                value(3, template("%d%%", "[BATTERY_PERCENT]"), TM_BATTERY, "64%")]

    def slot(slot_id, x, y, w, h, name, provider, kind, types, body):
        """Complication slot over a fallback drawn in the scene; body(type, w, h) covers it."""
        sx, sy, sw_, sh = (int(round(v)) for v in (x, y, w, h))
        parts = "\n".join(f'  <Complication type="{t}">\n{indent(body(t, sw_, sh), 4)}\n  </Complication>'
                          for t in types.split())
        return f"""<ComplicationSlot slotId="{slot_id}" x="{sx}" y="{sy}" width="{sw_}" height="{sh}" displayName="{name}"
    supportedTypes="{types}" isCustomizable="TRUE">
  <Variant mode="AMBIENT" target="alpha" value="0"/>
  <DefaultProviderPolicy defaultSystemProvider="{provider}" defaultSystemProviderType="{kind}"/>
  <BoundingBox x="0" y="0" width="{sw_}" height="{sh}"/>
{parts}
</ComplicationSlot>"""

    def cover(w, h):
        """Black box hiding the fallback once a complication has data."""
        return f"""<PartDraw x="0" y="0" width="{w}" height="{h}">
  <Rectangle x="0" y="0" width="{w}" height="{h}"><Fill color="#ff000000"/></Rectangle>
</PartDraw>"""

    # Sunrise / sunset.
    sun_fallback = [label(1, "SUN"), value(1, "--:--", TM_WHITE, "06:31")]

    def sun_body(kind, w, h):
        icon_x = int(round(mono.width("SUN", 11) + 3 * 1.1 + 5))
        return "\n".join([
            cover(w, h),
            part_text(0, 0, 40, mono.line_h(11) + 1, mono, 11, argb(TM_GREY), "SUN", align="START",
                      letter_spacing=0.1),
            f"""<PartImage x="{icon_x}" y="1" width="13" height="13" tintColor="{argb(TM_GREY)}">
  <Image resource="[COMPLICATION.MONOCHROMATIC_IMAGE]"/>
</PartImage>""",
            part_text(0, value_dy, w, mono.line_h(16) + 1, mono, 16, argb(TM_WHITE),
                      template("%s", "[COMPLICATION.TEXT]"), align="START", letter_spacing=1.1 / 16),
        ])

    sun = slot(0, col_x, tops[1], col_w, math.ceil(block_h) + 1, "sun_label", "SUNRISE_SUNSET", "SHORT_TEXT",
               "SHORT_TEXT", sun_body)

    # Prompt row: ">_", text and a blinking cursor, centred as one line. JetBrains Mono is
    # monospaced, so the row's width follows from the number of characters.
    row_x, row_w, row_y, row_h = 45, 360, int(round(TM_BOTTOM)) - 1, 18
    text_h = int(round(mono.line_h(11) + 1))

    def prompt_row(n, body):
        """n: character count of the message, a number or a WFF expression."""
        fixed = 2 * TM_CHAR + 8 + 8 + 7  # prompt, gaps and cursor
        text_x = 2 * TM_CHAR + 8

        def place(offset, per_char=0.0):
            """(x, Transform) for a part `offset` + n * `per_char` into the centred row."""
            if isinstance(n, int):
                return int(round((row_w - fixed - n * TM_CHAR) / 2 + offset + n * per_char)), ""
            expr = f"({fmt(row_w - fixed)} - ({n}) * {fmt(TM_CHAR)}) / 2 + {fmt(offset)} + ({n}) * {fmt(per_char)}"
            return 0, f'\n  <Transform target="x" value="{escape(expr)}"/>'

        def words(offset, color, content, width, tint=None):
            x, transform = place(offset)
            tint_attr = f' tintColor="{tint}"' if tint else ""
            return f"""<PartText x="{x}" y="1" width="{width}" height="{text_h}"{tint_attr}>{transform}
  <Text align="START" ellipsis="TRUE">
    <Font family="{mono.name}" size="11" color="{argb(color)}" letterSpacing="0.12">{content}</Font>
  </Text>
</PartText>"""

        x, transform = place(text_x + 8, TM_CHAR)
        cursor = f"""<PartDraw x="{x}" y="1" width="7" height="13" tintColor="{ACCENT}">{transform}
  <Transform target="alpha" value="([SECOND] % 2) * 255"/>
  <Rectangle x="0" y="0" width="7" height="13"><Fill color="#ffffffff"/></Rectangle>
</PartDraw>"""

        return "\n".join([
            words(0, "ffffff", "&gt;_", 20, tint=ACCENT),
            words(text_x, TM_SOFT, body, int(TM_MAX_CHARS * TM_CHAR) + 4),
            cursor,
        ])

    fallback_row = f"""<Group name="no_event" x="{row_x}" y="{row_y}" width="{row_w}" height="{row_h}">
{indent(prompt_row(len("NO EVENTS"), "NO EVENTS"), 2)}
</Group>"""

    def event_body(kind, w, h):
        if kind == "LONG_TEXT":
            fields, fmt_str, extra_chars = ["[COMPLICATION.TITLE]", "[COMPLICATION.TEXT]"], "NEXT %s %s", 6
        else:
            fields, fmt_str, extra_chars = ["[COMPLICATION.TEXT]"], "NEXT %s", 5
        n = " + ".join(f"textLength({f})" for f in fields)
        n = f"clamp({n} + {extra_chars}, 0, {TM_MAX_CHARS})"
        return "\n".join([cover(w, h), prompt_row(n, "<Upper>" + template(fmt_str, *fields) + "</Upper>")])

    event = slot(1, row_x, row_y, row_w, row_h, "next_label", "NEXT_EVENT", "LONG_TEXT",
                 "LONG_TEXT SHORT_TEXT", event_body)
    preview.append(("prompt", "NEXT 09:30 STANDUP", TM_BOTTOM))

    scene = [
        *time_on, *time_amb,
        group("date", [date], ambient_alpha=160),
        group("readings", [*readings, *sun_fallback], ambient_alpha=0),
        group("prompt", [fallback_row], ambient_alpha=0),
        sun, event,
    ]
    tm_preview_images(base, res, preview)
    write_module(face, "Outline", TM_ACCENTS, scene, res, base, extra=bitmap_fonts,
                 strings={"sun_label": "Sunrise / sunset", "next_label": "Next event"})


def tm_preview_images(base, res, ops):
    """Preview at 10:08 with sample data, one per accent, from the same layout as the XML."""
    from PIL import ImageFont
    ss = 3
    drawables = os.path.join(res, "drawable-nodpi")
    font_path = os.path.join(res, "font", "jetbrainsmono_regular.ttf")
    for name, hex_ in TM_ACCENTS:
        img = Image.new("RGB", (SIZE * ss, SIZE * ss), "black")
        dr = ImageDraw.Draw(img)

        def words(x, b, size, color, sample, ls):
            pil = ImageFont.truetype(font_path, round(size * ss))
            for ch in sample:
                dr.text((x * ss, b * ss), ch, font=pil, fill="#" + (color or hex_), anchor="ls")
                x += pil.getlength(ch) / ss + ls

        for op in ops:
            if op[0] == "image":
                _, resource, x, y, color = op
                alpha = Image.open(os.path.join(drawables, resource + ".png")).getchannel("A")
                size = (alpha.width * ss, alpha.height * ss)
                img.paste("#" + (color or hex_), (round(x * ss), round(y * ss)), alpha.resize(size, Image.LANCZOS))
            elif op[0] == "text":
                _, x, b, w, size, color, sample, align, ls = op
                if align == "CENTER":
                    x += (w - len(sample) * (0.6 * size + ls)) / 2
                words(x, b, size, color, sample, ls)
            elif op[0] == "prompt":
                _, sample, top = op
                x = CX - ((2 + len(sample)) * TM_CHAR + 23) / 2
                words(x, top + 11.2, 11, None, ">_", 1.32)
                words(x + 2 * TM_CHAR + 8, top + 11.2, 11, TM_SOFT, sample, 1.32)
                cx = x + (2 + len(sample)) * TM_CHAR + 16
                dr.rectangle([cx * ss, top * ss, (cx + 7) * ss - 1, (top + 13) * ss - 1], fill="#" + hex_)
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).ellipse([0, 0, img.size[0] - 1, img.size[1] - 1], fill=255)
        out = Image.new("RGBA", img.size, (0, 0, 0, 0))
        out.paste(img, (0, 0), mask)
        d = os.path.join(base, name, "res", "drawable-nodpi")
        os.makedirs(d, exist_ok=True)
        out.resize((SIZE, SIZE), Image.LANCZOS).save(os.path.join(d, "preview.png"), optimize=True)


# ---------------------------------------------------------------- Commit Grid
#
# A Git-hosting look: minute ring with twelve "commit" dots, a shell prompt, status badges and
# a 13 x 7 contribution grid. The design is drawn on a 360 x 360 board (scaled by 1.25 here).
# WFF has no step history (or network), so the grid shows today's step goal: its 91 cells fill
# column by column as the goal is reached, and the outline marks the cell being worked on.
# "N commits" in the top line is one per 1,000 steps.

CG_ACCENTS = [("green", "39D353"), ("blue", "58A6FF"), ("purple", "BC8CFF"), ("orange", "FF9E3D")]
CG_WHITE, CG_GREY, CG_MUTED = "e6edf3", "8b949e", "6e7681"
CG_CELL_BG, CG_TRACK, CG_DOT, CG_SECOND = "111418", "21262d", "30363d", "f78166"
CG_LABEL_BG, CG_LABEL = "30363d", "c9d1d9"
CG_BADGES = [  # (row y, [(id, label, colour, value characters, preview value)])
    (232.5, [("battery", "battery", "238636", 4, "82%"), ("steps", "steps", "1f6feb", 6, "7,240")]),
    (262.5, [("bpm", "bpm", "da3633", 3, "72"), ("temp", "temp", "bd561d", 5, "29°C")]),
]
CG_R = 203.75  # minute ring radius
CG_COLS, CG_ROWS, CG_CELL, CG_STEP = 13, 7, 10, 12.5
CG_CELLS = CG_COLS * CG_ROWS
CG_GRID_X = CX - (CG_COLS * CG_STEP - (CG_STEP - CG_CELL)) / 2
CG_GRID_Y = 297
CG_LEVELS = [80, 130, 190, 255]  # accent alpha of the four contribution levels
CG_GOAL = "([STEP_GOAL] > 0 ? [STEP_GOAL] : 10000)"
CG_TEXT = 13.75  # badge and curved line font size
CG_CHAR = 0.6 * CG_TEXT  # JetBrains Mono advance
CG_INFO_X, CG_INFO_Y = 342, 328  # centre of the info icon, right of the grid
CG_INFO_TAP = 52  # tap target
CG_GUIDE = "com.nightwise.watchwise/com.nightwise.watchwise.CommitGridGuideActivity"


def cg_levels():
    """The design's pseudo-random shade (0..3) of every cell, stable between builds."""
    seed, out = 7, []
    for _ in range(CG_CELLS):
        seed = (seed * 9301 + 49297) % 233280
        v = seed / 233280
        out.append(0 if v < 0.3 else 1 if v < 0.55 else 2 if v < 0.8 else 3)
    return out


def cg_badge_layout():
    """(id, label, colour, x, y, label width, value width, preview value) per badge."""
    for y, items in CG_BADGES:
        widths = [(len(label) * CG_CHAR + 12.5, chars * CG_CHAR + 12.5) for _, label, _, chars, _ in items]
        x = CX - (sum(a + b for a, b in widths) + 10 * (len(items) - 1)) / 2
        for (key, label, color, _, sample), (lw, vw) in zip(items, widths):
            yield key, label, color, x, y, lw, vw, sample
            x += lw + vw + 10


def commit_grid():
    face = "commitgrid"
    base = os.path.join(ROOT, "watchfaces", face, "src")
    res = os.path.join(base, "main", "res")
    mono = Font("jetbrainsmono_regular.ttf", os.path.join(res, "font"), "jetbrainsmono_regular", None)

    def top_of(baseline, size):
        return baseline - mono.asc / mono.upm * size

    def text(x, baseline, w, size, color, body, align="CENTER", tint=None):
        return part_text(x, top_of(baseline, size), w, mono.line_h(size) + 2, mono, size, argb(color), body,
                         align=align, tint=tint)

    def box(x, y, w, h, r, color, tint=None, alpha=255, transform=""):
        """Rounded rectangle at a fractional position."""
        px, py = math.floor(x), math.floor(y)
        tint_attr = f' tintColor="{tint}"' if tint else ""
        return f"""<PartDraw x="{px}" y="{py}" width="{math.ceil(w) + 2}" height="{math.ceil(h) + 2}" alpha="{alpha}"{tint_attr}>{transform}
  <RoundRectangle x="{fmt(x - px)}" y="{fmt(y - py)}" width="{fmt(w)}" height="{fmt(h)}" cornerRadiusX="{fmt(r)}" cornerRadiusY="{fmt(r)}"><Fill color="{argb(color)}"/></RoundRectangle>
</PartDraw>"""

    def rotating(name, expr, children):
        """Full-screen group turned clockwise around the centre by `expr` degrees."""
        body = "\n".join(indent(c, 2) for c in children)
        return f"""<Group name="{name}" x="0" y="0" width="{SIZE}" height="{SIZE}" pivotX="0.5" pivotY="0.5">
  <Transform target="angle" value="{escape(expr)}"/>
{body}
</Group>"""

    def arc(color, thickness, end, tint=None, alpha=255, transform=""):
        tint_attr = f' tintColor="{tint}"' if tint else ""
        return f"""<PartDraw x="0" y="0" width="{SIZE}" height="{SIZE}" alpha="{alpha}"{tint_attr}>
  <Arc centerX="{fmt(CX)}" centerY="{fmt(CY)}" width="{fmt(2 * CG_R)}" height="{fmt(2 * CG_R)}" startAngle="0" endAngle="{end}">{transform}
    <Stroke color="{argb(color)}" thickness="{fmt(thickness)}" cap="ROUND"/>
  </Arc>
</PartDraw>"""

    def node(x, y, outer, hole, core, color, tint=None):
        """Commit dot: ring of diameter `outer` around a black hole, with an optional core."""
        parts = [dot(x, y, outer, argb(color), tint), dot(x, y, hole, "#ff000000")]
        if core:
            parts.append(dot(x, y, core, argb(color), tint))
        return "\n".join(parts)

    def ring_point(deg):
        return CX + CG_R * math.sin(math.radians(deg)), CY - CG_R * math.cos(math.radians(deg))

    # Minute ring.
    track = arc(CG_TRACK, 2.5, 359.9)
    progress = condition(
        "minutes", "[MINUTE] > 0",
        arc("ffffff", 3.2, 6, tint=ACCENT, alpha=205,
            transform='\n    <Transform target="endAngle" value="[MINUTE] * 6"/>'))
    commits = []
    for i in range(12):
        x, y = ring_point(i * 30)
        commits.append(node(x, y, 13.75, 8.75, 0, CG_DOT))
        commits.append(f"""<Group name="commit_{i}" x="0" y="0" width="{SIZE}" height="{SIZE}" alpha="0">
  <Transform target="alpha" value="[MINUTE] &gt;= {i * 5} ? 255 : 0"/>
{indent(node(x, y, 13.75, 8.75, 4, "ffffff", ACCENT), 2)}
</Group>""")
    top_x, top_y = ring_point(0)
    head = rotating("head", "[MINUTE] * 6", [node(top_x, top_y, 23, 16.8, 8.75, "ffffff", ACCENT)])
    second = rotating("second", "[SECOND] * 6", [dot(top_x, top_y, 7.5, argb(CG_SECOND))])

    # Curved lines.
    def curved(radius, start, end, direction, color, body):
        d = int(round(2 * radius))
        return f"""<PartText x="0" y="0" width="{SIZE}" height="{SIZE}">
  <TextCircular centerX="{ifmt(CX)}" centerY="{ifmt(CY)}" width="{d}" height="{d}" startAngle="{start}" endAngle="{end}" direction="{direction}" align="CENTER">
    <Font family="{mono.name}" size="{fmt(CG_TEXT)}" color="{argb(color)}">{body}</Font>
  </TextCircular>
</PartText>"""

    def commit_line(word):
        return curved(187, -55, 55, "CLOCKWISE", CG_GREY,
                      template(f"main · %d {word} today", "floor([STEP_COUNT] / 1000)"))

    branch = condition("one_commit", "floor([STEP_COUNT] / 1000) == 1", commit_line("commit"), commit_line("commits"))
    summary = curved(186, 235, 125, "COUNTER_CLOCKWISE", CG_MUTED, template(
        "%d%% of goal · %d.%d km", f"floor([STEP_COUNT] * 100 / {CG_GOAL})",
        "floor([STEP_COUNT] * 0.000762)", "floor([STEP_COUNT] * 0.00762) % 10"))

    # Prompt, time, date.
    char = 0.6 * 15
    px = CX - 17 * char / 2
    prompt = [
        text(px, 105, 10 * char + 4, 15, "ffffff", "user@watch", align="START", tint=ACCENT),
        text(px + 10 * char, 105, 2 * char + 4, 15, CG_GREY, ":~", align="START"),
        text(px + 12 * char, 105, 5 * char + 6, 15, CG_WHITE, "$ now", align="START"),
    ]
    clock = time_text(70, top_of(182.5, 77.5), 300, mono.line_h(77.5) + 2, "hh:mm", mono, 77.5, argb(CG_WHITE))
    seconds = part_text(341, top_of(182.5, 20), 48, mono.line_h(20) + 2, mono, 20, argb("ffffff"),
                        template(":%s", "[SECOND_Z]"), align="START", tint=ACCENT)
    date = text(0, 212.5, SIZE, 16.25, CG_GREY,
                template("%s, %s %s %s", "[DAY_OF_WEEK_S]", "[DAY]", "[MONTH_S]", "[YEAR]"))

    # Badges.
    badges = []
    for key, label, color, x, y, lw, vw, _ in cg_badge_layout():
        badges += [box(x, y, lw + vw, 22.5, 5, color),
                   box(x, y, lw, 22.5, 5, CG_LABEL_BG),
                   box(x + lw - 6, y, 6, 22.5, 0, CG_LABEL_BG),
                   text(x, y + 16.25, lw, CG_TEXT, CG_LABEL, label)]

        def value(body, x=x, y=y, lw=lw, vw=vw):
            return text(x + lw - 2, y + 16.25, vw + 4, CG_TEXT, "ffffff", body)

        if key == "battery":
            badges.append(value(template("%d%%", "[BATTERY_PERCENT]")))
        elif key == "steps":
            badges.append(sw_choose("steps", sw_grouped("[STEP_COUNT]"),
                                    lambda f, p, value=value: value(template(f, *p))))
        elif key == "bpm":
            badges.append(condition("has_hr", "[HEART_RATE] > 0",
                                    value(template("%d", "round([HEART_RATE])")), value("--")))
        else:
            badges.append(condition(
                "weather", "[WEATHER.IS_AVAILABLE]",
                condition("fahrenheit", "[WEATHER.TEMPERATURE_UNIT] == 2",
                          value(template("%d°F", "[WEATHER.TEMPERATURE]")),
                          value(template("%d°C", "[WEATHER.TEMPERATURE]"))),
                value("--")))

    # Step goal grid.
    cells = []
    filled = f"floor([STEP_COUNT] * {CG_CELLS} / {CG_GOAL})"
    for i, level in enumerate(cg_levels()):
        x = CG_GRID_X + (i // CG_ROWS) * CG_STEP
        y = CG_GRID_Y + (i % CG_ROWS) * CG_STEP
        lit = escape(f"{filled} > {i} ? {CG_LEVELS[level]} : 0")
        cells.append(box(x, y, CG_CELL, CG_CELL, 2, CG_CELL_BG))
        cells.append(box(x, y, CG_CELL, CG_CELL, 2, "ffffff", tint=ACCENT, alpha=0,
                         transform=f'\n  <Transform target="alpha" value="{lit}"/>'))
    current = f"clamp({filled}, 0, {CG_CELLS - 1})"
    cursor_x = f"{fmt(CG_GRID_X - 2)} + floor({current} / {CG_ROWS}) * {fmt(CG_STEP)}"
    cursor_y = f"{fmt(CG_GRID_Y - 2)} + ({current} % {CG_ROWS}) * {fmt(CG_STEP)}"
    cells.append(f"""<PartDraw x="{ifmt(CG_GRID_X - 2)}" y="{CG_GRID_Y - 2}" width="14" height="14">
  <Transform target="x" value="{escape(cursor_x)}"/>
  <Transform target="y" value="{escape(cursor_y)}"/>
  <RoundRectangle x="2" y="2" width="{CG_CELL}" height="{CG_CELL}" cornerRadiusX="2" cornerRadiusY="2"><Stroke color="{argb(CG_WHITE)}" thickness="1.5"/></RoundRectangle>
</PartDraw>""")

    # Info icon: opens the watch app's guide to the readings.
    half, mid = CG_INFO_TAP // 2, CG_INFO_TAP / 2
    info = f"""<PartDraw x="{CG_INFO_X - half}" y="{CG_INFO_Y - half}" width="{CG_INFO_TAP}" height="{CG_INFO_TAP}">
  <Launch target="{CG_GUIDE}"/>
  <Ellipse x="{fmt(mid - 10)}" y="{fmt(mid - 10)}" width="20" height="20"><Stroke color="{argb(CG_GREY)}" thickness="2"/></Ellipse>
  <Ellipse x="{fmt(mid - 1.6)}" y="{fmt(mid - 6.1)}" width="3.2" height="3.2"><Fill color="{argb(CG_GREY)}"/></Ellipse>
  <RoundRectangle x="{fmt(mid - 1.25)}" y="{fmt(mid - 1.5)}" width="2.5" height="7.5" cornerRadiusX="1.25" cornerRadiusY="1.25"><Fill color="{argb(CG_GREY)}"/></RoundRectangle>
</PartDraw>"""

    scene = [
        group("track", [track, *commits], ambient_alpha=0),
        group("progress", [progress, head], ambient_alpha=110),
        group("second", [second], ambient_alpha=0),
        group("header", [branch, *prompt], ambient_alpha=0),
        group("time", [clock], ambient_alpha=210),
        group("seconds", [seconds], ambient_alpha=0),
        group("date", [date], ambient_alpha=160),
        group("badges", badges, ambient_alpha=0),
        group("grid", cells, ambient_alpha=90),
        group("summary", [summary], ambient_alpha=0),
        group("info", [info], ambient_alpha=0),
    ]
    cg_preview_images(base, res)
    write_module(face, "Commit Grid", CG_ACCENTS, scene, res, base)


def cg_preview_images(base, res):
    """Preview at 10:08:32 with 7,240 of 10,000 steps, one per accent."""
    from PIL import ImageFont
    ss = 3
    path = os.path.join(res, "font", "jetbrainsmono_regular.ttf")
    steps, goal, minute, second = 7240, 10000, 8, 32
    for name, hex_ in CG_ACCENTS:
        img = Image.new("RGBA", (SIZE * ss, SIZE * ss), "black")
        dr = ImageDraw.Draw(img)
        accent = "#" + hex_

        def font(size):
            return ImageFont.truetype(path, round(size * ss))

        def words(x, y, s, size, color, anchor="ms"):
            dr.text((x * ss, y * ss), s, font=font(size), fill=color, anchor=anchor)

        def circle(x, y, d, color):
            dr.ellipse([(x - d / 2) * ss, (y - d / 2) * ss, (x + d / 2) * ss, (y + d / 2) * ss], fill=color)

        def ring(a1, w, color):
            e = CG_R + w / 2
            dr.arc([(CX - e) * ss, (CY - e) * ss, (CX + e) * ss, (CY + e) * ss], -90, a1 - 90,
                   fill=color, width=round(w * ss))

        def point(deg, r=CG_R):
            return CX + r * math.sin(math.radians(deg)), CY - r * math.cos(math.radians(deg))

        def curved(s, r, mid, color, bottom=False):
            step = math.degrees(CG_CHAR / r) * (-1 if bottom else 1)
            for i, ch in enumerate(s):
                a = mid + (i - (len(s) - 1) / 2) * step
                tile = Image.new("RGBA", (40 * ss, 40 * ss), (0, 0, 0, 0))
                ImageDraw.Draw(tile).text((20 * ss, 20 * ss), ch, font=font(CG_TEXT), fill=color, anchor="mm")
                tile = tile.rotate(-(a - 180 if bottom else a), resample=Image.BICUBIC)
                x, y = point(a, r)
                img.alpha_composite(tile, (round((x - 20) * ss), round((y - 20) * ss)))

        ring(359.9, 2.5, "#" + CG_TRACK)
        ring(minute * 6, 3.2, accent)
        for i in range(12):
            x, y = point(i * 30)
            done = minute >= i * 5
            circle(x, y, 13.75, accent if done else "#" + CG_DOT)
            circle(x, y, 8.75, "black")
            if done:
                circle(x, y, 4, accent)
        x, y = point(minute * 6)
        for d, c in ((23, accent), (16.8, "black"), (8.75, accent)):
            circle(x, y, d, c)
        circle(*point(second * 6), 7.5, "#" + CG_SECOND)
        curved(f"main · {steps // 1000} commits today", 187, 0, "#" + CG_GREY)
        px = CX - 17 * 9 / 2
        words(px, 105, "user@watch", 15, accent, "ls")
        words(px + 90, 105, ":~", 15, "#" + CG_GREY, "ls")
        words(px + 108, 105, "$ now", 15, "#" + CG_WHITE, "ls")
        words(220, 182.5, f"10:{minute:02d}", 77.5, "#" + CG_WHITE)
        words(341, 182.5, f":{second}", 20, accent, "ls")
        words(CX, 212.5, "Thu, 26 Nov 2026", 16.25, "#" + CG_GREY)
        for _, label, color, x, y, lw, vw, sample in cg_badge_layout():
            dr.rounded_rectangle([x * ss, y * ss, (x + lw + vw) * ss, (y + 22.5) * ss], 5 * ss, fill="#" + color)
            dr.rounded_rectangle([x * ss, y * ss, (x + lw) * ss, (y + 22.5) * ss], 5 * ss, fill="#" + CG_LABEL_BG,
                                 corners=(True, False, False, True))
            words(x + lw / 2, y + 16.25, label, CG_TEXT, "#" + CG_LABEL)
            words(x + lw + vw / 2, y + 16.25, sample, CG_TEXT, "white")
        filled = steps * CG_CELLS // goal
        rgb = tuple(int(hex_[k:k + 2], 16) for k in (0, 2, 4))
        bg = tuple(int(CG_CELL_BG[k:k + 2], 16) for k in (0, 2, 4))
        for i, level in enumerate(cg_levels()):
            x = CG_GRID_X + (i // CG_ROWS) * CG_STEP
            y = CG_GRID_Y + (i % CG_ROWS) * CG_STEP
            a = CG_LEVELS[level] / 255 if i < filled else 0
            color = tuple(round(c * a + b * (1 - a)) for c, b in zip(rgb, bg))
            dr.rounded_rectangle([x * ss, y * ss, (x + CG_CELL) * ss, (y + CG_CELL) * ss], 2 * ss, fill=color,
                                 outline="#" + CG_WHITE if i == filled else None, width=round(1.5 * ss))
        curved(f"{steps * 100 // goal}% of goal · 5.5 km", 186, 180, "#" + CG_MUTED, bottom=True)
        ix, iy = CG_INFO_X, CG_INFO_Y
        dr.ellipse([(ix - 11) * ss, (iy - 11) * ss, (ix + 11) * ss, (iy + 11) * ss],
                   outline="#" + CG_GREY, width=2 * ss)
        circle(ix, iy - 4.5, 3.2, "#" + CG_GREY)
        dr.rounded_rectangle([(ix - 1.25) * ss, (iy - 1.5) * ss, (ix + 1.25) * ss, (iy + 6) * ss], 1.25 * ss,
                             fill="#" + CG_GREY)
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).ellipse([0, 0, img.size[0] - 1, img.size[1] - 1], fill=255)
        out = Image.new("RGBA", img.size, (0, 0, 0, 0))
        out.paste(img, (0, 0), mask)
        d = os.path.join(base, name, "res", "drawable-nodpi")
        os.makedirs(d, exist_ok=True)
        out.resize((SIZE, SIZE), Image.LANCZOS).save(os.path.join(d, "preview.png"), optimize=True)


# ---------------------------------------------------------------- Silhouette

# Pictures (shared/src/main/assets/photos/silhouette_<name>.webp), one accent flavour each.
# The colour only identifies the option in the app (see WatchFaces.kt).
SI_PICTURES = [("woman", "E8E8E8"), ("man", "9FB4C7"), ("tender", "D8CDE2"), ("close", "B9BDC6"),
               ("love", "E6C3CF")]
SI_RIGHT = 388  # right edge of the text column
SI_DATE_BASE, SI_TIME_BASE, SI_BATTERY_BASE = 256, 336, 370  # text baselines
SI_DATE, SI_TIME, SI_BATTERY = 30, 96, 24  # text sizes
SI_ICON_W = 40  # battery symbol (30) and its gap


def silhouette():
    face = "silhouette"
    base = os.path.join(ROOT, "watchfaces", face, "src")
    res = os.path.join(base, "main", "res")
    fdir = os.path.join(res, "font")
    semibold = Font("spacegrotesk.ttf", fdir, "spacegrotesk_semibold", {"wght": 600})
    medium = Font("spacegrotesk.ttf", fdir, "spacegrotesk_medium", {"wght": 500})
    drawables = os.path.join(res, "drawable-nodpi")
    os.makedirs(drawables, exist_ok=True)
    for name, _ in SI_PICTURES:
        photo = Image.open(os.path.join(PHOTO_SRC, f"silhouette_{name}.webp")).convert("RGB")
        photo.resize((SIZE, SIZE), Image.LANCZOS).save(os.path.join(drawables, f"photo_{name}.png"), optimize=True)
        # The Customise screen's option icon: at most 400 x 400, or the face fails to show.
        photo.resize((SIZE // 3, SIZE // 3), Image.LANCZOS).save(os.path.join(drawables, f"thumb_{name}.png"),
                                                              optimize=True)

    white = "#ffffffff"

    def line(baseline, font, size, body, right=SI_RIGHT):
        """Right-aligned line of text ending at `right`, on `baseline`."""
        top = baseline - font.asc / font.upm * size
        return part_text(0, top, right, font.line_h(size) + 2, font, size, white, body, align="END")

    date = line(SI_DATE_BASE, semibold, SI_DATE,
                "<Upper>" + template("%s %s", "[DAY_OF_WEEK_S]", "[DAY]") + "</Upper>")
    top = SI_TIME_BASE - medium.asc / medium.upm * SI_TIME
    clock = time_text(0, top, SI_RIGHT, medium.line_h(SI_TIME) + 2, "hh:mm", medium, SI_TIME, white, align="END")

    percent = line(SI_BATTERY_BASE, medium, SI_BATTERY, template("%d%%", "[BATTERY_PERCENT]"),
                   right=SI_RIGHT - SI_ICON_W)
    x, y = SI_RIGHT - 30, SI_BATTERY_BASE - 15
    icon = f"""<PartDraw x="{x - 2}" y="{y - 2}" width="34" height="19">
  <RoundRectangle x="2" y="2" width="26" height="14" cornerRadiusX="3" cornerRadiusY="3"><Stroke color="{white}" thickness="2"/></RoundRectangle>
  <Rectangle x="29" y="6" width="3" height="6"><Fill color="{white}"/></Rectangle>
  <Rectangle x="5" y="5" width="20" height="8">
    <Transform target="width" value="clamp([BATTERY_PERCENT] / 5, 1, 20)"/>
    <Fill color="{white}"/>
  </Rectangle>
</PartDraw>"""

    # The picture is chosen here or in the watch's Customise screen; each flavour starts on its own.
    def picture_config(default_index):
        options = "\n".join(
            f'    <ListOption id="{i}" displayName="accent_{name}" icon="thumb_{name}"/>'
            for i, (name, _) in enumerate(SI_PICTURES))
        return f"""<UserConfigurations>
  <ListConfiguration id="picture" displayName="accent_label" defaultValue="{default_index}">
{options}
  </ListConfiguration>
</UserConfigurations>"""

    options = "\n".join(f"""  <ListOption id="{i}">
    <PartImage x="0" y="0" width="{SIZE}" height="{SIZE}"><Image resource="photo_{name}"/></PartImage>
  </ListOption>""" for i, (name, _) in enumerate(SI_PICTURES))
    picture = f"""<ListConfiguration id="picture">
{options}
</ListConfiguration>"""

    scene = [
        # Always-on keeps only the dimmed date and time, so very few pixels are lit.
        group("picture", [picture], ambient_alpha=0),
        group("details", [date, clock], ambient_alpha=170),
        group("battery", [percent, icon], ambient_alpha=0),
    ]
    silhouette_preview_images(base, res)
    write_module(face, "Silhouette", SI_PICTURES, scene, res, base, user_config=False, extra=picture_config,
                 config_label="Picture")


def silhouette_preview_images(base, res):
    """Preview at SAT 28, 10:08 with 84% battery, one per picture."""
    from PIL import ImageFont
    ss = 3
    fonts = os.path.join(res, "font")

    for name, _ in SI_PICTURES:
        img = Image.open(os.path.join(res, "drawable-nodpi", f"photo_{name}.png")).convert("RGBA")
        img = img.resize((SIZE * ss, SIZE * ss), Image.LANCZOS)
        dr = ImageDraw.Draw(img)

        def words(x, y, s, weight, size):
            font = ImageFont.truetype(os.path.join(fonts, f"spacegrotesk_{weight}.ttf"), size * ss)
            dr.text((x * ss, y * ss), s, font=font, fill="white", anchor="rs")

        words(SI_RIGHT, SI_DATE_BASE, "SAT 28", "semibold", SI_DATE)
        words(SI_RIGHT, SI_TIME_BASE, "10:08", "medium", SI_TIME)
        words(SI_RIGHT - SI_ICON_W, SI_BATTERY_BASE, "84%", "medium", SI_BATTERY)
        x, y = SI_RIGHT - 30, SI_BATTERY_BASE - 15
        dr.rounded_rectangle([(x - 1) * ss, (y - 1) * ss, (x + 27) * ss, (y + 15) * ss], 4 * ss,
                             outline="white", width=2 * ss)
        dr.rectangle([(x + 27) * ss, (y + 4) * ss, (x + 30) * ss, (y + 10) * ss], fill="white")
        dr.rectangle([(x + 3) * ss, (y + 3) * ss, (x + 20) * ss, (y + 11) * ss], fill="white")
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).ellipse([0, 0, img.size[0] - 1, img.size[1] - 1], fill=255)
        out = Image.new("RGBA", img.size, (0, 0, 0, 0))
        out.paste(img, (0, 0), mask)
        d = os.path.join(base, name, "res", "drawable-nodpi")
        os.makedirs(d, exist_ok=True)
        out.resize((SIZE, SIZE), Image.LANCZOS).save(os.path.join(d, "preview.png"), optimize=True)


# ---------------------------------------------------------------- Java and SQL
#
# Two "code" faces: the readings written as a Java class and as an SQL query with its result
# table. Both are seven lines of JetBrains Mono ExtraBold; the font is
# monospaced (600 units per glyph), so coloured spans on one line are separate PartTexts placed
# by column. The accent is the keyword colour. Weekday names are always English, like the code.

CODE_SIZE = 32  # font size
CODE_LINE = 42  # line pitch
CODE_COL = 0.6 * CODE_SIZE  # one monospace column
CODE_TOP = (SIZE - 7 * CODE_LINE) / 2
CODE_DAYS = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]  # [DAY_OF_WEEK] 1..7

JV_ACCENTS = [("orange", "CC7832"), ("pink", "F06292"), ("cyan", "29C5F6"), ("lime", "A5D64C")]
JV_TEXT, JV_FIELD, JV_NUMBER = "a9b7c6", "9876aa", "6897bb"
JV_STRING, JV_COMMENT, JV_CLASS = "6a8759", "808080", "ffc66d"
# Larger than the SQL grid. The left margin centres the typical (shorter) lines, which leaves the
# longest one (the day, on the widest part of the screen) reaching almost to the right edge.
JV_SIZE, JV_LINE, JV_LEFT = 34, 46, 72
JV_CLASS_SIZE = 41

SQ_ACCENTS = [("cyan", "29B6F6"), ("violet", "C792EA"), ("orange", "FF8A3D"), ("pink", "F06292")]
SQ_TEXT, SQ_STRING, SQ_GREEN = "d4d4d4", "f0a732", "7cb342"
SQ_LEFT = (SIZE - 17 * CODE_COL) / 2


class CodeFace:
    """Lays out spans on the code grid and records them for the preview image."""

    def __init__(self, face, left, size=CODE_SIZE, line=CODE_LINE):
        self.size, self.line = size, line
        self.base = os.path.join(ROOT, "watchfaces", face, "src")
        self.res = os.path.join(self.base, "main", "res")
        self.font = Font("jetbrainsmono_extrabold.ttf", os.path.join(self.res, "font"),
                         "jetbrainsmono_extrabold", None, ligatures=False)
        self.left = left
        self.preview = []

    def baseline(self, row):
        f, s = self.font, self.size
        top = (SIZE - 7 * self.line) / 2
        return top + row * self.line + (self.line - (f.asc + f.desc) / f.upm * s) / 2 + f.asc / f.upm * s

    def box(self, row, col, chars, size=None):
        """(x, y, width, height) of a text box starting at `col`, with a column of slack."""
        size = size or self.size
        x = self.left + col * 0.6 * self.size
        top = self.baseline(row) - self.font.asc / self.font.upm * size
        return x, top, min(SIZE - x, (chars + 1) * 0.6 * size), self.font.line_h(size) + 2

    def sample(self, row, col, text, color, size=None):
        """Records text for the preview image."""
        x, _, w, _ = self.box(row, col, len(text), size)
        self.preview.append(("text", x, self.baseline(row), w, self.font, size or self.size, color, text, "START", 0))

    def span(self, row, col, text, color, size=None):
        """Fixed text. color "ACCENT" follows the configured accent."""
        self.sample(row, col, text, color, size)
        accent = color == "ACCENT"
        return part_text(*self.box(row, col, len(text), size), self.font, size or self.size,
                         argb("ffffff" if accent else color), escape(text), align="START",
                         tint=ACCENT if accent else None)

    def value(self, row, col, chars, body, color):
        """Live text; record its preview with sample()."""
        return part_text(*self.box(row, col, chars), self.font, self.size, argb(color), body, align="START")

    def clock(self, row, col, fmt_str, color, sample):
        self.sample(row, col, sample, color)
        return time_text(*self.box(row, col, len(sample)), fmt_str, self.font, self.size, argb(color),
                         align="START")

    def weekday(self, row, col, quote, color):
        """The quoted day name, e.g. 'SAT'."""
        self.sample(row, col, f"{quote}SAT{quote}", color)
        options = [(f"[DAY_OF_WEEK] == {i + 1}" if i < 6 else None, f"{quote}{day}{quote}", [])
                   for i, day in enumerate(CODE_DAYS)]
        return sw_choose("day", options, lambda f, _: self.value(row, col, 5, escape(f), color))

    def write(self, face, title, accents, static, clock, live):
        scene = [
            group("code", static, ambient_alpha=140),
            group("time", clock, ambient_alpha=230),
            group("readings", live, ambient_alpha=140),
        ]
        sw_preview_images(self.base, self.preview, k=1, accents=accents)
        write_module(face, title, accents, scene, self.res, self.base)


def java_face():
    c = CodeFace("java", JV_LEFT, JV_SIZE, JV_LINE)
    name_col = 6
    name_cols = 5 * JV_CLASS_SIZE / JV_SIZE  # width of the larger class name
    static = [
        c.span(0, 0, "class", "ACCENT"),
        c.span(0, name_col, "Watch", JV_CLASS, size=JV_CLASS_SIZE),
        c.span(0, name_col + name_cols + 0.6, "{", JV_TEXT),
    ]
    for row, name in ((1, "hh"), (2, "mm")):
        static += [c.span(row, 1, "int", "ACCENT"), c.span(row, 5, name, JV_FIELD),
                   c.span(row, 8, "=", JV_TEXT), c.span(row, 12, ";", JV_TEXT)]
    static += [
        c.span(3, 1, "String", JV_TEXT), c.span(3, 8, "day", JV_FIELD), c.span(3, 11, "=", JV_TEXT),
        c.span(3, 17, ";", JV_TEXT),
        c.span(4, 1, "int", "ACCENT"), c.span(4, 5, "steps", JV_FIELD), c.span(4, 10, "=", JV_TEXT),
        c.span(5, 1, "int", "ACCENT"), c.span(5, 5, "bpm", JV_FIELD), c.span(5, 9, "=", JV_TEXT),
        c.span(6, 0, "}", JV_TEXT),
    ]
    clock = [c.clock(1, 10, "hh", JV_NUMBER, "20"), c.clock(2, 10, "mm", JV_NUMBER, "58")]

    def number(row, col, digits, expr):
        """A number followed by its semicolon, which moves with the number's width."""
        return "\n".join([c.value(row, col, digits, template("%d", expr), JV_NUMBER),
                          c.value(row, col + digits, 1, ";", JV_TEXT)])

    def by_width(name, row, col, expr, widths):
        options = [(f"{expr} < {10 ** n}" if n != widths[-1] else None, n, []) for n in widths]
        return sw_choose(name, options, lambda n, _: group(f"{name}_{n}", [number(row, col, n, expr)]))

    steps = by_width("steps", 4, 11, "[STEP_COUNT]", [1, 2, 3, 4, 5])
    bpm = condition("has_hr", "[HEART_RATE] > 0",
                    by_width("bpm", 5, 11, "round([HEART_RATE])", [2, 3]),
                    group("no_hr", [c.value(5, 11, 2, "--", JV_NUMBER), c.value(5, 13, 1, ";", JV_TEXT)]))
    battery = c.value(6, 2, 7, template("// %d%%", "[BATTERY_PERCENT]"), JV_COMMENT)
    day = c.weekday(3, 12, '"', JV_STRING)
    for row, col, text, color in ((4, 11, "7038", JV_NUMBER), (4, 15, ";", JV_TEXT), (5, 11, "90", JV_NUMBER),
                                  (5, 13, ";", JV_TEXT), (6, 2, "// 87%", JV_COMMENT)):
        c.sample(row, col, text, color)
    c.write("java", "Java", JV_ACCENTS, static, clock, [day, steps, bpm, battery])


def sql_face():
    c = CodeFace("sql", SQ_LEFT)
    border = "+-------+-----+"
    static = [
        c.span(0, 0, "SELECT", "ACCENT"), c.span(0, 7, "time, bpm", SQ_TEXT),
        c.span(1, 0, "FROM", "ACCENT"), c.span(1, 5, "watch", SQ_TEXT),
        c.span(2, 0, "WHERE", "ACCENT"), c.span(2, 6, "day=", SQ_TEXT), c.span(2, 15, ";", SQ_TEXT),
        c.span(3, 0, border, SQ_GREEN),
        *[c.span(4, col, "|", SQ_GREEN) for col in (0, 8, 14)],
        c.span(5, 0, border, SQ_GREEN),
    ]
    white = "ffffff"
    clock = [c.clock(4, 2, "hh:mm", white, "20:58")]
    day = c.weekday(2, 10, "'", SQ_STRING)

    def bpm_text(body):
        """Right-aligned in its table cell."""
        x, y, _, h = c.box(4, 10, 3)
        return part_text(x, y, 3 * CODE_COL, h, c.font, CODE_SIZE, argb(white), body, align="END")
    bpm = condition("has_hr", "[HEART_RATE] > 0", bpm_text(template("%d", "round([HEART_RATE])")), bpm_text("--"))
    c.sample(4, 11, "90", white)

    def footer(col, chars):
        return c.value(6, col, chars, template("1 row, %d steps", "[STEP_COUNT]"), SQ_GREEN)
    # Five-digit counts start half a column further left, to stay inside the round screen.
    steps = condition("long_count", "[STEP_COUNT] < 10000", footer(0, 17), footer(-0.5, 18))
    c.sample(6, 0, "1 row, 7038 steps", SQ_GREEN)
    c.write("sql", "SQL", SQ_ACCENTS, static, clock, [day, bpm, steps])


# ---------------------------------------------------------------- Space Terminal and Retro Pixel
#
# Two pixel-art faces copied from the design mockup: an astronaut on a moon beside a
# terminal-style column of readings, and a kid and a cat watching the city at night with the
# readings in a panel. The art comes from tools/pixel_art.py (tools/art/*.png, 225 x 225,
# 2 face px per art pixel); text positions, sizes and colours are measured from the mockup.
# Each digit of the time is placed on its own, as in the design (tighter than the font's
# spacing; negative letterSpacing is ignored on Wear OS 7).
#
# The "accent" picks a colour theme: every flavour carries all the themes (switchable in the
# watch's Customise screen) and starts on its own. The scenes move like Ember Forest: an
# animated picture loop from tools/pixel_motion.py (stars, shooting stars, sparks...) plays
# over the still art, and on Retro Pixel the clouds drift and window lights switch off.
# Always-on keeps only the time and date (and the battery on Space Terminal).
# The images are also written to shared/src/main/assets/pixel for the app previews
# (PixelPainters.kt), with each theme's text colours in pixel/<face>.json.

RP_CLOUD_PERIOD = 60  # seconds for a cloud to cross the screen and come round again
# Drifting clouds: (start x, art px down from the design's cloud, alpha).
RP_CLOUDS = ((0, 0, 255), (150, 21, 150))

PX_FONT = {"bold": "jetbrainsmono_extrabold", "regular": "jetbrainsmono_regular"}

SP_TIME = 60  # size; ExtraBold
SP_TIME_BASE = 147
SP_DIGITS = (249.5, 282.7, 330.8, 363.4)  # centres of the four digits
SP_COLON = 306.2
SP_DATE, SP_DATE_X, SP_DATE_BASE = 20.5, 242.9, 181.5
SP_RULE = (238.1, 12.73, 9.6, 203.6, 13)  # first dash x, pitch, dash width, y, count
SP_TEXT, SP_TEXT_X = 21, 289
SP_BASES = (245, 285, 325, 365)  # weather, battery, heart rate, steps
SP_COLOURS = {"time": "fdfdfd", "date": "d9d9da", "rule": "c8c5c6", "text": "e1e0e1"}

RP_TIME = 52  # size; ExtraBold for hh:mm, Regular for :ss
RP_TIME_BASE = 145
RP_DIGITS = (193.8, 225.3, 280.3, 310.0)
RP_COLON = 251.7
RP_SECONDS = (354.1, 381.6)
RP_SECONDS_COLON = 332.4
RP_DATE, RP_DATE_X, RP_DATE_BASE = 21, 216.1, 180.5
RP_TEXT, RP_TEXT_X = 21, 369
RP_BASES = (246.5, 287.5, 329)  # battery, heart rate, steps
RP_COLOURS = {"time": "f5e0f9", "seconds": "ebd3ed", "date": "d3d0d5", "text": "eaeceb"}


class PixelFace:
    """Builds a face once per theme (see assemble), and its preview images."""

    def __init__(self, face, themes, hues, colours):
        import shutil
        self.face, self.themes, self.hues, self.colours = face, themes, hues, colours
        self.base = os.path.join(ROOT, "watchfaces", face, "src")
        self.res = os.path.join(self.base, "main", "res")
        self.drawables = os.path.join(self.res, "drawable-nodpi")
        # Generated folders: start empty so no image from an older version is left behind.
        shutil.rmtree(self.drawables, ignore_errors=True)
        os.makedirs(self.drawables)
        os.makedirs(PIXEL_ASSETS, exist_ok=True)
        for name in os.listdir(PIXEL_ASSETS):
            if name.startswith(face):
                os.remove(os.path.join(PIXEL_ASSETS, name))
        fdir = os.path.join(self.res, "font")
        self.fonts = {k: Font(f"{v}.ttf", fdir, v, None, ligatures=False) for k, v in PX_FONT.items()}
        self.texts = []  # (anchor, x, baseline, text, size, colour key, font key) for the preview
        self.pictures = []  # (resource, x, y) drawn on the preview
        self.rects = []  # (x, y, w, h, colour key) drawn on the preview
        self.i = 0  # theme being built
        self.ids = None

    # ---- theme

    @property
    def theme(self):
        return self.themes[self.i][0]

    def colour(self, key, i=None):
        shift = self.themes[self.i if i is None else i][1]
        return art.recolour_hex(self.colours[key], shift, self.hues)

    def name(self, prefix):
        return f"{prefix}{next(self.ids)}"

    def assemble(self, build):
        """Calls build() for every theme; scene children that differ by theme are put in a
        ListConfiguration, so the watch's Customise screen can switch them."""
        per_theme = []
        for i in range(len(self.themes)):
            self.i, self.ids = i, iter(range(10_000))
            texts, pictures, rects = len(self.texts), len(self.pictures), len(self.rects)
            per_theme.append(build())
            if i:  # the preview's layout is recorded once
                del self.texts[texts:], self.pictures[pictures:], self.rects[rects:]
        out = []
        for variants in zip(*per_theme):
            if len(set(variants)) == 1:
                out.append(variants[0])
            else:
                options = "\n".join(f'  <ListOption id="{i}">\n{indent(v, 4)}\n  </ListOption>'
                                    for i, v in enumerate(variants))
                out.append(f'<ListConfiguration id="theme">\n{options}\n</ListConfiguration>')
        return out

    # ---- images

    def art_images(self, name):
        """tools/art/<face>_<name>.png for each theme, enlarged to face size and recoloured,
        written as <name>_<theme> resources and app assets."""
        src = Image.open(os.path.join(art.ART, f"{self.face}_{name}.png"))
        for theme, shift, _ in self.themes:
            img = art.enlarge(art.themed_image(src, shift, self.hues))
            img.save(os.path.join(self.drawables, f"{name}_{theme}.png"), optimize=True)
            img.save(os.path.join(PIXEL_ASSETS, f"{self.face}_{theme}_{name}.png"), optimize=True)
            if name == "scene":  # the Customise screen's option icon (at most 400 x 400)
                img.resize((SIZE // 3, SIZE // 3), Image.NEAREST).save(
                    os.path.join(self.drawables, f"thumb_{theme}.png"), optimize=True)

    def motion(self):
        """The face's loop of moving pixels as animated pictures, one per region of the screen,
        played over the scene. The frames also go to the app assets for the previews."""
        with Image.open(os.path.join(art.ART, f"{self.face}_scene.png")) as scene:
            frames = motion.frames(self.face, scene.convert("RGBA"))
        for k, img in enumerate(frames):
            img.save(os.path.join(PIXEL_ASSETS, f"{self.face}_motion_{k:02d}.png"), optimize=True)
        parts = []
        for k, region in enumerate(motion.REGIONS[self.face]):
            box = motion.bounds(frames, region)
            cut = [art.enlarge(img.crop(box)) for img in frames]
            cut[0].save(os.path.join(self.drawables, f"motion_{k}.webp"), save_all=True, append_images=cut[1:],
                        duration=1000 // motion.FPS, loop=0, lossless=True, quality=100, method=6)
            x, y = box[0] * art.PX, box[1] * art.PX
            parts.append(f"""<PartAnimatedImage x="{x}" y="{y}" width="{cut[0].width}" height="{cut[0].height}">
  <AnimationController play="ON_VISIBLE" repeat="TRUE" beforePlaying="FIRST_FRAME" afterPlaying="FIRST_FRAME"/>
  <AnimatedImage resource="motion_{k}" format="WEBP"/>
</PartAnimatedImage>""")
            print(f"[motion] {self.face}: region {k} is {cut[0].width} x {cut[0].height}, {len(cut)} frames")
        self.motion_frame = frames[motion.PREVIEW_FRAME]
        return parts

    def cloud(self, start, down, alpha):
        """This theme's cloud, drifting right and coming back in from the left."""
        x0, y0, x1, y1 = art.RP_CLOUD
        width = x1 - x0
        span = art.N + width
        travel = f"([SECOND_MILLISECOND] * {fmt(span / RP_CLOUD_PERIOD)} + {start + width})"
        # Whole art pixels, so the cloud steps like pixel art.
        x = f"floor({travel} - floor({travel} / {span}) * {span} - {width}) * {art.PX}"
        size = f'width="{width * art.PX}" height="{(y1 - y0) * art.PX}"'
        return f"""<PartImage x="{start * art.PX}" y="{(y0 + down) * art.PX}" {size} alpha="{alpha}">
  <Transform target="x" value="{escape(x)}"/>
  <Image resource="cloud_{self.theme}"/>
</PartImage>"""

    def icons(self, *names):
        """Copied icons (same in every theme), at their places in the design."""
        for name in names:
            img = art.enlarge(Image.open(os.path.join(art.ART, f"{self.face}_icon_{name}.png")))
            img.save(os.path.join(self.drawables, f"icon_{name}.png"), optimize=True)
            img.save(os.path.join(PIXEL_ASSETS, f"{self.face}_icon_{name}.png"), optimize=True)

    def image(self, resource, x=0, y=0, w=SIZE, h=SIZE):
        return f"""<PartImage x="{x}" y="{y}" width="{w}" height="{h}">
  <Image resource="{resource}"/>
</PartImage>"""

    def icon(self, name):
        x, y, x1, y1 = (v * art.PX for v in art.ICON_BOXES[self.face][name])
        self.pictures.append((f"icon_{name}", x, y))
        return self.image(f"icon_{name}", x, y, x1 - x, y1 - y)

    def art(self, name):
        """This theme's copy of an art image."""
        return self.image(f"{name}_{self.theme}")

    def blink(self, name, expr):
        """An art overlay shown while `expr` holds."""
        return condition(self.name(name), expr, self.art(name))

    def rect(self, x, y, w, h, colour):
        self.rects.append((x, y, w, h, colour))
        return rect(x, y, w, h, argb(self.colour(colour)))

    # ---- text

    def text_box(self, x, baseline, font, size, chars):
        top = baseline - font.asc / font.upm * size
        return x, top, min(SIZE - x, (chars + 1) * 0.6 * size), font.line_h(size) + 2

    def text(self, x, baseline, chars, body, colour, sample, size, font="regular", ambient_alpha=None):
        """Left-aligned text starting at x; `sample` is what the preview shows."""
        if sample:
            self.texts.append(("ls", x, baseline, sample, size, colour, font))
        f = self.fonts[font]
        return part_text(*self.text_box(x, baseline, f, size, chars), f, size, argb(self.colour(colour)),
                         body, align="START", ambient_alpha=ambient_alpha)

    def glyph(self, centre, baseline, body, colour, sample, size, font, pitch):
        """One character centred on `centre`."""
        if sample:
            self.texts.append(("ms", centre, baseline, sample, size, colour, font))
        f = self.fonts[font]
        x, top, _, h = self.text_box(centre - pitch / 2, baseline, f, size, 0)
        return part_text(x, top, pitch, h, f, size, argb(self.colour(colour)), body, align="CENTER")

    def clock(self, centres, colon, baseline, size, font, colour, sample):
        """hh:mm as separate digits, as spaced in the design. Hours follow the 12/24-hour setting."""
        pitch = centres[1] - centres[0] + 4

        def digit(k, expr, show=True):
            return self.glyph(centres[k], baseline, template("%d", expr), colour, sample[k] if show else None,
                              size, font, pitch)
        hours = condition(self.name("h24_"), "[IS_24_HOUR_MODE]",
                          "\n".join([digit(0, "floor([HOUR_0_23] / 10)"), digit(1, "[HOUR_0_23] % 10")]),
                          "\n".join([digit(0, "floor([HOUR_1_12] / 10)", False),
                                     digit(1, "[HOUR_1_12] % 10", False)]))
        return [hours, self.glyph(colon, baseline, ":", colour, ":", size, font, pitch),
                digit(2, "floor([MINUTE] / 10)"), digit(3, "[MINUTE] % 10")]

    def seconds(self, centres, colon, baseline, size, font, colour, sample):
        pitch = centres[1] - centres[0] + 4
        return [self.glyph(colon, baseline, ":", colour, ":", size, font, pitch),
                self.glyph(centres[0], baseline, template("%d", "floor([SECOND] / 10)"), colour, sample[0],
                           size, font, pitch),
                self.glyph(centres[1], baseline, template("%d", "[SECOND] % 10"), colour, sample[1],
                           size, font, pitch)]

    def date(self, x, baseline, size, ambient_alpha=None):
        return self.text(x, baseline, 11, template("%s, %s %s", "[DAY_OF_WEEK_S]", "[DAY]", "[MONTH_S]"),
                         "date", "Thu, 26 Nov", size, ambient_alpha=ambient_alpha)

    def heart(self, x, baseline, suffix, size):
        self.texts.append(("ls", x, baseline, "72" + suffix, size, "text", "regular"))
        chars = 3 + len(suffix)
        return condition(
            self.name("has_hr"), "[HEART_RATE] > 0",
            self.text(x, baseline, chars, template("%d" + suffix, "round([HEART_RATE])"), "text", None, size),
            self.text(x, baseline, chars, "--" + suffix, "text", None, size))

    def steps(self, x, baseline, size):
        """Steps as 840 or 7.8k."""
        self.texts.append(("ls", x, baseline, "7.8k", size, "text", "regular"))
        return condition(
            self.name("under_1k"), "[STEP_COUNT] < 1000",
            self.text(x, baseline, 4, template("%d", "[STEP_COUNT]"), "text", None, size),
            self.text(x, baseline, 5, template("%d.%dk", "floor([STEP_COUNT] / 1000)",
                                               "floor([STEP_COUNT] / 100) % 10"), "text", None, size))

    def battery(self, x, baseline, size):
        return self.text(x, baseline, 4, template("%d%%", "[BATTERY_PERCENT]"), "text", "68%", size)

    # ---- output

    def write(self, title, scene, preview_overlays):
        def config(default_index):
            options = "\n".join(
                f'    <ListOption id="{i}" displayName="accent_{name}" icon="thumb_{name}"/>'
                for i, (name, _, _) in enumerate(self.themes))
            return f"""<UserConfigurations>
  <ListConfiguration id="theme" displayName="accent_label" defaultValue="{default_index}">
{options}
  </ListConfiguration>
</UserConfigurations>"""

        self.previews(preview_overlays)
        with open(os.path.join(PIXEL_ASSETS, f"{self.face}.json"), "w", encoding="utf-8") as f:
            json.dump({t: {k: "#" + self.colour(k, i) for k in self.colours}
                       for i, (t, _, _) in enumerate(self.themes)}, f, indent=1)
        write_module(self.face, title, [(t, a) for t, _, a in self.themes], scene, self.res, self.base,
                     user_config=False, extra=config, config_label="Theme")

    def previews(self, overlays):
        """Preview at 21:18:23 with sample data, from the same layout as the XML."""
        from PIL import ImageFont
        ss = 3
        for i, (theme, _, _) in enumerate(self.themes):
            img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 255))
            for name in ["scene", *overlays]:
                img.alpha_composite(Image.open(os.path.join(self.drawables, f"{name}_{theme}.png")))
            img.alpha_composite(art.enlarge(self.motion_frame))
            if self.face == "retropixel":
                cloud = Image.open(os.path.join(self.drawables, f"cloud_{theme}.png")).convert("RGBA")
                for start, down, alpha in RP_CLOUDS:
                    part = cloud.copy()
                    part.putalpha(part.getchannel("A").point(lambda a: a * alpha // 255))
                    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
                    layer.paste(part, (start * art.PX, (art.RP_CLOUD[1] + down) * art.PX))
                    img.alpha_composite(layer)
            for name, x, y in self.pictures:
                img.alpha_composite(Image.open(os.path.join(self.drawables, f"{name}.png")), (x, y))
            img = img.resize((SIZE * ss, SIZE * ss), Image.NEAREST)
            dr = ImageDraw.Draw(img)
            for x, y, w, h, colour in self.rects:
                dr.rectangle([x * ss, y * ss, (x + w) * ss - 1, (y + h) * ss - 1], fill="#" + self.colour(colour, i))
            for anchor, x, baseline, text, size, colour, font in self.texts:
                pil = ImageFont.truetype(self.fonts[font].src, round(size * ss))
                dr.text((x * ss, baseline * ss), text, font=pil, fill="#" + self.colour(colour, i), anchor=anchor)
            d = os.path.join(self.base, theme, "res", "drawable-nodpi")
            os.makedirs(d, exist_ok=True)
            art.round_screen(img).resize((SIZE, SIZE), Image.LANCZOS).save(os.path.join(d, "preview.png"),
                                                                           optimize=True)


def space_terminal():
    f = PixelFace("spaceterminal", art.SPACE_THEMES, art.SPACE_HUES, SP_COLOURS)
    f.art_images("scene")
    moving = f.motion()
    f.icons("moon", "battery", "heart", "shoe")
    weather_b, battery_b, heart_b, steps_b = SP_BASES
    x, size = SP_TEXT_X, SP_TEXT

    def weather():
        f.texts.append(("ls", x, weather_b, "24°C Haze", size, "text", "regular"))

        def reading(unit):
            short = f.text(x, weather_b, 11, template(f"%d°{unit} %s", "[WEATHER.TEMPERATURE]",
                                                      "[WEATHER.CONDITION_NAME]"), "text", None, size)
            long_ = f.text(x, weather_b, 6, template(f"%d°{unit}", "[WEATHER.TEMPERATURE]"), "text", None, size)
            # Longer condition names would run off the round screen: then the temperature only.
            return condition(f.name("short_sky"), "textLength([WEATHER.CONDITION_NAME]) <= 6", short, long_)
        return condition(f.name("weather"), "[WEATHER.IS_AVAILABLE]",
                         condition(f.name("fahrenheit"), "[WEATHER.TEMPERATURE_UNIT] == 2",
                                   reading("F"), reading("C")),
                         f.text(x, weather_b, 4, "--°", "text", None, size))

    def build():
        x0, pitch, w, y, count = SP_RULE
        rule = [f.rect(x0 + k * pitch, y, w, 2, "rule") for k in range(count)]
        return [
            group("scene", [f.art("scene")], ambient_alpha=0),
            group("motion", moving, ambient_alpha=0),
            group("clock", f.clock(SP_DIGITS, SP_COLON, SP_TIME_BASE, SP_TIME, "bold", "time", "2118"),
                  ambient_alpha=220),
            group("date", [f.date(SP_DATE_X, SP_DATE_BASE, SP_DATE)], ambient_alpha=170),
            group("readings", [*rule, f.icon("moon"), weather(), f.icon("heart"), f.heart(x, heart_b, " bpm", size),
                               f.icon("shoe"), f.steps(x, steps_b, size)], ambient_alpha=0),
            group("battery", [f.icon("battery"), f.battery(x, battery_b, size)], ambient_alpha=140),
        ]
    f.write("Space Terminal", f.assemble(build), [])


def retro_pixel():
    f = PixelFace("retropixel", art.RETRO_THEMES, art.RETRO_HUES, RP_COLOURS)
    for name in ("scene", "cloud", "lights"):
        f.art_images(name)
    moving = f.motion()
    f.icons("battery", "heart", "shoe")
    battery_b, heart_b, steps_b = RP_BASES
    x, size = RP_TEXT_X, RP_TEXT

    def build():
        return [
            group("scene", [f.art("scene"), f.blink("lights", "[SECOND] % 10 >= 6")], ambient_alpha=0),
            group("motion", moving, ambient_alpha=0),
            group("clouds", [f.cloud(*c) for c in RP_CLOUDS], ambient_alpha=0),
            group("clock", f.clock(RP_DIGITS, RP_COLON, RP_TIME_BASE, RP_TIME, "bold", "time", "2118"),
                  ambient_alpha=220),
            group("seconds", f.seconds(RP_SECONDS, RP_SECONDS_COLON, RP_TIME_BASE, RP_TIME, "regular", "seconds",
                                       "23"), ambient_alpha=0),
            group("date", [f.date(RP_DATE_X, RP_DATE_BASE, RP_DATE)], ambient_alpha=170),
            group("readings", [f.icon("battery"), f.battery(x, battery_b, size),
                               f.icon("heart"), f.heart(x, heart_b, "", size),
                               f.icon("shoe"), f.steps(x, steps_b, size)], ambient_alpha=0),
        ]
    f.write("Retro Pixel", f.assemble(build), [])


# ---------------------------------------------------------------- Orbit
#
# A rotary dial: three rings of numbers (hours, minutes, seconds) turn clockwise so that the
# current time lines up in a pill at 3 o'clock, around the date. Radii, sizes and colours are
# measured from the design mockup (tools/art/orbit_mockup.png). Numbers lie along the
# spokes, upright at 3 o'clock, counting anticlockwise: as a ring turns clockwise the next
# number comes down from above. Each dim ring is one picture turned by the time (the seconds
# sweep; minutes and hours step); the lit numbers in the pill are text at the very same
# places. The ring pictures are also written to shared/src/main/assets/orbit for the app
# preview (OrbitPainter.kt). Always-on keeps the date and the pill with hours and minutes.

ORBIT_ASSETS = os.path.join(ROOT, "shared", "src", "main", "assets", "orbit")
OB_ACCENTS = [("orange", "E8652A"), ("blue", "3D9BFF"), ("lime", "A6E22E"), ("white", "E8E8E8")]

# Dim rings: (radius, font size, weight, colour).
OB_HOURS = (100.7, 22.5, "bold", "4a4a4a")
OB_MINUTES = (152.2, 13.1, "regular", "464646")
OB_SECONDS = (200.5, 11.7, "medium", "303030")
OB_LIT = (23.5, 14, 12)  # sizes of the lit hour, minutes and seconds in the pill
OB_LINES = (125.2, 176.4)  # thin circles between the rings
OB_CENTRE_R = 62.7  # dashed circle around the date
OB_PILL = (296.8, 203.8, 443.7, 246.2)  # left, top, right, bottom
OB_DATE = ((194, 11), (224.5, 48.5), (256, 10.5))  # (centre y, size) of weekday, day, month
OB_CAP = 0.70  # Space Grotesk digit height, per unit of font size


def ob_stamp(img, ss, font_path, radius, size, angle, text, colour, alpha=255):
    """One number at `radius`, turned `angle` degrees clockwise from 3 o'clock."""
    from PIL import ImageFont
    font = ImageFont.truetype(font_path, round(size * ss))
    side = round(size * 3 * ss)
    tile = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    rgb = tuple(int(colour[i:i + 2], 16) for i in (0, 2, 4))
    ImageDraw.Draw(tile).text((side / 2, side / 2 + OB_CAP * size * ss / 2), text, font=font,
                              fill=rgb + (alpha,), anchor="ms")
    tile = tile.rotate(-angle, Image.BICUBIC, expand=True)
    a = math.radians(angle)
    x, y = CX + radius * math.cos(a), CY + radius * math.sin(a)
    img.alpha_composite(tile, (round(x * ss - tile.width / 2), round(y * ss - tile.height / 2)))


def ob_dial(path):
    """The still parts: rim ticks, the lines between rings and the dashed circle."""
    ss = 4
    img = Image.new("RGBA", (SIZE * ss, SIZE * ss), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)

    def box(r):
        return [(CX - r) * ss, (CY - r) * ss, (CX + r) * ss, (CY + r) * ss]
    for r in OB_LINES:
        dr.ellipse(box(r), outline="#121212", width=ss)
    for k in range(96):
        dr.arc(box(OB_CENTRE_R), k * 3.75, k * 3.75 + 1.9, fill="#272727", width=ss)
    for k in range(60):
        a = math.radians(k * 6)
        inner, outer, colour = (214, 222.5, "#363636") if k % 5 == 0 else (217.5, 222, "#222222")
        dr.line([((CX + inner * math.sin(a)) * ss, (CY - inner * math.cos(a)) * ss),
                 ((CX + outer * math.sin(a)) * ss, (CY - outer * math.cos(a)) * ss)], fill=colour,
                width=round(1.2 * ss))
    img.resize((SIZE, SIZE), Image.LANCZOS).save(path, optimize=True)


def ob_pill(fill_path, line_path):
    """The pill's tinted backing, and its outline with a soft glow (both white, tinted)."""
    from PIL import ImageFilter
    ss = 4
    box = [v * ss for v in OB_PILL]
    radius = (OB_PILL[3] - OB_PILL[1]) / 2 * ss
    size = (SIZE * ss, SIZE * ss)

    def save(alpha, path):
        out = Image.new("RGBA", size, (255, 255, 255, 0))
        out.putalpha(alpha)
        out.resize((SIZE, SIZE), Image.LANCZOS).save(path, optimize=True)

    glow = Image.new("L", size, 0)
    ImageDraw.Draw(glow).rounded_rectangle(box, radius, fill=62)
    glow = glow.filter(ImageFilter.GaussianBlur(7 * ss))
    inside = Image.new("L", size, 0)
    ImageDraw.Draw(inside).rounded_rectangle(box, radius, fill=255)
    glow.paste(22, (0, 0), inside)  # the faint tint inside the pill
    save(glow, fill_path)
    line = Image.new("L", size, 0)
    ImageDraw.Draw(line).rounded_rectangle(box, radius, outline=188, width=round(1.5 * ss))
    save(line, line_path)


def orbit():
    import shutil
    face = "orbit"
    base = os.path.join(ROOT, "watchfaces", face, "src")
    res = os.path.join(base, "main", "res")
    fdir = os.path.join(res, "font")
    drawables = os.path.join(res, "drawable-nodpi")
    os.makedirs(drawables, exist_ok=True)
    os.makedirs(ORBIT_ASSETS, exist_ok=True)
    fonts = {"bold": Font("spacegrotesk.ttf", fdir, "spacegrotesk_bold", {"wght": 700}),
             "medium": Font("spacegrotesk.ttf", fdir, "spacegrotesk_medium", {"wght": 500}),
             "regular": Font("spacegrotesk.ttf", fdir, "spacegrotesk_regular", {"wght": 400})}
    bold, medium = fonts["bold"], fonts["medium"]
    paths = {k: os.path.join(fdir, f"spacegrotesk_{k}.ttf") for k in fonts}

    two = [(v, f"{v:02d}") for v in range(60)]
    rings = {
        "hours12": (OB_HOURS, [(v, str(v or 12)) for v in range(12)], 30),
        "hours24": (OB_HOURS, [(v, str(v)) for v in range(24)], 15),
        "minutes": (OB_MINUTES, two, 6),
        "seconds": (OB_SECONDS, two, 6),
    }
    names = []
    for name, ((radius, size, weight, colour), values, step) in rings.items():
        ss = 4
        img = Image.new("RGBA", (SIZE * ss, SIZE * ss), (0, 0, 0, 0))
        for value, label in values:
            ob_stamp(img, ss, paths[weight], radius, size, -value * step, label, colour)
        img.resize((SIZE, SIZE), Image.LANCZOS).save(os.path.join(drawables, f"ring_{name}.png"), optimize=True)
        names.append(f"ring_{name}")
    ob_dial(os.path.join(drawables, "dial.png"))
    ob_pill(os.path.join(drawables, "pill_fill.png"), os.path.join(drawables, "pill_line.png"))
    for name in [*names, "dial", "pill_fill", "pill_line"]:
        shutil.copyfile(os.path.join(drawables, f"{name}.png"), os.path.join(ORBIT_ASSETS, f"{name}.png"))

    white = "#ffffffff"

    def picture(resource, angle=None, tint=None):
        turn = f'\n  <Transform target="angle" value="{escape(angle)}"/>' if angle else ""
        tint_attr = f' tintColor="{tint}"' if tint else ""
        return f"""<PartImage x="0" y="0" width="{SIZE}" height="{SIZE}" pivotX="0.5" pivotY="0.5"{tint_attr}>{turn}
  <Image resource="{resource}"/>
</PartImage>"""

    def text(cx, cy, width, font, size, color, body, tint=None, letter_spacing=None):
        """A line centred on (cx, cy), measured on the digit height."""
        top = cy + OB_CAP * size / 2 - font.asc / font.upm * size
        return part_text(cx - width / 2, top, width, font.line_h(size) + 2, font, size, color, body,
                         tint=tint, letter_spacing=letter_spacing)

    def turned(name, children, angle=0, angle_expr=None, alpha_expr=None):
        """Children laid out at 3 o'clock, turned about the centre of the face."""
        transforms = "".join(f'\n  <Transform target="{t}" value="{escape(e)}"/>'
                             for t, e in (("angle", angle_expr), ("alpha", alpha_expr)) if e)
        body = "\n".join(indent(c, 2) for c in children)
        return f"""<Group name="{name}" x="0" y="0" width="{SIZE}" height="{SIZE}" pivotX="0.5" pivotY="0.5" angle="{angle}">{transforms}
{body}
</Group>"""

    def two_digits(expr):
        return template("%d%d", f"floor(({expr}) / 10)", f"({expr}) % 10")

    def by_clock(name, then_xml, else_xml):
        return condition(f"{name}{next(_time_ids)}", "[IS_24_HOUR_MODE]", then_xml, else_xml)

    hour_size, minute_size, second_size = OB_LIT

    def hour_text(source):
        return text(CX + OB_HOURS[0], CY, 44, bold, hour_size, white, template("%d", source))

    def minute_text(offset):
        return text(CX + OB_MINUTES[0], CY, 30, bold, minute_size, white,
                    two_digits(f"([MINUTE] + {offset}) % 60"))

    def second_text(offset):
        return text(CX + OB_SECONDS[0], CY, 28, bold, second_size, white,
                    two_digits(f"([SECOND] + {offset}) % 60"), tint=ACCENT)

    # The seconds sweep through the pill: as the ring turns clockwise this second leaves
    # downwards while the next arrives from above. Each fades at the pill's edge.
    part = "([SECOND_MILLISECOND] - floor([SECOND_MILLISECOND]))"
    seconds = [
        turned("this_second", [second_text(0)], angle_expr=f"{part} * 6",
               alpha_expr=f"clamp((0.9 - {part}) * 850, 0, 255)"),
        turned("next_second", [second_text(1)], angle_expr=f"({part} - 1) * 6",
               alpha_expr=f"clamp(({part} - 0.1) * 850, 0, 255)"),
    ]

    (day_y, day_size), (date_y, date_size), (month_y, month_size) = OB_DATE
    date = [
        text(CX, day_y, 100, medium, day_size, argb("8a8a8a"),
             "<Upper>" + template("%s", "[DAY_OF_WEEK_S]") + "</Upper>", letter_spacing=0.2),
        text(CX, date_y, 110, bold, date_size, white, template("%d", "[DAY]")),
        text(CX, month_y, 100, bold, month_size, white,
             "<Upper>" + template("%s", "[MONTH_S]") + "</Upper>", tint=ACCENT, letter_spacing=0.2),
    ]
    hour_ring = by_clock("ring_h", picture("ring_hours24", "[HOUR_0_23] * 15"),
                         picture("ring_hours12", "([HOUR_1_12] % 12) * 30"))
    scene = [
        group("dial", [picture("dial"), hour_ring, picture("ring_minutes", "[MINUTE] * 6"),
                       picture("ring_seconds", "[SECOND_MILLISECOND] * 6")], ambient_alpha=0),
        group("pill_back", [picture("pill_fill", tint=ACCENT)], ambient_alpha=0),
        group("date", date, ambient_alpha=170),
        group("time", [by_clock("pill_h", hour_text("[HOUR_0_23]"), hour_text("[HOUR_1_12]")),
                       minute_text(0)], ambient_alpha=200),
        group("around", [turned("minute_before", [minute_text(59)], angle=6),
                         turned("minute_after", [minute_text(1)], angle=-6)], ambient_alpha=0),
        group("seconds", seconds, ambient_alpha=0),
        # Over the numbers, so the pill's edge clips the ones leaving it.
        group("pill", [picture("pill_line", tint=ACCENT)], ambient_alpha=140),
    ]
    orbit_preview_images(base, drawables, paths)
    write_module(face, "Orbit", OB_ACCENTS, scene, res, base)


def orbit_preview_images(base, drawables, paths):
    """Preview at the mockup's time: THU 26 NOV, 8:27 and two and a half seconds."""
    ss = 3
    for name, hex_ in OB_ACCENTS:
        img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 255))

        def layer(resource, angle=0, tint=None):
            part = Image.open(os.path.join(drawables, f"{resource}.png")).convert("RGBA")
            if tint:
                alpha = part.getchannel("A")
                part = Image.new("RGBA", part.size, "#" + tint)
                part.putalpha(alpha)
            img.alpha_composite(part.rotate(-angle, Image.BICUBIC))
        layer("dial")
        layer("ring_hours12", 8 * 30)
        layer("ring_minutes", 27 * 6)
        layer("ring_seconds", 2.5 * 6)
        layer("pill_fill", tint=hex_)
        big = img.resize((SIZE * ss, SIZE * ss), Image.LANCZOS)
        hour_size, minute_size, second_size = OB_LIT
        ob_stamp(big, ss, paths["bold"], OB_HOURS[0], hour_size, 0, "8", "ffffff")
        for offset, label in ((-1, "28"), (0, "27"), (1, "26")):
            ob_stamp(big, ss, paths["bold"], OB_MINUTES[0], minute_size, offset * 6, label, "ffffff")
        for offset, label in ((0.5, "02"), (-0.5, "03")):
            ob_stamp(big, ss, paths["bold"], OB_SECONDS[0], second_size, offset * 6, label, hex_)
        line = Image.open(os.path.join(drawables, "pill_line.png")).getchannel("A").resize(big.size, Image.LANCZOS)
        big.paste(Image.new("RGBA", big.size, "#" + hex_), (0, 0), line)
        dr = ImageDraw.Draw(big)
        from PIL import ImageFont
        for (cy, size), s, weight, colour, spacing in zip(
                OB_DATE, ("THU", "26", "NOV"), ("medium", "bold", "bold"), ("8a8a8a", "ffffff", hex_),
                (0.2, 0, 0.2)):
            font = ImageFont.truetype(paths[weight], round(size * ss))
            total = sum(font.getlength(c) for c in s) + spacing * size * ss * (len(s) - 1)
            left = CX * ss - total / 2
            for c in s:
                dr.text((left, (cy + OB_CAP * size / 2) * ss), c, font=font, fill="#" + colour, anchor="ls")
                left += font.getlength(c) + spacing * size * ss
        mask = Image.new("L", big.size, 0)
        ImageDraw.Draw(mask).ellipse([0, 0, big.width - 1, big.height - 1], fill=255)
        out = Image.new("RGBA", big.size, (0, 0, 0, 0))
        out.paste(big, (0, 0), mask)
        d = os.path.join(base, name, "res", "drawable-nodpi")
        os.makedirs(d, exist_ok=True)
        out.resize((SIZE, SIZE), Image.LANCZOS).save(os.path.join(d, "preview.png"), optimize=True)


# ---------------------------------------------------------------- module files

def write_module(face, title, accents, scene, res, base, user_config=True, extra="", editable=True,
                 strings=None, config_label="Accent"):
    """scene: list of scene XML children, or a function accent index -> list (per-flavour scenes)."""
    for d in ("values", "xml", "drawable-nodpi"):
        os.makedirs(os.path.join(res, d), exist_ok=True)
    labels = "\n".join(f'    <string name="accent_{n}">{n.capitalize()}</string>' for n, _ in accents)
    labels += "".join(f'\n    <string name="{k}">{escape(v)}</string>' for k, v in (strings or {}).items())
    with open(os.path.join(res, "values", "strings.xml"), "w", encoding="utf-8") as f:
        f.write(f"""<?xml version="1.0" encoding="utf-8"?>
<!-- Generated by tools/gen_watchfaces.py -->
<resources>
    <string name="app_name">{title}</string>
    <string name="accent_label">{config_label}</string>
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
    shell_window()
    shell_full()
    stack()
    terminal()
    commit_grid()
    silhouette()
    java_face()
    sql_face()
    space_terminal()
    retro_pixel()
    orbit()

"""Pixel art for the Space Terminal and Retro Pixel faces, copied from the design mockup.

The design (tools/art/pixel_faces_mockup.png) is a small screenshot of both faces. Each art
pixel in it is only about 1.75 screenshot pixels and a little blurred, so there is no exact
pixel grid to recover (script/pixel_copy.py reports that). The art is copied onto a
225 x 225 grid instead, one art pixel per 2 x 2 face pixels, which keeps all of its detail.

Then the text and icons drawn over the art are removed (the faces draw live ones), the parts
the screenshot hides (the top of each screen, the bottom behind the name labels) are filled
in, Retro Pixel's cloud and the window lights that switch off are separated, and the icons are
copied. The rest of the motion is drawn by tools/pixel_motion.py.

Run `python tools/pixel_art.py` after changing the mockup or the clean-up below. It writes
tools/art/<face>_*.png (225 x 225, or icon size), which tools/gen_watchfaces.py enlarges,
recolours for each theme and builds the faces from.
"""

import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "script"))
import pixel_copy as pc  # noqa: E402

ART = os.path.join(ROOT, "tools", "art")
MOCKUP = os.path.join(ART, "pixel_faces_mockup.png")
N = 225  # art grid
PX = 2  # face pixels per art pixel

# Watch screens in the mockup: centre x, centre y, radius (screenshot px), fitted to the bezels.
SCREENS = {"spaceterminal": (223.6, 132.3, 196.5), "retropixel": (694.25, 134.2, 196.5)}
VISIBLE_BOTTOM = 315  # screenshot y where the face name labels start covering the screens

# Icons, as art-pixel boxes on the grid (x0, y0, x1, y1).
ICON_BOXES = {
    "spaceterminal": {"moon": (123, 110, 140, 127), "battery": (123, 130, 140, 147),
                      "heart": (123, 150, 140, 167), "shoe": (123, 170, 140, 187)},
    "retropixel": {"battery": (162, 111, 177, 127), "heart": (162, 132, 177, 148),
                   "shoe": (162, 152, 177, 169)},
}


# ---------------------------------------------------------------- theme colours

# (name, hue shift in degrees, app accent colour). The shift turns the art's purples; colours
# outside the hue window (whites, the warm moon, rim light and windows) stay as they are.
SPACE_THEMES = [("violet", 0, "b4a0ff"), ("cyan", -65, "6fd8ff"), ("amber", 150, "ffb454"), ("mint", -110, "74eab0")]
SPACE_HUES = (180, 340)
RETRO_THEMES = [("violet", 0, "a66bff"), ("blue", -45, "4ea1ff"), ("sunset", 70, "ff7a59"), ("teal", -115, "3dd6b0")]
RETRO_HUES = (190, 345)


def recolour(rgb, shift, hues):
    """Turns the hue of the colours inside `hues` (degrees) by `shift`. rgb: (..., 3) uint8 array."""
    if shift == 0:
        return rgb
    a = rgb.astype(np.float32) / 255
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx, mn = a.max(-1), a.min(-1)
    d = mx - mn
    h = np.zeros_like(mx)
    nz = d > 1e-6
    rm = nz & (mx == r)
    gm = nz & (mx == g) & ~rm
    bm = nz & ~rm & ~gm
    h[rm] = ((g - b)[rm] / d[rm]) % 6
    h[gm] = (b - r)[gm] / d[gm] + 2
    h[bm] = (r - g)[bm] / d[bm] + 4
    h *= 60
    s = np.where(mx > 0, d / np.maximum(mx, 1e-6), 0)
    turn = (h >= hues[0]) & (h <= hues[1]) & (s > 0.12)
    h = np.where(turn, (h + shift) % 360, h) / 60
    i = np.floor(h).astype(int) % 6
    f = h - np.floor(h)
    p, q, t = mx * (1 - s), mx * (1 - s * f), mx * (1 - s * (1 - f))
    out = np.stack([np.choose(i, [mx, q, p, p, t, mx]), np.choose(i, [t, mx, mx, q, p, p]),
                    np.choose(i, [p, p, t, mx, mx, q])], -1)
    return np.where(turn[..., None], np.round(out * 255), rgb).astype(np.uint8)


def recolour_hex(hex_, shift, hues):
    c = np.array([[int(hex_[k:k + 2], 16) for k in (0, 2, 4)]], np.uint8)
    return "%02x%02x%02x" % tuple(int(v) for v in recolour(c, shift, hues)[0])


def themed_image(img, shift, hues):
    """An RGBA image recoloured for a theme."""
    a = np.asarray(img.convert("RGBA"))
    rgb = recolour(a[..., :3], shift, hues)
    return Image.fromarray(np.dstack([rgb, a[..., 3]]), "RGBA")


def round_screen(img):
    """Clears everything outside the round screen."""
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).ellipse([0, 0, img.width - 1, img.height - 1], fill=255)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def enlarge(img):
    return img.resize((img.width * PX, img.height * PX), Image.NEAREST)


# ---------------------------------------------------------------- copying a screen

def copy_screen(face):
    """The screen's art on the N x N grid, and which rows the screenshot actually shows."""
    cx, cy, r = SCREENS[face]
    size = 2 * r / N
    x0, y0 = math.floor(cx - r) - 1, math.floor(cy - r) - 1
    crop = Image.open(MOCKUP).convert("RGB").crop((x0, y0, x0 + math.ceil(2 * r) + 4, y0 + math.ceil(2 * r) + 4))
    grid = pc.Grid(size, size, cx - r - x0, cy - r - y0)
    cells, fx, fy = pc.read_cells(crop, grid)
    i0, j0 = round((cx - r - x0 - fx) / size), round((cy - r - y0 - fy) / size)
    cells = cells[j0:j0 + N, i0:i0 + N]
    # Merge only blur and compression noise: real colours stay apart.
    pal, index = pc.merge_palette(cells, merge=12)
    centre_y = cy - r + (np.arange(N) + 0.5) * size
    shown = (centre_y >= 0) & (centre_y <= VISIBLE_BOTTOM)
    return pal[index].copy(), shown


def radius_map():
    j, i = np.mgrid[0:N, 0:N]
    return np.hypot(i + 0.5 - N / 2, j + 0.5 - N / 2)


def lum(c):
    return c.astype(np.int32).max(-1)


def components(mask):
    """4-connected groups of True cells, as lists of (y, x)."""
    seen = np.zeros_like(mask)
    groups = []
    for y, x in zip(*np.nonzero(mask)):
        if seen[y, x]:
            continue
        stack, group = [(y, x)], []
        seen[y, x] = True
        while stack:
            cy, cx = stack.pop()
            group.append((cy, cx))
            for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                if 0 <= ny < N and 0 <= nx < N and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        groups.append(group)
    return groups


def in_box(y, x, box):
    x0, y0, x1, y1 = box
    return x0 <= x < x1 and y0 <= y < y1


def neighbourhood_colour(c, y, x, skip):
    """Median colour around a cell, leaving out the cells in `skip`."""
    vals = [c[ny, nx] for ny in range(y - 2, y + 3) for nx in range(x - 2, x + 3)
            if 0 <= ny < N and 0 <= nx < N and (ny, nx) not in skip]
    return np.median(np.array(vals), axis=0).astype(np.uint8)


def overlay(cells_and_colours):
    """Transparent N x N image with the given cells painted."""
    img = np.zeros((N, N, 4), np.uint8)
    for (y, x), colour in cells_and_colours:
        img[y, x, :3] = colour
        img[y, x, 3] = 255
    return Image.fromarray(img, "RGBA")


def save_icons(face, c):
    """Each icon in its whole box (so it goes back at the box's position), background clear."""
    for name, (x0, y0, x1, y1) in ICON_BOXES[face].items():
        part = c[y0:y1, x0:x1]
        alpha = np.where(lum(part) > 60, 255, 0).astype(np.uint8)
        Image.fromarray(np.dstack([part, alpha]), "RGBA").save(os.path.join(ART, f"{face}_icon_{name}.png"))


def as_image(c):
    """RGBA scene image, transparent outside the round screen."""
    alpha = np.where(radius_map() <= N / 2, 255, 0).astype(np.uint8)
    return Image.fromarray(np.dstack([c, alpha]), "RGBA")


# ---------------------------------------------------------------- Space Terminal

SP_TEXT = (115, 45, N, 190)  # time, date, rule and readings


def space_terminal():
    face = "spaceterminal"
    c, shown = copy_screen(face)
    save_icons(face, c)
    x0, y0, x1, y1 = SP_TEXT
    c[y0:y1, x0:x1] = 0
    # Above the screenshot: empty space. Behind the label: the moon goes on as above it.
    c[:np.argmax(shown)] = 0
    last = N - 1 - np.argmax(shown[::-1])
    c[last + 1:] = c[last]
    # Space is black: the screenshot's near-black is glare and compression.
    c[lum(c) < 24] = 0
    # The bezel's reflection along the edge.
    ring = radius_map() > N / 2 - 4
    grey = (c.astype(int).max(-1) - c.astype(int).min(-1)) < 40
    c[ring & grey] = 0
    as_image(c).save(os.path.join(ART, f"{face}_scene.png"))


# ---------------------------------------------------------------- Retro Pixel

RP_TEXT = (86, 49, 202, 96)  # time and date, over the sky
RP_PANEL = (149, 103)  # left and top edge of the readings panel
RP_SKY_SOURCES = [(18, 86), (202, 220)]  # columns to borrow sky from
RP_NOT_SKY = [(0, 50, 72, 82), (62, 98, 96, 128)]  # cloud, moon
RP_CLOUD = (0, 50, 72, 82)  # the box the cloud is cut from
RP_CLOUD_JOIN = (27, 40)  # columns where the whole cloud starts its middle, and its mirrored end
RP_CLOUD_DARK = 30  # darker than this in the box is sky
RP_NOT_WINDOWS = [(46, 132, 84, 190), (84, 150, 108, 190)]  # kid, cat (their rim light)
RP_ART_EDGE = 105.5  # radius (art pixels) where the mockup's art meets the screen's black border


def panel_border_colour():
    """The thin panel outline is too fine for the grid: read it from the screenshot."""
    cx, cy, r = SCREENS["retropixel"]
    size = 2 * r / N
    img = np.asarray(Image.open(MOCKUP).convert("RGB")).astype(int)
    x = round(cx - r + (RP_PANEL[0] + 0.5) * size)
    ys = range(round(cy - r + 120 * size), round(cy - r + 190 * size))
    column = np.array([img[y, x - 2:x + 3] for y in ys]).reshape(-1, 3)
    return tuple(int(v) for v in column[np.argmax(column.max(-1))])


def whole_cloud(img):
    """The design's cloud runs off the left of the screen. Drifting, it needs both ends: its left
    end is its right end mirrored, joined where the two are about the same height."""
    right = img.crop((RP_CLOUD_JOIN[1], 0, img.getbbox()[2], img.height))
    middle = img.crop((RP_CLOUD_JOIN[0], 0, img.getbbox()[2], img.height))
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    left = right.transpose(Image.FLIP_LEFT_RIGHT)
    out.paste(left, (1, 0))
    out.paste(middle, (1 + left.width, 0))
    return out


def retro_pixel():
    face = "retropixel"
    c, shown = copy_screen(face)
    save_icons(face, c)
    rng = np.random.default_rng(7)
    rad = radius_map()
    first = int(np.argmax(shown))
    last = N - 1 - int(np.argmax(shown[::-1]))

    def sky_like(y, x):
        """A cell of sky from the same row, away from the text, cloud and moon."""
        for _ in range(200):
            x0, x1 = RP_SKY_SOURCES[rng.integers(len(RP_SKY_SOURCES))]
            sx = int(rng.integers(x0, x1))
            if rad[y, sx] < N / 2 - 5 and not any(in_box(y, sx, b) for b in RP_NOT_SKY):
                return c[y, sx]
        return c[y, x]

    # Sky behind the time and date: the same row's sky, picked at random so it doesn't repeat.
    x0, y0, x1, y1 = RP_TEXT
    for y in range(y0, y1):
        for x in range(x0, x1):
            c[y, x] = sky_like(y, x)
    # Above the screenshot (and its first rows, greyed by the screenshot's edge): more of the
    # top of the sky.
    top = first + 4
    for y in range(top):
        for x in range(N):
            c[y, x] = c[top + int(rng.integers(0, 6)), x]
    # Behind the label: below the art, which ends above it.
    c[last + 1:] = 0
    # The mockup's screen has a black border inside the bezel (the art stops at about radius
    # RP_ART_EDGE). Carry the art out to the edge instead: each border cell takes the cell
    # mirrored just inside the art's edge, which keeps its texture.
    for y, x in zip(*np.nonzero(rad > RP_ART_EDGE)):
        k = (2 * RP_ART_EDGE - rad[y, x]) / rad[y, x]
        c[y, x] = c[int((y + 0.5 - N / 2) * k + N / 2), int((x + 0.5 - N / 2) * k + N / 2)]

    # The readings panel: black, with a thin outline and a rounded top-left corner.
    img = Image.fromarray(c)
    px, py = RP_PANEL
    ImageDraw.Draw(img).rounded_rectangle([px, py, N + 8, N + 8], radius=4, fill=(2, 1, 3),
                                          outline=panel_border_colour())
    c = np.asarray(img).copy()
    # The cloud drifts, so it is cut out into a picture of its own and the sky filled in.
    x0, y0, x1, y1 = RP_CLOUD
    inside = np.zeros((N, N), bool)
    inside[y0:y1, x0:x1] = True
    cloud = max(components(inside & (lum(c) > RP_CLOUD_DARK)), key=len)
    whole_cloud(overlay([(p, c[p]) for p in cloud]).crop(RP_CLOUD)).save(os.path.join(ART, f"{face}_cloud.png"))
    halo = {(y + dy, x + dx) for y, x in cloud for dy in (-1, 0, 1) for dx in (-1, 0, 1)
            if 0 <= y + dy < N and 0 <= x + dx < N}
    filled = [(p, sky_like(*p)) for p in sorted(halo)]
    for p, colour in filled:
        c[p] = colour
    as_image(c).save(os.path.join(ART, f"{face}_scene.png"))

    # Window lights: small warm dots on the buildings; every third one switches off now and then.
    a = c.astype(int)
    warm = (a[..., 0] > 140) & (a[..., 0] - a[..., 2] > 10)
    windows = np.zeros((N, N), bool)
    windows[118:200, :px] = True
    for b in RP_NOT_WINDOWS:
        windows[b[1]:b[3], b[0]:b[2]] = False
    lights = [g for g in components(warm & windows) if len(g) <= 3]
    lights.sort(key=lambda g: (g[0][1], g[0][0]))
    off = []
    for g in lights[::3]:
        skip = set(g)
        off.extend((p, neighbourhood_colour(c, *p, skip)) for p in g)
    overlay(off).save(os.path.join(ART, f"{face}_lights.png"))
    print(f"[art] {face}: cloud of {len(cloud)} pixels, {len(lights[::3])} of {len(lights)} window lights blink")


if __name__ == "__main__":
    space_terminal()
    retro_pixel()

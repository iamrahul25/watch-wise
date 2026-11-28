"""The moving parts of the two pixel faces, as a seamless loop of transparent frames.

Like Ember Forest, the watch plays them as animated pictures over the still scene. Everything
is drawn on the 225 x 225 art grid (one art pixel = 2 face pixels) in colours that suit every
theme, so one loop per face serves all four. The apps' previews play the same frames.

Space Terminal: twinkling stars, shooting stars, a moonlet circling the ringed planet, a
satellite passing by, moon dust floating up, a glint across the visor and a chest light.

Retro Pixel: twinkling stars, shooting stars, a breathing glow round the moon, sparks drifting
up over the city, windows lighting up, a plane, an antenna beacon and the cat's swaying tail.
(Its clouds drift too: the faces move those themselves, because they are themed.)

Every motion repeats a whole number of times per loop, so the loop has no seam. Everything is
deterministic: regenerating gives identical frames.
"""

import math

import numpy as np
from PIL import Image, ImageDraw

N = 225  # art grid
LOOP = 8.0  # seconds
FPS = 10
FRAMES = int(LOOP * FPS)
PREVIEW_FRAME = 14  # the still shown in preview images: a shooting star is in the sky


def noise(a, b):
    v = math.sin(a * 127.1 + b * 311.7) * 43758.5453
    return v - math.floor(v)


def wave(t, cycles, phase=0.0):
    """0..1 sine that completes `cycles` whole cycles per loop."""
    return 0.5 + 0.5 * math.sin(2 * math.pi * (t * cycles / LOOP + phase))


class Frame:
    def __init__(self):
        self.img = Image.new("RGBA", (N, N), (0, 0, 0, 0))

    def dot(self, x, y, colour, alpha=255):
        """Blends one art pixel over what the frame already has."""
        x, y, alpha = int(math.floor(x + 0.5)), int(math.floor(y + 0.5)), int(max(0, min(255, alpha)))
        if not (0 <= x < N and 0 <= y < N) or alpha == 0:
            return
        r, g, b, a = self.img.getpixel((x, y))
        top = alpha / 255
        under = a / 255 * (1 - top)
        out = top + under
        mix = tuple(round((c * top + d * under) / out) for c, d in zip(colour, (r, g, b)))
        self.img.putpixel((x, y), mix + (round(out * 255),))

    def plus(self, x, y, arm, colour, alpha):
        """A star: bright centre, arms fading outwards."""
        self.dot(x, y, colour, alpha)
        for k in range(1, arm + 1):
            a = alpha * (1 - k / (arm + 1))
            for dx, dy in ((k, 0), (-k, 0), (0, k), (0, -k)):
                self.dot(x + dx, y + dy, colour, a)


def meteor(frame, t, start, begin, end, duration=0.9, tail=18, colour=(255, 244, 224)):
    """A shooting star from `begin` to `end`, starting `start` seconds into the loop."""
    age = (t - start) % LOOP
    if age > duration:
        return
    p = age / duration
    fade = min(1.0, p * 5, (1 - p) * 3)
    dx, dy = end[0] - begin[0], end[1] - begin[1]
    length = math.hypot(dx, dy)
    hx, hy = begin[0] + dx * p, begin[1] + dy * p
    for k in range(tail):
        back = min(k, p * length)
        a = 255 * fade * (1 - k / tail) ** 1.4
        frame.dot(hx - dx / length * back, hy - dy / length * back, colour, a)
    frame.plus(hx, hy, 1, (255, 255, 255), 255 * fade)


# ---------------------------------------------------------------- Space Terminal

# The scene's own stars: (x, y, arm length).
SP_STARS = [(25, 91, 5), (36, 58, 2), (88, 108, 2), (101, 157, 3), (86, 140, 1)]
# Extra stars that fade in and out: (x, y, cycles per loop, phase).
SP_FAINT = [(30, 42, 2, 0.1), (52, 33, 3, 0.6), (74, 46, 1, 0.3), (96, 38, 2, 0.8), (104, 62, 3, 0.2),
            (44, 52, 1, 0.7), (14, 74, 2, 0.45), (40, 100, 3, 0.9), (100, 88, 1, 0.05), (110, 128, 2, 0.55),
            (74, 121, 3, 0.35), (13, 143, 1, 0.65), (68, 134, 2, 0.15), (90, 25, 1, 0.5), (61, 105, 2, 0.25)]
# Top edge of the moon under the astronaut: dust lifts off from here.
SP_RIM = [(24, 166), (31, 165), (39, 165), (73, 169), (80, 171), (87, 175), (94, 180), (100, 186)]
SP_PLANET = (68.5, 72.8, 10.5)  # centre x, y, radius of the body
SP_ORBIT = (27.0, 8.5, -19.0)  # moonlet: half width, half height, tilt in degrees
SP_VISOR = (50.5, 126.0, 7.2, 7.6)  # centre x, y, half width, half height
SP_TEXT_LEFT = 115  # nothing moves right of this between rows 45 and 190
SP_SATELLITE = [".....w.....",  # panels either side of the body, a dish below
                "....www....",
                "PpPp-wws-PpPp"[1:12],
                "pPpP-wos-pPpP"[1:12],
                "PpPp-wss-PpPp"[1:12],
                "....sss....",
                ".....s....."]


def space_frame(index, scene):
    t = index / FPS
    f = Frame()
    px = scene.load()
    lavender = (196, 180, 255)

    # The scene's stars breathe: their arms dim to black, then flare past their usual length.
    for k, (x, y, arm) in enumerate(SP_STARS):
        v = wave(t, 2 + k % 3, k * 0.27)
        if v < 0.55:
            dim = 255 * (0.55 - v) / 0.55
            for d in range(1, arm + 1):
                for dx, dy in ((d, 0), (-d, 0), (0, d), (0, -d)):
                    f.dot(x + dx, y + dy, (0, 0, 0), dim * min(1.0, 0.45 + d / arm))
        elif v > 0.75:
            flare = (v - 0.75) / 0.25
            for d in range(arm + 1, arm + 1 + max(1, arm // 2)):
                for dx, dy in ((d, 0), (-d, 0), (0, d), (0, -d)):
                    f.dot(x + dx, y + dy, (255, 255, 255), 150 * flare)
            for dx, dy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
                f.dot(x + dx, y + dy, lavender, 170 * flare)

    for x, y, cycles, phase in SP_FAINT:
        v = wave(t, cycles, phase) ** 3
        f.plus(x, y, 1 if v > 0.7 else 0, (236, 230, 255), 255 * v)

    meteor(f, t, 0.8, (112, 24), (50, 55))
    meteor(f, t, 4.9, (62, 20), (10, 66), duration=0.8, tail=14, colour=(206, 190, 255))

    # A moonlet circling the planet, hidden while it passes behind.
    cx, cy, radius = SP_PLANET
    rx, ry, tilt = SP_ORBIT
    cos_t, sin_t = math.cos(math.radians(tilt)), math.sin(math.radians(tilt))
    for trail in range(5, -1, -1):
        a = 2 * math.pi * (t / LOOP) - trail * 0.13
        ex, ey = rx * math.cos(a), ry * math.sin(a)
        x, y = cx + ex * cos_t - ey * sin_t, cy + ex * sin_t + ey * cos_t
        behind = math.sin(a) < 0 and math.hypot(x - cx, y - cy) < radius + 1
        if behind:
            continue
        if trail:
            f.dot(x, y, lavender, 190 - trail * 32)
        else:
            for dx, dy, colour in ((0, 0, (255, 255, 255)), (1, 0, (255, 248, 230)), (0, 1, lavender),
                                   (1, 1, (140, 118, 205))):
                f.dot(x + dx, y + dy, colour)

    # A satellite crossing between the planet and the astronaut, its lamp blinking.
    p = (t / LOOP + 0.35) % 1
    sx, sy = -10 + p * 128, 101 - p * 9 + math.sin(p * 2 * math.pi) * 1.5
    if sx < SP_TEXT_LEFT - 9:
        sx, sy = math.floor(sx), math.floor(sy)
        fade = min(1.0, (SP_TEXT_LEFT - 9 - sx) / 10)
        colours = {"p": (74, 108, 200), "P": (140, 176, 250), "-": (120, 110, 160),
                   "w": (240, 236, 250), "s": (170, 160, 205), "o": (255, 200, 110)}
        for row, line in enumerate(SP_SATELLITE):
            for col, ch in enumerate(line):
                if ch in colours:
                    f.dot(sx + col - len(line) // 2, sy + row - 3, colours[ch], 255 * fade)
        if int(t * 5) % 4 == 0:
            f.plus(sx, sy - 4, 1, (255, 90, 90), 255 * fade)

    # Moon dust lifting off in the low gravity.
    for i in range(18):
        age = (t * (1 + i % 2) / LOOP + noise(i, 3)) % 1
        bx, by = SP_RIM[i % len(SP_RIM)]
        x = bx + (noise(i, 5) - 0.5) * 8 - age * (6 + 10 * noise(i, 9)) + math.sin(age * 6 + i) * 1.5
        y = by - 2 - age * (16 + 22 * noise(i, 13))
        if 40 <= x <= 70 and y > 112:  # not across the astronaut
            continue
        f.dot(x, y, (230, 222, 255) if i % 3 else lavender, 235 * math.sin(math.pi * age) ** 0.8)

    # A glint sweeping across the dark visor, twice a loop.
    vx, vy, vw, vh = SP_VISOR
    sweep = (t % (LOOP / 2)) / 1.1
    if sweep < 1:
        line = -vw - vh + sweep * 2 * (vw + vh)
        for y in range(int(vy - vh), int(vy + vh) + 1):
            for x in range(int(vx - vw), int(vx + vw) + 1):
                if ((x - vx) / vw) ** 2 + ((y - vy) / vh) ** 2 > 0.92 or max(px[x, y][:3]) > 60:
                    continue
                d = (x - vx) + (y - vy) * 0.6 - line
                if -1.2 <= d <= 1.2:
                    f.dot(x, y, (205, 195, 255), 170 if abs(d) < 0.7 else 90)
                elif -4.5 <= d <= -3.2:
                    f.dot(x, y, lavender, 70)

    # The suit's chest light.
    beat = t % 2.0
    if beat < 0.5:
        a = 255 if beat < 0.3 else 140
        f.dot(55, 145, (255, 82, 96), a)
        f.dot(56, 145, (255, 150, 150), a)
        f.dot(55, 146, (190, 40, 70), a)
    else:
        f.dot(55, 145, (110, 40, 66), 230)
    return f.img


# ---------------------------------------------------------------- Retro Pixel

RP_PANEL = (149, 103)  # the readings panel: nothing moves over it
# Sky stars: (x, y, cycles per loop, phase, arm).
RP_STARS = [(19, 87, 2, 0.0, 2), (54, 87, 3, 0.4, 1), (80, 83, 1, 0.7, 1), (28, 101, 2, 0.2, 1),
            (123, 104, 3, 0.85, 1), (137, 101, 2, 0.5, 2), (113, 111, 1, 0.1, 0), (46, 108, 3, 0.65, 0),
            (94, 133, 2, 0.3, 1), (110, 127, 1, 0.9, 0), (42, 134, 2, 0.75, 0), (189, 99, 3, 0.15, 1),
            (212, 84, 2, 0.55, 1), (171, 90, 1, 0.35, 0), (66, 54, 2, 0.95, 1), (33, 42, 1, 0.45, 1),
            (78, 35, 3, 0.05, 0), (140, 36, 2, 0.8, 1), (196, 43, 1, 0.25, 1), (214, 60, 3, 0.6, 0),
            (58, 96, 2, 0.12, 0), (126, 90, 1, 0.58, 0), (101, 100, 3, 0.72, 0), (22, 122, 2, 0.38, 0)]
RP_MOON = (78.3, 114.2, 11.6)
# Windows that light up now and then: (x, y).
RP_WINDOWS = [(8, 130), (13, 137), (30, 147), (33, 155), (29, 166), (44, 172), (115, 166), (119, 172),
              (137, 148), (142, 155), (134, 162), (145, 167), (10, 150), (131, 172)]
RP_BEACONS = [(16, 112, 0.0), (139, 123, 0.9)]  # antenna tips: (x, y, delay)
# The cat's tail: from its side, over the edge of the roof; the tip swings.
RP_TAIL_ROOT = (101.0, 181.0)


def tail(frame, t):
    swing = math.sin(2 * math.pi * t * 2 / LOOP)
    flick = math.sin(2 * math.pi * t * 4 / LOOP + 0.8) * 0.35
    rx, ry = RP_TAIL_ROOT
    # Down over the edge of the roof, ending in a hook that swings and curls.
    points = [(rx, ry), (rx + 6, ry + 1.5), (rx + 8 + swing, ry + 7),
              (rx + 10.5 + swing * 3.5, ry + 11),
              (rx + 15 + swing * 5, ry + 10.5 - flick * 3),
              (rx + 16 + swing * 6 + flick * 3, ry + 6.5 - flick * 5)]
    mask = Image.new("L", (N, N), 0)
    dr = ImageDraw.Draw(mask)
    ends = [points[0], *points, points[-1]]
    for seg in range(len(points) - 1):
        a, b, c, d = ends[seg:seg + 4]
        for k in range(13):
            s = k / 12
            x, y = (0.5 * (2 * b[i] + (c[i] - a[i]) * s + (2 * a[i] - 5 * b[i] + 4 * c[i] - d[i]) * s * s +
                           (3 * b[i] - a[i] - 3 * c[i] + d[i]) * s ** 3) for i in (0, 1))
            r = 2.4 - 0.9 * (seg + s) / (len(points) - 1)
            dr.ellipse([round(x - r), round(y - r), round(x + r - 0.5), round(y + r - 0.5)], fill=255)
    m = np.asarray(mask) > 0
    ys, xs = np.nonzero(m)
    for y, x in zip(ys.tolist(), xs.tolist()):
        # Outlined by the city's glow, as the cat itself is; open where it joins the body.
        edge = not (m[y - 1, x] and m[y + 1, x] and m[y, x - 1] and m[y, x + 1])
        frame.dot(x, y, (214, 108, 96) if edge and x > rx + 3 else (20, 8, 52))


def retro_frame(index, scene):
    t = index / FPS
    f = Frame()

    for x, y, cycles, phase, arm in RP_STARS:
        v = wave(t, cycles, phase) ** 3
        f.plus(x, y, arm if v > 0.65 else min(arm, 1) if v > 0.35 else 0, (255, 214, 244), 255 * v)

    meteor(f, t, 0.9, (150, 22), (78, 62), duration=1.0, tail=22)
    meteor(f, t, 5.2, (219, 62), (176, 96), duration=0.8, tail=15, colour=(255, 200, 230))

    # The moon's glow swells and shrinks, in a dithered ring.
    mx, my, r = RP_MOON
    glow = wave(t, 2)
    reach = r + 4 + 4 * glow
    for y in range(int(my - reach), int(my + reach) + 1):
        for x in range(int(mx - reach), int(mx + reach) + 1):
            d = math.hypot(x - mx, y - my)
            if r + 0.8 < d < reach:
                k = 1 - (d - r) / (reach - r)
                if (x + y) % 2 == 0 or k > 0.72:
                    f.dot(x, y, (255, 188, 112), 150 * k * (0.55 + 0.45 * glow))

    # A plane crossing under the stars, once a loop.
    p = (t / LOOP + 0.1) % 1
    ax, ay = -8 + p * 245, 97 - p * 12
    f.dot(ax, ay, (210, 196, 236), 220)
    f.dot(ax - 1, ay, (150, 130, 190), 200)
    f.dot(ax - 2, ay, (130, 110, 170), 120)
    if int(t * 5) % 4 == 0:
        f.plus(ax + 1, ay, 1, (255, 74, 84), 255)
    elif int(t * 5) % 4 == 2:
        f.dot(ax - 1, ay - 1, (255, 255, 255))

    # Warm sparks drifting up from the city, like the embers over a fire.
    for i in range(26):
        age = (t * (1 + i % 2) / LOOP + noise(i, 4)) % 1
        x = 6 + noise(i, 7) * 138 + math.sin(age * 7 + i) * 4 + age * 7 * (noise(i, 8) - 0.4)
        y = 178 - noise(i, 11) * 14 - age * (30 + 34 * noise(i, 12))
        colour = (255, 232, 160) if age < 0.35 else (255, 170, 96) if age < 0.7 else (232, 96, 132)
        a = 255 * min(1.0, age * 6, (1 - age) * 1.8)
        f.dot(x, y, colour, a)
        if i % 5 == 0:
            f.dot(x, y + 1, colour, a * 0.55)

    # Windows switching on for a while, each at its own time.
    for i, (x, y) in enumerate(RP_WINDOWS):
        phase = (t / LOOP + noise(i, 21)) % 1
        if phase < 0.45:
            a = 255 * min(1.0, phase * 12, (0.45 - phase) * 12)
            f.dot(x, y, (255, 214, 130), a)
            f.dot(x, y + 1, (255, 160, 96), a)

    for x, y, delay in RP_BEACONS:
        beat = (t + delay) % 1.6
        if beat < 0.5:
            f.plus(x, y, 2 if beat < 0.2 else 1, (255, 70, 96), 255 if beat < 0.35 else 150)

    tail(f, t)

    # Nothing over the readings panel.
    ImageDraw.Draw(f.img).rectangle([RP_PANEL[0], RP_PANEL[1], N, N], fill=(0, 0, 0, 0))
    return f.img


FACES = {"spaceterminal": space_frame, "retropixel": retro_frame}


def frames(face, scene):
    """The loop for a face over its (violet) scene, outside the round screen left clear."""
    j, i = np.mgrid[0:N, 0:N]
    outside = np.hypot(i + 0.5 - N / 2, j + 0.5 - N / 2) > N / 2
    out = []
    for index in range(FRAMES):
        a = np.asarray(FACES[face](index, scene)).copy()
        a[outside] = 0
        out.append(Image.fromarray(a, "RGBA"))
    return out


def bounds(images, box):
    """The part of `box` (art pixels) that the frames ever draw on, or None."""
    found = None
    for img in images:
        b = img.crop(box).getbbox()
        if b:
            b = (b[0] + box[0], b[1] + box[1], b[2] + box[0], b[3] + box[1])
            found = b if not found else (min(found[0], b[0]), min(found[1], b[1]),
                                         max(found[2], b[2]), max(found[3], b[3]))
    return found


# Parts of the screen animated separately, to keep the watch's picture memory small.
REGIONS = {"spaceterminal": [(0, 0, 116, N)],
           "retropixel": [(0, 0, N, 103), (0, 103, RP_PANEL[0], N)]}

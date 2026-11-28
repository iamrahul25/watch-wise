"""Copy pixel art out of an image: find its pixel size, read each art pixel's colour, rebuild it.

Works on screenshots and mockups where the art was scaled by any factor (2.6 is as fine as
3), blurred a little or saved as JPEG.

How it finds the pixel size: for every candidate size it rebuilds the image from one colour
per cell and measures how far that is from the source. On real pixel art the error drops
sharply at the true size (and at its halves, thirds...), so the largest size with a sharp
drop wins. If no size has one, the image has no exact grid (art smaller than ~2 image pixels
per art pixel, heavy blur, or AI-made "pixel art" with uneven pixels): it says so and copies
at the coarsest size that still keeps the detail.

The colour of each art pixel is the median of the middle of its cell (edges are blurred),
then colours that only differ by blur / compression noise are merged into one palette.

Usage:
  python script/pixel_copy.py IMAGE [options]

  --box X0,Y0,X1,Y1     only look at this part of the image
  --pixel-size P        skip detection: art pixel size in image pixels (or PX,PY)
  --offset OX,OY        with --pixel-size: image position of a grid line (default: best fit)
  --max-size S          largest pixel size to search (default 32)
  --merge D             merge colours closer than D (redmean distance 0..765, default 28)
  --colors N            or: reduce to exactly N colours
  --out PATH            output base name (default: <image>_pixels)
  --scale K             also write the copy enlarged K times (default 8)

Prints the pixel size, grid position, art size, how sure it is, and the palette.
Writes
  <out>.png            the art, one image pixel per art pixel
  <out>_x<K>.png       the art enlarged, for looking at
  <out>_compare.png    the source next to the copy, at the same size
  <out>.json           pixel size, grid, palette and the art as palette indices

From Python: detect_grid(), fit_offset(), read_cells(), merge_palette(), copy_pixel_art().
"""

import argparse
import json
import math
import os
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw


@dataclass
class Grid:
    """Art pixels are `size_x` x `size_y` image pixels; grid lines pass through x = offset_x, y = offset_y."""
    size_x: float
    size_y: float
    offset_x: float
    offset_y: float
    confidence: float = float("nan")  # 0..1 for a detected grid; 0 when the image has no exact grid

    def columns(self, width):
        """x of the first grid line at or before 0, and the number of cells covering 0..width."""
        start = self.offset_x - math.ceil(self.offset_x / self.size_x) * self.size_x
        return start, math.ceil((width - start) / self.size_x)

    def rows(self, height):
        start = self.offset_y - math.ceil(self.offset_y / self.size_y) * self.size_y
        return start, math.ceil((height - start) / self.size_y)


def colour_distance(a, b):
    """Perceptual-ish RGB distance ("redmean"), 0..765."""
    a = np.asarray(a, np.float32)
    b = np.asarray(b, np.float32)
    r = (a[..., 0] + b[..., 0]) / 2
    d = a - b
    return np.sqrt((2 + r / 256) * d[..., 0] ** 2 + 4 * d[..., 1] ** 2 + (2 + (255 - r) / 256) * d[..., 2] ** 2)


# ---------------------------------------------------------------- measuring a grid

def _centres(start, size, length):
    return np.arange(start + size / 2, length, size)


def copy_error(rgb, grid):
    """Average colour difference between the source and a quick copy on this grid
    (each cell takes the colour of the image pixel at its centre)."""
    h, w = rgb.shape[:2]
    x0, _ = grid.columns(w)
    y0, _ = grid.rows(h)
    cx, cy = _centres(x0, grid.size_x, w), _centres(y0, grid.size_y, h)
    if len(cx) == 0 or len(cy) == 0:
        return float("inf")
    cells = rgb[np.clip(cy.astype(int), 0, h - 1)][:, np.clip(cx.astype(int), 0, w - 1)]
    ix = np.floor((np.arange(w) + 0.5 - x0) / grid.size_x).astype(int).clip(0, len(cx) - 1)
    iy = np.floor((np.arange(h) + 0.5 - y0) / grid.size_y).astype(int).clip(0, len(cy) - 1)
    return float(colour_distance(cells[iy[:, None], ix[None, :]], rgb).mean())


def _edge_profiles(rgb):
    """How much the colour changes across each column / row boundary (boundary k is before pixel k)."""
    a = rgb.astype(np.float32)
    dx = np.abs(np.diff(a, axis=1)).sum(axis=2)
    dy = np.abs(np.diff(a, axis=0)).sum(axis=2)
    return dx.sum(axis=0), dy.sum(axis=1)


def _phase(profile, size):
    """Where the edges sit for this period: a grid line position in 0..size."""
    pos = np.arange(1, len(profile) + 1, dtype=np.float64)
    coef = (profile * np.exp(-2j * np.pi * pos / size)).sum()
    return float((-np.angle(coef) * size / (2 * np.pi)) % size)


def fit_offset(rgb, sx, sy, steps=8):
    """Grid line position that copies best for this pixel size."""
    px, py = _edge_profiles(rgb)
    gx, gy = _phase(px, sx), _phase(py, sy)
    best = Grid(sx, sy, gx, gy)
    best_err = copy_error(rgb, best)
    for dx in np.linspace(-sx / 2, sx / 2, steps, endpoint=False):
        for dy in np.linspace(-sy / 2, sy / 2, steps, endpoint=False):
            g = Grid(sx, sy, (gx + dx) % sx, (gy + dy) % sy)
            e = copy_error(rgb, g)
            if e < best_err:
                best, best_err = g, e
    return best, best_err


# ---------------------------------------------------------------- finding the pixel size

SHARP_DROP = 0.75  # a size's error must be below this share of its neighbours' to count as a grid


def detect_grid(img, max_size=32.0):
    """Finds the art's pixel size and grid. confidence 0..1; 0 means there is no exact grid
    and the returned grid is the coarsest size that keeps the detail (see faithful_grid)."""
    rgb = np.asarray(img.convert("RGB"))
    h, w = rgb.shape[:2]
    px, py = _edge_profiles(rgb)
    max_size = min(max_size, w / 4, h / 4)
    sizes = np.exp(np.arange(math.log(1.2), math.log(max(1.3, max_size)), 0.003))
    errs = np.array([copy_error(rgb, Grid(s, s, _phase(px, s), _phase(py, s))) for s in sizes])

    # Sharpness of the drop: error against the median of sizes within +-8%.
    logs = np.log(sizes)
    drops = []
    for i, s in enumerate(sizes):
        near = errs[np.abs(logs - logs[i]) < 0.08]
        ratio = errs[i] / max(1e-6, float(np.median(near)))
        is_min = errs[i] == errs[max(0, i - 2):i + 3].min()
        if ratio < SHARP_DROP and is_min:
            drops.append((s, ratio))
    if not drops:
        return faithful_grid(rgb)

    # Halves and thirds of the true size copy just as exactly, so the largest sharp drop wins.
    size, ratio = max(drops)
    # Refine: over a few hundred cells, 0.1% of error drifts by whole pixels.
    best = None
    for s in size * np.linspace(0.994, 1.006, 61):
        g, e = fit_offset(rgb, s, s, steps=4)
        if best is None or e < best[1]:
            best = (g, e)
    g, _ = fit_offset(rgb, best[0].size_x, best[0].size_y, steps=12)
    g.confidence = float(min(1.0, max(0.0, 1 - ratio)))
    return g


def faithful_grid(rgb, slack=1.5):
    """For images without an exact grid: the largest size whose copy is still about as close
    to the source as a copy at 1.25 image pixels per art pixel."""
    rgb = np.asarray(rgb)
    chosen, limit = None, None
    for s in np.arange(1.25, 6.001, 0.05):
        g, e = fit_offset(rgb, s, s, steps=4)
        if limit is None:
            limit = e * slack + 2
        if e <= limit:
            chosen = g
    chosen.confidence = 0.0
    return chosen


# ---------------------------------------------------------------- reading colours

def read_cells(img, grid, inner=0.5):
    """Colour of every cell: the median of the image pixels in the middle `inner` of the cell,
    or the pixel nearest its centre when the cell is small.
    Returns (cells as an (rows, cols, 3) uint8 array, x of the first column, y of the first row)."""
    rgb = np.asarray(img.convert("RGB"))
    h, w = rgb.shape[:2]
    x0, cols = grid.columns(w)
    y0, rows = grid.rows(h)

    def span(centre, size, limit):
        a = max(0, math.ceil(centre - inner * size / 2 - 0.5))
        b = min(limit, math.floor(centre + inner * size / 2 - 0.5) + 1)
        if a >= b:
            a = min(limit - 1, max(0, int(centre)))
            b = a + 1
        return a, b

    out = np.zeros((rows, cols, 3), np.uint8)
    for j in range(rows):
        ya, yb = span(y0 + (j + 0.5) * grid.size_y, grid.size_y, h)
        for i in range(cols):
            xa, xb = span(x0 + (i + 0.5) * grid.size_x, grid.size_x, w)
            out[j, i] = np.median(rgb[ya:yb, xa:xb].reshape(-1, 3), axis=0)
    return out, x0, y0


def merge_palette(cells, merge=28.0, colors=None):
    """Merges colours that differ only by noise. Returns (palette as (n, 3) uint8, index per cell)."""
    if colors:
        q = Image.fromarray(cells, "RGB").quantize(colors=colors, method=Image.Quantize.MEDIANCUT, kmeans=4)
        pal = np.array(q.getpalette()[:3 * colors], np.uint8).reshape(-1, 3)
        return pal, np.asarray(q, np.int32)
    flat = cells.reshape(-1, 3)
    uniq, inverse, counts = np.unique(flat, axis=0, return_inverse=True, return_counts=True)
    centres, assign = [], np.zeros(len(uniq), np.int32)
    # Most common colours first: they are the real ones; rarer near ones are blur and noise.
    for u in np.argsort(-counts):
        if centres:
            d = colour_distance(np.array(centres), uniq[u])
            k = int(d.argmin())
            if d[k] < merge:
                assign[u] = k
                continue
        assign[u] = len(centres)
        centres.append(uniq[u].astype(np.float32))
    # Each palette colour is the most common real colour of its group, not an average
    # (which would be a colour that is not in the art).
    pal = np.array(centres, np.uint8).reshape(-1, 3)
    index = assign[inverse.reshape(-1)].reshape(cells.shape[:2])
    return pal, index


# ---------------------------------------------------------------- whole job

def copy_pixel_art(img, grid=None, merge=28.0, colors=None, max_size=32.0):
    """Returns (grid, palette, index array, x of the first column, y of the first row)."""
    grid = grid or detect_grid(img, max_size)
    cells, x0, y0 = read_cells(img, grid)
    pal, index = merge_palette(cells, merge, colors)
    return grid, pal, index, x0, y0


def to_image(pal, index):
    return Image.fromarray(pal[index], "RGB")


def compare_image(src, grid, art, x0, y0, zoom=4):
    """The source and the copy side by side, the copy drawn on the grid so they line up."""
    w, h = src.size
    left = src.convert("RGB").resize((w * zoom, h * zoom), Image.NEAREST)
    right = Image.new("RGB", left.size)
    d = ImageDraw.Draw(right)
    px = art.load()
    for j in range(art.height):
        for i in range(art.width):
            xa = round((x0 + i * grid.size_x) * zoom)
            ya = round((y0 + j * grid.size_y) * zoom)
            xb = round((x0 + (i + 1) * grid.size_x) * zoom) - 1
            yb = round((y0 + (j + 1) * grid.size_y) * zoom) - 1
            d.rectangle([xa, ya, xb, yb], fill=px[i, j])
    out = Image.new("RGB", (left.width * 2 + 8, left.height), (255, 0, 255))
    out.paste(left, (0, 0))
    out.paste(right, (left.width + 8, 0))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("--box")
    ap.add_argument("--pixel-size")
    ap.add_argument("--offset")
    ap.add_argument("--max-size", type=float, default=32.0)
    ap.add_argument("--merge", type=float, default=28.0)
    ap.add_argument("--colors", type=int)
    ap.add_argument("--out")
    ap.add_argument("--scale", type=int, default=8)
    a = ap.parse_args()

    src = Image.open(a.image).convert("RGB")
    if a.box:
        src = src.crop(tuple(int(v) for v in a.box.split(",")))
    grid = None
    if a.pixel_size:
        sizes = [float(v) for v in a.pixel_size.split(",")]
        sx, sy = (sizes * 2)[:2]
        if a.offset:
            ox, oy = (float(v) for v in a.offset.split(","))
            grid = Grid(sx, sy, ox, oy)
        else:
            grid, _ = fit_offset(np.asarray(src), sx, sy, steps=12)

    grid, pal, index, x0, y0 = copy_pixel_art(src, grid, a.merge, a.colors, a.max_size)
    art = to_image(pal, index)
    out = a.out or os.path.splitext(a.image)[0] + "_pixels"
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    art.save(out + ".png")
    art.resize((art.width * a.scale, art.height * a.scale), Image.NEAREST).save(f"{out}_x{a.scale}.png")
    compare_image(src, grid, art, x0, y0).save(out + "_compare.png")

    counts = np.bincount(index.reshape(-1), minlength=len(pal))
    hexes = ["%02x%02x%02x" % tuple(int(v) for v in c) for c in pal]
    with open(out + ".json", "w", encoding="utf-8") as f:
        json.dump({"pixel_size": [grid.size_x, grid.size_y], "grid_line": [grid.offset_x, grid.offset_y],
                   "first_cell": [x0, y0], "confidence": grid.confidence, "size": [art.width, art.height],
                   "palette": hexes, "pixels": index.tolist()}, f)

    print(f"pixel size : {grid.size_x:.4f} x {grid.size_y:.4f} image px")
    print(f"grid line  : x {grid.offset_x:.2f}, y {grid.offset_y:.2f}  (first cell at {x0:.2f}, {y0:.2f})")
    print(f"art size   : {art.width} x {art.height} pixels")
    if a.pixel_size:
        print("confidence : (pixel size given)")
    elif grid.confidence == 0:
        print("confidence : no exact pixel grid in this image (too small, blurred, or uneven pixels);")
        print("             copied at the coarsest size that keeps the detail. Use --pixel-size to choose.")
    else:
        print(f"confidence : {grid.confidence:.2f}")
    print(f"palette    : {len(pal)} colours (most used first)")
    total = counts.sum()
    for k in np.argsort(-counts)[:40]:
        print(f"  #{hexes[k]}  {counts[k]:6d}  {100 * counts[k] / total:5.1f}%")
    if len(pal) > 40:
        print(f"  ... and {len(pal) - 40} more (see {out}.json)")
    print(f"wrote      : {out}.png, {out}_x{a.scale}.png, {out}_compare.png, {out}.json")


if __name__ == "__main__":
    main()

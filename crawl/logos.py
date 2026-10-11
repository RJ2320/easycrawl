"""Make logos of any resolution sit together evenly.

Two problems with scaling every logo file to the same height:

  padding   a file with transparent margin renders smaller than one cropped
            tight, though the artwork is "the same size"
  shape     at equal height a wide wordmark covers several times the area of a
            compact emblem and dominates the row

So logos are measured by their *ink box* (the artwork, margins trimmed) and
sized by `balance`: 0 gives equal heights, 1 gives equal areas, in between
blends the two. A logo of aspect REFERENCE_ASPECT is exactly `logo_height`
tall at any balance.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional, Tuple

import numpy as np
from PIL import Image

Box = Tuple[int, int, int, int]   # left, top, right, bottom in source pixels

REFERENCE_ASPECT = 2.0            # width / height that maps to exactly logo_height
MIN_FACTOR, MAX_FACTOR = 0.5, 1.6 # how far balancing may move a logo off logo_height
PLACEHOLDER_ASPECT = 2.5          # empty slot box

_ALPHA_INK = 16     # alpha above this is artwork
_BLACK_BG = 24      # an opaque file whose corners are darker than this has a black margin
_BG_DIFF = 24       # ...and pixels this far from it are artwork


def apply_levels(im: Image.Image, black: float, white: float) -> Image.Image:
    """Remap an RGBA image's colours so `black` → 0 and `white` → full, clipping
    outside. Raising the black point crushes a not-quite-black background to
    true black, which is invisible on the crawl. Alpha is left alone."""
    if black <= 0 and white >= 1:
        return im
    span = max(0.02, white - black)
    lut = [int(round(min(1.0, max(0.0, (v / 255 - black) / span)) * 255)) for v in range(256)]
    r, g, b, alpha = im.split()
    return Image.merge("RGBA", (r.point(lut), g.point(lut), b.point(lut), alpha))


def _opaque_rgb(a: np.ndarray, invert: bool) -> np.ndarray:
    rgb = a[..., :3]
    return 255 - rgb if invert else rgb


@lru_cache(maxsize=512)
def _ink_box(path: str, mtime: float, invert: bool, black: int) -> Optional[Box]:
    with Image.open(path) as im:
        a = np.asarray(im.convert("RGBA"))
    h, w = a.shape[:2]
    alpha = a[..., 3]
    if int(alpha.min()) < 250:
        mask = alpha > _ALPHA_INK
    else:
        # Opaque. Only a margin that ends up black is safe to trim: it is
        # invisible on the crawl. That is judged on the artwork as it will be
        # drawn (inverted, black point raised), so a logo on a dark-grey or a
        # white background trims once it has been levelled or inverted. Any
        # other background is part of the artwork (a boxed logo).
        rgb = _opaque_rgb(a, invert)
        corners = rgb[[0, 0, -1, -1], [0, -1, 0, -1]].astype(np.int16)
        if int(corners.max()) >= max(_BLACK_BG, black + 1):
            return (0, 0, w, h)
        mask = rgb.max(axis=2) > max(_BG_DIFF, black)
    if not mask.any():
        return (0, 0, w, h)
    ys = np.flatnonzero(mask.any(axis=1))
    xs = np.flatnonzero(mask.any(axis=0))
    return (int(xs[0]), int(ys[0]), int(xs[-1]) + 1, int(ys[-1]) + 1)


def ink_box(path: Optional[str], invert: bool = False, black: float = 0.0) -> Optional[Box]:
    """The artwork's bounding box as it will be drawn, or None if the file can't be read."""
    if not path:
        return None
    try:
        return _ink_box(path, os.path.getmtime(path), bool(invert), int(round(black * 255)))
    except Exception:
        return None


def auto_black(path: Optional[str], invert: bool = False) -> float:
    """A black point (0..1) that just crushes the artwork's background, read
    from its corners. 0 for artwork with transparency or a background that is
    already black, or one too bright to be a background to remove."""
    try:
        with Image.open(path) as im:
            a = np.asarray(im.convert("RGBA"))
    except Exception:
        return 0.0
    if int(a[..., 3].min()) < 250:
        return 0.0
    corners = _opaque_rgb(a, invert)[[0, 0, -1, -1], [0, -1, 0, -1]]
    level = int(corners.max())
    if level < 2 or level > 140:
        return 0.0
    return min(0.6, (level + 6) / 255)       # a little headroom for compression noise


def aspect(path: Optional[str], invert: bool = False, black: float = 0.0) -> float:
    box = ink_box(path, invert, black)
    if box is None:
        return PLACEHOLDER_ASPECT
    l, t, r, b = box
    return max(1e-3, (r - l) / max(1, b - t))


def balanced_height(base_height: float, logo_aspect: float, balance: float) -> float:
    """Height for a logo of this aspect: balance 0 = equal heights, 1 = equal areas."""
    balance = min(1.0, max(0.0, balance))
    factor = (REFERENCE_ASPECT / logo_aspect) ** (0.5 * balance)
    return base_height * min(MAX_FACTOR, max(MIN_FACTOR, factor))


def size(path: Optional[str], base_height: float, balance: float, scale: float = 1.0,
         invert: bool = False, black: float = 0.0) -> Tuple[int, int]:
    """(width, height) in px for a logo slot."""
    r = aspect(path, invert, black)
    h = balanced_height(base_height, r, balance if path and ink_box(path, invert, black) else 0.0) * scale
    h = max(1, int(round(h)))
    return max(1, int(round(h * r))), h

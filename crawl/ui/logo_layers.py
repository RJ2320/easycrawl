"""Prepare logo display images in the rebuild worker, away from UI interactions."""
import os
from PySide6.QtGui import QImage
from PIL import Image, ImageChops
from .. import logos


def key(item, scale):
    stamp = os.path.getmtime(item.path) if item.path and os.path.isfile(item.path) else None
    return (item.path, stamp, item.crop, item.w, item.h, item.invert, item.black, item.white, item.mode, scale)


def prepare(item, scale):
    try:
        with Image.open(item.path) as source:
            image = source.convert('RGBA')
        if item.crop:
            image = image.crop(item.crop)
        image = image.resize((max(1, round(item.w * scale)), max(1, round(item.h * scale))), Image.Resampling.LANCZOS)
        if item.invert:
            r, g, b, alpha = image.split()
            image = Image.merge('RGBA', (*ImageChops.invert(Image.merge('RGB', (r, g, b))).split(), alpha))
        image = logos.apply_levels(image, item.black, item.white)
        if item.mode == 'grayscale':
            gray = image.convert('L')
            image = Image.merge('RGBA', (gray, gray, gray, image.getchannel('A')))
    except (OSError, TypeError):
        image = Image.new('RGBA', (max(1, round(item.w * scale)), max(1, round(item.h * scale))), '#414141')
    return QImage(image.tobytes(), image.width, image.height, image.width * 4, QImage.Format_RGBA8888).copy()

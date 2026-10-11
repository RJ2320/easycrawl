"""Delivery-size geometry shared by layout review and preview selection."""
from dataclasses import dataclass
import hashlib
import json
from PIL import Image
from . import text
from .lint import Finding


@dataclass(frozen=True)
class Region:
    box: tuple
    row: int
    target: str
    label: str

    def contains(self, x, y):
        a, b, c, d = self.box
        return a <= x <= c and b <= y <= d


def regions(layout, look):
    result = []
    styles = look.styles()
    for line in layout.lines:
        style = styles[line.style]
        width = text.width(style, line.text)
        x = line.x - (width / 2 if line.anchor[0] == 'm' else width if line.anchor[0] == 'r' else 0)
        boxes = []
        for st, value in text.runs(style, line.text):
            font = text.font_for(st)
            if st.tracking:
                for char, advance in zip(value, text.advances(st, value)):
                    a,b,c,d = font.getbbox(char, anchor='ls')
                    if c > a and d > b:
                        boxes.append((x+a,line.y+b,x+c,line.y+d))
                    x += advance
            else:
                a,b,c,d = font.getbbox(value, anchor='ls')
                if c > a and d > b:
                    boxes.append((x+a,line.y+b,x+c,line.y+d))
                x += font.getlength(value)
            x += style.tracking
        if boxes:
            box = (min(b[0] for b in boxes), min(b[1] for b in boxes),
                   max(b[2] for b in boxes), max(b[3] for b in boxes))
            result.append(Region(box, line.row, line.target, line.text))
    result.extend(Region((lg.x,lg.y,lg.x+lg.w,lg.y+lg.h),lg.row,'logo',lg.label) for lg in layout.logos)
    return result


def check_layout(layout, look):
    findings = []
    def add(kind, severity, region, message, detail=()):
        a,b,c,d = region.box
        identity = (kind,region.target,region.label,a,c,d-b,detail)
        key = 'layout:' + hashlib.sha256(json.dumps(identity).encode()).hexdigest()
        findings.append(Finding(kind,severity,region.row,message,region.target,key))

    objects = regions(layout, look)
    for obj in objects:
        left,top,right,bottom = obj.box
        if left < 0 or right > layout.width:
            add('layout-frame','error',obj,'Content extends outside the left or right frame edge.')
        elif left < layout.width*.05 or right > layout.width*.95:
            add('layout-safe','warning',obj,'Content is inside the outer 5% of the frame; check the safe margin.')
    active = []
    for obj in sorted(objects, key=lambda r:r.box[1]):
        a,b,c,d = obj.box
        active = [other for other in active if other.box[3] > b+2]
        for other in active:
            e,f,g,h = other.box
            if min(c,g)-max(a,e) > 2 and min(d,h)-max(b,f) > 2:
                for first,second in ((obj,other),(other,obj)):
                    add('layout-overlap','warning',first,
                        f'Possible overlap with “{second.label[:60]}” (row {second.row}).',
                        (second.label,second.target,second.box[0],second.box[2],second.box[1]-first.box[1]))
        active.append(obj)
    for lg in layout.logos:
        if not lg.path:
            continue  # Missing artwork is already reported by the source checks.
        region = Region((lg.x,lg.y,lg.x+lg.w,lg.y+lg.h),lg.row,'logo',lg.label)
        try:
            with Image.open(lg.path) as image:
                w,h = image.size
                if lg.crop:
                    a,b,c,d = lg.crop
                    w,h = c-a,d-b
                if lg.w > w*1.5 or lg.h > h*1.5:
                    add('layout-resolution','warning',region,
                        'Logo is enlarged beyond 150% of its source pixels and may look soft.',(lg.path,w,h))
        except (OSError,ValueError):
            add('layout-artwork','error',region,'Logo artwork could not be read.',(lg.path,))
    return findings

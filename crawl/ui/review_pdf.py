"""Paginated proofs rendered from the same layout and artwork as the crawl."""
from dataclasses import replace
from math import ceil, floor

from PySide6.QtCore import QIODevice, QRect, QSaveFile, Qt, QPointF
from PySide6.QtGui import QFont, QImage, QPageSize, QPainter, QPdfWriter

from ..layout_checks import regions
from ..model import Header
from ..render import render_panel


def section_choices(build):
    headings = sorted((b.row,b.text) for b in build.crawl.blocks() if isinstance(b,Header) and b.level==1)
    return [(f"{title} · row {row}", (row, headings[i+1][0] if i+1<len(headings) else float("inf")))
            for i,(row,title) in enumerate(headings)]


def write_review(path, build, look, section=None):
    layout = build.layout
    if section:
        first,end = section
        layout = replace(layout,lines=[v for v in layout.lines if first<=v.row<end],
                         logos=[v for v in layout.logos if first<=v.row<end])
    objects = regions(layout,look)
    boxes = sorted((floor(r.box[1]),ceil(r.box[3])) for r in objects)
    if not boxes:
        raise ValueError("There are no visible credits to export.")
    bands=[]
    for top,bottom in boxes:
        if bands and top<=bands[-1][1]:
            bands[-1]=(bands[-1][0],max(bottom,bands[-1][1]))
        else:
            bands.append((top,bottom))
    output=QSaveFile(str(path))
    if not output.open(QIODevice.WriteOnly):
        raise OSError(output.errorString())
    pdf=QPdfWriter(output)
    pdf.setPageSize(QPageSize(QPageSize.Letter))
    pdf.setResolution(180)
    pdf.setTitle("EasyCrawl review proof")
    painter=QPainter()
    if not painter.begin(pdf):
        raise OSError("Could not start the PDF.")
    try:
        width,height=pdf.width(),pdf.height()
        scale=width/look.width
        capacity=max(1,floor(height/scale))
        top=bands[0][0]
        end=bands[-1][1]
        while top<end:
            stop=min(end,top+capacity)
            cut=next((a for a,b in bands if top<a<stop<b),stop)
            pixels=render_panel(layout,look,top,cut,scale=scale).convert("RGB")
            raw=pixels.tobytes()
            image=QImage(raw,pixels.width,pixels.height,pixels.width*3,QImage.Format_RGB888)
            painter.fillRect(QRect(0,0,width,height),Qt.black)
            # The proof image preserves the film typography. Place a searchable
            # text layer beneath it at the corresponding credit positions.
            for obj in objects:
                left,y,_,bottom=obj.box
                if obj.target=="logo" or not top<=y<cut:
                    continue
                font=QFont()
                font.setPixelSize(max(1,round((bottom-y)*scale)))
                painter.setFont(font)
                painter.drawText(QPointF(left*scale,(bottom-top)*scale),obj.label)
            painter.drawImage(0,0,image)
            top=cut
            if top<end and not pdf.newPage():
                raise OSError("Could not write the next PDF page.")
    finally:
        painter.end()
        del pdf
    if not output.commit():
        raise OSError(output.errorString())

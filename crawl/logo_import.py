"""Convert EPS artwork once, keeping an immutable PNG and original locally."""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile

from PIL import Image

LOGO_FILTER = 'Logo artwork (*.png *.tif *.tiff *.jpg *.jpeg *.bmp *.webp *.eps)'
GHOSTSCRIPT_URL = 'https://ghostscript.com/releases/gsdnld.html'
MAX_INPUT = 32 * 1024 * 1024
MAX_EDGE = 4096
TIMEOUT = 45


class MissingGhostscript(ValueError):
    def __init__(self):
        super().__init__('EPS import needs Ghostscript for the initial conversion. Install it once, then try again. '
                         'Previously converted logos still work without it. Download: ' + GHOSTSCRIPT_URL)


def find_ghostscript():
    explicit = os.environ.get('CRAWL_GHOSTSCRIPT')
    if explicit and Path(explicit).is_file():
        return str(Path(explicit).resolve())
    for name in ('gswin64c', 'gswin32c', 'gs'):
        found = shutil.which(name)
        if found:
            return found
    from .logo_library import default_root
    candidates = [default_root().parent / 'tools' / 'ghostscript' / 'bin' / 'gswin64c.exe',
                  Path('/opt/homebrew/bin/gs'), Path('/usr/local/bin/gs'), Path('/usr/bin/gs')]
    for variable in ('ProgramFiles', 'ProgramFiles(x86)'):
        if os.environ.get(variable):
            root = Path(os.environ[variable]) / 'gs'
            if root.is_dir():
                versions = sorted(root.glob('gs*'), key=lambda p:tuple(int(n) for n in re.findall(r'\d+',p.name)), reverse=True)
                for version in versions:
                    candidates.extend(version / 'bin' / name for name in ('gswin64c.exe','gswin32c.exe'))
    return next((str(path) for path in candidates if path.is_file()), None)


def _postscript(data):
    # Some EPS files have a DOS preview header before the PostScript program.
    if data[:4] == b'\xc5\xd0\xd3\xc6':
        if len(data)<30:
            raise ValueError('This EPS preview header is incomplete.')
        offset,length = struct.unpack_from('<II',data,4)
        if offset<30 or length<1 or offset+length>len(data):
            raise ValueError('This EPS has an invalid PostScript data range.')
        data=data[offset:offset+length]
    if not data.startswith(b'%!PS'):
        raise ValueError('This file is not valid EPS / PostScript artwork.')
    return data


def _bounds(data):
    number=rb'([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)'
    for label in (b'HiResBoundingBox',b'BoundingBox'):
        pattern=rb'^%%'+label+rb':\s*'+rb'\s+'.join([number]*4)+rb'\s*$'
        for match in re.finditer(pattern,data,re.M):
            values=tuple(float(value) for value in match.groups())
            if all(math.isfinite(value) and abs(value)<10_000_000 for value in values):
                x0,y0,x1,y1=values
                if x1>x0 and y1>y0:
                    return values
    raise ValueError('This EPS has no usable bounding box. Re-export it as EPS with a bounding box, or use PNG/TIFF.')


def _valid_png(path, limited=True):
    try:
        with Image.open(path) as image:
            if image.width*image.height>40_000_000 or image.mode!='RGBA':
                return False
            if limited and (image.width>MAX_EDGE+2 or image.height>MAX_EDGE+2):
                return False
            image.load()
            return image.getchannel('A').getbbox() is not None
    except (OSError,ValueError,Image.DecompressionBombError):
        return False


def prepare_logo(path, *, root=None):
    """Return a renderable path. Raster inputs are unchanged; EPS becomes PNG."""
    path=Path(path).resolve()
    if path.suffix.lower()!='.eps':
        return str(path)
    if path.stat().st_size>MAX_INPUT:
        raise ValueError('This EPS is too large (maximum 32 MB).')
    data=path.read_bytes()
    if len(data)>MAX_INPUT:
        raise ValueError('This EPS is too large (maximum 32 MB).')
    program=_postscript(data)
    x0,y0,x1,y1=_bounds(program)
    from .logo_library import default_root, _atomic
    root=(Path(root) if root is not None else default_root()).resolve()
    digest=hashlib.sha256(b'EasyCrawl EPS v1 4096\0'+data).hexdigest()
    folder=root/'eps'/digest
    name=re.sub(r'[^\w .()-]','-',path.stem).strip(' .')[:100] or 'Logo'
    output=folder/(name+'.png')
    original=folder/'source.eps'
    if _valid_png(output) and original.is_file():
        return str(output)
    executable=find_ghostscript()
    if not executable:
        raise MissingGhostscript()
    dpi=72*MAX_EDGE/max(x1-x0,y1-y0)
    root.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.eps-',dir=root) as temporary:
        temporary=Path(temporary)
        source=temporary/'source.eps'
        # Resolve (atend) declarations up front so cropping never falls back to
        # a full printer page at logo resolution.
        integer_box=f'%%BoundingBox: {math.floor(x0)} {math.floor(y0)} {math.ceil(x1)} {math.ceil(y1)}'.encode()
        hires_box=f'%%HiResBoundingBox: {x0} {y0} {x1} {y1}'.encode()
        program=re.sub(rb'^%%BoundingBox:\s*\(atend\)[ \t]*\r?$',lambda _:integer_box,program,flags=re.M)
        program=re.sub(rb'^%%HiResBoundingBox:\s*\(atend\)[ \t]*\r?$',lambda _:hires_box,program,flags=re.M)
        if not re.search(rb'^%%BoundingBox:\s*[-+\d.]',program,re.M):
            first,separator,rest=program.partition(b'\n')
            program=first+b'\n'+integer_box+b'\n'+hires_box+b'\n'+rest
        source.write_bytes(program)
        rendered=temporary/'logo.png'
        command=[executable,'-dSAFER','-dBATCH','-dNOPAUSE','-dQUIET','-dEPSCrop',
                 '-dFirstPage=1','-dLastPage=1','-sDEVICE=pngalpha',f'-r{dpi:.8f}',
                 '-dTextAlphaBits=4','-dGraphicsAlphaBits=4',f'-sOutputFile={rendered}','-f',str(source)]
        env=dict(os.environ);env.pop('GS_OPTIONS',None)
        try:
            result=subprocess.run(command,capture_output=True,text=True,errors='replace',timeout=TIMEOUT,
                                  env=env,creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
        except subprocess.TimeoutExpired as error:
            raise ValueError('EPS conversion took too long. Re-export the artwork as a simpler EPS or PNG/TIFF.') from error
        except OSError as error:
            raise ValueError('The EPS conversion helper could not start. Reinstall Ghostscript and try again.') from error
        if result.returncode or not _valid_png(rendered,limited=False):
            raise ValueError('This EPS could not be converted to a visible logo. Check that its fonts and linked artwork are embedded, or export a PNG/TIFF.')
        with Image.open(rendered) as image:
            image.thumbnail((MAX_EDGE,MAX_EDGE),Image.Resampling.LANCZOS)
            payload=io.BytesIO();image.save(payload,format='PNG')
        # Only publish complete assets. Failed conversions never replace a cached logo.
        _atomic(original,data)
        _atomic(output,payload.getvalue())
        _atomic(folder/'conversion.json',json.dumps(dict(original_name=path.name,
                source_sha256=hashlib.sha256(data).hexdigest(),max_edge=MAX_EDGE,dpi=dpi)).encode('utf-8'))
    return str(output)


def original_eps(path):
    path=Path(path)
    original=path.parent/'source.eps'
    return original if path.parent.parent.name=='eps' and original.is_file() else None

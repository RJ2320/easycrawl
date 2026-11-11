"""Local, reusable logo assets and a curated directory of official downloads.

No project artwork is uploaded. Assets are content-addressed and never replaced
or deleted by catalog changes, so saved projects keep their selected version.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import uuid
import zipfile

from PIL import Image
from .gsheets import _urlopen

MAX_DOWNLOAD = 64 * 1024 * 1024
MAX_IMAGE = 32 * 1024 * 1024
RASTER = {'.png', '.tif', '.tiff', '.jpg', '.jpeg', '.bmp', '.webp'}
PANAVISION = 'https://www.panavision.com/resources/logo-download'
CANON = 'https://www.usa.canon.com/pro/resources/download-official-canon-logo'


def _official(key, name, page, download, usage, tags):
    return dict(id=key, name=name, source=page, download=download, usage=usage,
                tags=tags, kind='official', checked='2026-11-03')


CATALOG = [
    _official('panavision', 'Panavision — Camera & Optics', PANAVISION,
        'https://www.panavision.com/docs/default-source/logo-downloads/panavision-logo-%28camera-optics%29.zip?Status=Master&sfvrsn=df30f662_5',
        'For productions serviced by Panavision Camera & Optics or Grip & Remote Systems. Check the official source for current usage requirements.', 'camera lenses rental'),
    _official('panavision-dxl', 'Panavision — Millennium DXL', PANAVISION,
        'https://www.panavision.com/docs/default-source/logo-downloads/panavision-millennium-dxl---credit-logo.zip?Status=Master&sfvrsn=fcf7695d_5',
        'Only for productions shot with Millennium DXL or DXL2 cameras.', 'camera digital dxl2'),
    _official('panavision-anamorphic', 'Filmed in Panavision', PANAVISION,
        'https://www.panavision.com/docs/default-source/logo-downloads/panavision-logo-%28anamorphic%29.zip?Status=Master&sfvrsn=74295940_5',
        'Only for productions shot with Panavision anamorphic lenses.', 'camera lenses anamorphic'),
    _official('panalux', 'Panalux', PANAVISION,
        'https://www.panavision.com/docs/default-source/logo-downloads/panalux-logo.zip?Status=Master&sfvrsn=dd8829d2_9',
        'For productions supported by this division. See official source for usage and variants.', 'lighting rental'),
    _official('lee-filters', 'LEE Filters', PANAVISION,
        'https://www.panavision.com/docs/default-source/logo-downloads/lee-filters-logo.zip?Status=Master&sfvrsn=3aa8c3d3_5',
        'For productions using the corresponding products. See official source for usage.', 'camera lenses filters'),
    _official('canon', 'Canon — Monochrome', CANON,
        'https://downloads.canon.com/nw/camera/misc-pages/pro-portal/downloads/canon-monochrome.zip',
        'For productions captured using Canon cameras or lenses. No endorsement is implied. Review Canon brand guidelines before use.', 'camera lenses'),
    _official('canon-eos', 'Canon — Cinema EOS Monochrome', CANON,
        '',
        'Canon provides this variant as EPS artwork. Obtain it from the official source and import the EPS into My logos. For Cinema EOS productions; review Canon brand guidelines before use.', 'camera lenses cinema eos'),
    _official('tcs', 'TCS — White', 'https://tcsfilm.com/logos/',
        'https://tcsfilm.com/wp-content/uploads/2023/07/TCS_LOGO_WHITE.png',
        'For screen credits of productions supported with equipment rented from TCS.', 'camera lenses rental technological cinevideo services'),
    _official('kodak', 'KODAK Film', 'https://www.kodak.com/en/motion/page/end-credit-logos/', '',
        'For films captured or projected on KODAK Film. Download the appropriate official pack and follow its included guidelines, then import the still artwork here.', 'film stock lab'),
    _official('sag-aftra', 'SAG-AFTRA — Official brand center', 'https://www.sagaftra.org/brandcenter', '',
        'Request the production-approved artwork from SAG-AFTRA, then import it into My logos. The public brand center assets are intended for news media.', 'guild union actors performers'),
    _official('dolby', 'Dolby — Official brand assets', 'https://handbook.dolby.com/dsh/dolby-licensee-community/', '',
        'Obtain the appropriate artwork through Dolby’s official licensee resources, then import it here.', 'audio sound atmos vision'),
]


def default_root():
    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Application Support'
    else:
        base = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
    return base / 'EasyCrawl' / 'logo-library'


def _atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.library-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


class LogoLibrary:
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else default_root()
        self.index_path = self.root / 'index.json'
        self.data = {'personal': [], 'official': {}}
        if self.index_path.exists():
            try:
                data = json.loads(self.index_path.read_text(encoding='utf-8'))
                if not isinstance(data.get('personal'), list) or not isinstance(data.get('official'), dict):
                    raise ValueError('Invalid library index')
                self.data = data
            except (ValueError, TypeError) as error:
                raise ValueError('The logo library index could not be read. Your saved artwork has not been changed.') from error

    def save(self):
        _atomic(self.index_path, json.dumps(self.data, ensure_ascii=False, indent=2).encode('utf-8'))

    def asset_path(self, asset):
        path = (self.root / asset['path']).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError('Invalid library artwork path')
        return path

    def entries(self, query='', scope='all'):
        official = [dict(entry, assets=self.data['official'].get(entry['id'], [])) for entry in CATALOG]
        personal = [dict(entry, kind='personal', usage='Saved locally for reuse. Never uploaded by EasyCrawl.')
                    for entry in self.data['personal']]
        entries = official + personal if scope == 'all' else official if scope == 'official' else personal
        tokens = query.casefold().split()
        return [entry for entry in entries if all(token in (' '.join(str(entry.get(key,'')) for key in
                ('name','tags','usage'))).casefold() for token in tokens)]

    def store_image(self, data, name):
        if len(data) > MAX_IMAGE:
            raise ValueError('This logo image is too large (maximum 32 MB).')
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > 40_000_000:
                raise ValueError('This logo has too many pixels. Use an image below 40 megapixels.')
            image.load()
            image = image.convert('RGBA')
            output = io.BytesIO()
            image.save(output, format='PNG')
        payload = output.getvalue()
        digest = hashlib.sha256(payload).hexdigest()
        clean = re.sub(r'[^\w .()-]', '-', name).strip(' .')[:100] or 'Logo'
        asset = dict(name=name, path=f'assets/{digest}/{clean}.png', sha256=digest)
        path = self.asset_path(asset)
        if not path.exists():
            _atomic(path, payload)
        return asset

    def import_file(self, path, name=None, tags=''):
        from .logo_import import prepare_logo, original_eps
        path = Path(path)
        if path.stat().st_size > MAX_IMAGE:
            raise ValueError('This logo image is too large (maximum 32 MB).')
        prepared=Path(prepare_logo(path,root=self.root))
        original=original_eps(prepared)
        original_info=None
        if original:
            if not original.is_relative_to(self.root.resolve()):
                data=original.read_bytes()
                original=self.root.resolve()/'originals'/hashlib.sha256(data).hexdigest()/'source.eps'
                if not original.exists():
                    _atomic(original,data)
            original_info=dict(path=original.relative_to(self.root.resolve()).as_posix(),format='EPS')
        asset = self.store_image(prepared.read_bytes(), name or path.stem)
        existing = next((entry for entry in self.data['personal'] if entry['assets'][0]['sha256']==asset['sha256']), None)
        if existing:
            if original and 'original' not in existing:
                existing['original']=original_info
                self.save()
            return existing
        entry = dict(id='personal-'+uuid.uuid4().hex, name=name or path.stem, tags=tags,
                     assets=[asset], source='')
        if original:
            entry['original']=original_info
        self.data['personal'].append(entry)
        self.save()
        return entry

    def remove_personal(self, entry_id):
        self.data['personal'] = [entry for entry in self.data['personal'] if entry['id']!=entry_id]
        # Keep immutable image files: saved projects may still reference them.
        self.save()

    def fetch(self, entry_id, opener=None):
        import urllib.request
        entry = next(entry for entry in CATALOG if entry['id']==entry_id)
        if not entry['download']:
            raise ValueError('Open the official source to obtain this artwork, then import it into My logos.')
        request = urllib.request.Request(entry['download'], headers={'User-Agent':'EasyCrawl/LogoLibrary'})
        with (opener or _urlopen)(request, timeout=30) as response:
            data = response.read(MAX_DOWNLOAD+1)
        if len(data)>MAX_DOWNLOAD:
            raise ValueError('The official download exceeds 64 MB. Open the source page and import a still image instead.')
        images = []
        if zipfile.is_zipfile(io.BytesIO(data)):
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                candidates = [info for info in archive.infolist() if not info.is_dir()
                    and Path(info.filename).suffix.lower() in RASTER
                    and not info.filename.startswith('__MACOSX/') and not Path(info.filename).name.startswith('._')]
                if len(candidates)>100 or sum(info.file_size for info in candidates)>MAX_DOWNLOAD:
                    raise ValueError('This artwork pack is too large. Import an individual still image instead.')
                for info in candidates:
                    if info.file_size>MAX_IMAGE:
                        continue
                    images.append(self.store_image(archive.read(info), entry['name']+' — '+Path(info.filename).stem))
        else:
            images.append(self.store_image(data, entry['name']))
        if not images:
            raise ValueError('No supported still images were found. Open the official source and import a PNG, TIFF or JPEG version.')
        images.sort(key=lambda asset: ('white' not in asset['name'].lower(), asset['name'].lower()))
        self.data['official'][entry_id] = images
        self.save()
        return images

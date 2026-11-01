"""Generate the CleanTV add-on wallpapers from cleantv-wallpapers/images/.

Every original in images/ (JPG, PNG or WebP) becomes seven baseline JPEGs in
generated/<id>/ and one entry in index.json, which the CleanTV Samsung host
reads. Run it from anywhere:

    python cleantv-wallpapers/tools/generate.py

The material recipe is a port of scripts/build-materials.mjs in Psychnix/CleanTV
at commit d432730 (the Chromium canvas builder of the bundled wallpapers). Its
parameters are kept identical:

- the photo is cover-scaled to a centred 1920 x 1080 frame and padded by 96 px
  on each side with mirrored copies;
- field-blur: blur 28 px, saturation .92, JPEG quality 82;
  field-frost: blur 42 px, saturation .92, quality 82;
  field-clear: blur 2 px, saturation 1.06, quality 86;
- blur and frost soft-clip highlights in linear light: a luminance above .82 is
  compressed with slope .4;
- panel: the frost field scaled to 320 x 180, quality 85;
- study-soft: a lower scrim from y 560 (rgba(4,10,12) at 0, .42 at 70 % and .52
  at the bottom), blur 14 px and saturation 1.12, every pixel mixed 65/35 with
  the mean colour of the dock band (y 676-907, x 96-1823), then a tint
  rgba(4,10,12,t) with t = clamp((p95 - 94) / (p95 - 8.87), .28, .6) from the
  dock band luminance (y 720-907, x 112-1807, every fourth pixel), quality 94.
  This is the recipe build-materials.mjs uses for new photos; the fixed tints of
  the original nine are not needed here.

Canvas filters are approximated with Pillow: a CSS blur(N px) is a Gaussian with
standard deviation N, which Pillow's GaussianBlur(N) takes as its radius;
pixels outside the canvas are transparent, as in the canvas, and colours are
un-premultiplied before the alpha is set to opaque, as getImageData does. The
CSS saturate() matrix of the Filter Effects specification is applied in sRGB.
Skia's gradient dithering is not reproduced.

The background and thumbnail follow scripts/prepare-wallpapers.py for the newer
photos (centred crop with LANCZOS; background quality 90 with full chroma,
thumbnail 512 x 288 at quality 85), but every output is re-encoded without
EXIF, ICC or other metadata; an embedded ICC profile is converted to sRGB first.

The foreground metadata follows a rule derived from the fifteen bundled
wallpapers (catalog.js at d432730). Luminance is .2126 R + .7152 G + .0722 B on
the encoded 0-255 values of the generated background:

- ut.tr (x 1300-1919, y 0-223) and ut.br (x 1180-1919, y 760-999): "dark" when
  the zone mean is at least 235, "light" when its 90th percentile is below 112,
  otherwise "mist". This reproduces all fifteen curated values.
- tone: "light" when the median of the whole frame is at least 100, otherwise
  "dark". It matches the six newer photos; the original nine were labelled by
  hand, and the rule gives heavier scrims to bright photos than some of them.
- frostVeil from the 90th percentile of the frost field's dock band (y 676-907,
  x 96-1823): .44 from 178, .30 from 165, otherwise .20. New photos never get
  the lightest veil .12, which only reviewed originals keep.
- listColumn (x 0-1039, y 220-999): 3 for a light tone, 2 for a dark tone when
  the mean is at least 110 or the 90th percentile at least 180, otherwise 0.
- dockQuiet: the dock band (y 676-907, x 96-1823) has a mean of at least 122
  and a 90th percentile below 205. This reproduces all fifteen values.
- clockMist: the clock zone (x 100-699, y 40-229) has a 90th percentile of at
  least 170. Add-on photos have no adaptive ink, so a bright clock zone always
  gets the mist.

The output is deterministic for one set of pinned tool versions: the same
images give the same bytes. Removing an image removes its folder and entry.
"""
import argparse
import hashlib
import io
import json
import math
import re
import shutil
import sys
import unicodedata
from pathlib import Path

import numpy as np
from PIL import Image, ImageCms, ImageFilter, ImageOps

TOOLS = Path(__file__).resolve().parent
DEFAULT_ROOT = TOOLS.parent
# Paths in index.json are relative to the repository root, where the TV fetches them.
PREFIX = 'cleantv-wallpapers/'
EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
FORMATS = {'JPEG', 'PNG', 'WEBP'}
IGNORED = {'readme.md'}
MAX_BYTES = 30 * 1024 * 1024
MAX_ENTRIES = 200
INDEX_LIMIT = 262144
TITLE_LIMIT = 120
W, H, P = 1920, 1080, 96
# Role -> file name inside generated/<id>/. The TV and validate.py require exactly these paths.
FILES = {'jpg': 'image.jpg', 'thumb': 'thumb.jpg', 'panel': 'panel.jpg', 'study-soft': 'study-soft.jpg',
         'field-blur': 'field-blur.jpg', 'field-frost': 'field-frost.jpg', 'field-clear': 'field-clear.jpg'}
ID = re.compile(r'^aw-[a-z0-9]+(?:-[a-z0-9]+)*$')
FOLD = {'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss', 'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue', 'ẞ': 'SS'}


class GenerateError(Exception):
    def __init__(self, message, file=None):
        super().__init__(message)
        self.file = file


def annotate(kind, message, file=None):
    """GitHub Actions annotation; locally it is a readable line too."""
    location = ' file=' + file if file else ''
    print(f'::{kind}{location}::{message}', flush=True)


# ---------- Names ----------
def title_of(path):
    text = unicodedata.normalize('NFC', path.stem)
    return re.sub(r'\s+', ' ', re.sub(r'[_-]', ' ', text)).strip()


def slug_of(title):
    text = ''.join(FOLD.get(c, c) for c in title)
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').lower()
    return re.sub(r'[^a-z0-9]+', '-', text).strip('-') or 'image'


def assign_id(slug, used):
    def make(suffix):
        return 'aw-' + slug[:40 - 3 - len(suffix)].rstrip('-') + suffix
    candidate, n = make(''), 2
    while candidate in used:
        candidate, n = make('-' + str(n)), n + 1
    used.add(candidate)
    return candidate


def units(text):
    return len(text.encode('utf-16-le', 'surrogatepass')) // 2


# ---------- Decoding ----------
def originals(images):
    files = []
    for path in sorted(images.iterdir(), key=lambda p: p.name) if images.is_dir() else []:
        if path.name.startswith('.') or path.name.lower() in IGNORED:
            continue
        label = PREFIX + 'images/' + path.name
        if path.is_dir():
            raise GenerateError(f'{path.name}: folders are not read; put images directly into images/.', label)
        if path.suffix.lower() not in EXTENSIONS:
            raise GenerateError(f'{path.name}: unsupported file type; use JPG, PNG or WebP.', label)
        files.append(path)
    return files


def decode(path, label):
    size = path.stat().st_size
    if size > MAX_BYTES:
        raise GenerateError(f'{path.name}: {size} bytes is over the 30 MB limit; export a smaller JPG.', label)
    data = path.read_bytes()
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in FORMATS:
                raise GenerateError(f'{path.name}: the file is {image.format}, not JPG, PNG or WebP.', label)
            image.load()
            exif = image.getexif()
            gps = bool(exif.get_ifd(0x8825)) if 0x8825 in exif else False
            icc = image.info.get('icc_profile')
            image = ImageOps.exif_transpose(image)
            image.load()
    except GenerateError:
        raise
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise GenerateError(f'{path.name}: the image cannot be decoded ({error.__class__.__name__}).', label)
    return image, icc, gps


def to_srgb(image, icc, label):
    """Flatten transparency onto black, as the canvas JPEG encoder does, and convert to sRGB."""
    if image.mode in ('P', 'PA', 'LA', 'La', 'RGBa') or (image.mode == 'L' and 'transparency' in image.info):
        image = image.convert('RGBA')
    if image.mode == 'RGBA':
        ground = Image.new('RGB', image.size, (0, 0, 0))
        ground.paste(image, mask=image.getchannel('A'))
        image = ground
    if image.mode in ('I;16', 'I;16L', 'I;16B', 'I;16N', 'I'):
        # A 16-bit grey PNG (I;16 since Pillow 10, I before): round(v / 257) to 8 bit. convert('RGB')
        # would clip every value above 255, so the photo would become white.
        values = np.clip(np.asarray(image).astype(np.int64), 0, 65535)
        image = Image.fromarray(((values + 128) // 257).astype(np.uint8))
    if image.mode in ('1', 'YCbCr'):
        image = image.convert('RGB')
    if image.mode not in ('RGB', 'CMYK', 'L'):
        name = (label or '').rsplit('/', 1)[-1]
        raise GenerateError(f'{name}: the colour mode {image.mode} is not supported; export an 8-bit JPG or PNG.', label)
    if icc:
        try:
            source = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            image = ImageCms.profileToProfile(image, source, ImageCms.createProfile('sRGB'), outputMode='RGB')
        except (ImageCms.PyCMSError, OSError, ValueError):
            annotate('warning', 'The embedded colour profile could not be read; the colours are taken as sRGB.', label)
    image = image.convert('RGB')
    image.info = {}
    return image


def encode(pixels, quality, subsampling=2, size=None):
    image = Image.fromarray(pixels if pixels.dtype == np.uint8 else quantize(pixels))
    if size:
        image = image.resize(size, Image.Resampling.BILINEAR)
    image.info = {}
    out = io.BytesIO()
    image.save(out, 'JPEG', quality=quality, subsampling=subsampling, optimize=True, progressive=False, exif=b'')
    return out.getvalue()


def pixels(data):
    with Image.open(io.BytesIO(data)) as image:
        return np.asarray(image.convert('RGB'))


# ---------- Canvas emulation ----------
LINEAR = np.array([v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in (np.arange(256) / 255.0)])


def saturate(rgb, amount):
    s = amount
    matrix = np.array([[.213 + .787 * s, .715 - .715 * s, .072 - .072 * s],
                       [.213 - .213 * s, .715 + .285 * s, .072 - .072 * s],
                       [.213 - .213 * s, .715 - .715 * s, .072 + .928 * s]], dtype=np.float64)
    return np.clip(rgb @ matrix.T, 0, 255)


def blur(rgb, sigma):
    """A canvas drawImage with filter blur(sigma px): transparent outside the source, colours un-premultiplied."""
    margin = 3 * math.ceil(sigma) + 4
    h, w = rgb.shape[:2]
    colour = np.zeros((h + 2 * margin, w + 2 * margin, 3), np.uint8)
    colour[margin:margin + h, margin:margin + w] = rgb
    alpha = np.zeros((h + 2 * margin, w + 2 * margin), np.uint8)
    alpha[margin:margin + h, margin:margin + w] = 255
    c = np.asarray(Image.fromarray(colour).filter(ImageFilter.GaussianBlur(sigma)), np.float64)[margin:margin + h, margin:margin + w]
    a = np.asarray(Image.fromarray(alpha).filter(ImageFilter.GaussianBlur(sigma)), np.float64)[margin:margin + h, margin:margin + w]
    a = np.maximum(a, 1)[..., None]
    return np.clip(c * 255 / a, 0, 255)


def quantize(values):
    """Uint8ClampedArray rounding: nearest, ties to even."""
    return np.rint(np.clip(values, 0, 255)).astype(np.uint8)


def soft_clip(field):
    lin = LINEAR[field]
    lum = lin[..., 0] * .2126 + lin[..., 1] * .7152 + lin[..., 2] * .0722
    high = lum > .82
    ratio = np.ones_like(lum)
    ratio[high] = (.82 + .4 * (lum[high] - .82)) / lum[high]
    v = lin * ratio[..., None]
    encoded = 255 * np.where(v <= .0031308, 12.92 * v, 1.055 * np.power(np.maximum(v, 0), 1 / 2.4) - .055)
    out = field.copy()
    out[high] = quantize(encoded[high])
    return out


def materials(photo):
    files = {}
    padded = np.pad(photo, ((P, P), (P, P), (0, 0)), mode='symmetric')
    frost = None
    for suffix, sigma, saturation, quality in (('field-blur', 28, .92, 82), ('field-frost', 42, .92, 82), ('field-clear', 2, 1.06, 86)):
        field = quantize(saturate(blur(padded, sigma), saturation))[P:P + H, P:P + W]
        if suffix != 'field-clear':
            field = soft_clip(field)
        files[suffix] = encode(field, quality)
        if suffix == 'field-frost':
            frost = field
    files['panel'] = encode(frost, 85, size=(320, 180))

    # Soft: lower scrim, blur and a bounded tint selected from the dock band.
    y = np.arange(560, H, dtype=np.float64) + .5
    t = (y - 560) / (H - 560)
    a = np.where(t < .7, .42 * t / .7, .42 + .10 * (t - .7) / .3)[:, None, None]
    base = photo.astype(np.float64)
    base[560:] = base[560:] * (1 - a) + np.array([4, 10, 12], np.float64) * a
    soft = quantize(saturate(blur(quantize(base), 14), 1.12)).astype(np.float64)
    mean = soft[676:908, 96:1824].reshape(-1, 3).mean(axis=0)
    mixed = quantize(soft * .65 + mean * .35).astype(np.float64)
    sample = mixed[720:908:4, 112:1808:4]
    lumas = np.sort((sample[..., 0] * .2126 + sample[..., 1] * .7152 + sample[..., 2] * .0722).ravel())
    high = float(lumas[int(math.floor(len(lumas) * .95))])
    tint = .28 if high == 8.87 else max(.28, min(.6, (high - 94) / (high - 8.87)))
    files['study-soft'] = encode(quantize(mixed * (1 - tint) + np.array([4, 10, 12], np.float64) * tint), 94)
    return files


# ---------- Foreground metadata ----------
def luminance(rgb):
    rgb = rgb.astype(np.float64)
    return rgb[..., 0] * .2126 + rgb[..., 1] * .7152 + rgb[..., 2] * .0722


def zone(l, x0, y0, x1, y1):
    part = l[y0:y1, x0:x1]
    return float(part.mean()), float(np.percentile(part, 90))


def ink(l, box):
    mean, p90 = zone(l, *box)
    return 'dark' if mean >= 235 else 'light' if p90 < 112 else 'mist'


def metadata(photo, frost):
    l, f = luminance(photo), luminance(frost)
    tone = 'light' if float(np.median(l)) >= 100 else 'dark'
    veil = zone(f, 96, 676, 1824, 908)[1]
    column = zone(l, 0, 220, 1040, 1000)
    dock = zone(l, 96, 676, 1824, 908)
    out = {'tone': tone, 'ut': {'tr': ink(l, (1300, 0, 1920, 224)), 'br': ink(l, (1180, 760, 1920, 1000))},
           'frostVeil': .44 if veil >= 178 else .3 if veil >= 165 else .2}
    if column[0] >= 110 or column[1] >= 180:
        out['listColumn'] = 3 if tone == 'light' else 2
    if dock[0] >= 122 and dock[1] < 205:
        out['dockQuiet'] = True
    if zone(l, 100, 40, 700, 230)[1] >= 170:
        out['clockMist'] = True
    return out


# ---------- One wallpaper ----------
def generate(path, label, wid, title):
    image, icc, gps = decode(path, label)
    if gps:
        annotate('warning', f'{path.name} carries a GPS position in its EXIF data. The original is public in this repository; '
                 'replace it with a copy without location data. The generated files carry no metadata.', label)
    image = to_srgb(image, icc, label)
    if image.width < image.height:
        annotate('warning', f'{path.name} is portrait; its centre is cropped to 16:9.', label)
    if image.width < W or image.height < H:
        annotate('warning', f'{path.name} is {image.width} x {image.height}; it is enlarged to fill 1920 x 1080.', label)
    background = ImageOps.fit(image, (W, H), Image.Resampling.LANCZOS, centering=(.5, .5))
    files = {}
    out = io.BytesIO()
    background.info = {}
    background.save(out, 'JPEG', quality=90, subsampling=0, optimize=True, progressive=False, exif=b'')
    files['jpg'] = out.getvalue()
    thumb = background.resize((512, 288), Image.Resampling.LANCZOS)
    thumb.info = {}
    out = io.BytesIO()
    thumb.save(out, 'JPEG', quality=85, subsampling=2, optimize=True, progressive=False, exif=b'')
    files['thumb'] = out.getvalue()
    # Materials and metadata use the encoded background, as the TV and build-materials.mjs see it.
    photo = pixels(files['jpg'])
    files.update(materials(photo))
    entry = {'id': wid, 'title': title}
    digests = {role: hashlib.sha256(files[role]).hexdigest() for role in FILES}
    entry['rev'] = digests['jpg'][:12]
    entry.update(metadata(photo, pixels(files['field-frost'])))
    entry['files'] = {role: {'path': PREFIX + 'generated/' + wid + '/' + FILES[role], 'size': len(files[role]), 'sha256': digests[role]} for role in FILES}
    return entry, files


def dump(index):
    lines = [json.dumps(entry, ensure_ascii=False, separators=(',', ':')) for entry in index['entries']]
    body = ',\n'.join(lines)
    return ('{"api":1,"entries":[' + ('\n' + body + '\n' if lines else '') + ']}\n').encode('utf-8')


def run(root):
    images, generated = root / 'images', root / 'generated'
    paths = originals(images)
    if len(paths) > MAX_ENTRIES:
        raise GenerateError(f'{len(paths)} images; the TV reads at most {MAX_ENTRIES}.')
    used, plan = set(), []
    for path in paths:
        label = PREFIX + 'images/' + path.name
        title = title_of(path)
        if not title:
            raise GenerateError(f'{path.name}: the file name gives an empty title.', label)
        if units(title) > TITLE_LIMIT:
            raise GenerateError(f'{path.name}: the title is longer than {TITLE_LIMIT} characters; shorten the file name.', label)
        plan.append((path, label, assign_id(slug_of(title), used), title))
    # Decode everything first, so a bad file changes nothing.
    for path, label, _, _ in plan:
        decode(path, label)
    entries, outputs = [], {}
    for path, label, wid, title in plan:
        entry, files = generate(path, label, wid, title)
        entries.append(entry)
        outputs[wid] = files
        print(f'{wid}: {title} ({sum(len(b) for b in files.values())} bytes)', flush=True)
    index = dump({'api': 1, 'entries': entries})
    if len(index) > INDEX_LIMIT:
        raise GenerateError(f'index.json would be {len(index)} bytes; the TV reads at most {INDEX_LIMIT}. Remove some images or shorten their names.')
    # Write: remove folders and files that no longer belong, then the new outputs, then the index.
    if generated.is_dir():
        for folder in generated.iterdir():
            if folder.name not in outputs:
                shutil.rmtree(folder) if folder.is_dir() else folder.unlink()
            elif folder.is_dir():
                for stray in folder.iterdir():
                    if stray.name not in FILES.values():
                        shutil.rmtree(stray) if stray.is_dir() else stray.unlink()
    for wid, files in outputs.items():
        folder = generated / wid
        folder.mkdir(parents=True, exist_ok=True)
        for role, data in files.items():
            target = folder / FILES[role]
            if not target.is_file() or target.read_bytes() != data:
                target.write_bytes(data)
    if generated.is_dir() and not any(generated.iterdir()):
        generated.rmdir()
    target = root / 'index.json'
    if not target.is_file() or target.read_bytes() != index:
        target.write_bytes(index)
    print(f'{len(entries)} wallpapers, index.json {len(index)} bytes.', flush=True)
    return entries


def main(argv=None):
    parser = argparse.ArgumentParser(description='Generate the CleanTV add-on wallpapers.')
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT, help='the cleantv-wallpapers folder (default: next to tools/)')
    args = parser.parse_args(argv)
    try:
        run(args.root.resolve())
    except GenerateError as error:
        annotate('error', str(error), error.file)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

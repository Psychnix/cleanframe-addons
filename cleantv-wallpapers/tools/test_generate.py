"""Tests for generate.py. Synthesises originals with Pillow in a temporary folder at runtime
(no sample photos are committed), runs the real generator twice and checks its outputs."""
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

TOOLS = Path(__file__).resolve().parent
GENERATOR = TOOLS / 'generate.py'
SCHEMA = TOOLS.parent / 'index.schema.json'
SIZES = {'image.jpg': (1920, 1080), 'thumb.jpg': (512, 288), 'panel.jpg': (320, 180), 'study-soft.jpg': (1920, 1080),
         'field-blur.jpg': (1920, 1080), 'field-frost.jpg': (1920, 1080), 'field-clear.jpg': (1920, 1080)}
ROLES = {'jpg': 'image.jpg', 'thumb': 'thumb.jpg', 'panel': 'panel.jpg', 'study-soft': 'study-soft.jpg',
         'field-blur': 'field-blur.jpg', 'field-frost': 'field-frost.jpg', 'field-clear': 'field-clear.jpg'}


def run(root):
    return subprocess.run([sys.executable, str(GENERATOR), '--root', str(root)], capture_output=True, text=True,
                          encoding='utf-8', errors='replace')


def snapshot(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file() and 'images' not in p.relative_to(root).parts}


def split(width, height, left, right):
    """Left half one colour, right half another, with a soft gradient so the materials have detail."""
    image = Image.new('RGB', (width, height), left)
    image.paste(Image.new('RGB', (width - width // 2, height), right), (width // 2, 0))
    for y in range(0, height, 40):
        image.paste(Image.new('RGB', (width, 4), (240, 240, 230)), (0, y))
    return image


class Generate(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cleantv-wallpapers-')
        self.root = Path(self.temp.name) / 'cleantv-wallpapers'
        self.images = self.root / 'images'
        self.images.mkdir(parents=True)
        (self.images / 'README.md').write_text('Drop images here.\n', encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def originals(self):
        # Red left, blue right, stored upside down with EXIF orientation 3 and a GPS position.
        exif = Image.Exif()
        exif[0x0112] = 3
        exif[0x8825] = {1: 'N', 2: (52.0, 31.0, 12.0), 3: 'E', 4: (13.0, 24.0, 0.0)}
        split(2400, 1600, (200, 30, 30), (30, 40, 210)).save(self.images / 'Grüße aus Köln.jpg', 'JPEG', quality=92, exif=exif.tobytes())
        # A small PNG with transparency, and a WebP whose title folds to the same ID.
        png = split(1600, 900, (240, 220, 180), (40, 60, 40)).convert('RGBA')
        png.putalpha(200)
        png.save(self.images / 'Berg_am-See.png', 'PNG')
        split(2000, 1125, (20, 20, 30), (90, 120, 160)).save(self.images / 'berg  am   see.webp', 'WEBP', quality=90)

    def index(self):
        return json.loads((self.root / 'index.json').read_bytes().decode('utf-8'))

    def test_outputs_are_complete_deterministic_and_follow_removal(self):
        self.originals()
        first = run(self.root)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        before = snapshot(self.root)
        second = run(self.root)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(snapshot(self.root), before, 'the same images must give the same bytes')

        index = self.index()
        self.assertEqual(index['api'], 1)
        entries = {entry['id']: entry for entry in index['entries']}
        self.assertEqual([entry['id'] for entry in index['entries']], ['aw-berg-am-see', 'aw-gruesse-aus-koeln', 'aw-berg-am-see-2'])
        self.assertEqual(entries['aw-berg-am-see']['title'], 'Berg am See')
        self.assertEqual(entries['aw-gruesse-aus-koeln']['title'], 'Grüße aus Köln')
        self.assertEqual(entries['aw-berg-am-see-2']['title'], 'berg am see')
        try:
            from jsonschema import Draft7Validator
        except ImportError:
            Draft7Validator = None
        if Draft7Validator:
            Draft7Validator(json.loads(SCHEMA.read_text(encoding='utf-8'))).validate(index)
        self.assertLessEqual(len((self.root / 'index.json').read_bytes()), 262144)

        for wid, entry in entries.items():
            self.assertEqual(set(entry['files']), set(ROLES))
            self.assertIn(entry['tone'], ('light', 'dark'))
            self.assertIn(entry['frostVeil'], (0.12, 0.2, 0.3, 0.36, 0.44))
            for role, name in ROLES.items():
                item = entry['files'][role]
                path = self.root.parent / item['path']
                self.assertEqual(item['path'], 'cleantv-wallpapers/generated/' + wid + '/' + name)
                data = path.read_bytes()
                self.assertEqual(item['size'], len(data))
                self.assertEqual(item['sha256'], hashlib.sha256(data).hexdigest())
                with Image.open(io.BytesIO(data)) as image:
                    self.assertEqual(image.format, 'JPEG')
                    self.assertEqual(image.size, SIZES[name], wid + '/' + name)
                    self.assertNotIn('progressive', image.info)
                    self.assertNotIn('icc_profile', image.info)
                    self.assertNotIn('exif', image.info)
                    self.assertEqual(len(image.getexif()), 0, 'outputs carry no metadata')
            self.assertEqual(entry['rev'], entry['files']['jpg']['sha256'][:12])
            self.assertEqual(sorted(p.name for p in (self.root / 'generated' / wid).iterdir()), sorted(ROLES.values()))

        # EXIF orientation 3 turned the original: blue is now on the left.
        with Image.open(self.root / 'generated' / 'aw-gruesse-aus-koeln' / 'image.jpg') as image:
            left, right = image.getpixel((200, 540)), image.getpixel((1720, 540))
        self.assertGreater(left[2], left[0])
        self.assertGreater(right[0], right[2])
        self.assertIn('::warning file=cleantv-wallpapers/images/Grüße aus Köln.jpg::', first.stdout)
        self.assertIn('GPS', first.stdout)
        self.assertIn('enlarged', first.stdout)  # the 1600 x 900 PNG

        # Removing an image removes its folder and entry; the others keep their bytes.
        (self.images / 'berg  am   see.webp').unlink()
        third = run(self.root)
        self.assertEqual(third.returncode, 0, third.stdout + third.stderr)
        self.assertEqual([entry['id'] for entry in self.index()['entries']], ['aw-berg-am-see', 'aw-gruesse-aus-koeln'])
        self.assertFalse((self.root / 'generated' / 'aw-berg-am-see-2').exists())
        kept = {k: v for k, v in before.items() if 'aw-berg-am-see-2' not in k and k != 'index.json'}
        self.assertEqual({k: v for k, v in snapshot(self.root).items() if k != 'index.json'}, kept)

    def test_bad_files_fail_clearly_and_change_nothing(self):
        split(1920, 1080, (90, 90, 90), (120, 120, 120)).save(self.images / 'Grau.jpg', 'JPEG')
        self.assertEqual(run(self.root).returncode, 0)
        before = snapshot(self.root)
        cases = [('kaputt.jpg', b'\xff\xd8 not really a JPEG', 'kaputt.jpg: the image cannot be decoded'),
                 ('notiz.txt', b'text', 'notiz.txt: unsupported file type; use JPG, PNG or WebP.'),
                 ('bild.gif', None, 'bild.gif: unsupported file type')]
        for name, data, message in cases:
            path = self.images / name
            if data is None:
                Image.new('RGB', (16, 9)).save(path, 'GIF')
            else:
                path.write_bytes(data)
            result = run(self.root)
            self.assertEqual(result.returncode, 1, name)
            self.assertIn('::error file=cleantv-wallpapers/images/' + name + '::', result.stdout)
            self.assertIn(message, result.stdout)
            self.assertEqual(snapshot(self.root), before, name + ' must not change the outputs')
            path.unlink()
        # Size is checked before decoding.
        large = self.images / 'gross.jpg'
        with large.open('wb') as handle:
            handle.truncate(30 * 1024 * 1024 + 1)
        result = run(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn('gross.jpg: 31457281 bytes is over the 30 MB limit', result.stdout)
        self.assertEqual(snapshot(self.root), before)

    def test_empty_folder_gives_an_empty_index(self):
        result = run(self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.root / 'index.json').read_bytes(), b'{"api":1,"entries":[]}\n')
        self.assertFalse((self.root / 'generated').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)

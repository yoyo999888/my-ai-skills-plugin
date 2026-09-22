"""Regression cases for opaque backgrounds, real alpha, and material intent."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

SCRIPT = Path(__file__).with_name("inspect_png_alpha.py")


class AlphaInspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="spine-alpha-test-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def run_scan(self, image, *args):
        result = subprocess.run([sys.executable, str(SCRIPT), str(image), *args], capture_output=True, text=True)
        return result.returncode, json.loads(result.stdout)

    def test_opaque_rgb_checkerboard_is_not_transparency(self):
        path = self.root / "checker.png"
        im = Image.new("RGB", (8, 8))
        im.putdata([(255, 255, 255) if (x + y) % 2 else (160, 160, 160) for y in range(8) for x in range(8)])
        im.save(path)
        code, report = self.run_scan(path, "--require-transparency")
        self.assertEqual(code, 1)
        self.assertEqual(report["files"][0]["fully_opaque_pixels"], 64)
        self.assertFalse(report["files"][0]["source_has_alpha"])

    def test_near_opaque_cutout_is_reported_without_rewriting(self):
        path = self.root / "ceramic.png"
        im = Image.new("RGBA", (8, 8), (200, 120, 80, 253))
        im.putpixel((0, 0), (0, 0, 0, 0)); im.save(path)
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        code, report = self.run_scan(path, "--require-transparency", "--require-clear-pixels")
        self.assertEqual(code, 0)
        self.assertTrue(report["files"][0]["near_opaque_without_fully_opaque"])
        code, report = self.run_scan(path, "--require-opaque-pixels")
        self.assertEqual(code, 1)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)

    def test_glass_is_not_failed_by_default(self):
        path = self.root / "glass.png"
        Image.new("RGBA", (8, 8), (50, 120, 220, 128)).save(path)
        code, report = self.run_scan(path, "--require-transparency")
        self.assertEqual(code, 0)
        self.assertEqual(report["files"][0]["partial_alpha_pixels"], 64)

    def test_palette_transparency_is_accepted(self):
        path = self.root / "palette.png"
        im = Image.new("P", (8, 8), 1)
        im.putpalette([0, 0, 0, 240, 140, 40] + [0] * 762)
        im.putpixel((0, 0), 0); im.save(path, transparency=0)
        code, report = self.run_scan(path, "--require-transparency", "--require-clear-pixels", "--require-opaque-pixels")
        self.assertEqual(code, 0)
        self.assertEqual(report["files"][0]["clear_pixels"], 1)
        self.assertEqual(report["files"][0]["fully_opaque_pixels"], 63)

    def test_corrupt_png_is_retained_as_failure(self):
        path = self.root / "broken.png"; path.write_bytes(b"not a PNG")
        code, report = self.run_scan(path)
        self.assertEqual(code, 1)
        self.assertEqual(report["summary"]["decoded"], 0)
        self.assertIn("decode_failed", report["files"][0]["issues"])


if __name__ == "__main__":
    unittest.main()

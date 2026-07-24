import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fbx_to_rbxm.py"
SPEC = importlib.util.spec_from_file_location("fbx_to_rbxm", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class HelpersTest(unittest.TestCase):
    def test_extract_asset_id_from_json(self):
        text = json.dumps({"response": {"assetId": "123456789"}})
        self.assertEqual(MODULE.extract_asset_id(text), "123456789")

    def test_extract_asset_id_from_uri(self):
        self.assertEqual(MODULE.extract_asset_id("rbxassetid://987654"), "987654")

    def test_extract_operation_id(self):
        self.assertEqual(
            MODULE.extract_operation_id(json.dumps({"path": "operations/abc-123"})),
            "abc-123",
        )

    def test_checkpoint_requires_digest_creator_and_recipe(self):
        settings = {"creatorId": "42", "creatorType": "group"}
        checkpoint = {
            "recipeVersion": MODULE.RECIPE_VERSION,
            "inputSha256": "abc",
            "creatorId": "42",
            "creatorType": "group",
            "assetId": "123",
            "uploadStatus": "uploaded",
        }
        self.assertTrue(MODULE.valid_checkpoint(checkpoint, "abc", settings))
        self.assertFalse(MODULE.valid_checkpoint(checkpoint, "changed", settings))

    def test_cloud_script_only_interpolates_numeric_asset_id(self):
        source = MODULE.cloud_script("123456")
        self.assertIn("local assetId = 123456", source)
        self.assertIn("SerializeInstancesAsync", source)
        self.assertIn("boundsSize", source)
        self.assertIn("meshParts", source)
        with self.assertRaises(ValueError):
            MODULE.cloud_script("1; error('injected')")

    def test_parse_size_requires_three_positive_numbers(self):
        self.assertEqual(MODULE.parse_size("1, 2.5,3"), [1.0, 2.5, 3.0])
        with self.assertRaises(MODULE.argparse.ArgumentTypeError):
            MODULE.parse_size("1,2")
        with self.assertRaises(MODULE.argparse.ArgumentTypeError):
            MODULE.parse_size("1,0,3")

    def test_expected_size_validation_is_unit_agnostic(self):
        summary = {"meshPartCount": 2, "boundsSize": [101.0, 49.5, 25.0]}
        passed = MODULE.validate_cloud_geometry(summary, [100.0, 50.0, 25.0], 0.02)
        failed = MODULE.validate_cloud_geometry(summary, [100.0, 40.0, 25.0], 0.02)
        self.assertEqual(passed["status"], "passed")
        self.assertEqual(failed["status"], "failed")

    def test_binary_atomic_write_keeps_rbxm_magic(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.rbxm"
            payload = MODULE.RBXM_MAGIC + b"test"
            MODULE.write_bytes_atomic(path, payload)
            self.assertEqual(path.read_bytes(), payload)

    def test_execute_writes_checkpoint_rbxm_and_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fbx = root / "arbitrary source.fbx"
            output = root / "result.rbxm"
            fbx.write_bytes(b"mock-fbx")
            settings = {
                "apiKey": "not-written-to-output",
                "creatorId": "42",
                "creatorType": "group",
                "universeId": "100",
                "placeId": "200",
                "configPath": "",
            }
            summary = {
                "status": "loaded",
                "modelAssetId": "123456",
                "meshPartCount": 2,
                "boundsSize": [10.0, 20.0, 30.0],
                "meshParts": [
                    {"name": "A", "size": [10.0, 20.0, 30.0], "position": [0.0, 0.0, 0.0]}
                ],
            }
            argv = [
                str(SCRIPT),
                str(fbx),
                "--output",
                str(output),
                "--expected-size",
                "10,20,30",
                "--execute",
            ]
            with (
                mock.patch.object(MODULE.sys, "argv", argv),
                mock.patch.object(MODULE, "load_settings", return_value=settings),
                mock.patch.object(MODULE, "upload_fbx", return_value="123456"),
                mock.patch.object(
                    MODULE,
                    "run_cloud_serialization",
                    return_value=(MODULE.RBXM_MAGIC + b"payload", summary, "tasks/abc"),
                ),
            ):
                self.assertEqual(MODULE.main(), 0)
            checkpoint = json.loads(Path(str(output) + ".upload.json").read_text())
            report = json.loads(Path(str(output) + ".report.json").read_text())
            self.assertEqual(checkpoint["assetId"], "123456")
            self.assertEqual(report["status"], "complete")
            self.assertEqual(report["geometryValidation"]["status"], "passed")
            self.assertNotIn("apiKey", report)
            self.assertTrue(output.read_bytes().startswith(MODULE.RBXM_MAGIC))

    def test_execute_fails_when_cloud_bounds_exceed_tolerance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fbx = root / "model.fbx"
            output = root / "model.rbxm"
            fbx.write_bytes(b"mock-fbx")
            settings = {
                "apiKey": "secret",
                "creatorId": "42",
                "creatorType": "group",
                "universeId": "100",
                "placeId": "200",
                "configPath": "",
            }
            summary = {
                "status": "loaded",
                "modelAssetId": "123456",
                "meshPartCount": 1,
                "boundsSize": [100.0, 20.0, 30.0],
                "meshParts": [],
            }
            argv = [
                str(SCRIPT),
                str(fbx),
                "--output",
                str(output),
                "--expected-size",
                "10,20,30",
                "--execute",
            ]
            with (
                mock.patch.object(MODULE.sys, "argv", argv),
                mock.patch.object(MODULE, "load_settings", return_value=settings),
                mock.patch.object(MODULE, "upload_fbx", return_value="123456"),
                mock.patch.object(
                    MODULE,
                    "run_cloud_serialization",
                    return_value=(MODULE.RBXM_MAGIC + b"payload", summary, "tasks/abc"),
                ),
            ):
                self.assertEqual(MODULE.main(), 1)
            report = json.loads(Path(str(output) + ".report.json").read_text())
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["geometryValidation"]["status"], "failed")
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()

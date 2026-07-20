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
        with self.assertRaises(ValueError):
            MODULE.cloud_script("1; error('injected')")

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
            }
            argv = [str(SCRIPT), str(fbx), "--output", str(output), "--execute"]
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
            self.assertNotIn("apiKey", report)
            self.assertTrue(output.read_bytes().startswith(MODULE.RBXM_MAGIC))


if __name__ == "__main__":
    unittest.main()

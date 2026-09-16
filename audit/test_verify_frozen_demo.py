import json
import tempfile
import unittest
from pathlib import Path

from audit.verify_frozen_demo import git_blob_sha, verify


class FrozenDemoAuditTests(unittest.TestCase):
    def make_fixture(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        config_path = root / "cloud/config/crypto_24h_demo_v1.json"
        config_path.parent.mkdir(parents=True)
        config = {
            "strategy_id": "CRYPTO_24H_DEMO_V1",
            "status": "SHADOW_PAPER_FROZEN",
            "immutable_for_demo": True,
            "execution_enabled": False,
            "paper_positions_enabled": True,
            "real_trading_enabled": False,
            "decision_cadence": "every_closed_hour",
            "demo_duration_days": 90,
            "configured_asset_classes": ["crypto"],
        }
        config_path.write_text(json.dumps(config), encoding="utf-8")
        worker_path = root / "cloud/worker.py"
        worker_path.write_text("# frozen worker\n", encoding="utf-8")
        manifest = {
            "protected_git_blobs": {
                "cloud/config/crypto_24h_demo_v1.json": git_blob_sha(config_path.read_bytes()),
                "cloud/worker.py": git_blob_sha(worker_path.read_bytes()),
            },
            "required_config_assertions": config,
        }
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return temporary, root, manifest_path

    def test_unchanged_fixture_passes(self):
        temporary, root, manifest = self.make_fixture()
        self.addCleanup(temporary.cleanup)
        self.assertEqual(verify(root, manifest), [])

    def test_runtime_mutation_is_detected(self):
        temporary, root, manifest = self.make_fixture()
        self.addCleanup(temporary.cleanup)
        (root / "cloud/worker.py").write_text("# changed worker\n", encoding="utf-8")
        errors = verify(root, manifest)
        self.assertTrue(any("protected file changed: cloud/worker.py" in e for e in errors))

    def test_real_trading_toggle_is_detected(self):
        temporary, root, manifest = self.make_fixture()
        self.addCleanup(temporary.cleanup)
        path = root / "cloud/config/crypto_24h_demo_v1.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        config["real_trading_enabled"] = True
        path.write_text(json.dumps(config), encoding="utf-8")
        errors = verify(root, manifest)
        self.assertTrue(any("real_trading_enabled" in e for e in errors))


if __name__ == "__main__":
    unittest.main()

"""Unit tests for the inventory script. No Docker daemon is needed."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

FILE = Path(__file__).resolve().parents[1] / "inventory_noske.py"
SPEC = importlib.util.spec_from_file_location("inventory_noske", FILE)
inventory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory)


class InventoryTests(unittest.TestCase):
    def test_secret_environment_values_not_copied(self):
        keys, safe = inventory.environment([
            "SERVER_NAME=https://korpuss.lnb.lv/",
            "HTPASSWD=PRIVATE_DO_NOT_REPORT",
            "PRIVATE_KEY=PRIVATE_DO_NOT_REPORT",
            "CITATION_LINK=https://example.org/?token=private",
            "LANG=C.UTF-8",
        ])
        self.assertIn("HTPASSWD", keys)
        self.assertNotIn("HTPASSWD", safe)
        self.assertNotIn("PRIVATE_DO_NOT_REPORT", json.dumps(safe))
        self.assertEqual(safe["SERVER_NAME"], "https://korpuss.lnb.lv/")
        self.assertEqual(safe["CITATION_LINK"], "[set; value redacted]")

    def test_most_specific_mount_and_missing_paths(self):
        items = inventory.mounts_of([
            {"Type": "bind", "Source": "/srv/corpora", "Destination": "/corpora", "RW": True},
            {"Type": "volume", "Source": "/var/lib/docker/volumes/bonito",
             "Destination": "/var/lib/bonito", "RW": True},
        ])
        self.assertEqual(inventory.covering_mount("/corpora/registry", items)["source"],
                         "/srv/corpora")
        self.assertEqual(inventory.covering_mount("/var/lib/bonito/cache", items)["type"],
                         "volume")
        self.assertIsNone(inventory.covering_mount("/var/www", items))

    def test_corpus_root_shallow_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "registry").mkdir()
            (root / "sample" / "vertical").mkdir(parents=True)
            (root / "sample" / "indexed").mkdir()
            report = inventory.corpora_info({
                "type": "bind", "source": tmp, "destination": "/corpora"
            })
            self.assertEqual(report["corpus_directory_count"], 1)
            self.assertTrue(report["sample_corpus_layouts"][0]["indexed_exists"])
            self.assertTrue(report["registry"]["exists"])

    def test_missing_mount(self):
        self.assertIn("No mount", inventory.corpora_info(None)["status"])


if __name__ == "__main__":
    unittest.main()

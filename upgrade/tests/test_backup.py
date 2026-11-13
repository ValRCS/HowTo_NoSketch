import importlib.util
import gzip
import json
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "backup" / "backup_noske.py"
spec = importlib.util.spec_from_file_location("backup_noske", MODULE)
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


class BackupTests(unittest.TestCase):
    def test_destination_rejects_inside_source_and_repo(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "deployment" / "corpora"
            source.mkdir(parents=True)
            for invalid in (source / "new", source.parent / "backup", backup.ROOT / "upgrade" / "backup" / "x"):
                with self.assertRaises(RuntimeError):
                    backup.validate_destination(invalid, source)

    def test_destination_rejects_existing_or_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "dep" / "corpora"
            source.mkdir(parents=True)
            dest = base / "target"
            dest.mkdir()
            with self.assertRaises(RuntimeError):
                backup.validate_destination(dest, source)
            alias = base / "alias"
            alias.symlink_to(dest, target_is_directory=True)
            with self.assertRaises(RuntimeError):
                backup.validate_destination(alias / "data", source)

    def test_inspect_rejects_nested_mount(self):
        mounts = [{"Destination": "/corpora", "Type": "bind", "Source": "/tmp"},
                  {"Destination": "/corpora/registry", "Type": "volume"}]
        obj = {"State": {"Running": True}, "Mounts": mounts, "Image": "sha256:abc"}
        with patch.object(backup, "docker_json", return_value=[obj]):
            with self.assertRaisesRegex(RuntimeError, "Nested"):
                backup.inspect(["docker"], "noske")

    def test_verify_detects_changed_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "artifacts").mkdir()
            (root / "private").mkdir()
            for name in ("container-inspect.json", "image-inspect.json", "docker-diff.txt"):
                (root / "private" / name).write_text("private")
            target = root / "artifacts" / "original-image.tar.gz"
            target.write_bytes(b"original")
            backup.save_manifest(root, {"state_complete": True, "corpora_complete": False,
                                        "archives": {target.name: {"bytes": 8, "sha256": backup.sha256(target)}}})
            with self.assertRaisesRegex(RuntimeError, "Mandatory"):
                backup.verify(root, False)
            for needed in ("bonito.tar.gz", "container-rootfs-export.tar.gz"):
                p = root / "artifacts" / needed
                p.write_bytes(b"test")
                m = backup.load_manifest(root)
                m["archives"][needed] = {"bytes": 4, "sha256": backup.sha256(p)}
                backup.save_manifest(root, m)
            backup.verify(root, False)
            target.write_bytes(b"modified")
            with self.assertRaisesRegex(RuntimeError, "Archive verification failed"):
                backup.verify(root, False)

    def test_archive_stream_is_complete_and_gzip_valid(self):
        with tempfile.TemporaryDirectory() as d:
            archive = Path(d) / "test.gz"
            backup.archive_stream(["python3", "-c", "import sys; sys.stdout.buffer.write(b'example')"], archive)
            with gzip.open(archive, "rb") as f:
                self.assertEqual(b"example", f.read())
            with self.assertRaisesRegex(RuntimeError, "Refusing to overwrite"):
                backup.archive_stream(["python3", "-c", "print(42)"], archive)

    def test_backup_requires_execute(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(2, backup.main(["backup", "--destination", str(Path(d)/"a")]))


if __name__ == "__main__":
    unittest.main()

import importlib.util
import io
import sys
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

    def test_corpus_rsync_enables_overall_progress(self):
        args = backup.corpus_rsync_args(Path("/source"), Path("/destination"))
        self.assertIn("--info=progress2", args)
        self.assertIn("--no-inc-recursive", args)
        self.assertIn("--partial", args)
        self.assertNotIn("--delete", args)
        self.assertEqual(["/source/", "/destination/"], args[-2:])

    def test_progress_is_mirrored_to_terminal_and_private_log(self):
        class Capture:
            def __init__(self):
                self.buffer = io.BytesIO()

            def isatty(self):
                return True

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "corpora-rsync.log"
            command = [sys.executable, "-c",
                       "import sys; sys.stdout.buffer.write(b'20%\\r100%\\n')"]
            capture = Capture()
            with patch.object(backup.sys, "stdout", capture):
                backup.log_rsync(command, path, show_progress=True)
            self.assertEqual(b"20%\r100%\n", capture.buffer.getvalue())
            self.assertEqual(capture.buffer.getvalue(), path.read_bytes())
            self.assertEqual(0o600, path.stat().st_mode & 0o777)

    def test_progress_stream_fails_on_child_error(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "corpora-rsync.log"
            command = [sys.executable, "-c", "import sys; sys.exit(5)"]
            with self.assertRaisesRegex(RuntimeError, "exit 5"):
                backup.log_rsync(command, log, show_progress=True)


if __name__ == "__main__":
    unittest.main()

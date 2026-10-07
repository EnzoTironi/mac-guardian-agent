import errno
import importlib.util
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("guardian_volumes", Path(__file__).parents[1] / "native/mac_guardian.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class VolumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve() / "home"
        self.home.mkdir()
        self.g = m.Guardian(self.home)
        self.busy = patch.object(m, "in_use", return_value=False)
        self.busy.start()
        self.addCleanup(self.busy.stop)

    def file(self, relative, content=b"personal file"):
        path = self.home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        os.utime(path, (time.time() - 3 * m.DAY,) * 2)
        return path

    def foreign_volume(self, root):
        original = Path.stat
        def stat(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            if path == root or path.is_relative_to(root):
                values = list(result)
                values[2] += 1
                return os.stat_result(values)
            return result
        return patch.object(Path, "stat", stat)

    def test_foreign_volume_and_orbstack_are_preserved_while_local_files_move(self):
        external = self.file("Mounted/notes.pdf")
        app = self.file("OrbStack/README.txt", b"app-managed file")
        local = self.file("Downloads/report.pdf")
        with self.foreign_volume(external.parent):
            result = self.g.organize(True)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(external.read_bytes(), b"personal file")
        self.assertEqual(app.read_bytes(), b"app-managed file")
        self.assertFalse(local.exists())
        self.g.undo(result["transaction"])
        self.assertEqual(local.read_bytes(), b"personal file")

    def test_a_file_mounted_inside_local_downloads_is_not_moved(self):
        external = self.file("Downloads/mounted.pdf")
        local = self.file("Downloads/report.pdf")
        with self.foreign_volume(external):
            result = self.g.organize(True)
        self.assertEqual(len(result["items"]), 1)
        self.assertTrue(external.exists())
        self.assertFalse(local.exists())

    def test_cross_device_race_keeps_original_and_does_not_abort_remaining_moves(self):
        external = self.file("Downloads/aaa-mounted.pdf")
        local = self.file("Downloads/zzz-local.pdf")
        link = os.link
        def changed_volume(source, destination, **kwargs):
            if source == external:
                raise OSError(errno.EXDEV, "fixture volume changed")
            return link(source, destination, **kwargs)
        with patch.object(m.os, "link", changed_volume):
            result = self.g.organize(True)
        self.assertEqual([item["source"] for item in result["items"]], [str(local)])
        self.assertEqual(external.read_bytes(), b"personal file")
        self.g.undo(result["transaction"])
        self.assertEqual(local.read_bytes(), b"personal file")

    def test_discovered_project_on_a_new_foreign_volume_is_not_snapshotted(self):
        project = self.file("Mounted/app/package.json", b'{}').parent
        self.assertIn(project, list(self.g.projects()))
        reopened = m.Guardian(self.home)
        with self.foreign_volume(self.home / "Mounted"):
            self.assertNotIn(project, list(reopened.projects()))

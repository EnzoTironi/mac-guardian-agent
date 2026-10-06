import importlib.util
import contextlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("guardian", Path(__file__).parents[1] / "native/mac_guardian.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class GuardianTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        self.g = m.Guardian(self.home, self.root / "state")

    def old(self, path, days=45):
        for p in [*path.rglob("*"), path]:
            if not p.is_symlink():
                os.utime(p, (time.time() - days * m.DAY,) * 2)

    def cache(self):
        p = self.home / ".npm/_npx/old-job"
        p.mkdir(parents=True)
        (p / "reinstallable.txt").write_text("discardable data")
        self.old(p)
        return p

    def test_only_planned_old_cache_is_quarantined_and_restorable(self):
        old = self.cache()
        fresh = old.parent / "new-job"
        fresh.mkdir()
        (fresh / "busy.txt").write_text("recent data")
        plan = self.g.cleanup_plan()
        self.assertEqual([i["path"] for i in plan["items"]], [str(old.relative_to(self.home))])
        with patch.object(m, "in_use", return_value=False):
            result = self.g.clean(True)
        self.assertFalse(old.exists())
        self.assertTrue(fresh.exists())
        self.assertEqual(result["deleted_bytes"], 0)
        self.assertEqual(result["freed_bytes"], 0)
        self.assertGreater(result["quarantined_bytes"], 0)
        with patch.object(m, "in_use", return_value=False):
            self.g.restore_quarantine(result["items"][0]["receipt"])
        self.assertEqual((old / "reinstallable.txt").read_text(), "discardable data")

    def test_recently_changed_file_cancels_planned_deletion(self):
        old = self.cache()
        self.g.cleanup_plan()
        (old / "reinstallable.txt").write_text("newly changed")
        with patch.object(m, "in_use", return_value=False):
            result = self.g.clean(True)
        self.assertTrue(old.exists())
        self.assertFalse(result["items"][0]["removed"])

    def test_open_file_cancels_deletion(self):
        old = self.cache()
        self.g.cleanup_plan()
        with patch.object(m, "in_use", return_value=True):
            self.g.clean(True)
        self.assertTrue(old.exists())

    def test_same_size_rewrite_with_restored_mtime_cancels_deletion(self):
        old = self.cache()
        file = old / "reinstallable.txt"
        stamp = file.stat().st_mtime
        self.g.cleanup_plan()
        file.write_text("X" * file.stat().st_size)
        os.utime(file, (stamp, stamp))
        with patch.object(m, "in_use", return_value=False):
            result = self.g.clean(True)
        self.assertTrue(file.exists())
        self.assertFalse(result["items"][0]["removed"])

    def test_symlink_cannot_escape_cleanup(self):
        old = self.cache()
        outside = self.root / "precious"
        outside.mkdir()
        (outside / "keep").write_text("keep")
        link = old.parent / "linked"
        link.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.g.eligible(link, "cache")
        self.assertTrue((outside / "keep").exists())

    def test_managed_codex_artifacts_require_native_archive(self):
        p = self.home / ".codex/worktrees/a/project/node_modules"
        p.mkdir(parents=True)
        (p.parent / "package.json").write_text("{}")
        (p.parent / "package-lock.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "gerenciado"):
            self.g.eligible(p, "node_modules")

    def test_organization_is_reversible_and_never_overwrites(self):
        root = self.home / "Downloads"
        root.mkdir()
        source = root / "report.pdf"
        source.write_bytes(b"private document")
        os.utime(source, (time.time() - 14 * m.DAY,) * 2)
        with patch.object(m, "in_use", return_value=False):
            result = self.g.organize(True)
        dest = Path(result["items"][0]["destination"])
        self.assertTrue(dest.is_relative_to(self.home / "Wiki/Documentos"))
        self.assertFalse(source.exists())
        self.assertEqual(dest.read_bytes(), b"private document")
        self.g.undo(result["transaction"])
        self.assertEqual(source.read_bytes(), b"private document")
        dest.write_bytes(b"existing")
        with patch.object(m, "in_use", return_value=False):
            duplicate = self.g.organize(True)
        self.assertEqual(dest.read_bytes(), b"existing")
        self.assertEqual(Path(duplicate["items"][0]["destination"]).read_bytes(), b"private document")

    def test_secret_names_and_contents_block_backup(self):
        source = self.home / "Archive"
        source.mkdir()
        self.g.policy["backup_roots"] = ["Archive"]
        env = source / ".env.production"
        env.write_text("KEY=private")
        with self.assertRaises(ValueError):
            self.g.backup_manifest(source)
        env.unlink()
        (source / "notes.txt").write_text("ghp_" + "a" * 36)
        with self.assertRaises(ValueError):
            self.g.backup_manifest(source)

    def test_bad_application_plist_does_not_abort_other_apps(self):
        root = self.home / "Applications"
        bad = root / "Broken.app/Contents"
        good = root / "Working.app/Contents"
        bad.mkdir(parents=True)
        good.mkdir(parents=True)
        (bad / "Info.plist").write_text("<plist><broken &></plist>")
        import plistlib
        (good / "Info.plist").write_bytes(plistlib.dumps({"CFBundleShortVersionString": "1.0"}))
        with patch.object(m, "signature", return_value={"verified": None}):
            apps = self.g.applications([root])
        self.assertEqual(len(apps), 2)
        self.assertTrue(apps[0]["inventory_error"])
        self.assertEqual(apps[1]["version"], "1.0")

    def test_expired_plan_cannot_delete(self):
        old = self.cache()
        plan = self.g.cleanup_plan()
        plan["created_at"] = "2020-01-01T00:00:00+00:00"
        m.write_json(self.g.state / "cleanup-plan.json", plan)
        with self.assertRaisesRegex(ValueError, "plan"):
            self.g.clean(True)
        self.assertTrue(old.exists())

    def test_dirty_project_dependencies_are_preserved(self):
        root = self.home / "Code/project"
        root.mkdir(parents=True)
        self.git(["init", str(root)])
        (root / "package.json").write_text("{}")
        (root / "package-lock.json").write_text("{}")
        (root / ".gitignore").write_text("node_modules/\n")
        self.git(["-C", str(root), "add", "."])
        self.git(["-C", str(root), "commit", "-m", "project"])
        modules = root / "node_modules"
        modules.mkdir()
        (modules / "installed.js").write_text("dependency")
        self.old(modules)
        (root / "package.json").write_text('{"changed": true}')
        with self.assertRaisesRegex(ValueError, "alterações"):
            self.g.eligible(modules, "node_modules")
        self.assertTrue(modules.exists())

    def prepare_remote(self):
        source = self.home / "Archive"
        source.mkdir()
        (source / "one.txt").write_text("relevant notes")
        self.g.policy["backup_roots"] = ["Archive"]
        remote = self.root / "remote.git"
        seed = self.root / "seed"
        self.git(["init", "--bare", "--initial-branch=main", str(remote)])
        self.git(["init", "--initial-branch=main", str(seed)])
        (seed / "README.md").write_text("private backups")
        self.git(["-C", str(seed), "add", "."])
        self.git(["-C", str(seed), "commit", "-m", "initial"])
        self.git(["-C", str(seed), "remote", "add", "origin", str(remote)])
        self.git(["-C", str(seed), "push", "-u", "origin", "main"])
        return source, remote

    def git(self, args):
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def fake_require(self, remote, private=True, tamper=False):
        actual = m.require
        def invoke(argv, timeout=120):
            if argv[:3] == ["gh", "repo", "view"]:
                return json.dumps({"isPrivate": private, "url": "https://github.com/test/private"})
            if argv[:3] == ["gh", "repo", "clone"]:
                destination = Path(argv[4])
                result = actual(["git", "clone", str(remote), str(destination)], timeout)
                if tamper and destination.name == "restored":
                    next((destination / "snapshots").rglob("one.txt")).write_text("corrupted")
                return result
            if argv[0] == "git":
                argv = ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *argv[1:]]
            return actual(argv, timeout)
        return invoke

    def test_private_backup_roundtrip_precedes_offload(self):
        source, remote = self.prepare_remote()
        with patch.object(m, "require", side_effect=self.fake_require(remote)), \
             patch.object(m, "in_use", return_value=False):
            result = self.g.backup(source, "test/private", offload=True)
        self.assertTrue(result["restored_and_verified"])
        self.assertTrue(result["offloaded"])
        self.assertFalse(source.exists())
        verify = self.root / "check"
        self.git(["clone", str(remote), str(verify)])
        self.assertEqual(next(verify.rglob("one.txt")).read_text(), "relevant notes")

    def test_public_repo_cannot_receive_private_data(self):
        source, remote = self.prepare_remote()
        with patch.object(m, "require", side_effect=self.fake_require(remote, private=False)):
            with self.assertRaisesRegex(ValueError, "privado"):
                self.g.backup(source, "test/public", offload=True)
        self.assertTrue((source / "one.txt").exists())

    def test_corrupt_restore_preserves_local_original(self):
        source, remote = self.prepare_remote()
        with patch.object(m, "require", side_effect=self.fake_require(remote, tamper=True)):
            with self.assertRaisesRegex(ValueError, "divergiu"):
                self.g.backup(source, "test/private", offload=True)
        self.assertEqual((source / "one.txt").read_text(), "relevant notes")

    def prepare_worktree(self):
        _, remote = self.prepare_remote()
        seed = self.root / "seed"
        path = self.home / "Code/old-worktree"
        path.parent.mkdir(parents=True)
        self.git(["-C", str(seed), "worktree", "add", "-b", "old-worktree", str(path)])
        self.old(path)
        return seed, path

    @contextlib.contextmanager
    def workspace_remote(self):
        actual = self.g.git_run
        def git(project, args, **kwargs):
            args = [str(self.root / "remote.git") if a == "https://github.com/test/private.git" else a for a in args]
            return actual(project, args, **kwargs)
        def gh(argv, *args, **kwargs):
            if argv[:3] != ["gh", "repo", "view"]:
                raise AssertionError("Test attempted an unexpected external command")
            return {"ok": True, "stdout": '{"isPrivate":true}', "stderr": ""}
        with patch.object(self.g, "private_project_repo", return_value="test/private"), \
             patch.object(self.g, "_command", side_effect=gh), patch.object(self.g, "git_run", side_effect=git):
            yield

    def test_old_worktree_with_all_commits_remote_can_be_removed(self):
        seed, path = self.prepare_worktree()
        with self.workspace_remote(), patch.object(m, "in_use", return_value=False):
            result = self.g.remove_worktree(path, apply=True)
        self.assertTrue(result["removed"])
        self.assertFalse(path.exists())
        self.assertTrue((seed / "README.md").exists())

    def test_ignored_personal_data_is_restored_from_local_worktree_archive(self):
        seed, path = self.prepare_worktree()
        (seed / ".git/info/exclude").write_text(".env\n")
        (path / ".env").write_text("personal configuration")
        self.old(path)
        with self.workspace_remote(), patch.object(m, "in_use", return_value=False):
            result = self.g.remove_worktree(path, apply=True)
            self.assertFalse(path.exists())
            self.g.restore_worktree(result["receipt"])
        self.assertTrue((path / ".env").exists())

    def test_unpushed_worktree_commit_is_preserved(self):
        seed, path = self.prepare_worktree()
        (path / "README.md").write_text("work not yet pushed")
        self.git(["-C", str(path), "add", "."])
        self.git(["-C", str(path), "commit", "-m", "unpublished"])
        self.old(path)
        with self.workspace_remote(), patch.object(m, "in_use", return_value=False):
            result = self.g.remove_worktree(path, apply=True)
            self.g.restore_worktree(result["receipt"])
        self.assertTrue(path.exists())
        self.assertEqual((path / "README.md").read_text(), "work not yet pushed")


if __name__ == "__main__":
    unittest.main()

"""Behavior tests using real Git repositories and an isolated bare remote."""
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "native"))
import mac_guardian as m


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        self.g = m.Guardian(self.home, self.root / "state")
        self.remote = self.root / "remote.git"
        self.git(self.root, "init", "--bare", "--initial-branch=main", str(self.remote))

    def git(self, path, *args):
        return subprocess.check_output(["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
            "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "-C", str(path), *args],
            stderr=subprocess.PIPE)

    def personal(self, name, text="Example notes", days=45):
        path = self.home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        os.utime(path, (time.time() - days * 86400,) * 2)
        return path

    def project(self):
        path = self.home / "Projects/client/site"
        path.mkdir(parents=True)
        self.git(path, "init", "--initial-branch=main")
        (path / "README.md").write_text("# Client website\n")
        (path / ".gitignore").write_text(".env\nnode_modules/\n")
        self.git(path, "add", ".")
        self.git(path, "commit", "-m", "Initial")
        return path

    def worktree(self):
        main = self.project()
        path = self.home / "Projects/client/old-site"
        self.git(main, "worktree", "add", "-b", "draft", str(path))
        return main, path

    def old(self, path):
        stamp = time.time() - 45 * 86400
        for child in [*path.rglob("*"), path]:
            os.utime(child, (stamp, stamp), follow_symlinks=False)

    @contextlib.contextmanager
    def github(self, private=True, fail=False, mutate=None):
        actual = self.g.git_run
        def git(project, args, **kwargs):
            if fail and "push" in args:
                raise RuntimeError("Remote unavailable")
            args = [str(self.remote) if a == "https://github.com/test/private.git" else a for a in args]
            output = actual(project, args, **kwargs)
            if mutate and "clone" in args:
                mutate()
            return output
        def gh(argv, *args, **kwargs):
            if argv[:3] == ["gh", "repo", "view"]:
                return {"ok": True, "stdout": json.dumps({"isPrivate": private}), "stderr": ""}
            raise AssertionError("Unexpected external command in isolated test")
        with patch.object(self.g, "git_run", side_effect=git), patch.object(self.g, "_command", side_effect=gh), \
             patch.object(self.g, "private_project_repo", return_value="test/private"), \
             patch.object(m, "in_use", return_value=False):
            yield

    def test_snapshot_keeps_branch_index_and_unstaged_content(self):
        path = self.project()
        (path / "README.md").write_text("Staged draft")
        self.git(path, "add", "README.md")
        (path / "README.md").write_text("Working draft")
        (path / "new.txt").write_text("Untracked local work")
        (path / ".env").write_text("API_KEY=local-only-test-fixture")
        head = self.git(path, "rev-parse", "HEAD")
        index = (path / ".git/index").read_bytes()
        with self.github():
            result = self.g.project_snapshot(path, "test/private")
            repeated = self.g.project_snapshot(path, "test/private")
        self.assertTrue(result["verified"])
        self.assertEqual(result["commit"], repeated["commit"])
        self.assertEqual(self.git(path, "rev-parse", "HEAD"), head)
        self.assertEqual(self.git(path, "branch", "--show-current").strip(), b"main")
        self.assertEqual((path / ".git/index").read_bytes(), index)
        self.assertEqual(self.git(path, "show", ":README.md"), b"Staged draft")
        self.assertEqual((path / "README.md").read_text(), "Working draft")
        self.assertEqual(self.git(self.remote, "show", result["branch"] + ":new.txt"), b"Untracked local work")
        self.assertNotIn(b".env", self.git(self.remote, "ls-tree", "-r", "--name-only", result["branch"]))
        secret = next((self.home / "Backup/MacGuardian/Secrets").rglob("content"))
        self.assertEqual(secret.read_bytes(), (path / ".env").read_bytes())
        self.assertEqual(secret.stat().st_mode & 0o777, 0o600)

    def test_historical_and_misnamed_secrets_never_enter_remote_history(self):
        path = self.project()
        fixture = "ghp_" + "x" * 36
        (path / "old-settings.txt").write_text(fixture)
        self.git(path, "add", ".")
        self.git(path, "commit", "-m", "Historical private settings")
        (path / "old-settings.txt").unlink()
        self.git(path, "add", "-u")
        self.git(path, "commit", "-m", "Remove settings")
        (path / "untracked-notes.txt").write_text("password=" + "z" * 20)
        with self.github():
            result = self.g.project_snapshot(path, "test/private")
        self.assertEqual(self.git(self.remote, "rev-list", "--count", result["branch"]).strip(), b"1")
        objects = self.git(self.remote, "rev-list", "--objects", "--all").splitlines()
        for line in objects:
            oid = line.split()[0].decode()
            if self.git(self.remote, "cat-file", "-t", oid).strip() == b"blob":
                data = self.git(self.remote, "cat-file", "blob", oid)
                self.assertNotIn(fixture.encode(), data)
                self.assertNotIn(b"z" * 20, data)

    def test_public_remote_is_rejected_before_upload(self):
        path = self.project()
        with self.github(private=False), self.assertRaisesRegex(ValueError, "privado"):
            self.g.project_snapshot(path, "test/private")
        self.assertEqual(self.git(self.remote, "for-each-ref").strip(), b"")

    def test_changed_source_after_remote_clone_blocks_verified_receipt(self):
        path = self.project()
        with self.github(mutate=lambda: (path / "README.md").write_text("Changed during backup")), \
             self.assertRaisesRegex(ValueError, "Origem mudou"):
            self.g.project_snapshot(path, "test/private")
        self.assertTrue(path.exists())
        self.assertFalse((self.g.state / "project-snapshots.json").exists())

    def test_failed_remote_preserves_worktree_and_copies_env_locally(self):
        _, path = self.worktree()
        (path / ".env").write_text("Private configuration")
        self.old(path)
        with self.github(fail=True), self.assertRaises(RuntimeError):
            self.g.remove_worktree(path, apply=True)
        self.assertTrue(path.exists())
        self.assertEqual(next((self.home / "Backup/MacGuardian/Secrets").rglob("content")).read_text(), "Private configuration")

    def test_archive_restores_staged_dirty_ignored_links_and_metadata(self):
        _, path = self.worktree()
        (path / "README.md").write_text("Staged draft")
        self.git(path, "add", "README.md")
        (path / "README.md").write_text("Working draft")
        (path / "notes.txt").write_text("Untracked notes")
        (path / ".env").write_text("Local only settings")
        (path / "empty").mkdir()
        (path / "notes-link").symlink_to("notes.txt")
        (path / "notes.txt").chmod(0o640)
        if hasattr(os, "setxattr"):
            os.setxattr(path / "notes.txt", "com.macguardian.test" if sys.platform == "darwin" else "user.macguardian", b"fixture metadata")
        self.old(path)
        before = self.g.tree_manifest(path, exclude_git=True)
        with self.github():
            snapshot = self.g.project_snapshot(path, "test/private")
            result = self.g.archive_worktree(path, snapshot)
            self.assertFalse(path.exists())
            restored = self.g.restore_worktree(result["receipt"])
        self.assertTrue(restored["verified"])
        self.assertEqual(self.g.tree_manifest(path, exclude_git=True), before)
        self.assertEqual(self.git(path, "show", ":README.md"), b"Staged draft")
        self.assertEqual(self.git(path, "branch", "--show-current").strip(), b"draft")
        self.assertEqual((path / ".env").read_text(), "Local only settings")

    def test_archive_recovers_history_when_original_repository_is_gone(self):
        main, path = self.worktree()
        (path / "README.md").write_text("Unpublished commit")
        self.git(path, "add", ".")
        self.git(path, "commit", "-m", "Unpublished")
        expected = self.git(path, "rev-parse", "HEAD")
        self.old(path)
        with self.github():
            result = self.g.remove_worktree(path, apply=True)
            shutil.rmtree(main)
            self.g.restore_worktree(result["receipt"])
        self.assertEqual(self.git(path, "rev-parse", "HEAD"), expected)
        self.assertEqual((path / "README.md").read_text(), "Unpublished commit")

    def test_corrupt_archive_cannot_restore_or_overwrite(self):
        _, path = self.worktree()
        self.old(path)
        with self.github():
            result = self.g.remove_worktree(path, apply=True)
            folder = self.g.receipt_path("Worktrees", result["receipt"]).parent
            (folder / "files.zip").write_bytes(b"corrupted")
            with self.assertRaisesRegex(ValueError, "alterado"):
                self.g.restore_worktree(result["receipt"])
        self.assertFalse(path.exists())

    def test_recent_and_locked_worktrees_are_preserved(self):
        main, path = self.worktree()
        with self.github():
            snapshot = self.g.project_snapshot(path, "test/private")
            with self.assertRaisesRegex(ValueError, "recente"):
                self.g.archive_worktree(path, snapshot)
            self.old(path)
            self.git(main, "worktree", "lock", str(path))
            with self.assertRaisesRegex(ValueError, "bloqueado"):
                self.g.archive_worktree(path, snapshot)
        self.assertTrue(path.exists())

    def test_cloud_choice_is_asked_once_and_local_only_is_persistent(self):
        self.assertTrue(self.g.cloud_status()["needs_question"])
        self.g.configure_cloud(asked=True)
        self.assertFalse(self.g.cloud_status()["needs_question"])
        self.assertTrue(self.g.cloud_status()["awaiting_answer"])
        self.g.configure_cloud("none")
        reopened = m.Guardian(self.home, self.g.state)
        self.assertEqual(reopened.cloud_status()["provider"], "none")
        self.assertFalse(reopened.cloud_status()["awaiting_answer"])

    def test_backup_root_cannot_be_redirected_to_cloud_or_symlink(self):
        self.g.policy["excluded_roots"] = []
        for root in ("Documents/Backup", "Library/CloudStorage/Drive/Backup", "Library/Mobile Documents/Backup"):
            self.g.policy["local_backup_root"] = root
            with self.assertRaises(ValueError):
                self.g.backup_folder()
        (self.home / "Backup").symlink_to(self.root / "elsewhere")
        self.g.policy["local_backup_root"] = "Backup/MacGuardian"
        with self.assertRaises(ValueError):
            self.g.backup_folder()

    def test_secret_backup_is_deduplicated_and_restores_without_overwrite(self):
        path = self.personal("Projects/.env", "Private configuration")
        self.g.local_secret_backup(path.parent, [path])
        self.g.local_secret_backup(path.parent, [path])
        copies = list((self.home / "Backup/MacGuardian/Secrets").rglob("content"))
        self.assertEqual(len(copies), 1)
        identity, version = copies[0].parent.parent.name, copies[0].parent.name
        with self.assertRaisesRegex(ValueError, "sobrescreveria"):
            self.g.restore_secret(identity, version)
        path.unlink()
        self.assertTrue(self.g.restore_secret(identity, version)["verified"])
        self.assertEqual(path.read_text(), "Private configuration")

    def test_purge_requires_exact_fresh_single_use_owner_approval(self):
        path = self.personal("OldCache/content.txt", "Recoverable cache").parent
        result = self.g.quarantine_tree(path, "cache")
        with self.assertRaisesRegex(ValueError, "autorização"), patch.object(m, "in_use", return_value=False):
            self.g.purge_quarantine(result["receipt"], apply=True)
        request = self.g.purge_quarantine(result["receipt"])
        self.g.approve(request["request_id"], "Owner: permanently delete this cache")
        with patch.object(m, "in_use", return_value=False):
            self.assertTrue(self.g.purge_quarantine(result["receipt"], True, request["request_id"])["purged"])
        self.assertFalse(self.g.consume_approval("purge_quarantine", {}, request["request_id"]))

    def test_content_change_invalidates_purge_approval_and_keeps_data(self):
        path = self.personal("OldCache/content.txt").parent
        result = self.g.quarantine_tree(path, "cache")
        request = self.g.purge_quarantine(result["receipt"])
        self.g.approve(request["request_id"], "Owner: permanently delete this cache")
        target = Path(result["destination"]) / "content.txt"
        target.write_text("New content")
        with patch.object(m, "in_use", return_value=False), self.assertRaisesRegex(ValueError, "autorização"):
            self.g.purge_quarantine(result["receipt"], True, request["request_id"])
        self.assertTrue(target.exists())

    def test_expired_approval_is_reported_and_can_be_renewed(self):
        request = self.g.request_approval("example", {"version": 1})
        self.g.approve(request["request_id"], "Owner: approve version 1")
        saved = m.read_json(self.g.state / "approvals.json")
        saved[0]["approved_at"] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)).isoformat()
        m.write_json(self.g.state / "approvals.json", saved)
        self.assertFalse(self.g.consume_approval("example", {"version": 1}))
        self.assertEqual(len(self.g.status()["pending_approvals"]), 1)
        self.g.request_approval("example", {"version": 1})
        self.g.approve(request["request_id"], "Owner: approve version 1 again")
        self.assertTrue(self.g.consume_approval("example", {"version": 1}))
        self.assertFalse(self.g.consume_approval("example", {"version": 1}))

    def test_nested_personal_files_use_content_topic_and_all_indexes(self):
        source = self.personal("Projects/Personal/Client/raw/untitled.md", "# Brand launch plan\n\nClient: Northstar\n\nNotes.")
        project = self.project()
        untouched = self.personal(str(project.relative_to(self.home) / "untitled.md"), "# Project source")
        with patch.object(m, "in_use", return_value=False):
            result = self.g.organize(True)
        expected = self.home / "Wiki/Documentos/northstar/brand-launch-plan.md"
        self.assertTrue(expected.exists())
        self.assertTrue(untouched.exists())
        self.assertIn("brand-launch-plan.md", (expected.parent / "_Index.md").read_text())
        self.assertIn("northstar/", (expected.parent.parent / "_Index.md").read_text())
        self.g.undo(result["transaction"])
        self.assertTrue(source.exists())

    def test_index_links_preserve_personal_indexes_and_nested_folder_navigation(self):
        personal = self.personal("Wiki/Documentos/_Index.md", "My personal index")
        self.personal("Wiki/Documentos/Client/Year/notes.txt")
        self.personal("Wiki/Home.md", "My personal home")
        self.personal("Wiki/Projects.md", "My project page")
        result = self.g.file_wiki()
        self.assertEqual(personal.read_text(), "My personal index")
        category = self.home / "Wiki/Documentos/_MacGuardian-1.md"
        self.assertIn("Client/_Index.md", category.read_text())
        self.assertIn("../_MacGuardian-1.md", (category.parent / "Client/_Index.md").read_text())
        self.assertIn("Year/_Index.md", (category.parent / "Client/_Index.md").read_text())
        self.assertIn("# Wiki pessoal", Path(result["home"]).read_text())
        root_generated = [p.read_text() for p in (self.home / "Wiki").glob("_MacGuardian-*.md")]
        self.assertTrue(any("# Projetos" in text for text in root_generated))
        self.assertTrue(any("# Wiki pessoal" in text for text in root_generated))

    def test_agent_classification_uses_hash_evidence_and_can_be_undone(self):
        path = self.personal("Family/reports/scan.txt", "A school timetable")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        with patch.object(m, "in_use", return_value=False):
            result = self.g.classify_file(path, "Documentos", "school", "school-timetable.txt", digest, "The content describes a school timetable")
        destination = self.home / "Wiki/Documentos/school/school-timetable.txt"
        self.assertTrue(destination.exists())
        self.g.undo(result["transaction"])
        self.assertTrue(path.exists())
        path.write_text("Changed")
        with self.assertRaisesRegex(ValueError, "alterado"):
            self.g.classify_file(path, "Documentos", "school", "school-timetable.txt", digest, "Previous analysis")

    def test_local_ref_cursor_reaches_every_branch_across_cycles(self):
        path = self.project()
        self.git(path, "branch", "draft-a")
        self.git(path, "branch", "draft-b")
        self.g.policy["max_project_refs_per_run"] = 1
        self.g.policy["auto_archive_worktrees"] = False
        with self.github(), patch.object(m.shutil, "which", return_value="/fixture/gh"):
            for _ in range(3):
                self.g.care_for_projects()
        saved = m.read_json(self.g.state / "project-snapshots.json")
        self.assertEqual({item["ref"] for item in saved.values() if item["ref"]},
                         {"refs/heads/main", "refs/heads/draft-a", "refs/heads/draft-b"})


    def test_project_without_git_is_saved_privately_without_initializing_source(self):
        path = self.home / "Apps/prototype"
        path.mkdir(parents=True)
        (path / "package.json").write_text('{"name":"prototype"}')
        (path / "index.js").write_text("console.log('prototype')")
        (path / ".gitignore").write_text(".envrc\nlocal-personal.txt\n")
        (path / "local-personal.txt").write_text("Ignored personal data")
        (path / ".envrc").write_text("export DEMO_TOKEN=local-test-fixture")
        with self.github(), patch.object(m.shutil, "which", return_value="/fixture/gh"):
            result = self.g.care_for_projects()
        self.assertEqual(result["verified"], 1)
        self.assertFalse((path / ".git").exists())
        snapshot = result["items"][0]["snapshot"]
        self.assertEqual(self.git(self.remote, "show", snapshot["branch"] + ":index.js"), b"console.log('prototype')")
        self.assertNotIn(b".envrc", self.git(self.remote, "ls-tree", "-r", "--name-only", snapshot["branch"]))
        self.assertNotIn(b"local-personal.txt", self.git(self.remote, "ls-tree", "-r", "--name-only", snapshot["branch"]))
        self.assertEqual(next((self.home / "Backup/MacGuardian/Secrets").rglob("content")).read_bytes(), (path / ".envrc").read_bytes())

    def test_app_and_virtual_machine_bundles_preserve_internal_files(self):
        files = [self.personal("Movies/Editing.fcpbundle/assets/clip.md"),
                 self.personal("VMs/Linux.utm/settings.txt"), self.personal("Music/Studio.logicx/notes.txt")]
        with patch.object(m, "in_use", return_value=False):
            self.assertEqual(self.g.organize(True)["items"], [])
        for path in files:
            self.assertTrue(path.exists())
            with self.assertRaisesRegex(ValueError, "preservam"):
                self.g.classify_file(path, "Documentos", "notes", "notes.txt", m.digest(path), "Example evidence")

    def test_project_discovery_resumes_after_directory_budget(self):
        for number in range(5):
            self.personal(f"Many/folder-{number}/project/pyproject.toml", "[project]\nname='example'\n")
        self.g.policy.update(project_roots=["Many"], max_scan_directories=2)
        m.write_json(self.g.state / "policy.json", self.g.policy)
        for _ in range(8):
            g = m.Guardian(self.home, self.g.state)
            found = list(g.projects())
        self.assertEqual(len(found), 5)

    def test_monorepo_packages_share_parent_snapshot_and_nested_git_stays_distinct(self):
        parent = self.project()
        self.personal(str(parent.relative_to(self.home) / "packages/ui/package.json"), "{}")
        nested = parent / "other-repo"
        nested.mkdir()
        self.git(nested, "init")
        self.assertEqual(set(self.g.projects()), {parent, nested})


if __name__ == "__main__":
    unittest.main()

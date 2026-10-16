"""The owner's files move, and code leaves the Mac, only after a preview and a yes."""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "native"))
import mac_guardian as m  # noqa: E402


class ConsentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.home = self.root / "home"
        for name in ("Downloads", "Desktop"):
            (self.home / name).mkdir(parents=True)
        self.g = m.Guardian(self.home, self.root / "state")

    def personal(self, name, data=b"personal document"):
        path = self.home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        os.utime(path, (time.time() - 3 * m.DAY,) * 2)
        return path

    def report(self):
        return {"at": m.now(), "full_checked_at": m.now(), "disk": {"free_bytes": 40 * m.GIB},
                "memory": {"swap_bytes": 0}, "load_average": [0, 0, 0], "alerts": []}

    def maintain(self):
        with patch.object(self.g, "check", return_value=self.report()), patch.object(m, "in_use", return_value=False), \
             patch.object(self.g, "package_updates", return_value={"items": [], "updated": 0}), \
             patch.object(self.g, "care_for_projects", return_value={"items": []}):
            return self.g.maintain()

    def test_new_installs_organize_downloads_and_desktop_only(self):
        self.assertEqual(m.DEFAULT_POLICY["organization_roots"], ["Downloads", "Desktop"])
        inbox = self.personal("Downloads/report.pdf")
        loose = self.personal("notes.md")
        pictures = self.personal("Pictures/holiday.jpg")
        preview = self.g.organize(False)
        self.assertEqual([i["source"] for i in preview["items"]], [str(inbox)])
        self.assertEqual(preview["summary"]["by_root"], {"Downloads": 1})
        self.assertEqual(preview["summary"]["by_category"], {"Documents": 1})
        self.assertTrue(loose.exists() and pictures.exists())

    def test_background_care_never_touches_files_without_consent(self):
        source = self.personal("Downloads/report.pdf")
        with patch.object(self.g, "organize") as organize, patch.object(self.g, "rename") as rename:
            result = self.maintain()
        organize.assert_not_called()
        rename.assert_not_called()
        self.assertTrue(source.exists())
        self.assertFalse(result["exception"])
        self.assertFalse({"organization", "naming", "cleanup"} & {s["name"] for s in result["stages"]})
        # Organization is offered when the owner asks, never computed in the background.
        self.assertFalse((self.g.state / "organization-plan.json").exists())
        self.assertEqual(sorted(self.g.setup_status()["consent_needed"]), ["github-projects", "organize"])

    def test_every_file_moving_command_requires_consent(self):
        source = self.personal("Downloads/report.pdf")
        for call in (lambda: self.g.organize(True), lambda: self.g.rename(True),
                     lambda: self.g.classify_file(source, "documents", "work", "report.pdf", m.digest(source), "evidence"),
                     lambda: self.g.rename_file(source, "renamed.pdf", m.digest(source), "evidence")):
            with self.assertRaisesRegex(ValueError, "consent_required"):
                call()
        self.assertTrue(source.exists())

    def test_consent_needs_a_fresh_preview_of_the_same_folders(self):
        with self.assertRaisesRegex(ValueError, "fresh preview"):
            self.g.grant_consent("organize", "yes")
        self.g.organize(False)
        with self.assertRaisesRegex(ValueError, "own words"):
            self.g.grant_consent("organize", "  ")
        plan = json.loads((self.g.state / "organization-plan.json").read_text())
        plan["at"] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)).isoformat()
        m.write_json(self.g.state / "organization-plan.json", plan)
        with self.assertRaisesRegex(ValueError, "fresh preview"):
            self.g.grant_consent("organize", "yes")
        self.g.organize(False)
        self.g.policy["organization_roots"] = ["Downloads"]
        with self.assertRaisesRegex(ValueError, "different folders"):
            self.g.grant_consent("organize", "yes")

    def test_yes_then_automatic_care_and_revoke_stops_it(self):
        first = self.personal("Downloads/report.pdf")
        self.g.organize(False)
        granted = self.g.grant_consent("organize", "Owner: yes, go ahead")
        self.assertNotIn("evidence", granted)
        self.assertEqual(json.loads((self.g.state / "consent.json").read_text())["organize"]["evidence"], "Owner: yes, go ahead")
        self.maintain()
        self.assertFalse(first.exists())
        self.g.revoke_consent("organize")
        second = self.personal("Downloads/later.pdf")
        m.write_json(self.g.state / "maintenance.json", {})
        self.maintain()
        self.assertTrue(second.exists())

    def test_changing_folders_needs_a_new_yes(self):
        self.g.organize(False)
        self.g.grant_consent("organize", "yes")
        result = self.g.configure_organization(["Downloads", "Desktop", "."])
        self.assertFalse(result["consent"]["granted"])
        self.assertEqual(result["consent"]["reason"], "folders changed since the owner said yes")
        saved = json.loads((self.g.state / "policy.json").read_text())
        self.assertEqual(saved["organization_roots"], ["Downloads", "Desktop", "."])
        self.assertEqual(m.Guardian(self.home, self.root / "state").policy["organization_roots"], ["Downloads", "Desktop", "."])

    def test_organization_folders_are_validated(self):
        (self.home / "Library").mkdir()
        (self.home / "Documents").mkdir()
        (self.home / "Dropbox").mkdir()
        for roots, message in [(["/Users/x/Downloads"], "relative"), (["../x"], "relative"),
                               (["Missing"], "not found"), (["Library"], "cannot be organized"),
                               (["Documents"], "cannot be organized"), (["Dropbox"], "cannot be organized"),
                               (["Wiki"], "not found")]:
            with self.subTest(roots=roots), self.assertRaisesRegex(ValueError, message):
                self.g.configure_organization(roots)
        (self.home / "Wiki").mkdir()
        with self.assertRaisesRegex(ValueError, "wiki itself"):
            self.g.configure_organization(["Wiki"])

    def test_app_libraries_sync_folders_and_packages_stay_in_place(self):
        kept = [self.personal("Music/Music/Media.localized/Artist/song.mp3"),
                self.personal("Movies/TV/Media.localized/show.mp4"),
                self.personal("Movies/Holiday.imovielibrary/clip.mov"),
                self.personal("Dropbox/shared.pdf"), self.personal("OneDrive - Contoso/plan.pdf"),
                self.personal("Backup/MacGuardian/copy.pdf")]
        moved = self.personal("Music/loose.mp3")
        self.g.configure_organization(["."])
        sources = {i["source"] for i in self.g.organize(False)["items"]}
        self.assertEqual(sources, {str(moved)})
        self.assertTrue(all(p.exists() for p in kept))

    @unittest.skipUnless(hasattr(os, "chflags") and hasattr(m.stat, "UF_HIDDEN"), "needs BSD file flags")
    def test_cloud_placeholders_are_never_downloaded_to_be_moved(self):
        placeholder = self.personal("Desktop/in-the-cloud.pdf")
        local = self.personal("Desktop/on-disk.pdf")
        os.chflags(placeholder, m.stat.UF_HIDDEN)
        # A real dataless flag is set by the kernel; stand in a flag the owner can set.
        with patch.object(m, "SF_DATALESS", m.stat.UF_HIDDEN):
            sources = {i["source"] for i in self.g.organize(False)["items"]}
        self.assertEqual(sources, {str(local)})

    def test_new_wikis_use_english_and_earlier_wikis_keep_their_names(self):
        self.personal("Downloads/report.pdf")
        self.g.organize(False)
        self.g.grant_consent("organize", "yes")
        with patch.object(m, "in_use", return_value=False):
            result = self.g.organize(True)
        self.assertTrue(Path(result["items"][0]["destination"]).is_relative_to(self.home / "Wiki/Documents/"))
        home = (self.home / "Wiki/Home.md").read_text()
        self.assertTrue(home.startswith(m.INDEX_MARKER))
        self.assertIn("# Personal wiki", home)

        legacy = m.Guardian(self.root / "legacy-home", self.root / "legacy-state")
        (legacy.home / "Downloads").mkdir(parents=True)
        (legacy.home / "Wiki/Documentos").mkdir(parents=True)
        self.assertEqual(legacy.wiki_language(), "pt")
        self.assertEqual(legacy.category_folder("documents"), "Documentos")
        self.assertEqual(legacy.category_folder("Imagens"), "Imagens")
        legacy.policy["wiki_language"] = "en"
        self.assertEqual(legacy.category_folder("Documentos"), "Documents")
        with self.assertRaisesRegex(ValueError, "Invalid category"):
            legacy.category_folder("Secrets")

    def test_legacy_generated_indexes_are_still_recognized_as_ours(self):
        page = self.home / "Wiki/Home.md"
        page.parent.mkdir()
        page.write_text(m.LEGACY_INDEX_MARKERS[0] + "<!-- Mac Guardian page: Home.md -->\n# Wiki pessoal\n")
        result = self.g.file_wiki()
        self.assertEqual(result["home"], str(page))
        self.assertIn("# Personal wiki", page.read_text())

    def test_health_reports_are_english_and_replace_legacy_pages(self):
        reports = self.home / self.g.policy["health_wiki_root"]
        reports.mkdir(parents=True)
        (reports / "Saude.md").write_text("old")
        report = {"at": m.now(), "folders": [], "disk": {"free_bytes": 10 * m.GIB}, "memory": {"swap": "0M"},
                  "applications": [], "background": []}
        self.g.wiki(report)
        self.assertEqual(sorted(p.name for p in reports.iterdir()), ["Applications.md", "Health.md", "Home.md", "Services.md"])
        self.assertIn("Free space: 10.00 GiB", (reports / "Health.md").read_text())

    def test_an_empty_cycle_leaves_no_undo_journal(self):
        self.g.organize(False)
        self.g.grant_consent("organize", "yes")
        result = self.g.organize(True)
        self.assertIsNone(result["transaction"])
        self.assertEqual(list((self.g.state / "moves").glob("*.json")) if (self.g.state / "moves").exists() else [], [])

    def test_earlier_installs_that_already_moved_files_are_not_interrupted(self):
        m.write_json(self.g.state / "moves" / ("a" * 32 + ".json"), {"items": []})
        self.assertFalse(self.g.consent_granted("organize"))
        m.write_json(self.g.state / "moves" / ("b" * 32 + ".json"), {"items": [{"source": "x", "destination": "y"}]})
        self.assertTrue(self.g.consent_granted("organize"))
        self.assertTrue(json.loads((self.g.state / "consent.json").read_text())["organize"]["grandfathered"])
        self.assertFalse(self.g.consent_granted("github-projects"))
        m.write_json(self.g.state / "project-snapshots.json", {"/p|working": {"verified": True}})
        self.assertTrue(self.g.consent_granted("github-projects"))

    def test_corrupt_consent_record_fails_without_being_replaced(self):
        (self.g.state / "consent.json").write_text("[]")
        with self.assertRaisesRegex(ValueError, "consent.json"):
            self.g.consent_granted("organize")
        self.assertEqual((self.g.state / "consent.json").read_text(), "[]")


class GitHubConsentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve() / "home"
        self.project = self.home / "Code/site"
        self.project.mkdir(parents=True)
        subprocess.run(["git", "init", "--quiet", str(self.project)], check=True)
        (self.project / "README.md").write_text("# Site\n")
        (self.project / ".env").write_text("TOKEN=local-only-value\n")
        (self.project / ".gitignore").write_text(".env\n")
        self.g = m.Guardian(self.home, self.home.parent / "state")

    def test_without_consent_code_never_leaves_and_no_repository_is_created(self):
        calls = []
        def external(argv, timeout=20):
            calls.append(argv)
            return {"ok": True, "stdout": "owner", "stderr": ""}
        with patch.object(self.g, "_command", side_effect=external), \
             patch.object(m.shutil, "which", return_value="/usr/local/bin/gh"):
            result = self.g.care_for_projects(True)
            with self.assertRaisesRegex(ValueError, "consent_required"):
                self.g.private_project_repo()
            with self.assertRaisesRegex(ValueError, "consent_required"):
                self.g.project_snapshot(self.project, "owner/backups")
            git = ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "-C", str(self.project)]
            subprocess.run([*git, "add", "README.md", ".gitignore"], check=True)
            subprocess.run([*git, "commit", "--quiet", "-m", "fixture"], check=True)
            secondary = self.home / "Code/site-old"
            subprocess.run([*git, "worktree", "add", "--quiet", "-b", "old", str(secondary)], check=True)
            with self.assertRaisesRegex(ValueError, "consent_required"):
                self.g.remove_worktree(secondary, apply=True)
            self.assertTrue(secondary.exists())
        self.assertEqual(calls, [])
        self.assertFalse(result["github_consent"])
        self.assertEqual(result["items"][0]["status"], "local_only")
        self.assertIn("awaiting_consent", result["items"][0]["reason"])
        # Secrets are still protected locally while the answer is pending.
        self.assertEqual(result["items"][0]["secrets"], 1)
        self.assertTrue(any((self.home / "Backup/MacGuardian/Secrets").rglob("content")))

    def test_preview_names_what_would_leave_and_only_a_recorded_preview_counts(self):
        background = self.g.care_for_projects(False)
        self.assertFalse((self.g.state / "project-plan.json").exists())
        self.assertEqual(background["visibility"], "private")
        self.g.__dict__.pop("_project_cache", None)
        preview = self.g.care_for_projects(False, record=True)
        self.assertEqual([i["project"] for i in preview["items"]], [str(self.project)])
        self.assertIn("heuristic", preview["secret_detection"])
        self.g.grant_consent("github-projects", "Owner: yes, private backups are fine")
        self.assertTrue(self.g.consent_status()["github-projects"]["granted"])


class ConsentCommandLineTests(unittest.TestCase):
    def run_cli(self, home, *args):
        return subprocess.run([sys.executable, str(ROOT / "native/mac_guardian.py"), "--home", str(home), *args],
                              capture_output=True, text=True, timeout=60,
                              env={k: v for k, v in os.environ.items() if k not in ("AGENT_ID", "BOSS_ID")})

    def test_consent_and_folder_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            (home / "Downloads").mkdir(parents=True)
            status = self.run_cli(home, "consent")
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertFalse(json.loads(status.stdout)["organize"]["granted"])
            refused = self.run_cli(home, "consent", "--grant", "--evidence", "yes")
            self.assertEqual(refused.returncode, 1)
            self.assertIn("Choose a --scope", refused.stderr)
            self.assertEqual(self.run_cli(home, "configure-organization", "--root", "Downloads").returncode, 0)
            self.assertEqual(self.run_cli(home, "organize").returncode, 0)
            granted = self.run_cli(home, "consent", "--scope", "organize", "--grant", "--evidence", "Owner: yes")
            self.assertEqual(granted.returncode, 0, granted.stderr)
            self.assertTrue(json.loads(self.run_cli(home, "consent", "--scope", "organize").stdout)["granted"])


if __name__ == "__main__":
    unittest.main()

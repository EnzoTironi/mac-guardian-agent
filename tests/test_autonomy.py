import importlib.util
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


class AutonomyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        self.g = m.Guardian(self.home, self.root / "state")

    def personal(self, name, data=b"personal document", old=True):
        path = self.home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if old:
            os.utime(path, (time.time() - 3 * m.DAY,) * 2)
        return path

    def report(self):
        return {"at": m.now(), "full_checked_at": m.now(), "disk": {"free_bytes": 40 * m.GIB},
                "memory": {"swap_bytes": 0}, "load_average": [0, 0, 0], "alerts": []}

    def test_nested_topics_and_root_files_are_really_moved_to_wiki(self):
        paths = [self.personal("Downloads/Viagens/Italia/roteiro.pdf"),
                 self.personal("Desktop/apresentacao.pptx"), self.personal("anotacoes.md")]
        with patch.object(m, "in_use", return_value=False):
            result = self.g.organize(True)
        self.assertEqual(len(result["items"]), 3)
        self.assertTrue((self.home / "Wiki/Documentos/Viagens/Italia/roteiro.pdf").exists())
        self.assertTrue(all(not p.exists() for p in paths))
        self.assertIn("roteiro.pdf", (self.home / "Wiki/Documentos/_Index.md").read_text())
        self.g.undo(result["transaction"])
        self.assertTrue(all(p.read_bytes() == b"personal document" for p in paths))

    def test_equal_filenames_keep_both_contents(self):
        self.personal("Downloads/report.pdf", b"one")
        self.personal("Desktop/report.pdf", b"two")
        with patch.object(m, "in_use", return_value=False):
            result = self.g.organize(True)
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual({Path(i["destination"]).read_bytes() for i in result["items"]}, {b"one", b"two"})

    def test_recent_open_linked_secret_and_project_files_stay_in_place(self):
        paths = [self.personal("Downloads/recent.pdf", old=False),
                 self.personal("Downloads/open.pdf"), self.personal("Downloads/passwords.pdf"),
                 self.personal("Downloads/app/manual.pdf")]
        self.personal("Downloads/app/pyproject.toml", b"[project]")
        target = self.personal("Downloads/linked.pdf")
        (self.home / "Desktop").mkdir()
        (self.home / "Desktop/alias.pdf").symlink_to(target)
        with patch.object(m, "in_use", side_effect=lambda p: Path(p).name == "open.pdf"):
            self.g.organize(True)
        self.assertTrue(all(p.exists() for p in paths))
        self.assertTrue((self.home / "Desktop/alias.pdf").is_symlink())

    def test_personal_index_pages_are_never_overwritten(self):
        home = self.personal("Wiki/Home.md", b"my own wiki")
        index = self.personal("Wiki/Documentos/_Index.md", b"my notes")
        self.personal("Wiki/Documentos/README.md", b"read me")
        result = self.g.file_wiki()
        self.assertEqual(home.read_bytes(), b"my own wiki")
        self.assertEqual(index.read_bytes(), b"my notes")
        self.assertNotEqual(result["home"], str(home))
        generated = next(index.parent.glob("_MacGuardian-*.md"))
        self.assertIn("README.md", generated.read_text())
        self.assertEqual(self.g.file_wiki()["home"], result["home"])

    def test_wiki_index_is_bounded(self):
        for i in range(4):
            self.personal(f"Wiki/Documentos/{i}.pdf")
        self.g.policy["wiki_max_files"] = 2
        result = self.g.file_wiki()
        self.assertTrue(result["incomplete"])
        self.assertEqual(result["indexed_files"], 2)
        self.assertEqual(len(list((self.home / "Wiki/Documentos").glob("*.pdf"))), 4)

    def test_crash_between_link_and_unlink_can_be_undone(self):
        source = self.personal("Downloads/report.pdf")
        actual_unlink = Path.unlink
        def interrupted(path, *args, **kwargs):
            if path == source:
                raise OSError("simulated interruption")
            return actual_unlink(path, *args, **kwargs)
        with patch.object(m, "in_use", return_value=False), patch.object(Path, "unlink", interrupted):
            with self.assertRaises(OSError):
                self.g.organize(True)
        journal = next((self.g.state / "moves").glob("*.json"))
        data = json.loads(journal.read_text())
        destination = Path(data["items"][0]["destination"])
        self.assertTrue(os.path.samefile(source, destination))
        self.g.undo(journal.stem)
        self.assertEqual(source.read_bytes(), b"personal document")
        self.assertFalse(destination.exists())

    def test_paused_agent_keeps_monitoring_without_mutations(self):
        self.g.pause()
        with patch.object(self.g, "check", return_value=self.report()) as check, \
             patch.object(self.g, "organize") as organize, patch.object(self.g, "package_updates") as updates:
            self.assertEqual(self.g.maintain()["status"], "paused")
        check.assert_called_once()
        organize.assert_not_called()
        updates.assert_not_called()
        self.assertTrue(self.g.status()["paused"])
        self.g.resume()
        self.assertFalse(self.g.status()["paused"])

    def test_automatic_run_moves_files_and_reuses_daily_schedule(self):
        source = self.personal("Downloads/report.pdf")
        with patch.object(self.g, "check", return_value=self.report()), patch.object(m, "in_use", return_value=False), \
             patch.object(self.g, "package_updates", return_value={"items": [], "updated": 0}):
            result = self.g.maintain()
            self.assertFalse(source.exists())
            self.assertFalse(result["exception"])
            second = self.g.maintain()
        self.assertNotIn("organization", [s["name"] for s in second["stages"]])
        self.assertFalse(self.g.status()["in_progress"])

    def test_dry_run_preserves_personal_files_and_packages(self):
        source = self.personal("Downloads/report.pdf")
        with patch.object(self.g, "check", return_value=self.report()), \
             patch.object(self.g, "package_updates", return_value={"items": [], "updated": 0}) as update:
            result = self.g.maintain(False)
        self.assertEqual(result["mode"], "preview")
        self.assertTrue(source.exists())
        self.assertFalse((self.g.state / "maintenance.json").exists())
        self.assertFalse(update.call_args.args[1])

    def test_verification_failure_clears_running_state_and_is_reported(self):
        with patch.object(self.g, "check", side_effect=[self.report(), OSError("collector failed")]), \
             patch.object(self.g, "package_updates", return_value={"items": [], "updated": 0}):
            result = self.g.maintain()
        self.assertTrue(result["exception"])
        self.assertFalse(self.g.status()["in_progress"])
        self.assertEqual(result["stages"][-1]["name"], "verification")

    def test_history_corruption_does_not_stop_collection(self):
        (self.g.state / "health-history.json").write_text("broken{")
        history = self.g.health_history(self.report())
        self.assertEqual(history["samples"], 1)
        self.assertEqual(len(list(self.g.state.glob("health-history-corrupt-*.json"))), 1)
        self.g.policy["history_max_samples"] = 2
        for _ in range(3):
            history = self.g.health_history(self.report())
        self.assertEqual(history["samples"], 2)

    def test_service_change_survives_later_checks_until_reviewed(self):
        def command(argv, timeout=20, env=None):
            output = "1024" if argv[:3] == ["sysctl", "-n", "hw.memsize"] else ""
            return {"ok": True, "code": 0, "stdout": output, "stderr": ""}
        job = {"plist": "/test/new.plist", "label": "new-service", "sha256": "new", "executable": "/test/bin", "review": []}
        with patch.object(m, "command", command), patch.object(self.g, "background", side_effect=[[], [job], [job]]):
            self.g.check()
            self.g.check()
            self.g.check()
        pending = self.g.status()["pending_reviews"]
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["change"], "added")
        self.g.review(pending[0]["id"], "Verified publisher, expected installation, no suspicious listener.")
        self.assertEqual(self.g.status()["pending_reviews"], [])

    def test_removed_jobs_are_observed_by_path(self):
        before = [{"plist": "/one", "label": "same"}, {"plist": "/two", "label": "same"}]
        changes = m.inventory_changes(before[:1], before, "plist", ["sha256"], "service")
        self.assertEqual(changes[0]["identity"], "/two")
        self.assertEqual(changes[0]["change"], "removed")

    def test_status_is_available_while_a_worker_holds_lock(self):
        script = Path(__file__).parents[1] / "native/mac_guardian.py"
        with self.g.lock():
            result = subprocess.run([os.sys.executable, str(script), "--home", str(self.home),
                                     "--state", str(self.g.state), "status"], capture_output=True, text=True)
            busy = subprocess.run([os.sys.executable, str(script), "--home", str(self.home),
                                   "--state", str(self.g.state), "maintain"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(json.loads(result.stdout)["free_disk_gib"])
        self.assertEqual(json.loads(busy.stdout)["status"], "busy")

    def test_private_atomic_writes_refuse_symlinks(self):
        target = self.personal("important.txt", b"keep")
        link = self.g.state / "report.json"
        link.symlink_to(target)
        with self.assertRaises(ValueError):
            m.write_json(link, {"unsafe": True})
        self.assertEqual(target.read_bytes(), b"keep")
        path = self.g.state / "safe.json"
        m.write_json(path, {"ok": True})
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def brew_setup(self, busy=False, malformed_verify=False, source="homebrew/core", pinned=False, dependency=False):
        cellar = self.root / "Cellar/tool"
        cellar.mkdir(parents=True, exist_ok=True)
        calls = []
        def command(argv, timeout=20, env=None):
            calls.append((argv, env))
            output = ""
            if argv[:2] == ["brew", "outdated"]:
                output = json.dumps({} if malformed_verify and "tool" in argv else
                                    {"formulae": [] if "tool" in argv else [{"name": "tool"}], "casks": []})
            elif argv[:2] == ["brew", "info"]:
                item = {"name": "tool", "tap": source, "pinned": pinned,
                        "dependencies": ["custom"] if dependency else []}
                output = json.dumps({"formulae": [item], "casks": []})
            elif argv[:2] == ["brew", "--cellar"]:
                output = str(cellar)
            return {"ok": True, "code": 0, "stdout": output, "stderr": ""}
        return calls, patch.object(m, "command", command), patch.object(m.shutil, "which", side_effect=lambda n: "/brew" if n == "brew" else None), patch.object(m, "in_use", return_value=busy)

    def test_explicitly_approved_upgrade_is_verified_and_rate_limited(self):
        calls, cmd, which, use = self.brew_setup()
        state = {}
        with cmd, which, use:
            requested = self.g.package_updates(state)
            self.assertEqual(requested["updated"], 0)
            self.assertFalse(any(argv[:2] == ["brew", "upgrade"] for argv, _ in calls))
            self.g.approve(requested["items"][0]["request_id"], "Owner: update this tool now")
            result = self.g.package_updates(state)
            self.g.package_updates(state)
        upgrades = [(argv, env) for argv, env in calls if argv[:2] == ["brew", "upgrade"]]
        self.assertEqual(result["updated"], 1)
        self.assertEqual(len(upgrades), 1)
        self.assertEqual(upgrades[0][0], ["brew", "upgrade", "--formula", "tool"])
        self.assertEqual(upgrades[0][1]["HOMEBREW_NO_INSTALL_CLEANUP"], "1")
        self.assertEqual(upgrades[0][1]["HOMEBREW_NO_SUDO"], "1")

    def test_busy_pinned_unofficial_and_unknown_dependencies_are_preserved(self):
        for case in ({"busy": True}, {"pinned": True}, {"source": "someone/tap"}, {"dependency": True}):
            with self.subTest(case=case):
                # Reuse the cellars but do not share updater state between cases.
                calls, cmd, which, use = self.brew_setup(**case)
                with cmd, which, use:
                    self.g.package_updates({})
                self.assertFalse(any(argv[:2] == ["brew", "upgrade"] for argv, _ in calls))

    def test_unverified_upgrade_is_not_counted_as_success(self):
        calls, cmd, which, use = self.brew_setup(malformed_verify=True)
        with cmd, which, use:
            requested = self.g.package_updates({})
            self.g.approve(requested["items"][0]["request_id"], "Owner: update this tool now")
            result = self.g.package_updates({})
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["items"][0]["status"], "failed")

    def test_update_preview_runs_no_catalog_refresh_or_upgrade(self):
        calls, cmd, which, use = self.brew_setup()
        with cmd, which, use:
            result = self.g.package_updates({}, apply=False)
        self.assertEqual(result["items"][0]["status"], "planned")
        self.assertFalse(any(argv[:2] in (["brew", "update"], ["brew", "upgrade"]) for argv, _ in calls))

    def test_cask_is_upgraded_only_from_app_metadata_and_verified(self):
        self.personal("Applications/Sample.app/Contents/Info.plist", b"fixture")
        calls = []
        def command(argv, timeout=20, env=None):
            calls.append(argv)
            if argv[:2] == ["brew", "outdated"]:
                data = {"formulae": [], "casks": [] if "sample" in argv else [{"name": "sample"}]}
            else:
                data = {"formulae": [], "casks": [{"token": "sample", "tap": "homebrew/cask",
                                                   "artifacts": [{"app": ["Sample.app"], "target": "/Applications/Sample.app"},
                                                                 {"binary": ["/Applications/Sample.app/Contents/MacOS/sample"],
                                                                  "target": "/opt/homebrew/bin/sample"}]}]}
            return {"ok": True, "code": 0, "stdout": json.dumps(data), "stderr": ""}
        with patch.object(m, "command", command), patch.object(m, "in_use", return_value=False), \
             patch.object(m.shutil, "which", side_effect=lambda n: "/brew" if n == "brew" else None):
            requested = self.g.package_updates({})
            self.g.approve(requested["items"][0]["request_id"], "Owner: update Sample now")
            result = self.g.package_updates({})
        self.assertEqual(result["updated"], 1)
        self.assertIn(["brew", "upgrade", "--cask", "sample"], calls)
        self.assertIn(["brew", "info", "--json=v2", "--installed", "--cask"], calls)

    def test_installer_hooks_are_not_run_automatically(self):
        self.personal("Applications/Sample.app/Contents/Info.plist", b"fixture")
        calls = []
        def command(argv, timeout=20, env=None):
            calls.append(argv)
            data = {"formulae": [], "casks": [{"name": "sample"}]} if argv[:2] == ["brew", "outdated"] else {
                "formulae": [], "casks": [{"token": "sample", "tap": "homebrew/cask",
                                            "artifacts": [{"app": ["Sample.app"]}, {"postflight_steps": []}]}]}
            return {"ok": True, "code": 0, "stdout": json.dumps(data), "stderr": ""}
        with patch.object(m, "command", command), patch.object(m, "in_use", return_value=False), \
             patch.object(m.shutil, "which", side_effect=lambda n: "/brew" if n == "brew" else None):
            result = self.g.package_updates({})
        self.assertEqual(result["items"][0]["status"], "needs_installer_review")
        self.assertFalse(any(a[:2] == ["brew", "upgrade"] for a in calls))

    def test_documents_and_cloud_roots_are_excluded_even_in_old_policy(self):
        source = self.personal("Documents/private.pdf")
        self.g.policy["organization_roots"] = ["Documents"]
        self.assertEqual(self.g.organize(True)["items"], [])
        self.assertTrue(source.exists())
        self.g.policy["backup_roots"] = ["Documents"]
        with self.assertRaisesRegex(ValueError, "excluída"):
            self.g.backup_manifest(source.parent)
        self.g.policy["file_wiki_root"] = "Documents/Wiki"
        with self.assertRaisesRegex(ValueError, "Documents"):
            self.g.file_wiki()
        self.assertFalse((self.home / "Documents/Wiki").exists())

    def test_heading_names_a_file_during_organization_and_undo_restores_original(self):
        source = self.personal("Downloads/untitled-3.md", "# Planejamento da viagem - Itália\n\nNotas locais.".encode())
        with patch.object(m, "in_use", return_value=False):
            result = self.g.organize(True)
        destination = Path(result["items"][0]["destination"])
        self.assertEqual(destination.name, "planejamento-da-viagem-italia.md")
        self.g.undo(result["transaction"])
        self.assertTrue(source.exists())
        self.assertIn("Itália", source.read_text())

    def test_office_title_comes_from_document_content(self):
        import zipfile
        path = self.home / "Wiki/Documentos/download-2.docx"
        path.parent.mkdir(parents=True)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("docProps/core.xml", '<cp:coreProperties xmlns:cp="urn:properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Plano Financeiro 2026</dc:title></cp:coreProperties>')
        os.utime(path, (time.time() - 3 * m.DAY,) * 2)
        context = self.g.naming_context(path)
        self.assertEqual(context["suggested_name"], "plano-financeiro-2026.docx")
        self.assertEqual(context["confidence"], "high")
        with patch.object(m, "in_use", return_value=False):
            result = self.g.rename(True)
        self.assertEqual(len(result["items"]), 1)
        self.g.undo(result["transaction"])
        self.assertTrue(path.exists())

    def test_pdf_naming_uses_extracted_text_without_executing_it(self):
        path = self.personal("Wiki/Documentos/download.pdf", b"fixture PDF bytes")
        calls = []
        def extract(argv, timeout=20, env=None):
            calls.append(argv)
            return {"ok": True, "code": 0, "stdout": "Fatura de servicos - Outubro 2026\n\nTexto de exemplo.", "stderr": ""}
        with patch.object(m, "command", extract), patch.object(m.shutil, "which", return_value="/pdftotext"):
            context = self.g.naming_context(path)
        self.assertEqual(context["suggested_name"], "fatura-de-servicos-outubro-2026.pdf")
        self.assertEqual(calls[0][0], "pdftotext")
        self.assertEqual(path.read_bytes(), b"fixture PDF bytes")

    def test_uncertain_content_waits_for_review_and_reviewed_name_requires_same_hash(self):
        path = self.personal("Wiki/Documentos/untitled.txt", b"A paragraph that is not an explicit document title.")
        with patch.object(m, "in_use", return_value=False):
            result = self.g.rename(True)
        self.assertEqual(result["items"], [])
        self.assertEqual(result["pending_context"], 1)
        old_hash = m.digest(path)
        with self.assertRaisesRegex(ValueError, "mudou"):
            self.g.rename_file(path, "notas-da-viagem.txt", "wrong", "Context reviewed")
        with patch.object(m, "in_use", return_value=False):
            result = self.g.rename_file(path, "notas-da-viagem.txt", old_hash, "Read the notes and existing topic; preserve original extension.")
        self.assertTrue((path.parent / "notas-da-viagem.txt").exists())
        with patch.object(m, "in_use", return_value=False):
            again = self.g.rename(True)
        self.assertEqual(again["items"], [])
        self.assertEqual(again["pending_context"], 0)
        self.g.undo(result["transaction"])
        self.assertTrue(path.exists())

    def test_secret_content_never_appears_in_naming_context(self):
        path = self.personal("Wiki/Documentos/notes.md", ("# Notes with access\nghp_" + "a" * 36).encode())
        context = self.g.naming_context(path)
        self.assertEqual(context["status"], "protected_content")
        self.assertNotIn("text_excerpt", context)
        self.assertNotIn("ghp_", json.dumps(context))

    def test_same_titles_preserve_contents_and_do_not_rename_forever(self):
        one = self.personal("Wiki/Documentos/one.md", b"# Monthly report\n\nOne")
        two = self.personal("Wiki/Documentos/two.md", b"# Monthly report\n\nTwo")
        with patch.object(m, "in_use", return_value=False):
            result = self.g.rename(True)
            again = self.g.rename(True)
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(again["items"], [])
        self.g.undo(result["transaction"])
        self.assertIn(b"One", one.read_bytes())
        self.assertIn(b"Two", two.read_bytes())

    def test_automatic_file_cycle_is_one_reversible_transaction(self):
        old = self.personal("Wiki/Documentos/old.md", b"# Existing title\n\nOld")
        source = self.personal("Downloads/new.md", b"# New document title\n\nNew")
        with patch.object(self.g, "check", return_value=self.report()), patch.object(m, "in_use", return_value=False), \
             patch.object(self.g, "package_updates", return_value={"items": [], "updated": 0}):
            result = self.g.maintain()
        self.assertIsNotNone(result["file_transaction"])
        organization = next(s["result"] for s in result["stages"] if s["name"] == "organization")
        self.g.undo(organization["transaction"])
        self.assertTrue(old.exists())
        self.assertTrue(source.exists())

    def test_local_ocr_names_a_document_image_from_its_text(self):
        path = self.personal("Wiki/Imagens/IMG_1234.png", b"fixture image")
        calls = []
        def extract(argv, timeout=20, env=None):
            calls.append((argv, env))
            return {"ok": True, "code": 0, "stdout": "Fatura de energia\nData: 06/10/2026\n", "stderr": ""}
        with patch.object(m, "command", extract), patch.object(m.shutil, "which", return_value="/tesseract"):
            context = self.g.naming_context(path)
        self.assertEqual(context["suggested_name"], "2026-10-06-fatura-de-energia.png")
        self.assertEqual(context["basis"], "local_ocr")
        self.assertEqual(calls[0][0][:3], ["tesseract", str(path), "stdout"])
        self.assertEqual(calls[0][1]["OMP_THREAD_LIMIT"], "1")

    def test_generic_title_uses_the_existing_subject_and_valid_content_date(self):
        path = self.personal("Wiki/Documentos/Cliente Alfa/note.md", b"# Relatorio mensal\nData: 2026-09-30\n")
        context = self.g.naming_context(path)
        self.assertEqual(context["suggested_name"], "2026-09-30-relatorio-mensal-cliente-alfa.md")
        path.write_bytes(b"# Relatorio mensal\nData: 2026-02-31\n")
        self.assertEqual(self.g.naming_context(path)["suggested_name"], "relatorio-mensal-cliente-alfa.md")

    def test_spotlight_filename_is_not_a_document_title(self):
        path = self.personal("Wiki/Documentos/download.pdf", b"fixture PDF")
        with patch.object(m.sys, "platform", "darwin"), patch.object(m.shutil, "which", return_value=None), \
             patch.object(m, "command", return_value={"ok": True, "stdout": "download.pdf"}):
            context = self.g.naming_context(path)
        self.assertEqual(context["status"], "needs_context")
        self.assertNotIn("suggested_name", context)

    def test_media_uses_embedded_title(self):
        path = self.personal("Wiki/Videos/movie.mp4", b"fixture video")
        with patch.object(m.shutil, "which", return_value="/ffprobe"), patch.object(m, "command", return_value={
                "ok": True, "stdout": json.dumps({"format": {"tags": {"title": "Entrevista do projeto Atlas"}}})}):
            context = self.g.naming_context(path)
        self.assertEqual(context["suggested_name"], "entrevista-do-projeto-atlas.mp4")

    def test_naming_cache_skips_unchanged_content_and_rechecks_modified_files(self):
        path = self.personal("Wiki/Documentos/draft.txt", b"An ordinary paragraph without an explicit title.")
        with patch.object(self.g, "naming_context", wraps=self.g.naming_context) as read, \
             patch.object(m, "in_use", return_value=False):
            self.g.rename(True)
            self.g.rename(True)
            self.assertEqual(read.call_count, 1)
            path.write_bytes(b"Title: A revised document title\n")
            os.utime(path, (time.time() - 3 * m.DAY,) * 2)
            self.g.rename(True)
            self.assertEqual(read.call_count, 2)
        self.assertTrue((path.parent / "a-revised-document-title.txt").exists())

    def test_rename_keeps_project_paths_and_rejects_control_characters(self):
        path = self.personal("Wiki/Documentos/notes.md", b"# Local meeting notes\n")
        project = self.personal("Wiki/Documentos/Project/README.md", b"# Project documentation\n")
        self.personal("Wiki/Documentos/Project/package.json", b"{}")
        with self.assertRaisesRegex(ValueError, "Nome"):
            self.g.rename_file(path, "meeting\nnotes.md", m.digest(path), "Read the content")
        with patch.object(m, "in_use", return_value=False):
            self.g.rename(True)
        self.assertTrue(project.exists())


if __name__ == "__main__":
    unittest.main()

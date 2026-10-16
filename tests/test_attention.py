"""Space is freed only after one yes for an exact inventory; texts are rare and specific."""
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "native"))
import attention  # noqa: E402
import mac_guardian as m  # noqa: E402


class SpaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve() / "home"
        self.home.mkdir()
        self.g = m.Guardian(self.home, self.home.parent / "state")
        self.g.policy["space_min_item_mib"] = 0
        self.running = set()
        patch.object(self.g, "_processes", side_effect=lambda: set(self.running)).start()
        self.addCleanup(patch.stopall)

    def make(self, rel, data=b"x" * 4096):
        path = self.home / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def labels(self, result):
        return sorted(i["label"] for i in result["items"])

    def test_proposal_lists_rebuildable_folders_only_and_needs_a_yes(self):
        self.make("Library/Developer/Xcode/DerivedData/App-abc/Build/out.o")
        self.make(".npm/_cacache/index-v5/aa")
        self.make("Documents/thesis.pdf")
        self.make("Library/Caches/Homebrew/downloads/x.tar.gz")
        (self.home / "Library/Caches/pip").parent.mkdir(parents=True, exist_ok=True)
        os.symlink(self.home / "Documents", self.home / "Library/Caches/pip")
        result = self.g.space()
        self.assertEqual(self.labels(result), ["Homebrew downloads", "Xcode build data", "npm cache"])
        self.assertIsNotNone(result["request_id"])
        self.assertTrue((self.g.state / "space-plan.json").exists())
        with self.assertRaisesRegex(ValueError, "recent yes"):
            self.g.free_space(result["request_id"])
        self.assertTrue((self.home / "Library/Developer/Xcode/DerivedData/App-abc").exists())

    def test_yes_deletes_contents_keeps_the_folders_and_is_used_once(self):
        derived = self.make("Library/Developer/Xcode/DerivedData/App-abc/Build/out.o").parents[2]
        self.make(".npm/_cacache/index-v5/aa")
        thesis = self.make("Documents/thesis.pdf")
        result = self.g.space()
        self.g.approve(result["request_id"], "Owner: yes, free it")
        freed = self.g.free_space(result["request_id"])
        self.assertTrue(all(i["freed"] for i in freed["items"]), freed)
        self.assertTrue(derived.is_dir())
        self.assertEqual(list(derived.iterdir()), [])
        self.assertEqual(list((self.home / ".npm/_cacache").iterdir()), [])
        self.assertTrue(thesis.exists())
        with self.assertRaisesRegex(ValueError, "nothing approved"):
            self.g.free_space(result["request_id"])

    def test_open_tools_are_deferred_and_replaced_folders_are_skipped(self):
        self.make("Library/Developer/Xcode/DerivedData/App/out.o")
        self.make(".npm/_cacache/x")
        self.make("Library/Caches/Homebrew/y")
        self.running = {"Xcode"}
        result = self.g.space()
        self.assertEqual(result["deferred"], [{"label": "Xcode build data", "reason": "in use right now"}])
        self.assertNotIn("Xcode build data", self.labels(result))
        self.g.approve(result["request_id"], "yes")
        shutil.rmtree(self.home / ".npm/_cacache")
        self.make(".npm/_cacache/new")
        self.running = {"brew"}
        freed = {i["label"]: i for i in self.g.free_space(result["request_id"])["items"]}
        self.assertIn("replaced", freed["npm cache"]["reason"])
        self.assertEqual(freed["Homebrew downloads"]["reason"], "in use right now")
        self.assertTrue((self.home / ".npm/_cacache/new").exists())
        self.assertTrue((self.home / "Library/Caches/Homebrew/y").exists())

    def test_unknown_processes_defer_everything(self):
        self.make(".npm/_cacache/x")
        with patch.object(self.g, "_processes", return_value=None):
            result = self.g.space()
        self.assertEqual(result["items"], [])
        self.assertIsNone(result["request_id"])

    def test_a_day_old_proposal_is_not_executed(self):
        self.make(".npm/_cacache/x")
        result = self.g.space()
        self.g.approve(result["request_id"], "yes")
        plan = json.loads((self.g.state / "space-plan.json").read_text())
        plan["at"] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=25)).isoformat()
        m.write_json(self.g.state / "space-plan.json", plan)
        with self.assertRaisesRegex(ValueError, "more than a day old"):
            self.g.free_space(result["request_id"])
        self.assertTrue((self.home / ".npm/_cacache/x").exists())

    def test_quarantine_from_earlier_versions_is_offered_and_purged_on_yes(self):
        cache = self.make(".npm/_npx/old/pkg.tgz").parent
        receipt = self.g.quarantine_tree(cache, "cache")
        result = self.g.space()
        set_aside = [i for i in result["items"] if i["kind"] == "quarantine"]
        self.assertEqual(len(set_aside), 1)
        self.g.approve(result["request_id"], "yes")
        self.g.free_space(result["request_id"])
        receipt_path = self.g.receipt_path("Quarantine", receipt["receipt"])
        self.assertEqual(json.loads(receipt_path.read_text())["state"], "purged")
        self.assertFalse((receipt_path.parent / "data").exists())

    def test_trash_is_a_separate_question(self):
        self.make(".Trash/old-photos.zip")
        self.make(".npm/_cacache/x")
        sizes = {str(self.home / ".Trash"): 2 * attention.GIB}
        real = self.g._du
        with patch.object(self.g, "_du", side_effect=lambda p: sizes.get(str(p)) or real(p)):
            result = self.g.space()
        self.assertNotIn(".Trash", json.dumps(result["items"]))
        self.assertIsNotNone(result["trash_request_id"])
        self.assertNotEqual(result["trash_request_id"], result["request_id"])
        with self.assertRaisesRegex(ValueError, "Trash needs"):
            self.g.empty_trash(result["request_id"])
        self.g.approve(result["trash_request_id"], "Owner: yes, empty the Trash")
        self.assertEqual(self.g.empty_trash(result["trash_request_id"])["removed"], 1)
        self.assertEqual(list((self.home / ".Trash").iterdir()), [])

    def test_unreadable_trash_is_unknown_not_empty(self):
        self.make(".Trash/x")
        real = self.g._du
        with patch.object(self.g, "_du", side_effect=lambda p: None if p.name == ".Trash" else real(p)):
            self.assertEqual(self.g.space()["trash"], {"status": "unknown"})

    def test_background_care_no_longer_quarantines_caches(self):
        cache = self.make(".npm/_npx/old/pkg.tgz").parent
        self.g.policy["auto_cleanup"] = True  # a saved pre-0.4.0 policy
        report = {"at": m.now(), "full_checked_at": m.now(), "disk": {"free_bytes": 1 * m.GIB},
                  "memory": {"swap_bytes": 0}, "load_average": [0, 0, 0], "alerts": []}
        with patch.object(self.g, "check", return_value=report), \
             patch.object(self.g, "package_updates", return_value={"items": [], "updated": 0}), \
             patch.object(self.g, "care_for_projects", return_value={"items": []}):
            result = self.g.maintain()
        self.assertNotIn("cleanup", [s["name"] for s in result["stages"]])
        self.assertTrue(cache.exists())
        self.assertFalse(m.DEFAULT_POLICY["auto_cleanup"])


def fake(outputs):
    def command(argv, timeout=20):
        key = " ".join(argv[:2])
        if key not in outputs:
            raise AssertionError("unexpected command " + key)
        return outputs[key]
    return command


def ok(stdout):
    return {"ok": True, "code": 0, "stdout": stdout, "stderr": ""}


class TimeMachineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.g = m.Guardian(Path(self.tmp.name) / "home", Path(self.tmp.name) / "state")

    def status(self, outputs):
        with patch.object(self.g, "_command", side_effect=fake(outputs)):
            return self.g.time_machine()

    def test_states(self):
        self.assertEqual(self.status({"tmutil destinationinfo": ok("tmutil: No destinations configured.\n")}),
                         {"status": "not_configured"})
        recent = (dt.datetime.now() - dt.timedelta(days=12)).strftime("%Y-%m-%d-%H%M%S")
        configured = ok("====================================================\nName          : Backup Drive\nKind          : Local\n")
        result = self.status({"tmutil destinationinfo": configured,
                              "tmutil latestbackup": ok(f"/Volumes/Backup Drive/{recent}.backup\n")})
        self.assertEqual(result["status"], "configured")
        self.assertAlmostEqual(result["age_days"], 12, delta=0.1)
        denied = {"ok": False, "code": 1, "stdout": "", "stderr": "Operation not permitted"}
        self.assertEqual(self.status({"tmutil destinationinfo": configured, "tmutil latestbackup": denied}),
                         {"status": "configured", "latest": None})
        self.assertEqual(self.status({"tmutil destinationinfo": {"ok": False, "code": None, "stdout": "", "stderr": "OSError"}}),
                         {"status": "unknown"})


class DigestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.g = m.Guardian(Path(self.tmp.name) / "home", Path(self.tmp.name) / "state")
        self.free = 200 * m.GIB
        self.backup = {"status": "configured", "latest": "2026-10-15T10:00:00", "age_days": 1.0}
        patch.object(self.g, "disk", side_effect=lambda: {"free_bytes": self.free, "total_bytes": 500 * m.GIB,
                     "used_percent": round(100 * (500 * m.GIB - self.free) / (500 * m.GIB), 1)}).start()
        patch.object(self.g, "time_machine", side_effect=lambda: dict(self.backup)).start()
        patch.object(self.g, "space", return_value={"bytes": 14 * m.GIB, "request_id": "r" * 32,
                     "items": [{"label": "Xcode build data"}, {"label": "npm cache"}]}).start()
        self.addCleanup(patch.stopall)

    def test_a_healthy_mac_sends_nothing(self):
        result = self.g.digest()
        self.assertFalse(result["notify"])
        self.assertIsNone(result["item"])

    def test_low_disk_comes_with_one_concrete_proposal(self):
        self.free = 40 * m.GIB  # 92% used
        item = self.g.digest()["item"]
        self.assertEqual((item["id"], item["severity"]), ("disk", "warning"))
        self.assertEqual(item["proposal"]["request_id"], "r" * 32)
        self.assertEqual(item["proposal"]["bytes"], 14 * m.GIB)

    def test_repeats_stay_quiet_and_getting_worse_is_news(self):
        self.free = 40 * m.GIB
        self.assertTrue(self.g.digest()["notify"])
        self.assertFalse(self.g.digest()["notify"])
        self.free = 4 * m.GIB
        escalated = self.g.digest()
        self.assertEqual(escalated["item"]["severity"], "critical")
        self.assertFalse(self.g.digest()["notify"])

    def test_dry_run_records_nothing(self):
        self.free = 40 * m.GIB
        self.assertTrue(self.g.digest(dry_run=True)["notify"])
        self.assertTrue(self.g.digest()["notify"])

    def test_only_the_most_urgent_item_is_sent(self):
        self.free = 40 * m.GIB
        self.backup = {"status": "configured", "latest": "2026-09-01T10:00:00", "age_days": 45.0}
        m.write_json(self.g.state / "maintenance.json", {"last_result": {"stages": [{"name": "projects", "ok": False}]}})
        first = self.g.digest()
        self.assertEqual(first["item"]["id"], "disk")
        self.assertEqual(sorted(first["quiet"]), ["maintenance:projects", "time-machine"])
        second = self.g.digest()
        self.assertIn(second["item"]["id"], ("time-machine", "maintenance:projects"))

    def test_backup_and_setup_reminders(self):
        self.backup = {"status": "configured", "latest": "2026-09-01T10:00:00", "age_days": 45.0}
        self.assertEqual(self.g.digest()["item"]["facts"]["days_ago"], 45)
        self.backup = {"status": "not_configured"}
        item = self.g.digest()["item"]
        self.assertEqual((item["id"], item["severity"]), ("time-machine-setup", "suggestion"))
        self.assertFalse(self.g.digest()["notify"])


class CommandLineTests(unittest.TestCase):
    def test_new_commands_run_in_an_isolated_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            (home / ".npm/_cacache").mkdir(parents=True)
            env = {k: v for k, v in os.environ.items() if k not in ("AGENT_ID", "BOSS_ID")}
            run = lambda *a: subprocess.run([sys.executable, str(ROOT / "native/mac_guardian.py"), "--home", str(home), *a],
                                            capture_output=True, text=True, timeout=120, env=env)
            space = run("space")
            self.assertEqual(space.returncode, 0, space.stderr)
            self.assertIn("disk", json.loads(space.stdout))
            refused = run("free-space", "--approval", "0" * 32)
            self.assertEqual(refused.returncode, 1)
            digest = run("digest", "--dry-run")
            self.assertEqual(digest.returncode, 0, digest.stderr)
            self.assertIsInstance(json.loads(digest.stdout)["notify"], bool)


if __name__ == "__main__":
    unittest.main()

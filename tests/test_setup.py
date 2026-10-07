import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("guardian_setup", ROOT / "native/mac_guardian.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.g = m.Guardian(self.home)
        m.write_json(self.g.state / "snapshot.json", {"at": m.now(), "full_checked_at": m.now()})
        self.platform = patch.object(m.sys, "platform", "darwin")
        self.platform.start()
        self.addCleanup(self.platform.stop)
        self.commands = patch.object(m, "command", return_value={"ok": True, "stderr": ""})
        self.commands.start()
        self.addCleanup(self.commands.stop)

    def test_first_storage_question_does_not_block_ready_local_care(self):
        result = self.g.setup_status()
        self.assertEqual(result["status"], "READY")
        self.assertTrue(result["care_ready"])
        self.assertIsNotNone(result["question"])
        self.assertFalse(result["question_blocks_local_care"])
        self.assertFalse(result["relay_verified"])
        self.assertEqual(result["github_auth"], "not-checked")

    def test_saved_local_only_answer_and_asked_question_are_not_asked_again(self):
        self.g.configure_cloud(asked=True)
        self.assertIsNone(self.g.setup_status()["question"])
        self.g.configure_cloud("none")
        result = m.Guardian(self.home).setup_status()
        self.assertIsNone(result["question"])
        self.assertEqual(result["cloud"]["provider"], "none")
        self.assertTrue(result["care_ready"])

    def test_stale_collectors_override_old_ready_conversation(self):
        m.write_json(self.g.state / "snapshot.json", {})
        result = self.g.setup_status()
        self.assertEqual(result["status"], "ATTENTION_NEEDED")
        self.assertEqual(result["next"], "check-collectors")
        self.assertFalse(result["care_ready"])

    def test_missing_job_requires_installation_before_claiming_scheduled_care(self):
        with patch.object(m, "command", return_value={"ok": False, "stderr": "job absent"}):
            result = self.g.setup_status()
        self.assertEqual(result["status"], "SETUP_NEEDED")
        self.assertEqual(result["next"], "install-native")
        self.assertFalse(result["care_ready"])

    def test_linux_fixture_cannot_claim_real_mac_readiness(self):
        with patch.object(m.sys, "platform", "linux"):
            result = self.g.setup_status()
        self.assertEqual(result["next"], "connect-real-mac")
        self.assertFalse(result["care_ready"])

    def test_pause_and_failed_worker_are_reported_without_resetting_state(self):
        self.g.pause(2)
        self.assertEqual(self.g.setup_status()["status"], "PAUSED")
        maintenance = m.read_json(self.g.state / "maintenance.json")
        maintenance["exception"] = True
        m.write_json(self.g.state / "maintenance.json", maintenance)
        self.assertEqual(self.g.setup_status()["next"], "inspect-maintenance-failure")
        self.assertTrue(m.read_json(self.g.state / "maintenance.json")["paused"])

    def test_readiness_remains_available_with_worker_lock_held(self):
        self.commands.stop()
        self.platform.stop()
        with self.g.lock():
            result = subprocess.run([sys.executable, str(ROOT / "native/mac_guardian.py"),
                                     "--home", str(self.home), "setup-status"],
                                    capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["scope"], "native-mac")

    def test_corrupt_preferences_fail_without_overwriting_receipts(self):
        path = self.g.state / "cloud.json"
        path.write_text("{broken preference")
        with self.assertRaises(json.JSONDecodeError):
            self.g.setup_status()
        self.assertEqual(path.read_text(), "{broken preference")

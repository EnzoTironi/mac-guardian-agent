"""The Mac-side bootstrap installs only files whose hashes match the image.

The bootstrap text is read from the generator the agent runs, so these tests run
the exact code Latch would run. Two substitutions keep this Mac untouched: a
stand-in curl serves files from a folder, and a stand-in install_native.py
records its call instead of loading LaunchAgents.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).parents[1]
GENERATOR = ROOT / "skills/mac-health/scripts/install-command.mjs"
BASE = "https://raw.githubusercontent.com/EnzoTironi/mac-guardian-agent/" + "a" * 40 + "/"


def template(name):
    text = GENERATOR.read_text()
    match = re.search(r"export const " + name + r" = `(.*?)`;\n", text, re.S)
    return match[1]


FAKE_CURL = """#!{python}
import sys, urllib.parse
from pathlib import Path
url = sys.argv[-1]
assert sys.argv[1:6] == ["-fsSL", "--proto", "=https", "--max-time", "60"], sys.argv
rel = url.split("/", 6)[-1]
source = Path({served!r}) / rel
if not source.is_file():
    sys.stderr.write("404 " + rel)
    sys.exit(22)
sys.stdout.buffer.write(source.read_bytes())
"""

FAKE_INSTALLER = b"""import json, os, sys
from pathlib import Path
here = Path(__file__).resolve().parents[1]
record = {"executable": sys.executable, "native": sorted(p.name for p in (here / "native").glob("*.py"))}
Path(os.environ["HOME"], "installed.json").write_text(json.dumps(record))
"""


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.home = root / "home"
        self.home.mkdir()
        self.served = root / "served"
        files = {"native/mac_guardian.py": b"helper", "native/workspace_care.py": b"care",
                 "scripts/install_native.py": FAKE_INSTALLER}
        for rel, data in files.items():
            (self.served / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.served / rel).write_bytes(data)
        self.manifest = {rel: hashlib.sha256(data).hexdigest() for rel, data in files.items()}
        curl = root / "curl"
        curl.write_text(FAKE_CURL.format(python=sys.executable, served=str(self.served)))
        curl.chmod(0o700)
        self.code = template("BOOTSTRAP").replace('"/usr/bin/curl"', repr(str(curl)))

    def run_bootstrap(self, base=BASE, manifest=None):
        env = {"HOME": str(self.home), "PATH": "/usr/bin:/bin"}
        return subprocess.run([sys.executable, "-I", "-c", self.code, base, json.dumps(manifest or self.manifest)],
                              capture_output=True, text=True, env=env, timeout=60)

    def app(self):
        return self.home / "Library/Application Support/MacGuardian"

    def test_verified_files_are_staged_and_installed_with_this_python(self):
        result = self.run_bootstrap()
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads((self.home / "installed.json").read_text())
        self.assertEqual(record["native"], ["mac_guardian.py", "workspace_care.py"])
        self.assertEqual(record["executable"], sys.executable)
        self.assertEqual(list(self.app().iterdir()), [], "the staging folder is removed")
        self.assertEqual(self.app().stat().st_mode & 0o777, 0o700)

    def test_a_changed_file_installs_nothing(self):
        (self.served / "native/workspace_care.py").write_bytes(b"substituted")
        result = self.run_bootstrap()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum mismatch for native/workspace_care.py", result.stderr)
        self.assertFalse((self.home / "installed.json").exists())
        self.assertEqual(list(self.app().iterdir()), [])

    def test_missing_download_and_unexpected_sources_are_refused(self):
        (self.served / "native/mac_guardian.py").unlink()
        self.assertIn("download failed", self.run_bootstrap().stderr)
        self.assertIn("unexpected download source", self.run_bootstrap(base="https://example.com/x/").stderr)
        unsafe = dict(self.manifest, **{"../evil.py": "0" * 64})
        self.assertIn("unsafe path", self.run_bootstrap(manifest=unsafe).stderr)
        self.assertFalse((self.home / "installed.json").exists())

    def test_bootstrap_text_is_exact_and_portable(self):
        for name in ("BOOTSTRAP", "UNINSTALL"):
            text = template(name)
            self.assertNotIn("\\", text, "a backslash would be rewritten by the JS template literal")
            compile(text.replace("${JSON.stringify(LABELS)}", "[]"), name, "exec")
        # Python 3.9 syntax: a too-old interpreter must reach the version message.
        self.assertNotRegex(template("BOOTSTRAP"), r"\bmatch\b|:=|\bf\"")


@unittest.skipUnless(subprocess.run(["which", "node"], capture_output=True).returncode == 0, "node not installed")
class GeneratorTests(unittest.TestCase):
    def run_node(self, *args, **env):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp)
            for rel, name in {"native/attention.py": "attention.py", "native/mac_guardian.py": "mac_guardian.py",
                              "native/workspace_care.py": "workspace_care.py",
                              "scripts/install_native.py": "install_native.py"}.items():
                (image / name).write_bytes((ROOT / rel).read_bytes())
            environment = {k: v for k, v in os.environ.items() if k not in ("AGENT_ID", "MAC_GUARDIAN_REVISION")}
            environment.update(MAC_GUARDIAN_NATIVE_DIR=str(image), **env)
            return subprocess.run(["node", str(GENERATOR), *args], capture_output=True, text=True, env=environment, timeout=30)

    def test_install_arguments_pin_the_repository_files(self):
        result = self.run_node("install", "--python", "/opt/homebrew/bin/python3", MAC_GUARDIAN_REVISION="b" * 40)
        self.assertEqual(result.returncode, 0, result.stderr)
        args = json.loads(result.stdout)
        self.assertEqual(args["argv"][:3], ["/opt/homebrew/bin/python3", "-I", "-c"])
        self.assertEqual(args["argv"][4], "https://raw.githubusercontent.com/EnzoTironi/mac-guardian-agent/" + "b" * 40 + "/")
        expected = {rel: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
                    for rel in ("native/attention.py", "native/mac_guardian.py", "native/workspace_care.py",
                                "scripts/install_native.py")}
        self.assertEqual(json.loads(args["argv"][5]), expected)
        self.assertTrue(args["network"])
        self.assertIn("~/Library/LaunchAgents", args["write_paths"])

    def test_unpinned_images_and_unsafe_interpreters_are_refused(self):
        self.assertIn("release_not_pinned", self.run_node("install", "--python", "/usr/local/bin/python3").stderr)
        for path in ("python3", "/tmp/x; rm -rf ~/python3", "/opt/../python3", "/usr/bin/env"):
            result = self.run_node("install", "--python", path, MAC_GUARDIAN_REVISION="b" * 40)
            self.assertNotEqual(result.returncode, 0, path)
        probe = json.loads(self.run_node("probe").stdout)
        self.assertEqual(probe["argv"][:2], ["/bin/sh", "-c"])
        self.assertNotIn("network", probe)
        self.assertNotIn("/usr/bin/python3 ", probe["argv"][2])


if __name__ == "__main__":
    unittest.main()

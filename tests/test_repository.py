"""Repository-level checks: what the image contains, what releases refuse, and language."""
import ast
import fnmatch
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).parents[1]


def docker_includes(path, rules):
    """Docker's .dockerignore: the last matching rule wins; '!' re-includes."""
    included = True
    for rule in rules:
        negate = rule.startswith("!")
        pattern = rule[1:] if negate else rule
        pattern = pattern.rstrip("/")
        if pattern.startswith("**/"):
            matches = any(fnmatch.fnmatch(part, pattern[3:]) for part in Path(path).parts)
        else:
            matches = fnmatch.fnmatch(path, pattern) or path.startswith(pattern + "/")
        if matches:
            included = negate
    return included


class RepositoryTests(unittest.TestCase):
    def test_build_context_holds_what_the_image_copies_and_nothing_private(self):
        rules = [line.strip() for line in (ROOT / ".dockerignore").read_text().splitlines()
                 if line.strip() and not line.startswith("#")]
        needed = ["Dockerfile", "prompt/AGENTS.md", "skills/mac-health/SKILL.md",
                  "skills/mac-health/scripts/install-command.mjs", "native/mac_guardian.py",
                  "native/workspace_care.py", "native/attention.py", "scripts/install_native.py",
                  "runtime/healthcheck.mjs"]
        for path in needed:
            self.assertTrue(docker_includes(path, rules), path)
        for path in ["plow-credentials", ".env", "listing.json", "private/report.json", "tests/test_install.py",
                     "media/campaign-v1/README.md", "scripts/build_publish.py", "native/__pycache__/x.pyc", ".git/HEAD"]:
            self.assertFalse(docker_includes(path, rules), path)
        copied = re.findall(r"^COPY (?:--\S+ )*(\S+) ", (ROOT / "Dockerfile").read_text(), re.M)
        for source in copied:
            self.assertTrue(docker_includes(source.rstrip("/") if not source.endswith("/") else source.rstrip("/") + "/x", rules)
                            or docker_includes(source.rstrip("/"), rules), source)

    def test_helper_messages_are_english(self):
        # Content-matching patterns stay multilingual on purpose; messages do not.
        allowed = re.compile(r"índice gerado|fatura|relat\[|emiss\[|titulo\|título")
        for name in ("native/mac_guardian.py", "native/workspace_care.py", "scripts/install_native.py",
                     "scripts/configure_listing.py", "scripts/build_publish.py"):
            tree = ast.parse((ROOT / name).read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and re.search(r"[ãçéêíóôúõá]", node.value):
                    with self.subTest(file=name, line=node.lineno):
                        self.assertRegex(node.value, allowed)


class ReleaseScriptTests(unittest.TestCase):
    """build_publish.py must refuse before Docker when the Mac could not fetch the commit."""

    def clone(self, tmp):
        source = Path(tmp) / "source"
        shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".git", "__pycache__", "private", "media"))
        git = ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "-C", str(source)]
        subprocess.run([*git, "init", "--quiet"], check=True)
        subprocess.run([*git, "add", "-A"], check=True)
        subprocess.run([*git, "commit", "--quiet", "-m", "fixture"], check=True)
        (source / "listing.json").write_text('{"slug": "demo", "name": "Demo", "blurb": "Demo"}\n')
        (source / ".git/info/exclude").write_text("listing.json\n")
        return source, git

    def run_script(self, source):
        return subprocess.run([sys.executable, str(source / "scripts/build_publish.py"), "ghcr.io/test/demo:v1"],
                              cwd=source, capture_output=True, text=True, timeout=60)

    def test_unpushed_or_dirty_trees_are_refused_before_building(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, git = self.clone(tmp)
            unpushed = self.run_script(source)
            self.assertEqual(unpushed.returncode, 2)
            self.assertIn("first; the Mac downloads the helper from GitHub", unpushed.stderr)
            (source / "README.md").write_text("changed")
            dirty = self.run_script(source)
            self.assertEqual(dirty.returncode, 2)
            self.assertIn("commit your changes first", dirty.stderr)


if __name__ == "__main__":
    unittest.main()

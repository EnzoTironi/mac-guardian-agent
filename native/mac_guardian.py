#!/usr/bin/env python3
"""Mac maintenance commands for a Plow/OpenClaw agent. Python standard library."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.parse
import unicodedata
import uuid
import zipfile
import xml.etree.ElementTree as ET
from xml.parsers.expat import ExpatError

if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))
from workspace_care import WorkspaceCare

GIB = 1024 ** 3
DAY = 86400
VERSION = "0.3.2"
DEFAULT_POLICY = {
    "cache_age_days": 14,
    "artifact_age_days": 30,
    "worktree_age_days": 30,
    "organization_age_days": 7,
    "free_disk_warning_gib": 20,
    "free_disk_critical_gib": 5,
    "swap_warning_gib": 4,
    "snapshot_stale_minutes": 45,
    "audit_stale_hours": 36,
    "history_days": 30,
    "history_max_samples": 2880,
    "auto_cleanup": True,
    "auto_organize": True,
    "auto_name": True,
    "auto_updates": True,
    "auto_projects": True,
    "auto_archive_worktrees": True,
    "project_backup_repo": "",
    "local_backup_root": "Backup/MacGuardian",
    "max_projects_per_run": 3,
    "max_project_refs_per_run": 20,
    "project_snapshot_max_mib": 256,
    "worktree_archive_max_mib": 1024,
    "target_free_disk_gib": 30,
    "maintenance_every_hours": 24,
    "organization_every_minutes": 15,
    "update_check_every_hours": 12,
    "update_retry_hours": 24,
    "max_updates_per_run": 3,
    "maintenance_max_seconds": 600,
    "backup_repo": "",
    "health_wiki_root": "Library/Application Support/MacGuardian/reports",
    "organization_roots": ["Downloads", "Desktop", "."],
    "excluded_roots": ["Documents", "Library/Mobile Documents", "Library/CloudStorage"],
    "organization_stable_minutes": 120,
    "organization_max_files_per_run": 100,
    "organization_max_file_mib": 512,
    "wiki_max_files": 10000,
    "file_wiki_root": "Wiki",
    "project_roots": [".", "Code", ".codex/worktrees", "tryzoen-worktrees"],
    "cache_paths": [".npm/_npx", ".cache/uv", "Library/Caches/Aside/Default/Cache",
                    "Library/Caches/Aside/Default/Code Cache"],
    "backup_roots": ["Library/Application Support/MacGuardian/reports"],
    "max_scan_directories": 20000,
    "max_scan_seconds": 90,
}
PROTECTED = {".ssh", ".gnupg", ".secrets", ".config", ".codex", ".claude",
             ".openclaw", ".hermes", ".git", "Library", "Applications", "Backup",
             "Applications (Parallels)", "Parallels", "VirtualBox VMs"}
SKIP_NAMES = {"node_modules", "target", ".git", ".venv", "venv", ".next", "dist",
              "build", "__pycache__", ".DS_Store"}
BUNDLE_SUFFIXES = {".app", ".photoslibrary", ".photolibrary", ".musiclibrary", ".framework",
                   ".xcodeproj", ".xcworkspace", ".bundle", ".fcpbundle", ".logicx", ".band",
                   ".vmwarevm", ".pvm", ".utm", ".pages", ".numbers", ".key"}
SECRET_NAME = re.compile(r"(^\.env($|\.|rc$)|^\.(?:npmrc|pypirc|netrc|authinfo)$|kubeconfig|credentials|secret|token|password|"
                         r"\.(pem|key|p12|pfx|kdbx)$|^id_(rsa|ed25519))", re.I)
SECRET_CONTENT = re.compile(rb"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----|"
                            rb"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,}|"
                            rb"AKIA[A-Z0-9]{16}|sk-(?:proj-)?[A-Za-z0-9_-]{20,})\b|"
                            rb"(?i:(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)"
                            rb"[ \t]*[:=][ \t]*[\"']?[A-Za-z0-9/+_-]{16,})")


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def private_text(path, value):
    path = Path(path)
    if path.is_symlink():
        raise ValueError(f"Destino é um link simbólico: {path}")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix="." + path.name + "-", delete=False) as f:
            tmp = Path(f.name)
            f.write(value)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(path)
    finally:
        if tmp:
            tmp.unlink(missing_ok=True)


def write_json(path, value):
    private_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


def age_seconds(stamp):
    try:
        value = dt.datetime.fromisoformat(stamp)
        return time.time() - value.timestamp() if value.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


def inventory_changes(current, previous, key, fields, kind):
    """Compare identities without exposing program arguments or granting trust."""
    before = {item[key]: item for item in previous if key in item}
    after = {item[key]: item for item in current if key in item}
    changes = []
    for identity in sorted(before.keys() | after.keys()):
        old, new = before.get(identity), after.get(identity)
        changed = [field for field in fields if old and new and old.get(field) != new.get(field)]
        if old and new and (not changed or new.get("inventory_error") or new.get("error")):
            continue
        item = new or old
        changes.append({"kind": kind, "identity": identity,
                        "name": item.get("name", item.get("label", Path(identity).name)),
                        "change": "added" if old is None else "removed" if new is None else "modified",
                        "fields": changed})
    return changes


def command(argv, timeout=20, env=None):
    """Never invoke a shell or include process arguments in inventory."""
    try:
        p = subprocess.run([str(v) for v in argv], capture_output=True,
                           text=True, timeout=timeout, env=env, stdin=subprocess.DEVNULL)
        return {"ok": p.returncode == 0, "code": p.returncode,
                "stdout": p.stdout[-2000000:], "stderr": p.stderr[-4000:],
                "stdout_truncated": len(p.stdout) > 2000000}
    except subprocess.TimeoutExpired as e:
        def decode(value):
            return value.decode(errors="replace") if isinstance(value, bytes) else value or ""
        return {"ok": False, "code": None, "stdout": decode(e.stdout)[-100000:],
                "stderr": ("TimeoutExpired\n" + decode(e.stderr))[-4000:]}
    except OSError as e:
        return {"ok": False, "code": None, "stdout": "", "stderr": type(e).__name__}


def require(argv, timeout=120):
    r = command(argv, timeout)
    if not r["ok"]:
        raise RuntimeError(f"{argv[0]} falhou: {r['stderr'][:800]}")
    return r["stdout"].strip()


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def safe_inside(path, root):
    """Refuse symlink components as well as escape paths."""
    path, root = Path(os.path.abspath(path)), Path(root).resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError(f"Caminho fora do escopo: {path}")
    for part in [path, *path.parents]:
        if part == root:
            break
        if part.is_symlink():
            raise ValueError(f"Link simbólico protegido: {part}")
    return path


def tree_stats(path, deadline=None):
    path = Path(path)
    newest, ctime_ns, size, count = 0, 0, 0, 0
    stack = [path]
    while stack:
        if deadline and time.monotonic() > deadline:
            raise TimeoutError("Limite de varredura")
        p = stack.pop()
        s = p.lstat()
        if stat.S_ISLNK(s.st_mode):
            continue
        newest = max(newest, s.st_mtime)
        ctime_ns = max(ctime_ns, s.st_ctime_ns)
        if stat.S_ISDIR(s.st_mode):
            stack.extend(p.iterdir())
        elif stat.S_ISREG(s.st_mode):
            size += s.st_size
            count += 1
    return {"bytes": size, "files": count, "newest_mtime": newest, "newest_ctime_ns": ctime_ns}


def in_use(path):
    r = command(["lsof", "-t", "+D" if Path(path).is_dir() else "--", str(path)], 12)
    # lsof 1 with no output means no open files; timeout/permissions mean unknown.
    return r["code"] not in (0, 1) or bool(r["stdout"].strip()) or bool(r["stderr"].strip())


def signature(path, verify=False):
    info = command(["codesign", "-dv", "--verbose=4", str(path)], 8)
    raw = info["stdout"] + info["stderr"]
    result = {"signed": info["ok"], "team": "", "authority": [],
              "verified": None, "malware_status": "unknown"}
    for line in raw.splitlines():
        if line.startswith("TeamIdentifier="):
            result["team"] = line.split("=", 1)[1]
        if line.startswith("Authority="):
            result["authority"].append(line.split("=", 1)[1])
    if verify:
        verified = command(["codesign", "--verify", "--strict", str(path)], 15)
        result["verified"] = verified["ok"] if verified["code"] is not None else None
        if not verified["ok"]:
            result["verify_error"] = verified["stderr"][-500:]
        gate = command(["spctl", "--assess", "--type", "execute", str(path)], 15)
        result["gatekeeper"] = ("accepted" if gate["ok"] else
                                "unknown" if gate["code"] is None else "review")
    return result


class Guardian(WorkspaceCare):
    cloud_exclusions = tuple(DEFAULT_POLICY["excluded_roots"])
    secret_name = SECRET_NAME
    secret_content = SECRET_CONTENT
    skip_names = SKIP_NAMES
    _safe = staticmethod(safe_inside)
    _hash = staticmethod(digest)
    _read = staticmethod(read_json)
    _write = staticmethod(write_json)
    _now = staticmethod(now)

    def _busy(self, path):
        return in_use(path)

    def _command(self, argv, timeout=20):
        return command(argv, timeout)

    def __init__(self, home=None, state=None):
        self.home = Path(home or Path.home()).resolve()
        self.state = Path(state or self.home / "Library/Application Support/MacGuardian/state").resolve()
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.state.chmod(0o700)
        self.policy = DEFAULT_POLICY | read_json(self.state / "policy.json", {})

    @contextlib.contextmanager
    def lock(self):
        with (self.state / "lock").open("a") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield

    def record(self, kind, details):
        p = self.state / "operations.jsonl"
        with p.open("a") as f:
            f.write(json.dumps({"at": now(), "kind": kind, **details}, ensure_ascii=False) + "\n")
        p.chmod(0o600)
        if p.stat().st_size > 2 * 1024 * 1024:
            p.write_text("\n".join(p.read_text().splitlines()[-1000:]) + "\n")

    def relative(self, path):
        return str(Path(path).relative_to(self.home))

    def excluded(self, path):
        path = Path(os.path.abspath(path))
        resolved = path.resolve()
        return any(path == self.home / r or path.is_relative_to(self.home / r) or
                   resolved == (self.home / r).resolve() or resolved.is_relative_to((self.home / r).resolve())
                   for r in set(self.policy["excluded_roots"] + DEFAULT_POLICY["excluded_roots"] +
                                [self.policy["local_backup_root"]]))

    def projects(self):
        if hasattr(self, "_project_cache"):
            yield from self._project_cache
            return
        markers = {"package.json", "Cargo.toml", "pyproject.toml", "go.mod", "Package.swift", "CMakeLists.txt", ".git"}
        roots = [os.path.abspath(self.home / name) for name in sorted(self.policy["project_roots"], key=lambda n: n == ".")]
        inventory = read_json(self.state / "project-discovery.json", {})
        pending = inventory.get("pending", []) if inventory.get("roots") == roots else []
        if not pending:
            pending = list(reversed(roots))
        seen = set(inventory.get("known", [])) if inventory.get("roots") == roots else set()
        visited = set(inventory.get("visited", [])) if inventory.get("pending") and inventory.get("roots") == roots else set()
        deadline = time.monotonic() + self.policy["max_scan_seconds"]
        count = 0
        while pending and count < self.policy["max_scan_directories"] and time.monotonic() < deadline:
            p = Path(os.path.abspath(pending.pop()))
            if str(p) in visited or not p.is_relative_to(self.home) or self.excluded(p) or p.is_symlink() or not p.is_dir():
                continue
            if not any(p.is_relative_to(Path(root)) for root in roots) or (p != self.home and p.name in PROTECTED and str(p) not in roots):
                continue
            visited.add(str(p))
            count += 1
            try:
                entries = sorted(p.iterdir())
                if markers & {entry.name for entry in entries}:
                    seen.add(str(p))
                pending.extend(str(entry) for entry in reversed(entries) if entry.is_dir() and
                    not entry.is_symlink() and entry.name not in SKIP_NAMES | PROTECTED and
                    not entry.name.startswith(".") and entry.suffix.lower() not in BUNDLE_SUFFIXES)
            except OSError:
                continue
        valid = [Path(name) for name in sorted(seen) if Path(name).is_relative_to(self.home) and
            any(Path(name).is_relative_to(Path(root)) for root in roots) and not self.excluded(Path(name)) and
            not Path(name).is_symlink() and any((Path(name) / marker).exists() for marker in markers)]
        recognized = set(valid)
        self._project_cache = [p for p in valid if (p / ".git").exists() or not any(parent in recognized for parent in p.parents)]
        write_json(self.state / "project-discovery.json", {"roots": roots, "pending": pending,
                   "known": [str(p) for p in valid], "visited": sorted(visited) if pending else [],
                   "complete": not pending, "at": now()})
        if pending:
            self.record("scan_incomplete", {"reason": "project scan budget; next cycle resumes"})
        yield from self._project_cache

    def eligible(self, path, kind):
        path = safe_inside(path, self.home)
        if self.excluded(path):
            raise ValueError("Pasta excluída da manutenção local")
        if kind == "cache":
            valid = False
            for rel in self.policy["cache_paths"]:
                root = safe_inside(self.home / rel, self.home)
                if path != root and path.is_relative_to(root):
                    valid = True
            if not valid:
                raise ValueError("Cache fora da lista autorizada")
            days = self.policy["cache_age_days"]
        elif kind in ("node_modules", "target"):
            if path.name != kind:
                raise ValueError("Nome de artefato inválido")
            allowed = any(path.is_relative_to(self.home / r)
                          for r in self.policy["project_roots"])
            if not allowed:
                raise ValueError("Projeto fora da lista autorizada")
            parent = path.parent
            if kind == "node_modules":
                if not (parent / "package.json").is_file() or not any(
                    (parent / f).is_file() for f in ("package-lock.json", "pnpm-lock.yaml",
                                                    "yarn.lock", "bun.lock", "bun.lockb")):
                    raise ValueError("Manifesto e lockfile necessários")
            elif not (parent / "Cargo.toml").is_file() or not (parent / "Cargo.lock").is_file():
                raise ValueError("Cargo.toml e Cargo.lock necessários")
            if (self.home / ".codex/worktrees") in path.parents:
                raise ValueError("Worktree gerenciado pelo Codex: usar arquivamento nativo")
            git = command(["git", "-C", str(parent), "rev-parse", "--show-toplevel"])
            if not git["ok"]:
                raise ValueError("Projeto sem Git verificável")
            repo = Path(git["stdout"].strip())
            if require(["git", "-C", str(repo), "status", "--porcelain",
                        "--untracked-files=normal"]):
                raise ValueError("Projeto com alterações locais")
            tracked = require(["git", "-C", str(repo), "ls-files", "--",
                               str(path.relative_to(repo))])
            if tracked:
                raise ValueError("Artefato contém arquivos versionados")
            days = self.policy["artifact_age_days"]
        else:
            raise ValueError("Tipo de limpeza não autorizado")
        if not path.exists() or not path.is_dir():
            raise ValueError("Diretório ausente")
        data = tree_stats(path, time.monotonic() + 15)
        if data["newest_mtime"] > time.time() - days * DAY:
            raise ValueError("Arquivo ou diretório recente")
        return data

    def cleanup_plan(self):
        candidates, skipped = [], []
        possible = []
        for rel in self.policy["cache_paths"]:
            root = self.home / rel
            if root.is_dir() and not root.is_symlink():
                possible.extend((p, "cache") for p in root.iterdir()
                                if p.is_dir() and not p.is_symlink())
        for root in self.projects():
            possible.extend((root / name, name) for name in ("node_modules", "target")
                            if (root / name).is_dir())
        for path, kind in possible:
            try:
                stats = self.eligible(path, kind)
                if stats["bytes"]:
                    s = path.stat()
                    candidates.append({"path": self.relative(path), "kind": kind,
                                       "device": s.st_dev, "inode": s.st_ino, **stats})
            except (OSError, ValueError, RuntimeError, TimeoutError) as e:
                skipped.append({"path": str(path), "reason": str(e)})
        plan = {"created_at": now(), "items": candidates, "skipped": skipped,
                "reclaimable_bytes": sum(p["bytes"] for p in candidates),
                "scope": "Only disposable files; managed worktrees require Codex archive."}
        write_json(self.state / "cleanup-plan.json", plan)
        return plan

    def clean(self, apply=False):
        if not apply:
            return self.cleanup_plan()
        plan = read_json(self.state / "cleanup-plan.json")
        age = age_seconds(plan.get("created_at")) if plan else None
        if age is None or not 0 <= age <= 3600:
            raise ValueError("Execute plan antes de clean --apply; plano válido por uma hora")
        results = []
        for item in plan["items"]:
            path = self.home / item["path"]
            try:
                stats = self.eligible(path, item["kind"])
                s = path.stat()
                if (s.st_dev, s.st_ino) != (item["device"], item["inode"]):
                    raise ValueError("Caminho substituído após o plano")
                if any(stats[key] != item.get(key) for key in ("bytes", "files", "newest_mtime", "newest_ctime_ns")):
                    raise ValueError("Conteúdo alterado após o plano")
                if in_use(path):
                    raise ValueError("Em uso ou uso não verificável")
                receipt = self.quarantine_tree(path, item["kind"])
                result = {"path": str(path), "removed": True, "bytes": stats["bytes"],
                          "quarantined": True, **receipt}
            except (OSError, ValueError, RuntimeError, TimeoutError) as e:
                result = {"path": str(path), "removed": False, "reason": str(e)}
            results.append(result)
            self.record("cleanup", result)
        write_json(self.state / "cleanup-plan.json", {})
        return {"items": results, "deleted_bytes": 0, "freed_bytes": 0,
                "quarantined_bytes": sum(x.get("bytes", 0) for x in results if x["removed"])}

    def folders(self):
        result = []
        for p in sorted(self.home.iterdir(), key=lambda p: p.name.lower()):
            if not p.is_dir() or p.is_symlink() or self.excluded(p):
                continue
            role = ("Configuração de ferramenta" if p.name.startswith(".") else
                    "Aplicativos" if p.name in ("Applications", "Applications (Parallels)") else
                    "Sistema e dados de apps" if p.name == "Library" else
                    "Projetos" if (p / ".git").exists() or p.name in ("Code", "go") else
                    "Caixa de entrada" if p.name in ("Desktop", "Downloads") else "Arquivos pessoais")
            result.append({"name": p.name, "path": str(p), "category": role,
                           "protected": p.name in PROTECTED or p.name.startswith(".")})
        return result

    def worktrees(self):
        entries, common_seen = [], set()
        for project in self.projects():
            result = command(["git", "-C", str(project), "rev-parse", "--git-common-dir"])
            if not result["ok"]:
                continue
            common = (project / result["stdout"].strip()).resolve()
            if common in common_seen:
                continue
            common_seen.add(common)
            listing = require(["git", "-C", str(project), "worktree", "list", "--porcelain", "-z"])
            for block in listing.split("\0\0"):
                fields = {}
                for field in block.split("\0"):
                    key, _, val = field.partition(" ")
                    if key:
                        fields[key] = val
                if not fields.get("worktree"):
                    continue
                path = Path(fields["worktree"])
                item = {"path": str(path), "repository": str(project),
                        "branch": fields.get("branch", "detached"), "head": fields.get("HEAD", ""),
                        "locked": "locked" in fields, "prunable": "prunable" in fields,
                        "managed_by_codex": path.is_relative_to(self.home / ".codex/worktrees"),
                        "removal_status": "review"}
                if item["managed_by_codex"]:
                    item["removal_status"] = "use_codex_archive"
                elif not (path / ".git").is_file():
                    item["removal_status"] = "primary_or_unavailable"
                else:
                    status = command(["git", "-C", str(path), "status", "--porcelain"])
                    ignored = command(["git", "-C", str(path), "ls-files", "--others",
                                       "--ignored", "--exclude-standard"])
                    item["dirty"] = not status["ok"] or bool(status["stdout"].strip())
                    item["has_ignored_files"] = not ignored["ok"] or bool(ignored["stdout"].strip())
                    item["local_commits"] = command(["git", "-C", str(path), "rev-list",
                                                    "--count", "HEAD", "--not", "--remotes"])["stdout"].strip()
                entries.append(item)
        write_json(self.state / "worktrees.json", {"at": now(), "items": entries})
        return {"items": entries}

    def remove_worktree(self, path, apply=False):
        path = safe_inside(Path(path).expanduser(), self.home)
        if self.excluded(path) or not any(path.is_relative_to(self.home / r) for r in self.policy["project_roots"]):
            raise ValueError("Worktree fora das raízes locais permitidas")
        if path.is_relative_to(self.home / ".codex/worktrees"):
            raise ValueError("Worktree do Codex exige arquivamento gerenciado")
        if not (path / ".git").is_file() or (path / ".git").is_symlink():
            raise ValueError("Só worktrees secundários podem ser arquivados")
        if not apply:
            return {"path": str(path), "ready": False,
                    "steps": ["snapshot em branch privada", "backup local completo com segredos",
                              "verificação de conteúdo e arquivos em uso", "arquivamento reversível"]}
        repo = self.private_project_repo()
        snapshot = self.project_snapshot(path, repo)
        return self.archive_worktree(path, snapshot)

    def background(self, previous=None):
        items = []
        for root in [self.home / "Library/LaunchAgents", Path("/Library/LaunchAgents"),
                     Path("/Library/LaunchDaemons")]:
            if not root.is_dir():
                continue
            for path in sorted(root.glob("*.plist")):
                try:
                    with path.open("rb") as f:
                        p = plistlib.load(f)
                    exe = p.get("Program") or (p.get("ProgramArguments") or [""])[0]
                    flags = []
                    if exe.endswith(("/sh", "/bash", "/zsh", "/fish", "/python3", "/node")):
                        flags.append("wrapper: revisar argumentos localmente")
                    if exe and not Path(exe).exists():
                        flags.append("executável ausente ou relativo")
                    if any(x in exe for x in ("/tmp/", "/Downloads/", "/.Trash/")):
                        flags.append("executável em diretório temporário")
                    identity = None
                    if exe and Path(exe).is_absolute():
                        try:
                            binary = Path(exe).resolve()
                            s = binary.stat()
                            identity = {"path": str(binary), "device": s.st_dev, "inode": s.st_ino,
                                        "bytes": s.st_size, "mtime_ns": s.st_mtime_ns}
                        except OSError:
                            flags.append("identidade do executável indisponível")
                    items.append({"label": p.get("Label", path.stem), "plist": str(path),
                                  "sha256": digest(path), "executable": exe,
                                  "binary_identity": identity,
                                  "review": flags, "trust": "unreviewed"})
                except (OSError, ValueError, plistlib.InvalidFileException, ExpatError) as e:
                    items.append({"plist": str(path), "error": type(e).__name__, "trust": "unknown"})
        if previous is None:
            previous = read_json(self.state / "snapshot.json", {}).get("background", [])
        before = {item["plist"]: item for item in previous}
        for item in items:
            old = before.get(item["plist"])
            # Older versions did not collect binary_identity: seed it once.
            fields = ["sha256", "executable"] + (["binary_identity"] if old and "binary_identity" in old else [])
            item["change"] = ("new" if old is None else "modified" if
                              any(old.get(key) != item.get(key) for key in fields) else "unchanged")
        return items

    def applications(self, roots=None):
        paths = []
        for root in roots if roots is not None else [Path("/Applications"), self.home / "Applications"]:
            if not root.is_dir():
                continue
            for p in root.iterdir():
                if p.suffix == ".app":
                    paths.append(p)
                elif p.is_dir() and not p.is_symlink():
                    paths.extend(p.glob("*.app"))
        def inspect(path):
            item = {"name": path.stem, "path": str(path), "update_status": "unknown"}
            try:
                with (path / "Contents/Info.plist").open("rb") as f:
                    p = plistlib.load(f)
                item.update({"bundle_id": p.get("CFBundleIdentifier", ""),
                             "version": p.get("CFBundleShortVersionString", p.get("CFBundleVersion", "")),
                             "update_feed": p.get("SUFeedURL", "")})
            except (OSError, ValueError, plistlib.InvalidFileException, ExpatError) as e:
                item["inventory_error"] = True
                item["inventory_error_type"] = type(e).__name__
            item["signature"] = signature(path, verify=True)
            return item
        with ThreadPoolExecutor(max_workers=4) as pool:
            return list(pool.map(inspect, sorted(paths)))

    def updates(self):
        results = {}
        # Refreshing the catalogue does not install or upgrade any package.
        if shutil.which("brew"):
            refresh = command(["brew", "update"], 180)
            results["brew_refresh"] = {"ok": refresh["ok"], "error": refresh["stderr"][-1000:]}
            outdated = command(["brew", "outdated", "--json=v2", "--greedy"], 90)
            try:
                results["brew_outdated"] = json.loads(outdated["stdout"]) if outdated["ok"] else outdated
            except ValueError:
                results["brew_outdated"] = {"ok": False, "error": "invalid JSON"}
            casks = command(["brew", "info", "--json=v2", "--installed", "--cask"], 60)
            try:
                results["brew_casks"] = json.loads(casks["stdout"]).get("casks", []) if casks["ok"] else []
            except ValueError:
                results["brew_casks"] = []
        results["macos"] = command(["softwareupdate", "--list"], 120)
        results["app_store"] = command(["mas", "outdated"], 60) if shutil.which("mas") else {
            "ok": False, "stderr": "mas não instalado; cobertura da App Store desconhecida", "stdout": ""}
        return results

    def xprotect(self):
        packages = command(["pkgutil", "--pkgs"])
        if not packages["ok"]:
            return {"status": "unknown", "error": packages["stderr"]}
        ids = [p for p in packages["stdout"].splitlines()
               if re.fullmatch(r"com\.apple\.pkg\.(XProtectPayloads|XProtectPlistConfigData|MRTConfigData)[A-Za-z0-9_.-]*", p)]
        return {"status": "installed" if ids else "unknown",
                "receipts": [{"id": p, **command(["pkgutil", "--pkg-info", p])} for p in ids],
                "definition_freshness": "unknown",
                "limitation": "Recibos de instalação não comprovam definição mais recente nem ausência de malware."}

    def health_history(self, report=None, hours=24):
        path = self.state / "health-history.json"
        try:
            points = read_json(path, [])
            if not isinstance(points, list):
                raise ValueError("Histórico inválido")
        except ValueError:
            if report and path.exists():
                path.replace(self.state / ("health-history-corrupt-" + uuid.uuid4().hex + ".json"))
                self.record("history_recovered", {"reason": "invalid JSON or type"})
            points = []
        points = [p for p in points if isinstance(p, dict) and isinstance(p.get("free_bytes"), (int, float))]
        if report:
            points.append({"at": report["at"], "free_bytes": report["disk"]["free_bytes"],
                           "swap_bytes": report["memory"]["swap_bytes"],
                           "load_1m": report["load_average"][0]})
            points = [p for p in points if (age := age_seconds(p.get("at"))) is not None
                      and 0 <= age <= self.policy["history_days"] * DAY]
            points = points[-self.policy["history_max_samples"]:]
            write_json(path, points)
        selected = [p for p in points if (age := age_seconds(p.get("at"))) is not None
                    and 0 <= age <= hours * 3600]
        delta = None
        if len(selected) > 1:
            delta = selected[-1]["free_bytes"] - selected[0]["free_bytes"]
        return {"hours": hours, "samples": len(selected), "free_bytes_change": delta,
                "points": selected}

    def package_updates(self, state, apply=True, deadline=None):
        deadline = deadline or time.monotonic() + self.policy["maintenance_max_seconds"]
        attempts = state.setdefault("package_attempts", {})
        results, attempted = [], 0
        def run(argv, seconds=90, env=None):
            remaining = deadline - time.monotonic() - 20
            if remaining <= 0:
                raise TimeoutError("Próxima rotina retoma as atualizações")
            return command(argv, min(seconds, remaining), env=env)
        def update(key, argv, verify, target):
            nonlocal attempted
            age = age_seconds(attempts.get(key, {}).get("at"))
            if attempted >= self.policy["max_updates_per_run"] or (age is not None and age <
                    self.policy["update_retry_hours"] * 3600):
                return
            if not apply:
                results.append({"package": key, "status": "planned"})
                attempted += 1
                return
            payload = {"package": key, "command": argv, "target": target}
            if not self.consume_approval("package_update", payload):
                attempted += 1
                results.append({"package": key, "status": "awaiting_approval",
                                **self.request_approval("package_update", payload)})
                return
            attempted += 1
            attempts[key] = {"at": now(), "status": "started"}
            write_json(self.state / "maintenance.json", state)
            # Keep old kegs while running processes still reference them.
            env = dict(os.environ, HOMEBREW_NO_AUTO_UPDATE="1", HOMEBREW_NO_INSTALL_CLEANUP="1",
                       HOMEBREW_NO_ASK="1", HOMEBREW_NO_SUDO="1", HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK="1")
            try:
                result = run(argv, 180, env)
                verified = result["ok"] and verify()
            except (OSError, ValueError, RuntimeError, TimeoutError, KeyError) as e:
                result, verified = {"ok": False, "stderr": str(e)}, False
            entry = {"package": key, "status": "updated" if verified else "failed",
                     "error": (result["stderr"][-800:] or "Verificação pós-instalação falhou") if not verified else "",
                     "requires_user_action": bool(re.search(r"sudo|password|licen[cs]e|EULA|restart required",
                                                             result["stderr"], re.I))}
            attempts[key].update(entry)
            write_json(self.state / "maintenance.json", state)
            self.record("package_update", entry)
            results.append(entry)
        if shutil.which("brew"):
            age = age_seconds(state.get("last_update_check_at"))
            if apply and (age is None or age > self.policy["update_check_every_hours"] * 3600):
                if not run(["brew", "update"], 180)["ok"]:
                    raise RuntimeError("Catálogo Homebrew indisponível; atualizações adiadas")
                state["last_update_check_at"] = now()
                write_json(self.state / "maintenance.json", state)
            raw = run(["brew", "outdated", "--json=v2", "--greedy"])
            if not raw["ok"]:
                raise RuntimeError("Lista Homebrew indisponível")
            outdated = json.loads(raw["stdout"])
            metadata = {}
            for kind, group, key in [("formula", "formulae", "name"), ("cask", "casks", "token")]:
                raw = run(["brew", "info", "--json=v2", "--installed", "--" + kind])
                if not raw["ok"] or raw.get("stdout_truncated"):
                    raise RuntimeError("Metadados Homebrew indisponíveis")
                installed = json.loads(raw["stdout"])
                if group not in installed:
                    raise ValueError("Metadados Homebrew incompletos")
                metadata.update({(kind, p[key]): p for p in installed[group]})
            for kind, group in [("cask", "casks"), ("formula", "formulae")]:
                for item in outdated.get(group, []):
                    token = item["name"]
                    age = age_seconds(attempts.get("brew:" + token, {}).get("at"))
                    if attempted >= self.policy["max_updates_per_run"]:
                        break
                    if age is not None and age < self.policy["update_retry_hours"] * 3600:
                        continue
                    info = metadata.get((kind, token), {})
                    if not re.fullmatch(r"[a-z0-9][a-z0-9+_.@-]*", token) or item.get("pinned") or info.get("pinned"):
                        continue
                    if info.get("tap") != ("homebrew/cask" if kind == "cask" else "homebrew/core"):
                        results.append({"package": "brew:" + token, "status": "unverified_source"})
                        continue
                    if kind == "cask":
                        artifacts = info.get("artifacts", [])
                        # pkg installers, uninstall scripts and hooks can need privileges.
                        if any(not isinstance(a, dict) or set(a) - {"app", "binary", "zap", "target"} for a in artifacts):
                            results.append({"package": "brew:" + token, "status": "needs_installer_review"})
                            continue
                        names = [Path(a).name for row in artifacts for a in row.get("app", []) if isinstance(a, str)]
                        paths = [root / name for root in (Path("/Applications"), self.home / "Applications")
                                 for name in names if (root / name).exists()]
                    else:
                        # Upgrading a formula can also upgrade its dependencies.
                        dependencies, pending, valid = set(), [token], True
                        while pending:
                            dep = pending.pop()
                            if dep in dependencies:
                                continue
                            meta = metadata.get(("formula", dep), {})
                            if meta.get("tap") != "homebrew/core" or meta.get("pinned"):
                                valid = False
                                break
                            dependencies.add(dep)
                            pending.extend(meta.get("dependencies", []))
                        if not valid:
                            results.append({"package": "brew:" + token, "status": "dependency_requires_review"})
                            continue
                        paths = []
                        for dep in sorted(dependencies):
                            cellar = run(["brew", "--cellar", dep], 15)
                            path = Path(cellar["stdout"].strip()) if cellar["ok"] and cellar["stdout"].strip() else None
                            if path is None or not path.is_absolute() or not path.is_dir():
                                paths.clear()
                                break
                            paths.append(path)
                    if not paths or any(in_use(p) for p in paths):
                        results.append({"package": "brew:" + token, "status": "deferred_until_idle"})
                        continue
                    def verify(token=token, kind=kind, group=group, paths=paths):
                        check = run(["brew", "outdated", "--" + kind, "--json=v2", "--greedy", token])
                        if not check["ok"] or check.get("stdout_truncated"):
                            return False
                        data = json.loads(check["stdout"])
                        if group not in data or data[group] != []:
                            return False
                        if kind == "cask":
                            signatures = [signature(p, verify=True) for p in paths]
                            return all(s.get("signed") and s.get("verified") is True and
                                       s.get("gatekeeper") == "accepted" for s in signatures)
                        return True
                    update("brew:" + token, ["brew", "upgrade", "--" + kind, token], verify, item)
        if shutil.which("mas"):
            raw = run(["mas", "outdated"], 60)
            if not raw["ok"]:
                results.append({"package": "app-store", "status": "unavailable"})
            else:
                for line in raw["stdout"].splitlines():
                    match = re.match(r"\s*(\d+)\s+(.+?)\s+\([^()]*->[^()]*\)\s*$", line)
                    if not match:
                        continue
                    app_id, name = match.groups()
                    apps = read_json(self.state / "snapshot.json", {}).get("applications", [])
                    paths = [Path(a["path"]) for a in apps if a["name"] == name]
                    if not paths or any(in_use(p) for p in paths):
                        results.append({"package": "mas:" + app_id, "status": "deferred_until_idle"})
                        continue
                    def verify(app_id=app_id):
                        check = run(["mas", "outdated"], 60)
                        return check["ok"] and not any(row.split() and row.split()[0] == app_id
                                                      for row in check["stdout"].splitlines())
                    update("mas:" + app_id, ["mas", "upgrade", app_id], verify, line.strip())
        return {"items": results, "updated": sum(r["status"] == "updated" for r in results)}

    def maintain(self, apply=True):
        started = time.monotonic()
        deadline = started + self.policy["maintenance_max_seconds"]
        state = read_json(self.state / "maintenance.json", {})
        report = self.check()
        if state.get("paused"):
            until = state.get("paused_until")
            if not until or (age := age_seconds(until)) is None or age < 0:
                return {"status": "paused", "monitoring": True}
            state["paused"] = False
        result = {"at": now(), "mode": "automatic" if apply else "preview", "stages": []}
        def stage(name, invoke):
            try:
                data = invoke()
                result["stages"].append({"name": name, "ok": True, "result": data})
                return True
            except (OSError, ValueError, RuntimeError, TimeoutError, KeyError, subprocess.TimeoutExpired) as e:
                result["stages"].append({"name": name, "ok": False, "error": str(e)})
                return False
        if apply:
            state["in_progress"] = True
            state["started_at"] = now()
            write_json(self.state / "maintenance.json", state)
        def due(name):
            age = age_seconds(state.get("last_" + name + "_at"))
            return age is None or age > self.policy["maintenance_every_hours"] * 3600
        if self.policy["auto_cleanup"] and (due("cleanup") or
                report["disk"]["free_bytes"] < self.policy["target_free_disk_gib"] * GIB or not apply):
            def cleanup():
                plan = self.cleanup_plan()
                return self.clean(True) if apply else plan
            if stage("cleanup", cleanup) and apply:
                state["last_cleanup_at"] = now()
        org_age = age_seconds(state.get("last_organization_at"))
        if self.policy["auto_organize"] and (org_age is None or
                org_age > self.policy["organization_every_minutes"] * 60 or not apply):
            if stage("organization", lambda: self.organize(apply)) and apply:
                state["last_organization_at"] = now()
        if self.policy["auto_name"] and time.monotonic() < deadline - 60:
            stage("naming", lambda: self.rename(apply))
        if apply:
            result["file_transaction"] = self.combine_file_transactions(result["stages"])
        if self.policy["auto_projects"] and time.monotonic() < deadline - 120:
            stage("projects", lambda: self.care_for_projects(apply, deadline))
        age = age_seconds(report.get("full_checked_at"))
        if apply and (age is None or age > self.policy["audit_stale_hours"] * 3600):
            stage("audit", lambda: self.check(True))
        if self.policy["auto_updates"] and time.monotonic() < deadline - 30:
            stage("updates", lambda: self.package_updates(state, apply, deadline))
        if self.policy["backup_repo"] and self.cloud_status()["provider"] != "none" and due("backup") and time.monotonic() < deadline - 180:
            if apply and stage("wiki_backup", lambda: self.backup(self.home / self.policy["health_wiki_root"],
                                                                  self.policy["backup_repo"])):
                state["last_backup_at"] = now()
        if apply:
            final = report
            try:
                final = self.check()
            except (OSError, ValueError, RuntimeError, TimeoutError, KeyError) as e:
                result["stages"].append({"name": "verification", "ok": False, "error": str(e)})
            result["free_disk_gib"] = final["disk"]["free_bytes"] / GIB
            result["exception"] = any(a["severity"] == "critical" for a in final["alerts"]) or any(
                not step["ok"] for step in result["stages"]) or any(
                item.get("requires_user_action") for step in result["stages"]
                for item in step.get("result", {}).get("items", []))
            state.update({"in_progress": False, "exception": result["exception"], "last_result": result})
            write_json(self.state / "maintenance.json", state)
            self.record("maintenance", {"exception": result["exception"], "duration_seconds": round(time.monotonic() - started)})
        return result

    def pause(self, hours=0):
        if not 0 <= hours <= 24 * 365:
            raise ValueError("Pausa deve estar entre 0 e 8760 horas; 0 pausa sem prazo")
        state = read_json(self.state / "maintenance.json", {})
        state.update({"paused": True, "paused_until":
                      (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=hours)).isoformat() if hours else None})
        write_json(self.state / "maintenance.json", state)
        return {"paused": True, "until": state["paused_until"], "monitoring": True}

    def resume(self):
        state = read_json(self.state / "maintenance.json", {})
        state.update({"paused": False, "paused_until": None})
        write_json(self.state / "maintenance.json", state)
        return {"paused": False, "next_run": "maintain"}

    def status(self):
        report = read_json(self.state / "snapshot.json", {})
        maintenance = read_json(self.state / "maintenance.json", {})
        free = report.get("disk", {}).get("free_bytes")
        return {"version": VERSION, "at": report.get("at"),
                "age_seconds": age_seconds(report.get("at")),
                "free_disk_gib": free / GIB if free is not None else None,
                "alerts": report.get("alerts", []), "alert_changes": report.get("alert_changes", []),
                "coverage": report.get("coverage", {}),
                "maintenance": maintenance.get("last_result"),
                "in_progress": maintenance.get("in_progress", False),
                "exception": maintenance.get("exception", False),
                "paused": maintenance.get("paused", False), "paused_until": maintenance.get("paused_until"),
                "pending_naming": read_json(self.state / "naming-pending.json", {}).get("items", [])[:20],
                "cloud": self.cloud_status(),
                "backup_folder": str(self.home / self.policy["local_backup_root"]),
                "projects": read_json(self.state / "projects.json", {}),
                "pending_approvals": [p for p in read_json(self.state / "approvals.json", [])
                                      if not p.get("consumed_at") and not self.approval_valid(p)],
                "pending_reviews": [r for r in read_json(self.state / "reviews.json", []) if not r.get("reviewed_at")]}

    def review(self, event_id, evidence):
        if not evidence.strip():
            raise ValueError("Revisão exige evidência e conclusão")
        entries = read_json(self.state / "reviews.json", [])
        item = next((r for r in entries if r["id"] == event_id), None)
        if item is None:
            raise ValueError("Evento ausente")
        item.update({"reviewed_at": now(), "evidence": evidence[:4000]})
        write_json(self.state / "reviews.json", entries)
        self.record("review", {"id": event_id, "evidence": evidence[:4000]})
        return {"reviewed": event_id, "trust_granted": False}

    def doctor(self):
        report = read_json(self.state / "snapshot.json", {})
        checks = []
        def add(name, ok, detail):
            checks.append({"name": name, "ok": ok, "detail": detail})
        add("macos", sys.platform == "darwin", sys.platform)
        add("python", sys.version_info >= (3, 11), sys.version.split()[0])
        add("private_state", self.state.stat().st_mode & 0o077 == 0, str(self.state))
        for field, limit, name in [("at", self.policy["snapshot_stale_minutes"] * 60, "monitor"),
                                   ("full_checked_at", self.policy["audit_stale_hours"] * 3600, "audit")]:
            age = age_seconds(report.get(field))
            add(name, age is not None and 0 <= age <= limit,
                {"age_seconds": age, "maximum_seconds": limit})
        if sys.platform == "darwin":
            for label in ("local.macguardian.monitor", "local.macguardian.audit"):
                result = command(["launchctl", "print", f"gui/{os.getuid()}/{label}"], 8)
                add(label, result["ok"], "loaded" if result["ok"] else result["stderr"][-500:])
        tools = {name: bool(shutil.which(name)) for name in
                 ("git", "lsof", "brew", "mas", "gh", "codesign", "spctl", "pdftotext", "tesseract", "ffprobe")}
        return {"version": VERSION, "ok": all(c["ok"] for c in checks),
                "checks": checks, "tools": tools,
                "coverage": report.get("coverage", {}),
                "next_action": "maintain" if any(not c["ok"] for c in checks) else None}

    def setup_status(self):
        """Current native readiness, never inferred from earlier conversation."""
        diagnosis = self.doctor()
        failed = {c["name"] for c in diagnosis["checks"] if not c["ok"]}
        maintenance = read_json(self.state / "maintenance.json", {})
        cloud = self.cloud_status()
        status, action = "READY", None
        if "macos" in failed:
            status, action = "SETUP_NEEDED", "connect-real-mac"
        elif "python" in failed:
            status, action = "SETUP_NEEDED", "install-python-3.11-or-newer"
        elif "private_state" in failed:
            status, action = "SETUP_NEEDED", "repair-state-permissions"
        elif failed & {"local.macguardian.monitor", "local.macguardian.audit"}:
            status, action = "SETUP_NEEDED", "install-native"
        elif failed & {"monitor", "audit"}:
            status, action = "ATTENTION_NEEDED", "check-collectors"
        elif maintenance.get("exception"):
            status, action = "ATTENTION_NEEDED", "inspect-maintenance-failure"
        elif maintenance.get("paused"):
            status = "PAUSED"
        # Storage preference and optional tools never block local reversible care.
        return {"version": VERSION, "status": status, "next": action,
                "scope": "native-mac", "relay_verified": False,
                "care_ready": status == "READY",
                "worker_in_progress": maintenance.get("in_progress", False),
                "checks": diagnosis["checks"], "tools": diagnosis["tools"],
                "cloud": cloud, "question": cloud["question"] if cloud["needs_question"] else None,
                "github_auth": "not-checked",
                "question_blocks_local_care": False}

    def check(self, full=False):
        previous = read_json(self.state / "snapshot.json", {})
        disk = shutil.disk_usage(self.home)
        memory_size = command(["sysctl", "-n", "hw.memsize"])
        total = memory_size["stdout"].strip()
        pressure = command(["memory_pressure", "-Q"])
        swap_result = command(["sysctl", "vm.swapusage"])
        swap = swap_result["stdout"].strip()
        vm = command(["vm_stat"])
        ps = command(["ps", "-axo", "pid,pcpu,pmem,rss,comm"])
        battery = command(["pmset", "-g", "batt"])
        match = re.search(r"used = ([\d.]+)([MG])", swap)
        swap_bytes = float(match[1]) * (1024 ** (2 if match[2] == "M" else 3)) if match else None
        processes = []
        for line in ps["stdout"].splitlines()[1:]:
            parts = line.strip().split(None, 4)
            if len(parts) == 5:
                try:
                    processes.append({"pid": int(parts[0]), "cpu": float(parts[1]),
                                      "memory_percent": float(parts[2]), "rss_bytes": int(parts[3]) * 1024,
                                      "executable": parts[4]})
                except ValueError:
                    pass
        alerts = []
        if disk.free < self.policy["free_disk_warning_gib"] * GIB:
            alerts.append({"id": "disk", "severity": "critical" if disk.free <
                           self.policy["free_disk_critical_gib"] * GIB else "warning",
                           "text": f"Espaço livre: {disk.free/GIB:.2f} GiB"})
        if swap_bytes and swap_bytes > self.policy["swap_warning_gib"] * GIB:
            alerts.append({"id": "swap", "severity": "warning", "text": f"Swap usado: {swap_bytes/GIB:.2f} GiB"})
        report = {"at": now(), "version": VERSION, "platform": sys.platform,
                  "os": command(["sw_vers", "-productVersion"])["stdout"].strip(),
                  "disk": {"total_bytes": disk.total, "free_bytes": disk.free, "used_bytes": disk.used},
                  "memory": {"total_bytes": int(total) if total.isdigit() else None,
                             "pressure": pressure, "swap": swap, "swap_bytes": swap_bytes,
                             "vm_stat": vm["stdout"]},
                  "load_average": list(os.getloadavg()),
                  "battery": battery,
                  "processes": sorted(processes, key=lambda x: x["cpu"], reverse=True),
                  "memory_processes": sorted(processes, key=lambda x: x["rss_bytes"], reverse=True)[:20],
                  "collection": {name: {"ok": result["ok"], "error": result["stderr"] if not result["ok"] else ""}
                                 for name, result in [("memory", memory_size), ("pressure", pressure),
                                                      ("swap", swap_result), ("vm", vm), ("processes", ps),
                                                      ("battery", battery)]},
                  "alerts": alerts, "folders": self.folders()}
        for key in ("applications", "updates", "security", "full_checked_at"):
            if key in previous:
                report[key] = previous[key]
        if full:
            report["updates"] = self.updates()
            report["applications"] = self.applications()
            casks = report["updates"].get("brew_casks", [])
            outdated = report["updates"].get("brew_outdated", {})
            outdated_tokens = {c["name"] for c in outdated.get("casks", [])} if isinstance(outdated, dict) else set()
            for app in report["applications"]:
                for cask in casks:
                    artifacts = {Path(a).name for item in cask.get("artifacts", []) if isinstance(item, dict)
                                 for a in item.get("app", []) if isinstance(a, str)}
                    if Path(app["path"]).name in artifacts:
                        app["update_status"] = ("outdated" if cask["token"] in outdated_tokens else
                                                "current" if report["updates"]["brew_refresh"]["ok"] and
                                                "casks" in outdated else "unknown")
                        app["update_source"] = "Homebrew"
            report["security"] = {
                "sip": command(["csrutil", "status"]),
                "gatekeeper": command(["spctl", "--status"]),
                "filevault": command(["fdesetup", "status"]),
                "xprotect": self.xprotect(),
                "listeners": command(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"], 20),
                "limitation": "Assinatura, Gatekeeper e inventário não comprovam ausência de malware."}
            report["full_checked_at"] = now()
        report["background"] = self.background(previous.get("background", []))
        changes = []
        if "background" in previous:
            # Compare binary identity only after the one-time version migration.
            fields = ["sha256", "executable"]
            if all("binary_identity" in j for j in previous["background"] if not j.get("error")):
                fields.append("binary_identity")
            changes += inventory_changes(report["background"], previous["background"], "plist", fields, "service")
        if full and "applications" in previous:
            changes += inventory_changes(report["applications"], previous["applications"], "path",
                                         ["version", "bundle_id", "signature"], "app")
        report["inventory_changes"] = changes
        for job in report["background"]:
            if job.get("review") or job.get("error"):
                alerts.append({"id": "launch:" + job["plist"], "severity": "review",
                               "text": "Revisar serviço: " + job.get("label", Path(job["plist"]).stem)})
        for change in changes:
            identity = hashlib.sha256(change["identity"].encode()).hexdigest()[:16]
            alerts.append({"id": "change:" + change["kind"] + ":" + identity, "severity": "review",
                           "text": f"{change['name']}: {change['change']}", "evidence": change["change"]})
            self.record("inventory_change", change)
        for name, result in report["collection"].items():
            if not result["ok"]:
                alerts.append({"id": "collection:" + name, "severity": "warning",
                               "text": "Coleta indisponível: " + name})
        audit_age = age_seconds(report.get("full_checked_at"))
        if audit_age is None or not 0 <= audit_age <= self.policy["audit_stale_hours"] * 3600:
            alerts.append({"id": "audit", "severity": "warning", "text": "Auditoria completa ausente ou vencida"})
        apps = report.get("applications", [])
        report["coverage"] = {"checked_at": report.get("full_checked_at"), "total": len(apps),
                              **{state: sum(a.get("update_status", "unknown") == state for a in apps)
                                 for state in ("current", "outdated", "unknown")}}
        prev_ids = {a["id"]: (a["severity"], a.get("evidence")) for a in previous.get("alerts", [])}
        report["alert_changes"] = [a for a in alerts if prev_ids.get(a["id"]) != (a["severity"], a.get("evidence"))]
        # An observed change ceasing to be new is not a security finding resolved.
        report["resolved_alerts"] = sorted(i for i in set(prev_ids) - {a["id"] for a in alerts}
                                            if not i.startswith("change:"))
        history = self.health_history(report)
        report["trends"] = {key: val for key, val in history.items() if key != "points"}
        self.wiki(report)
        reviews = read_json(self.state / "reviews.json", [])
        known = {r["id"] for r in reviews}
        observations = changes + [{"kind": "service", "identity": j["plist"],
                                    "name": j.get("label", Path(j["plist"]).stem),
                                    "change": "requires_review", "sha256": j.get("sha256"),
                                    "review": j.get("review", []), "error": j.get("error")}
                                   for j in report["background"] if j.get("review") or j.get("error")]
        by_identity = {j["plist"]: j for j in report["background"]}
        for observation in observations:
            job = by_identity.get(observation["identity"], {})
            observation = observation | {"observed_identity": {k: job.get(k) for k in
                           ("sha256", "executable", "binary_identity")} if job else {}}
            event_id = hashlib.sha256(json.dumps(observation, sort_keys=True).encode()).hexdigest()[:24]
            if event_id not in known:
                reviews.append({"id": event_id, "at": report["at"], **observation})
                known.add(event_id)
        write_json(self.state / "reviews.json", reviews)
        write_json(self.state / "snapshot.json", report)
        self.record("check", {"full": full, "alerts": len(alerts),
                              "free_bytes": disk.free, "at": report["at"]})
        return report

    def wiki(self, report):
        root = safe_inside(self.home / self.policy["health_wiki_root"], self.home)
        if self.excluded(root):
            raise ValueError("Relatório não pode usar Documents ou armazenamento cloud excluído")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        pages = ["# Wiki do Mac", "", f"Atualizada em {report['at']}.", "",
                 "[Saúde](Saude.md) · [Aplicativos](Aplicativos.md) · [Serviços](Servicos.md)", "",
                 "Esta wiki indexa as pastas reais. Configurações e projetos mantêm seus caminhos.", "",
                 "| Pasta | Categoria | Local |", "| --- | --- | --- |"]
        for item in report["folders"]:
            title = item["name"].replace("|", r"\|").replace("\n", " ")
            url = "file://" + urllib.parse.quote(item["path"])
            pages.append(f"| {title} | {item['category']} | [Abrir]({url}) |")
        private_text(root / "Home.md", "\n".join(pages) + "\n")
        private_text(root / "Saude.md",
            f"# Saúde\n\nEspaço livre: {report['disk']['free_bytes']/GIB:.2f} GiB.\n\n"
            f"Swap: {report['memory']['swap']}.\n\n"
            "Limpeza exige plano recente, idade mínima e ausência de arquivos em uso.\n"
            "Backup exige repositório privado e restauração com hashes iguais antes de excluir.\n")
        apps = ["# Aplicativos", "", "| App | Versão | Atualização | Assinatura |",
                "| --- | --- | --- | --- |"]
        apps += [f"| {a['name']} | {a.get('version','?')} | {a['update_status']} | "
                 f"{a['signature']['verified']} |" for a in report.get("applications", [])]
        apps += ["", "unknown exige checagem no fornecedor. Assinatura válida não é veredito antimalware."]
        private_text(root / "Aplicativos.md", "\n".join(apps) + "\n")
        jobs = ["# Serviços", "", "A linha de base registra o que foi observado; não concede confiança.", "",
                "| Serviço | Executável | Mudança | Revisão |", "| --- | --- | --- | --- |"]
        jobs += [f"| {j.get('label','?')} | {j.get('executable','?')} | {j.get('change','?')} | "
                 f"{'; '.join(j.get('review',[])) or 'pendente'} |" for j in report.get("background", [])]
        private_text(root / "Servicos.md", "\n".join(jobs) + "\n")
        self.file_wiki()

    def file_wiki(self):
        """Index personal files; inspect only the marker of generated Markdown."""
        root = safe_inside(self.home / self.policy["file_wiki_root"], self.home)
        if self.excluded(root):
            raise ValueError("A wiki precisa ficar fora de Documents e das raízes cloud excluídas")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        marker = "<!-- Mac Guardian: índice gerado automaticamente -->\n"
        def generated(path):
            if not path.is_file() or path.is_symlink():
                return False
            with path.open("rb") as f:
                return f.read(len(marker.encode())) == marker.encode()
        def generated_page(folder, name, content):
            path = folder / name
            owner = "<!-- Mac Guardian page: " + urllib.parse.quote(name) + " -->\n"
            # Never replace a personal page, even if it has an index filename.
            for i in range(100):
                ours = False
                if generated(path):
                    with path.open("rb") as stream:
                        stream.readline()
                        role = stream.readline()
                    ours = role == owner.encode() or (path.name == name and not role.startswith(b"<!-- Mac Guardian page:"))
                if (not path.exists() and not path.is_symlink()) or ours:
                    if content is not None:
                        private_text(path, marker + owner + content)
                    return path
                path = folder / ("_MacGuardian-" + str(i + 1) + ".md")
            raise ValueError("Não foi possível reservar um índice da wiki")
        pages = ["# Wiki pessoal", "", "Arquivos organizados por categoria e assunto.", "",
                 "| Categoria | Arquivos |", "| --- | --- |"]
        count, incomplete = 0, False
        deadline = time.monotonic() + self.policy["max_scan_seconds"]
        for category in sorted(root.iterdir()):
            if not category.is_dir() or category.is_symlink() or category.name.startswith("."):
                continue
            rows, dirs, subject_rows, children = [], [category], {}, {}
            while dirs:
                folder = dirs.pop()
                subject_rows.setdefault(folder, [])
                children.setdefault(folder, [])
                for path in sorted(folder.iterdir()):
                    if time.monotonic() > deadline or count >= self.policy["wiki_max_files"]:
                        incomplete = True
                        dirs.clear()
                        break
                    if path.is_symlink() or path.name.startswith("."):
                        continue
                    if path.is_dir():
                        dirs.append(path)
                        children[folder].append(path)
                    elif path.is_file():
                        if path.suffix.lower() == ".md" and generated(path):
                            continue
                        count += 1
                        label = path.relative_to(category).as_posix().replace("[", "\\[").replace("]", "\\]").replace("\n", " ")
                        rows.append(f"- [{label}]({urllib.parse.quote(path.relative_to(category).as_posix())})")
                        subject_rows.setdefault(path.parent, []).append(path)
            # Reserve index names first so links remain correct beside personal indexes.
            indexes = {folder: generated_page(folder, "_Index.md", None) for folder in subject_rows}
            for folder, paths in subject_rows.items():
                links = ["# " + folder.name, ""]
                if folder != category:
                    links += [f"[Voltar]({urllib.parse.quote(os.path.relpath(indexes[folder.parent], folder))})", ""]
                for child in sorted(children.get(folder, [])):
                    if child in indexes:
                        label = child.name.replace("[", "\\[").replace("]", "\\]")
                        links.append(f"- [{label}/]({urllib.parse.quote(indexes[child].relative_to(folder).as_posix())})")
                for path in paths:
                    label = path.name.replace("[", "\\[").replace("]", "\\]").replace("\n", " ")
                    links.append(f"- [{label}]({urllib.parse.quote(path.name)})")
                if folder == category and any(p != category for p in subject_rows):
                    links += ["", "## Todos os arquivos", "", *sorted(rows)]
                generated_page(folder, "_Index.md", "\n".join(links) + "\n")
            index = indexes[category]
            label = category.name.replace("|", "\\|").replace("[", "\\[").replace("]", "\\]")
            pages.append(f"| [{label}]({urllib.parse.quote(index.relative_to(root).as_posix())}) | {len(rows)} |")
            if incomplete:
                break
        pages += ["", "## Locais de trabalho", "",
                  "Projetos e bibliotecas continuam em seus caminhos, com acesso pela wiki.", ""]
        for path in sorted(self.home.iterdir()):
            if path.is_dir() and not path.is_symlink() and not path.name.startswith(".") and path.name not in PROTECTED and not self.excluded(path):
                label = path.name.replace("[", "\\[").replace("]", "\\]")
                pages.append(f"- [{label}](file://{urllib.parse.quote(str(path))})")
        snapshots = read_json(self.state / "project-snapshots.json", {})
        project_rows = ["# Projetos", "", "Caminhos de trabalho preservados. Código em branches privadas; segredos no backup local.", ""]
        for project in self.projects():
            if not (project / ".git").exists():
                continue
            label = self.relative(project).replace("[", "\\[").replace("]", "\\]").replace("\n", " ")
            saved = snapshots.get(str(project) + "|working", {})
            status = "snapshot remoto verificado" if saved.get("verified") else "aguardando snapshot"
            project_rows.append(f"- [{label}](file://{urllib.parse.quote(str(project))}) · {status}")
        project_page = generated_page(root, "Projects.md", "\n".join(project_rows) + "\n")
        pages.append(f"\n[Projetos e snapshots]({urllib.parse.quote(project_page.name)})")
        pages += ["", "Arquivos recentes ou em uso entram na wiki quando ficam estáveis.",
                  "Projetos, bibliotecas de apps e configurações mantêm seus locais."]
        if incomplete:
            pages.append("Índice parcial: o próximo ciclo continuará a organização; use as pastas para ver todos os arquivos.")
        home_page = generated_page(root, "Home.md", "\n".join(pages) + "\n")
        return {"home": str(home_page), "indexed_files": count, "incomplete": incomplete}

    def organize(self, apply=False):
        categories = {".pdf": "Documentos", ".docx": "Documentos", ".txt": "Documentos",
                      ".md": "Documentos", ".xlsx": "Planilhas", ".csv": "Planilhas",
                      ".png": "Imagens", ".jpg": "Imagens", ".jpeg": "Imagens",
                      ".webp": "Imagens", ".mp4": "Videos", ".mov": "Videos",
                      ".zip": "Arquivos", ".tar": "Arquivos", ".gz": "Arquivos",
                      ".dmg": "Instaladores", ".pkg": "Instaladores"}
        categories.update({suffix: category for category, suffixes in {
            "Documentos": (".doc", ".rtf", ".odt", ".pages", ".epub"),
            "Planilhas": (".xls", ".ods", ".numbers"),
            "Apresentacoes": (".ppt", ".pptx", ".key"),
            "Imagens": (".heic", ".gif", ".tiff", ".svg"),
            "Audio": (".mp3", ".m4a", ".wav", ".flac"),
            "Design": (".psd", ".ai", ".sketch"),
        }.items() for suffix in suffixes})
        moves = []
        cutoff = time.time() - self.policy["organization_stable_minutes"] * 60
        vault = safe_inside(self.home / self.policy["file_wiki_root"], self.home)
        protected = [self.home / name for name in self.policy["project_roots"] if name != "."] + [
            self.home / "Documents/Codex", self.home / self.policy["health_wiki_root"], vault]
        protected = [p.resolve() for p in protected]
        seen, reserved, scanned = set(), set(), 0
        deadline = time.monotonic() + self.policy["max_scan_seconds"]
        for folder in self.policy["organization_roots"]:
            root = self.home / folder
            if not root.is_dir() or root.is_symlink() or self.excluded(root):
                continue
            for base, dirs, files in os.walk(root, followlinks=False):
                base = Path(base)
                scanned += 1
                if scanned > self.policy["max_scan_directories"] or time.monotonic() > deadline or len(moves) >= self.policy["organization_max_files_per_run"]:
                    break
                if self.excluded(base) or any(base == p or base.is_relative_to(p) for p in protected) or any(
                        (base / name).exists() for name in (".git", ".obsidian", "wiki.toml", "package.json", "Cargo.toml", "CMakeLists.txt", "pyproject.toml", "requirements.txt", "go.mod", "Package.swift")):
                    dirs[:] = []
                    continue
                dirs[:] = sorted(name for name in dirs if not name.startswith(".")
                    and name not in PROTECTED | SKIP_NAMES and not (base / name).is_symlink()
                    and Path(name).suffix.lower() not in BUNDLE_SUFFIXES)
                for filename in sorted(files):
                    p = base / filename
                    category = categories.get(p.suffix.lower())
                    if len(moves) >= self.policy["organization_max_files_per_run"] or time.monotonic() > deadline:
                        break
                    if p in seen or not category or p.name.startswith(".") or p.name.upper() in {
                            "AGENTS.MD", "CLAUDE.MD", "SOUL.MD", "USER.MD", "TOOLS.MD", "HEARTBEAT.MD"} or SECRET_NAME.search(p.name) or p.is_symlink() or not p.is_file():
                        continue
                    seen.add(p)
                    try:
                        s = p.stat()
                        if s.st_mtime > cutoff or s.st_size > self.policy["organization_max_file_mib"] * 1024 ** 2 or s.st_nlink != 1:
                            continue
                        group = base.relative_to(root)
                        # Preserve existing subject folders; loose files use their year.
                        topic = group if group.parts else Path(dt.datetime.fromtimestamp(s.st_mtime).strftime("%Y"))
                        dest = vault / category / topic / p.name
                        if self.policy["auto_name"]:
                            context = self.naming_context(p)
                            if context["status"] == "protected_content":
                                continue
                            if context.get("confidence") == "high":
                                dest = dest.with_name(context["suggested_name"])
                            if context.get("explicit_topic"):
                                dest = vault / category / context["explicit_topic"] / dest.name
                        safe_inside(p, self.home)
                        safe_inside(dest, self.home)
                        if dest in reserved or dest.exists() or dest.is_symlink():
                            suffix = hashlib.sha256(self.relative(p).encode()).hexdigest()[:8]
                            dest = dest.with_name(dest.stem + "-" + suffix + dest.suffix)
                            if dest in reserved or dest.exists() or dest.is_symlink():
                                continue
                        item = {"source": str(p), "destination": str(dest), "sha256": digest(p),
                                "device": s.st_dev, "inode": s.st_ino, "mtime_ns": s.st_mtime_ns,
                                "ctime_ns": s.st_ctime_ns, "bytes": s.st_size}
                        moves.append(item)
                        reserved.add(dest)
                    except (ValueError, OSError):
                        continue
        return self.file_moves(moves, apply, deadline)

    def file_moves(self, moves, apply, deadline):
        if apply:
            deadline = time.monotonic() + self.policy["max_scan_seconds"]
            txn = uuid.uuid4().hex
            journal = self.state / "moves" / (txn + ".json")
            write_json(journal, {"items": []})
            done = []
            for m in moves:
                if time.monotonic() > deadline:
                    break
                source, dest = Path(m["source"]), Path(m["destination"])
                safe_inside(source, self.home)
                safe_inside(dest, self.home)
                if in_use(source):
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                s = source.stat()
                if dest.exists() or dest.is_symlink() or digest(source) != m["sha256"] or any(
                        val != m[key] for key, val in [("device", s.st_dev), ("inode", s.st_ino),
                                                     ("mtime_ns", s.st_mtime_ns), ("ctime_ns", s.st_ctime_ns), ("bytes", s.st_size)]):
                    raise ValueError("Arquivo mudou durante a organização")
                done.append(m)
                write_json(journal, {"items": done})
                # Journal first; a hard link publishes without overwriting.
                os.link(source, dest, follow_symlinks=False)
                source.unlink()
                self.record("move", m | {"transaction": txn})
            wiki = self.file_wiki()
            return {"transaction": txn, "items": done, "undo": f"undo {txn}", "wiki": wiki["home"]}
        write_json(self.state / "organization-plan.json", {"at": now(), "items": moves})
        return {"items": moves}

    def naming_context(self, path):
        path = safe_inside(Path(path).expanduser(), self.home)
        if self.excluded(path) or SECRET_NAME.search(path.name):
            raise ValueError("Origem excluída da análise de conteúdo")
        title, text, basis, confidence = "", "", "", "medium"
        suffix = path.suffix.lower()
        if suffix in (".md", ".txt", ".csv"):
            with path.open("rb") as f:
                text = f.read(65536).decode("utf-8", errors="replace")
            if text.startswith("<!-- Mac Guardian:"):
                return {"path": str(path), "status": "generated_index"}
            heading = re.search(r"^#{1,3}\s+(.+)$", text, re.M) if suffix == ".md" else None
            title = heading[1] if heading else next((l.strip() for l in text.splitlines() if l.strip()), "")
            basis = "document_text"
            if heading or re.match(r"^(?:title|titulo|título):\s*", title, re.I):
                title = re.sub(r"^(?:title|titulo|título):\s*", "", title, flags=re.I)
                confidence = "high"
        elif suffix in (".docx", ".pptx", ".xlsx"):
            try:
                with zipfile.ZipFile(path) as z:
                    def xml(name):
                        info = z.getinfo(name)
                        if info.file_size > 2 * 1024 * 1024:
                            raise ValueError("Metadados grandes demais")
                        return ET.fromstring(z.read(name))
                    if "docProps/core.xml" in z.namelist():
                        title = next((e.text for e in xml("docProps/core.xml").iter()
                                      if e.tag.endswith("}title") and e.text), "")
                        if title:
                            confidence = "high"
                    name = "word/document.xml" if suffix == ".docx" else "ppt/slides/slide1.xml"
                    if name in z.namelist():
                        root = xml(name)
                        lines = ["".join(e.itertext()).strip() for e in root.iter() if e.tag.endswith("}t")]
                        text = "\n".join(lines)[:65536]
                        title = title or next((l for l in lines if l), "")
                    basis = "office_title_or_first_paragraph"
            except (zipfile.BadZipFile, ET.ParseError, KeyError, ValueError):
                pass
        elif suffix == ".pdf" and shutil.which("pdftotext"):
            result = command(["pdftotext", "-f", "1", "-l", "1", "-layout", str(path), "-"], 8)
            if result["ok"]:
                text = result["stdout"][:65536]
                title = next((l.strip() for l in text.splitlines() if 8 <= len(l.strip()) <= 100), "")
                basis = "pdf_first_page"
                if re.search(r"\b(fatura|relat[oó]rio|contrato|roteiro|or[cç]amento|recibo|invoice|report|itinerary)\b", title, re.I):
                    confidence = "high"
        elif suffix in (".png", ".jpg", ".jpeg", ".webp", ".tiff") and shutil.which("tesseract"):
            result = command(["tesseract", str(path), "stdout", "--psm", "11"], 8,
                             dict(os.environ, OMP_THREAD_LIMIT="1"))
            if result["ok"]:
                text = result["stdout"][:65536]
                lines = [l.strip() for l in text.splitlines() if 8 <= len(l.strip()) <= 100]
                title = next((l for l in lines if re.search(r"\b(fatura|relat[oó]rio|contrato|roteiro|invoice|report)\b", l, re.I)), lines[0] if lines else "")
                basis = "local_ocr"
                if title and re.search(r"\b(fatura|relat[oó]rio|contrato|roteiro|invoice|report)\b", title, re.I):
                    confidence = "high"
        elif suffix in (".mp4", ".mov", ".mp3", ".m4a", ".wav", ".flac") and shutil.which("ffprobe"):
            result = command(["ffprobe", "-v", "error", "-show_entries", "format_tags=title", "-of", "json", str(path)], 8)
            if result["ok"]:
                try:
                    title = json.loads(result["stdout"]).get("format", {}).get("tags", {}).get("title", "")
                    basis, confidence = "media_title", "high"
                except (ValueError, TypeError):
                    pass
        if not title and sys.platform == "darwin":
            metadata = command(["mdls", "-raw", "-name", "kMDItemTitle", str(path)], 4)
            if metadata["ok"] and metadata["stdout"].strip() not in ("", "(null)"):
                title, basis, confidence = metadata["stdout"].strip().strip('"'), "spotlight_title", "high"
        if SECRET_CONTENT.search((title + "\n" + text).encode()):
            return {"path": str(path), "status": "protected_content"}
        topic_match = re.search(r"(?im)^(?:assunto|topic|projeto|project|cliente|client)\s*:\s*([^\n]{3,80})$", text[:4000])
        explicit_topic = ""
        if topic_match:
            explicit_topic = unicodedata.normalize("NFKD", topic_match[1]).encode("ascii", "ignore").decode().lower()
            explicit_topic = re.sub(r"[^a-z0-9]+", "-", explicit_topic).strip("-")[:80]
        generic = re.compile(r"^(?:untitled|document\d*|documento\d*|scan\d*|img[_ -]?\d+|screenshot|captura de tela)$", re.I)
        title = re.sub(r"\s+", " ", title).strip()
        filename_title = basis == "spotlight_title" and (title.casefold() == path.name.casefold() or
                        re.search(r"\.(pdf|docx?|pptx?|xlsx?|md|txt|jpe?g|png|mov|mp4)$", title, re.I))
        if not 8 <= len(title) <= 100 or filename_title or generic.fullmatch(title) or "�" in title or re.search(r"https?://|\S+@\S+", title):
            return {"path": str(path), "status": "needs_context", "basis": basis,
                    "sha256": digest(path), "text_excerpt": text[:1200], "topic": path.parent.name,
                    "explicit_topic": explicit_topic}
        slug = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
        slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")[:100].rstrip("-")
        if len(slug) < 5:
            return {"path": str(path), "status": "needs_context", "basis": basis}
        topic = unicodedata.normalize("NFKD", path.parent.name).encode("ascii", "ignore").decode().lower()
        topic = re.sub(r"[^a-z0-9]+", "-", topic).strip("-")
        if slug in ("relatorio-mensal", "monthly-report", "roteiro-de-viagem", "meeting-notes") and topic and not topic.isdigit() and topic not in ("downloads", "desktop", "documentos", "imagens", "wiki"):
            slug += "-" + topic
        date_match = re.search(r"(?im)^(?:data|emiss[aã]o|date)\s*:\s*(\d{4}-\d\d-\d\d|\d\d/\d\d/\d{4})\b", text[:1200])
        if date_match:
            try:
                stamp = dt.datetime.strptime(date_match[1], "%Y-%m-%d" if "-" in date_match[1] else "%d/%m/%Y").strftime("%Y-%m-%d")
                if not slug.startswith(stamp):
                    slug = stamp + "-" + slug
            except ValueError:
                pass
        if path.stem == slug or re.fullmatch(re.escape(slug) + r"-[a-f0-9]{8}", path.stem):
            name = path.name
        else:
            name = slug + suffix
        return {"path": str(path), "status": "named", "title": title, "basis": basis,
                "suggested_name": name, "topic": path.parent.name, "sha256": digest(path),
                "text_excerpt": text[:1200], "confidence": confidence, "explicit_topic": explicit_topic}

    def rename_file(self, path, name, expected_hash, evidence):
        path = safe_inside(Path(path).expanduser(), self.home)
        vault = safe_inside(self.home / self.policy["file_wiki_root"], self.home)
        if not path.is_relative_to(vault) or self.excluded(path):
            raise ValueError("Renomeação por contexto exige arquivo dentro da wiki local")
        if Path(name).name != name or re.search(r"[\\\x00-\x1f\x7f]", name) or name.startswith((".", "_")) or len(name.encode()) > 240 or Path(name).suffix.lower() != path.suffix.lower():
            raise ValueError("Nome inválido; preserve extensão e diretório")
        if not evidence.strip() or SECRET_NAME.search(path.name) or SECRET_NAME.search(name):
            raise ValueError("Renomeação exige evidência e não pode alcançar segredos")
        context = self.naming_context(path)
        if context["status"] in ("generated_index", "protected_content"):
            raise ValueError("Arquivo protegido")
        if digest(path) != expected_hash:
            raise ValueError("Conteúdo mudou desde a análise")
        s = path.stat()
        if s.st_nlink != 1 or s.st_mtime > time.time() - self.policy["organization_stable_minutes"] * 60:
            raise ValueError("Arquivo recente ou hardlink protegido")
        destination = path.with_name(name)
        if destination == path:
            return {"items": [], "unchanged": True}
        item = {"source": str(path), "destination": str(destination), "sha256": expected_hash,
                "device": s.st_dev, "inode": s.st_ino, "mtime_ns": s.st_mtime_ns,
                "ctime_ns": s.st_ctime_ns, "bytes": s.st_size, "name_basis": "agent_content_review",
                "evidence": evidence[:2000]}
        result = self.file_moves([item], True, time.monotonic() + self.policy["max_scan_seconds"])
        if result["items"]:
            s = destination.stat()
            observations = read_json(self.state / "naming-observations.json", {})
            observations.pop(self.relative(path), None)
            observations[self.relative(destination)] = {
                "identity": [s.st_dev, s.st_ino, s.st_mtime_ns, s.st_ctime_ns, s.st_size],
                "context": {"status": "named", "confidence": "high", "suggested_name": name,
                            "basis": "agent_content_review"}}
            write_json(self.state / "naming-observations.json", observations)
            pending = read_json(self.state / "naming-pending.json", {"items": []})
            pending["items"] = [p for p in pending["items"] if p["path"] not in (str(path), str(destination))]
            write_json(self.state / "naming-pending.json", pending)
        return result

    def classify_file(self, path, category, topic, name, expected_hash, evidence):
        path = safe_inside(Path(path).expanduser(), self.home)
        vault = safe_inside(self.home / self.policy["file_wiki_root"], self.home)
        if self.excluded(path) or not evidence.strip() or SECRET_NAME.search(path.name) or path.suffix.lower() not in {
                ".pdf", ".docx", ".txt", ".md", ".xlsx", ".csv", ".pptx", ".png", ".jpg", ".jpeg",
                ".webp", ".mp4", ".mov", ".mp3", ".wav", ".m4a", ".fig", ".sketch", ".zip", ".dmg"}:
            raise ValueError("Classificação exige evidência e uma origem pessoal permitida")
        for parent in [path.parent, *path.parents]:
            if parent == self.home:
                break
            if parent.name in PROTECTED or parent.suffix.lower() in BUNDLE_SUFFIXES or any((parent / marker).exists() for marker in
                    (".git", ".obsidian", "wiki.toml", "package.json", "Cargo.toml", "pyproject.toml", "go.mod")):
                raise ValueError("Configurações, projetos e bibliotecas preservam seus caminhos")
        if category not in {"Documentos", "Planilhas", "Apresentacoes", "Imagens", "Videos", "Audio", "Design", "Arquivos", "Instaladores"}:
            raise ValueError("Categoria inválida")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_. -]{1,79}", topic) or topic in (".", ".."):
            raise ValueError("Assunto inválido")
        if Path(name).name != name or SECRET_NAME.search(name) or name.startswith((".", "_")) or re.search(r"[\\\x00-\x1f\x7f]", name) or len(name.encode()) > 240 or Path(name).suffix.lower() != path.suffix.lower():
            raise ValueError("Nome inválido; preserve extensão")
        context = self.naming_context(path)
        if context["status"] in ("protected_content", "generated_index") or digest(path) != expected_hash:
            raise ValueError("Arquivo protegido ou alterado desde a análise")
        s = path.stat()
        if s.st_nlink != 1 or s.st_mtime > time.time() - self.policy["organization_stable_minutes"] * 60:
            raise ValueError("Arquivo recente ou vinculado")
        dest = safe_inside(vault / category / topic / name, self.home)
        if dest == path:
            return {"items": [], "unchanged": True}
        if dest.exists() or dest.is_symlink():
            dest = dest.with_name(dest.stem + "-" + hashlib.sha256(self.relative(path).encode()).hexdigest()[:8] + dest.suffix)
        item = {"source": str(path), "destination": str(dest), "sha256": expected_hash,
                "device": s.st_dev, "inode": s.st_ino, "mtime_ns": s.st_mtime_ns,
                "ctime_ns": s.st_ctime_ns, "bytes": s.st_size,
                "name_basis": "agent_context_classification", "evidence": evidence[:2000]}
        return self.file_moves([item], True, time.monotonic() + self.policy["max_scan_seconds"])

    def rename(self, apply=False):
        vault = safe_inside(self.home / self.policy["file_wiki_root"], self.home)
        if self.excluded(vault):
            raise ValueError("Wiki em raiz excluída")
        moves, pending, reserved = [], [], set()
        observations = read_json(self.state / "naming-observations.json", {})
        updated = observations.copy()
        def fingerprint(path):
            s = path.stat()
            return [s.st_dev, s.st_ino, s.st_mtime_ns, s.st_ctime_ns, s.st_size]
        deadline = time.monotonic() + self.policy["max_scan_seconds"]
        if vault.exists():
            for base, dirs, files in os.walk(vault, followlinks=False):
                dirs[:] = [n for n in dirs if not n.startswith(".") and not (Path(base) / n).is_symlink()]
                if any((Path(base) / n).exists() for n in (".git", ".obsidian", "wiki.toml", "package.json", "Cargo.toml", "pyproject.toml", "go.mod")):
                    dirs[:] = []
                    continue
                for name in sorted(files):
                    if time.monotonic() > deadline or len(moves) >= self.policy["organization_max_files_per_run"]:
                        break
                    path = Path(base) / name
                    if path.is_symlink() or name.startswith((".", "_")) or name == "Home.md" or name.upper() in {
                            "AGENTS.MD", "CLAUDE.MD", "SOUL.MD", "USER.MD", "TOOLS.MD", "HEARTBEAT.MD"} or SECRET_NAME.search(name):
                        continue
                    s = path.stat()
                    if s.st_nlink != 1 or s.st_mtime > time.time() - self.policy["organization_stable_minutes"] * 60 or s.st_size > self.policy["organization_max_file_mib"] * 1024 ** 2:
                        continue
                    key, identity = self.relative(path), fingerprint(path)
                    observed = observations.get(key, {})
                    context = observed.get("context", {}) if observed.get("identity") == identity else self.naming_context(path)
                    updated[key] = {"identity": identity, "context": {k: context[k] for k in
                                    ("status", "confidence", "suggested_name", "basis") if k in context}}
                    if context["status"] != "named" or context.get("confidence") != "high":
                        if context["status"] in ("needs_context", "named"):
                            pending.append({"path": str(path), "status": "needs_context", "topic": path.parent.name})
                        continue
                    dest = path.with_name(context["suggested_name"])
                    if dest == path:
                        continue
                    if dest.exists() or dest.is_symlink() or dest in reserved:
                        dest = dest.with_name(dest.stem + "-" + hashlib.sha256(self.relative(path).encode()).hexdigest()[:8] + dest.suffix)
                    if dest.exists() or dest.is_symlink() or dest in reserved:
                        continue
                    moves.append({"source": str(path), "destination": str(dest), "sha256": digest(path),
                                  "device": s.st_dev, "inode": s.st_ino, "mtime_ns": s.st_mtime_ns,
                                  "ctime_ns": s.st_ctime_ns, "bytes": s.st_size, "name_basis": context["basis"]})
                    reserved.add(dest)
                if time.monotonic() > deadline or len(moves) >= self.policy["organization_max_files_per_run"]:
                    break
        write_json(self.state / "naming-pending.json", {"at": now(), "items": pending})
        result = self.file_moves(moves, apply, deadline)
        if apply:
            for item in result["items"]:
                source, destination = Path(item["source"]), Path(item["destination"])
                observed = updated.pop(self.relative(source), None)
                if observed:
                    observed["identity"] = fingerprint(destination)
                    observed["context"]["suggested_name"] = destination.name
                    updated[self.relative(destination)] = observed
            write_json(self.state / "naming-observations.json", {k: v for k, v in updated.items()
                       if (self.home / k).is_file() and not (self.home / k).is_symlink()})
        result["pending_context"] = len(pending)
        return result

    def combine_file_transactions(self, stages):
        children, items = [], []
        for stage in stages:
            data = stage.get("result", {})
            if stage["name"] not in ("organization", "naming") or not data.get("items") or not data.get("transaction"):
                continue
            children.append(data["transaction"])
            for item in data["items"]:
                previous = next((i for i in items if i["destination"] == item["source"] and i["sha256"] == item["sha256"]), None)
                if previous:
                    previous["destination"] = item["destination"]
                else:
                    items.append(item.copy())
        if len(children) < 2:
            return children[0] if children else None
        transaction = uuid.uuid4().hex
        write_json(self.state / "moves" / (transaction + ".json"), {"items": items, "children": children})
        for child in children:
            write_json(self.state / "moves" / (child + ".json"), {"items": [], "superseded_by": transaction})
        self.record("file_transaction", {"transaction": transaction, "children": children, "files": len(items)})
        return transaction

    def undo(self, transaction):
        if not re.fullmatch("[a-f0-9]{32}", transaction):
            raise ValueError("Transação inválida")
        journal = self.state / "moves" / (transaction + ".json")
        data = read_json(journal)
        if data is None:
            raise ValueError("Transação ausente")
        if data.get("superseded_by"):
            return self.undo(data["superseded_by"])
        remaining = data["items"].copy()
        for m in reversed(data["items"]):
            source, dest = Path(m["source"]), Path(m["destination"])
            safe_inside(source, self.home)
            safe_inside(dest, self.home)
            if source.is_file() and not source.is_symlink() and not dest.exists() and not dest.is_symlink() and digest(source) == m["sha256"]:
                pass
            elif source.exists() and not source.is_symlink() and dest.exists() and os.path.samefile(source, dest):
                if digest(source) != m["sha256"]:
                    raise ValueError("Conteúdo alterado após interrupção da organização")
                dest.unlink()
            elif source.exists() or source.is_symlink() or digest(dest) != m["sha256"]:
                raise ValueError("Restaurar sobrescreveria arquivo ou conteúdo alterado")
            else:
                source.parent.mkdir(parents=True, exist_ok=True)
                os.link(dest, source, follow_symlinks=False)
                dest.unlink()
            remaining.remove(m)
            write_json(journal, {"items": remaining})
            self.record("undo_move", m)
        self.file_wiki()
        return {"restored": len(data["items"])}

    def backup_manifest(self, source):
        source = safe_inside(source, self.home)
        if self.excluded(source):
            raise ValueError("Origem de backup em pasta excluída")
        if not any(source == self.home / r or source.is_relative_to(self.home / r)
                   for r in self.policy["backup_roots"]):
            raise ValueError("Adicione esta pasta à política backup_roots antes de enviar dados")
        files = {}
        deadline = time.monotonic() + 120
        for root, dirs, names in os.walk(source, followlinks=False):
            if time.monotonic() > deadline:
                raise TimeoutError("Backup excedeu o limite de varredura")
            # Reject hidden metadata; silently excluding user data would make offload unsafe.
            for name in [*dirs, *names]:
                path = Path(root) / name
                if path.is_symlink() or name.startswith(".") or name in SKIP_NAMES or SECRET_NAME.search(name):
                    raise ValueError(f"Backup bloqueado por arquivo protegido: {path.name}")
            for name in names:
                path = Path(root) / name
                if not stat.S_ISREG(path.lstat().st_mode) or path.stat().st_nlink != 1:
                    raise ValueError("Backup contém arquivo especial ou hardlink")
                if path.stat().st_size > 45 * 1024 * 1024:
                    raise ValueError("Arquivo grande exige estratégia fora do Git")
                if SECRET_CONTENT.search(path.read_bytes()):
                    raise ValueError(f"Possível segredo em {path.name}; revisar localmente")
                files[str(path.relative_to(source))] = digest(path)
        if not files:
            raise ValueError("Backup vazio")
        return files

    def backup(self, source, repo, offload=False):
        if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", repo):
            raise ValueError("Use owner/repo")
        source = safe_inside(Path(source).expanduser(), self.home)
        manifest = self.backup_manifest(source)
        visibility = json.loads(require(["gh", "repo", "view", repo, "--json", "isPrivate,url"]))
        if not visibility["isPrivate"]:
            raise ValueError("Backup exige repositório privado")
        snapshot_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:8]
        with tempfile.TemporaryDirectory(prefix="backup-", dir=self.state) as tmp:
            checkout = Path(tmp) / "repo"
            require(["gh", "repo", "clone", repo, str(checkout), "--", "--depth", "1"], 180)
            target = checkout / "snapshots" / snapshot_id
            target.mkdir(parents=True)
            for rel in manifest:
                dest = target / "data" / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / rel, dest, follow_symlinks=False)
                if digest(dest) != manifest[rel]:
                    raise ValueError("Arquivo mudou durante a cópia")
            write_json(target / "manifest.json", {"at": now(), "files": manifest})
            require(["git", "-C", str(checkout), "add", "snapshots/" + snapshot_id])
            require(["git", "-C", str(checkout), "commit", "-m", "Backup verificado " + snapshot_id])
            require(["git", "-C", str(checkout), "push"], 180)
            commit = require(["git", "-C", str(checkout), "rev-parse", "HEAD"])
            verify = Path(tmp) / "restored"
            require(["gh", "repo", "clone", repo, str(verify), "--", "--depth", "1"], 180)
            if require(["git", "-C", str(verify), "rev-parse", "HEAD"]) != commit:
                raise ValueError("HEAD remoto mudou; backup enviado, exclusão cancelada")
            restored = verify / "snapshots" / snapshot_id / "data"
            restored_manifest = {str(p.relative_to(restored)): digest(p)
                                 for p in restored.rglob("*") if p.is_file()}
            if restored_manifest != manifest or self.backup_manifest(source) != manifest:
                raise ValueError("Conteúdo restaurado ou origem divergiu; exclusão cancelada")
            receipt = {"at": now(), "repo": repo, "snapshot": snapshot_id,
                       "commit": commit, "files": manifest, "source": str(source),
                       "restored_and_verified": True, "offloaded": False}
            receipt_path = self.state / "backups" / (snapshot_id + ".json")
            write_json(receipt_path, receipt)
            if offload:
                if source in (self.home / self.policy["health_wiki_root"], self.home / self.policy["file_wiki_root"]):
                    raise ValueError("Wiki ativa tem backup, mas não pode ser removida")
                if in_use(source):
                    raise ValueError("Origem em uso ou uso não verificável")
                # Remote files alone do not preserve all local metadata. Keep an exact
                # same-volume recovery copy before taking the original out of use.
                if self.backup_manifest(source) != manifest:
                    raise ValueError("Origem mudou; exclusão cancelada")
                receipt["recovery"] = self.quarantine_tree(source, "verified_backup")
                receipt["offloaded"] = not source.exists()
                receipt["freed_bytes"] = 0
                if source.exists():
                    receipt["remaining"] = "Novos arquivos ou diretórios ainda estão na origem."
            write_json(receipt_path, receipt)
            self.record("backup", {"repo": repo, "snapshot": snapshot_id, "commit": commit,
                                   "offloaded": receipt["offloaded"]})
            return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", help="Raiz local; também usada em testes isolados")
    parser.add_argument("--state", help="Diretório privado de relatórios")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("init")
    check = sub.add_parser("check")
    check.add_argument("--full", action="store_true")
    sub.add_parser("status")
    sub.add_parser("doctor")
    sub.add_parser("setup-status")
    history = sub.add_parser("history")
    history.add_argument("--hours", type=int, default=24)
    maintain = sub.add_parser("maintain")
    maintain.add_argument("--dry-run", action="store_true")
    pause = sub.add_parser("pause")
    pause.add_argument("--hours", type=float, default=0)
    sub.add_parser("resume")
    review = sub.add_parser("review")
    review.add_argument("--id", required=True)
    review.add_argument("--evidence", required=True)
    sub.add_parser("plan")
    sub.add_parser("worktrees")
    sub.add_parser("cloud-status")
    cloud = sub.add_parser("configure-cloud")
    cloud.add_argument("--provider", choices=["icloud", "google-drive", "both", "none"])
    cloud.add_argument("--root", action="append", default=[])
    cloud.add_argument("--asked", action="store_true")
    approval = sub.add_parser("approve")
    approval.add_argument("--id", required=True)
    approval.add_argument("--evidence", required=True)
    projects = sub.add_parser("projects")
    projects.add_argument("--dry-run", action="store_true")
    project = sub.add_parser("project-snapshot")
    project.add_argument("--path", required=True)
    for name in ("restore-quarantine", "restore-worktree"):
        recovery = sub.add_parser(name)
        recovery.add_argument("--receipt", required=True)
    purge = sub.add_parser("purge-quarantine")
    purge.add_argument("--receipt", required=True)
    purge.add_argument("--apply", action="store_true")
    purge.add_argument("--approval")
    restore_secret = sub.add_parser("restore-secret")
    restore_secret.add_argument("--identity", required=True)
    restore_secret.add_argument("--version", required=True)
    worktree = sub.add_parser("remove-worktree")
    worktree.add_argument("--path", required=True)
    worktree.add_argument("--apply", action="store_true")
    for name in ("clean", "organize", "rename"):
        p = sub.add_parser(name)
        p.add_argument("--apply", action="store_true")
    naming = sub.add_parser("naming-context")
    naming.add_argument("--path", required=True)
    rename_file = sub.add_parser("rename-file")
    rename_file.add_argument("--path", required=True)
    rename_file.add_argument("--name", required=True)
    rename_file.add_argument("--sha256", required=True)
    rename_file.add_argument("--evidence", required=True)
    classify = sub.add_parser("classify-file")
    classify.add_argument("--path", required=True)
    classify.add_argument("--category", required=True)
    classify.add_argument("--topic", required=True)
    classify.add_argument("--name", required=True)
    classify.add_argument("--sha256", required=True)
    classify.add_argument("--evidence", required=True)
    undo = sub.add_parser("undo")
    undo.add_argument("transaction")
    backup = sub.add_parser("backup")
    backup.add_argument("--source", required=True)
    backup.add_argument("--repo", required=True)
    backup.add_argument("--offload", action="store_true")
    args = parser.parse_args()
    try:
        if sys.platform != "darwin" and not args.home:
            raise ValueError("O componente nativo exige macOS; --home serve apenas para testes isolados")
        g = Guardian(args.home, args.state)
        # Read-only conversation commands remain available during maintenance.
        with contextlib.nullcontext() if args.action in ("status", "doctor", "setup-status", "history", "naming-context", "cloud-status") else g.lock():
            if args.action == "init":
                p = g.state / "policy.json"
                if not p.exists():
                    write_json(p, DEFAULT_POLICY)
                else:
                    write_json(p, g.policy)
                result = {"policy": str(p), "state": str(g.state), "backup_folder": str(g.backup_folder())}
            elif args.action == "check":
                report = g.check(args.full)
                result = {"snapshot": str(g.state / "snapshot.json"),
                          "alerts": report["alerts"], "alert_changes": report["alert_changes"],
                          "resolved_alerts": report["resolved_alerts"], "apps": len(report.get("applications", []))}
            elif args.action == "status":
                result = g.status()
            elif args.action == "doctor":
                result = g.doctor()
            elif args.action == "setup-status":
                result = g.setup_status()
            elif args.action == "history":
                if not 1 <= args.hours <= g.policy["history_days"] * 24:
                    raise ValueError("Período fora do histórico disponível")
                result = g.health_history(hours=args.hours)
            elif args.action == "maintain":
                result = g.maintain(not args.dry_run)
            elif args.action == "pause":
                result = g.pause(args.hours)
            elif args.action == "resume":
                result = g.resume()
            elif args.action == "review":
                result = g.review(args.id, args.evidence)
            elif args.action == "plan":
                result = g.cleanup_plan()
            elif args.action == "worktrees":
                result = g.worktrees()
            elif args.action == "cloud-status":
                result = g.cloud_status()
            elif args.action == "configure-cloud":
                result = g.configure_cloud(args.provider, args.root, args.asked)
            elif args.action == "approve":
                result = g.approve(args.id, args.evidence)
            elif args.action == "projects":
                result = g.care_for_projects(not args.dry_run)
            elif args.action == "project-snapshot":
                result = g.project_snapshot(args.path, g.private_project_repo())
            elif args.action == "restore-quarantine":
                result = g.restore_quarantine(args.receipt)
            elif args.action == "purge-quarantine":
                result = g.purge_quarantine(args.receipt, args.apply, args.approval)
            elif args.action == "restore-worktree":
                result = g.restore_worktree(args.receipt)
            elif args.action == "restore-secret":
                result = g.restore_secret(args.identity, args.version)
            elif args.action == "remove-worktree":
                result = g.remove_worktree(args.path, args.apply)
            elif args.action == "clean":
                result = g.clean(args.apply)
            elif args.action == "organize":
                result = g.organize(args.apply)
            elif args.action == "rename":
                result = g.rename(args.apply)
            elif args.action == "naming-context":
                result = g.naming_context(args.path)
            elif args.action == "rename-file":
                result = g.rename_file(args.path, args.name, args.sha256, args.evidence)
            elif args.action == "classify-file":
                result = g.classify_file(args.path, args.category, args.topic, args.name, args.sha256, args.evidence)
            elif args.action == "undo":
                result = g.undo(args.transaction)
            elif args.action == "backup":
                result = g.backup(args.source, args.repo, args.offload)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except BlockingIOError:
        print(json.dumps({"status": "busy", "executed": False,
                          "detail": "Outra rotina está ativa; o próximo ciclo retoma."}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError, TimeoutError, KeyError, subprocess.TimeoutExpired) as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

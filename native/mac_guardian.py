#!/usr/bin/env python3
"""Mac maintenance commands for a Plow/OpenClaw agent. Python standard library."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import contextlib
import datetime as dt
import fcntl
import hashlib
import html
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
import uuid
from xml.parsers.expat import ExpatError

GIB = 1024 ** 3
DAY = 86400
DEFAULT_POLICY = {
    "cache_age_days": 14,
    "artifact_age_days": 30,
    "worktree_age_days": 30,
    "organization_age_days": 7,
    "free_disk_warning_gib": 20,
    "free_disk_critical_gib": 5,
    "swap_warning_gib": 4,
    "project_roots": ["Code", "Documents/Codex", ".codex/worktrees", "tryzoen-worktrees"],
    "cache_paths": [".npm/_npx", ".cache/uv", "Library/Caches/Aside/Default/Cache",
                    "Library/Caches/Aside/Default/Code Cache"],
    "backup_roots": ["Documents/MacWiki"],
    "max_scan_directories": 20000,
    "max_scan_seconds": 90,
}
PROTECTED = {".ssh", ".gnupg", ".secrets", ".config", ".codex", ".claude",
             ".openclaw", ".hermes", ".git", "Library", "Applications"}
SKIP_NAMES = {"node_modules", "target", ".git", ".venv", "venv", ".next", "dist",
              "build", "__pycache__", ".DS_Store"}
SECRET_NAME = re.compile(r"(^\.env($|\.)|credentials|secret|token|password|"
                         r"\.(pem|key|p12|pfx|kdbx)$|^id_(rsa|ed25519))", re.I)
SECRET_CONTENT = re.compile(rb"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----|"
                            rb"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,}|"
                            rb"AKIA[A-Z0-9]{16}|sk-(?:proj-)?[A-Za-z0-9_-]{20,})\b|"
                            rb"(?i:(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)"
                            rb"[ \t]*[:=][ \t]*[\"']?[A-Za-z0-9/+_-]{16,})")


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    tmp.chmod(0o600)
    tmp.replace(path)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


def command(argv, timeout=20):
    """Never invoke a shell or include process arguments in inventory."""
    try:
        p = subprocess.run([str(v) for v in argv], capture_output=True,
                           text=True, timeout=timeout)
        return {"ok": p.returncode == 0, "code": p.returncode,
                "stdout": p.stdout[-100000:], "stderr": p.stderr[-4000:]}
    except (OSError, subprocess.TimeoutExpired) as e:
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
    newest, size, count = 0, 0, 0
    stack = [path]
    while stack:
        if deadline and time.monotonic() > deadline:
            raise TimeoutError("Limite de varredura")
        p = stack.pop()
        s = p.lstat()
        if stat.S_ISLNK(s.st_mode):
            continue
        newest = max(newest, s.st_mtime)
        if stat.S_ISDIR(s.st_mode):
            stack.extend(p.iterdir())
        elif stat.S_ISREG(s.st_mode):
            size += s.st_size
            count += 1
    return {"bytes": size, "files": count, "newest_mtime": newest}


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


class Guardian:
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

    def projects(self):
        deadline = time.monotonic() + self.policy["max_scan_seconds"]
        count = 0
        seen = set()
        for name in self.policy["project_roots"]:
            root = self.home / name
            if not root.is_dir() or root.is_symlink():
                continue
            for base, dirs, files in os.walk(root, followlinks=False):
                count += 1
                if count > self.policy["max_scan_directories"] or time.monotonic() > deadline:
                    self.record("scan_incomplete", {"reason": "project scan budget"})
                    return
                p = Path(base)
                dirs[:] = [d for d in dirs if d not in SKIP_NAMES and not (p / d).is_symlink()]
                if "package.json" in files or "Cargo.toml" in files or ".git" in files or (p / ".git").is_dir():
                    if p not in seen:
                        seen.add(p)
                        yield p

    def eligible(self, path, kind):
        path = safe_inside(path, self.home)
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
            allowed = any(path.is_relative_to(safe_inside(self.home / r, self.home))
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
        if not plan or time.time() - dt.datetime.fromisoformat(plan["created_at"]).timestamp() > 3600:
            raise ValueError("Execute plan antes de clean --apply; plano válido por uma hora")
        results = []
        for item in plan["items"]:
            path = self.home / item["path"]
            try:
                stats = self.eligible(path, item["kind"])
                s = path.stat()
                if (s.st_dev, s.st_ino) != (item["device"], item["inode"]):
                    raise ValueError("Caminho substituído após o plano")
                if in_use(path):
                    raise ValueError("Em uso ou uso não verificável")
                self.record("delete_started", {"path": str(path), "bytes": stats["bytes"]})
                shutil.rmtree(path)
                result = {"path": str(path), "removed": True, "bytes": stats["bytes"]}
            except (OSError, ValueError, RuntimeError, TimeoutError) as e:
                result = {"path": str(path), "removed": False, "reason": str(e)}
            results.append(result)
            self.record("cleanup", result)
        write_json(self.state / "cleanup-plan.json", {})
        return {"items": results, "deleted_bytes": sum(x.get("bytes", 0) for x in results if x["removed"])}

    def folders(self):
        result = []
        for p in sorted(self.home.iterdir(), key=lambda p: p.name.lower()):
            if not p.is_dir() or p.is_symlink():
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
        if not any(path.is_relative_to(safe_inside(self.home / r, self.home))
                   for r in self.policy["project_roots"]):
            raise ValueError("Worktree fora das raízes autorizadas")
        if path.is_relative_to(self.home / ".codex/worktrees"):
            raise ValueError("Worktree do Codex exige arquivamento gerenciado")
        if not (path / ".git").is_file() or (path / ".git").is_symlink():
            raise ValueError("Só worktrees secundários podem ser removidos")
        if (path / ".gitmodules").exists():
            raise ValueError("Worktree com submódulos exige revisão")
        listing = require(["git", "-C", str(path), "worktree", "list", "--porcelain", "-z"])
        if listing.split("\0", 1)[0] == "worktree " + str(path):
            raise ValueError("Worktree principal é protegido")
        block = next((b for b in listing.split("\0\0") if b.startswith("worktree " + str(path) + "\0")), "")
        if not block or "\0locked" in block or "\0prunable" in block:
            raise ValueError("Worktree não verificado, bloqueado ou inconsistente")
        def validate_files():
            if require(["git", "-C", str(path), "status", "--porcelain", "--untracked-files=all"]):
                raise ValueError("Worktree com alterações locais")
            if require(["git", "-C", str(path), "ls-files", "--others", "--ignored", "--exclude-standard"]):
                raise ValueError("Arquivos ignorados precisam de backup ou limpeza antes da remoção")
            data = tree_stats(path, time.monotonic() + 20)
            if data["newest_mtime"] > time.time() - self.policy["worktree_age_days"] * DAY:
                raise ValueError("Worktree recente")
            if in_use(path):
                raise ValueError("Worktree em uso ou uso não verificável")
            return data
        data = validate_files()
        if not require(["git", "-C", str(path), "remote"]):
            raise ValueError("Worktree sem remoto")
        common = Path(require(["git", "-C", str(path), "rev-parse", "--path-format=absolute", "--git-common-dir"]))
        repository = common
        if not apply:
            return {"path": str(path), "bytes": data["bytes"], "ready": False,
                    "pending": "Atualizar remotos e provar que todos os commits estão preservados"}
        # Fetch retrieves remote evidence. No commit, push or forced removal occurs.
        require(["git", "-C", str(path), "fetch", "--all", "--prune"], 120)
        if require(["git", "-C", str(path), "rev-list", "--count", "--all", "--not", "--remotes"]) != "0":
            raise ValueError("Há commits ou refs locais ainda não preservados em remotos")
        validate_files()
        self.record("worktree_remove_started", {"path": str(path), "repository": str(repository)})
        require(["git", "--git-dir", str(common), "worktree", "remove", str(path)], 60)
        self.record("worktree_removed", {"path": str(path), "bytes": data["bytes"]})
        return {"path": str(path), "removed": not path.exists(), "bytes": data["bytes"]}

    def background(self):
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
                    items.append({"label": p.get("Label", path.stem), "plist": str(path),
                                  "sha256": digest(path), "executable": exe,
                                  "review": flags, "trust": "unreviewed"})
                except (OSError, ValueError, plistlib.InvalidFileException, ExpatError) as e:
                    items.append({"plist": str(path), "error": type(e).__name__, "trust": "unknown"})
        previous = read_json(self.state / "background-baseline.json", {})
        for item in items:
            label = item.get("label", item["plist"])
            item["change"] = ("new" if label not in previous else
                              "unchanged" if previous[label] == item.get("sha256") else "modified")
        # An observed baseline is change detection, never an approval of a job.
        write_json(self.state / "background-baseline.json",
                   {i.get("label", i["plist"]): i.get("sha256") for i in items})
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

    def check(self, full=False):
        disk = shutil.disk_usage(self.home)
        total = command(["sysctl", "-n", "hw.memsize"])["stdout"].strip()
        pressure = command(["memory_pressure", "-Q"])
        swap = command(["sysctl", "vm.swapusage"])["stdout"].strip()
        match = re.search(r"used = ([\d.]+)([MG])", swap)
        swap_bytes = float(match[1]) * (1024 ** (2 if match[2] == "M" else 3)) if match else None
        processes = []
        for line in command(["ps", "-axo", "pid,pcpu,pmem,comm"])["stdout"].splitlines()[1:]:
            parts = line.strip().split(None, 3)
            if len(parts) == 4:
                try:
                    processes.append({"pid": int(parts[0]), "cpu": float(parts[1]),
                                      "memory_percent": float(parts[2]), "executable": parts[3]})
                except ValueError:
                    pass
        alerts = []
        if disk.free < self.policy["free_disk_warning_gib"] * GIB:
            alerts.append({"id": "disk", "severity": "critical" if disk.free <
                           self.policy["free_disk_critical_gib"] * GIB else "warning",
                           "text": f"Espaço livre: {disk.free/GIB:.2f} GiB"})
        if swap_bytes and swap_bytes > self.policy["swap_warning_gib"] * GIB:
            alerts.append({"id": "swap", "severity": "warning", "text": f"Swap usado: {swap_bytes/GIB:.2f} GiB"})
        previous = read_json(self.state / "snapshot.json", {})
        if not full:
            alerts.extend(a for a in previous.get("alerts", [])
                          if a["id"].startswith("launch:"))
        report = {"at": now(), "platform": sys.platform,
                  "os": command(["sw_vers", "-productVersion"])["stdout"].strip(),
                  "disk": {"total_bytes": disk.total, "free_bytes": disk.free, "used_bytes": disk.used},
                  "memory": {"total_bytes": int(total) if total.isdigit() else None,
                             "pressure": pressure, "swap": swap, "swap_bytes": swap_bytes,
                             "vm_stat": command(["vm_stat"])["stdout"]},
                  "load_average": list(os.getloadavg()),
                  "battery": command(["pmset", "-g", "batt"]),
                  "processes": sorted(processes, key=lambda x: x["cpu"], reverse=True),
                  "alerts": alerts, "folders": self.folders()}
        for key in ("applications", "updates", "background", "security", "full_checked_at"):
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
                    artifacts = json.dumps(cask.get("artifacts", []))
                    if (Path(app["path"]).name in artifacts):
                        app["update_status"] = ("outdated" if cask["token"] in outdated_tokens else
                                                "current" if report["updates"]["brew_refresh"]["ok"] and
                                                "casks" in outdated else "unknown")
                        app["update_source"] = "Homebrew"
            report["background"] = self.background()
            report["security"] = {
                "sip": command(["csrutil", "status"]),
                "gatekeeper": command(["spctl", "--status"]),
                "filevault": command(["fdesetup", "status"]),
                "xprotect_receipt": command(["pkgutil", "--pkg-info", "com.apple.pkg.XProtectPayloads"]),
                "listeners": command(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"], 20),
                "limitation": "Assinatura, Gatekeeper e inventário não comprovam ausência de malware."}
            report["full_checked_at"] = now()
            for job in report["background"]:
                if job.get("review") or job.get("change") == "modified":
                    alerts.append({"id": "launch:" + job.get("label", job["plist"]),
                                   "severity": "review", "text": "Revisar serviço em segundo plano"})
        prev_ids = {a["id"]: a["severity"] for a in previous.get("alerts", [])}
        report["alert_changes"] = [a for a in alerts if prev_ids.get(a["id"]) != a["severity"]]
        report["resolved_alerts"] = sorted(set(prev_ids) - {a["id"] for a in alerts})
        write_json(self.state / "snapshot.json", report)
        self.wiki(report)
        self.dashboard(report)
        self.record("check", {"full": full, "alerts": len(alerts),
                              "free_bytes": disk.free, "at": report["at"]})
        return report

    def wiki(self, report):
        root = safe_inside(self.home / "Documents/MacWiki", self.home)
        root.mkdir(parents=True, exist_ok=True)
        pages = ["# Wiki do Mac", "", f"Atualizada em {report['at']}.", "",
                 "[Saúde](Saude.md) · [Aplicativos](Aplicativos.md) · [Serviços](Servicos.md)", "",
                 "Esta wiki indexa as pastas reais. Configurações e projetos mantêm seus caminhos.", "",
                 "| Pasta | Categoria | Local |", "| --- | --- | --- |"]
        for item in report["folders"]:
            title = item["name"].replace("|", r"\|").replace("\n", " ")
            url = "file://" + urllib.parse.quote(item["path"])
            pages.append(f"| {title} | {item['category']} | [Abrir]({url}) |")
        (root / "Home.md").write_text("\n".join(pages) + "\n")
        (root / "Saude.md").write_text(
            f"# Saúde\n\nEspaço livre: {report['disk']['free_bytes']/GIB:.2f} GiB.\n\n"
            f"Swap: {report['memory']['swap']}.\n\n"
            "Limpeza exige plano recente, idade mínima e ausência de arquivos em uso.\n"
            "Backup exige repositório privado e restauração com hashes iguais antes de excluir.\n")
        apps = ["# Aplicativos", "", "| App | Versão | Atualização | Assinatura |",
                "| --- | --- | --- | --- |"]
        apps += [f"| {a['name']} | {a.get('version','?')} | {a['update_status']} | "
                 f"{a['signature']['verified']} |" for a in report.get("applications", [])]
        apps += ["", "unknown exige checagem no fornecedor. Assinatura válida não é veredito antimalware."]
        (root / "Aplicativos.md").write_text("\n".join(apps) + "\n")
        jobs = ["# Serviços", "", "A linha de base registra o que foi observado; não concede confiança.", "",
                "| Serviço | Executável | Mudança | Revisão |", "| --- | --- | --- | --- |"]
        jobs += [f"| {j.get('label','?')} | {j.get('executable','?')} | {j.get('change','?')} | "
                 f"{'; '.join(j.get('review',[])) or 'pendente'} |" for j in report.get("background", [])]
        (root / "Servicos.md").write_text("\n".join(jobs) + "\n")
        for p in root.glob("*.md"):
            p.chmod(0o600)

    def dashboard(self, report):
        esc = html.escape
        disk = report["disk"]
        def table(rows, columns):
            heads = "".join(f"<th>{esc(label)}</th>" for key, label in columns)
            body = "".join("<tr>" + "".join(f"<td>{esc(str(row.get(key,'')))}</td>" for key, _ in columns) + "</tr>" for row in rows)
            return f"<table><thead><tr>{heads}</tr></thead><tbody>{body}</tbody></table>"
        app_rows = [{**a, "signed": a["signature"]["verified"]} for a in report.get("applications", [])]
        bg_rows = [{**j, "review_text": "; ".join(j.get("review", [])) or "Revisão pendente"}
                   for j in report.get("background", [])]
        plan = read_json(self.state / "cleanup-plan.json", {}) or {}
        sections = {
            "Saúde": "<h2>Processos e memória</h2>" + table(report["processes"][:40],
                     [("pid", "PID"), ("cpu", "CPU %"), ("memory_percent", "Memória %"), ("executable", "Processo")]),
            "Wiki": "<h2>Pastas do Mac</h2><p>Índice das pastas reais. Configurações e projetos preservam os caminhos.</p>" +
                    table(report["folders"], [("name", "Pasta"), ("category", "Categoria"), ("path", "Local")]),
            "Apps": "<h2>Atualizações e assinaturas</h2><p>unknown indica cobertura pendente. Assinaturas não comprovam ausência de malware.</p>" +
                    table(app_rows, [("name", "App"), ("version", "Versão"), ("update_status", "Atualização"), ("signed", "Assinatura verificada")]),
            "Serviços": "<h2>Atividades em segundo plano</h2><p>A linha de base detecta mudanças. Cada serviço ainda exige classificação.</p>" +
                        table(bg_rows, [("label", "Serviço"), ("executable", "Executável"), ("change", "Mudança"), ("review_text", "Revisão")]),
            "Limpeza": "<h2>Plano de manutenção</h2><p>Plano antes da execução. Caches antigos; dependências com lockfile; projetos sem alterações locais.</p>" +
                       table(plan.get("items", []), [("path", "Candidato"), ("kind", "Tipo"), ("bytes", "Bytes")]) +
                       "<p>Worktrees do Codex usam o arquivamento nativo. Dados pessoais só podem ser excluídos após backup privado e restauração verificada.</p>",
        }
        nav = "".join(f'<button onclick="show({i})">{k}</button>' for i, k in enumerate(sections))
        content = "".join(f'<section id="s{i}" {"hidden" if i else ""}>{v}</section>' for i, v in enumerate(sections.values()))
        alerts = "".join(f"<li>{esc(a['text'])}</li>" for a in report["alerts"])
        document = f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Mac Guardian</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:#f3f4ef;color:#182522;font:15px -apple-system,BlinkMacSystemFont,sans-serif}}
main{{max-width:1260px;margin:auto;padding:44px 32px}}header{{display:flex;justify-content:space-between;align-items:center}}
h1{{font-size:42px;letter-spacing:-1.6px;margin:8px 0}}small,.muted{{color:#64746f}}.badge{{background:#d9eadf;padding:9px 14px;border-radius:20px}}
.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin:28px 0}}article{{background:white;border:1px solid #dde3dd;border-radius:18px;padding:22px}}
article strong{{display:block;font-size:34px;margin:14px 0}}.warning{{color:#a84e20}}nav{{display:flex;gap:9px;margin:30px 0 20px}}
button{{border:1px solid #cad6ce;border-radius:30px;padding:11px 22px;background:white;cursor:pointer;font:inherit}}
button.active{{background:#234d3d;color:white}}section{{background:white;border-radius:18px;padding:25px;overflow:auto;border:1px solid #dde3dd}}
table{{width:100%;border-collapse:collapse;font-size:13px}}td,th{{padding:12px 9px;text-align:left;border-bottom:1px solid #edf0eb;overflow-wrap:anywhere}}th{{color:#64746f}}
footer{{padding:22px 0;color:#64746f}}h2{{font-size:23px}}ul{{line-height:1.8}}@media(max-width:700px){{.cards{{grid-template-columns:1fr}}nav{{flex-wrap:wrap}}main{{padding:20px}}}}
</style><main><header><div><small>OPENCLAW · PLOW · MACOS</small><h1>Mac Guardian</h1>
<p class="muted">Manutenção com histórico e backups verificáveis.</p></div><span class="badge">Diagnóstico local</span></header>
<div class="cards"><article><small>ARMAZENAMENTO LIVRE</small><strong class="{'warning' if disk['free_bytes']<5*GIB else ''}">{disk['free_bytes']/GIB:.2f} GiB</strong>
<small>de {disk['total_bytes']/GIB:.0f} GiB no volume de dados</small></article>
<article><small>MEMÓRIA FÍSICA</small><strong>{(report['memory']['total_bytes'] or 0)/GIB:.0f} GiB</strong><small>Swap usado: {(report['memory']['swap_bytes'] or 0)/GIB:.2f} GiB</small></article>
<article><small>ITENS NO INVENTÁRIO</small><strong>{len(report.get('applications',[]))} apps</strong><small>{len(report['folders'])} pastas · {len(report.get('background',[]))} serviços</small></article></div>
<ul>{alerts}</ul><nav>{nav}</nav>{content}<footer>Atualizado: {esc(report['at'])}. Dados privados neste Mac. Auditoria de segurança ainda exige revisão.</footer></main>
<script>function show(n){{document.querySelectorAll('section').forEach((e,i)=>e.hidden=i!==n);document.querySelectorAll('button').forEach((e,i)=>e.classList.toggle('active',i===n))}}show(0)</script></html>"""
        p = self.state / "dashboard.html"
        p.write_text(document)
        p.chmod(0o600)

    def organize(self, apply=False):
        categories = {".pdf": "Documentos", ".docx": "Documentos", ".txt": "Documentos",
                      ".md": "Documentos", ".xlsx": "Planilhas", ".csv": "Planilhas",
                      ".png": "Imagens", ".jpg": "Imagens", ".jpeg": "Imagens",
                      ".webp": "Imagens", ".mp4": "Videos", ".mov": "Videos",
                      ".zip": "Arquivos", ".tar": "Arquivos", ".gz": "Arquivos",
                      ".dmg": "Instaladores", ".pkg": "Instaladores"}
        moves = []
        cutoff = time.time() - self.policy["organization_age_days"] * DAY
        for folder in ("Downloads", "Desktop"):
            root = self.home / folder
            if not root.is_dir() or root.is_symlink():
                continue
            for p in root.iterdir():
                category = categories.get(p.suffix.lower())
                if not category or p.name.startswith(".") or p.is_symlink() or not p.is_file():
                    continue
                if p.stat().st_mtime > cutoff:
                    continue
                dest = root / category / p.name
                try:
                    safe_inside(dest, root)
                    if dest.exists() or dest.is_symlink():
                        continue
                    item = {"source": str(p), "destination": str(dest), "sha256": digest(p)}
                    moves.append(item)
                except (ValueError, OSError):
                    continue
        if apply:
            txn = uuid.uuid4().hex
            journal = self.state / "moves" / (txn + ".json")
            write_json(journal, {"items": []})
            done = []
            for m in moves:
                source, dest = Path(m["source"]), Path(m["destination"])
                safe_inside(source, self.home)
                safe_inside(dest, self.home)
                if in_use(source):
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists() or dest.is_symlink() or digest(source) != m["sha256"]:
                    raise ValueError("Arquivo mudou durante a organização")
                # A hard link publishes the destination without overwriting it.
                os.link(source, dest, follow_symlinks=False)
                source.unlink()
                done.append(m)
                write_json(journal, {"items": done})
                self.record("move", m | {"transaction": txn})
            return {"transaction": txn, "items": done, "undo": f"undo {txn}"}
        write_json(self.state / "organization-plan.json", {"at": now(), "items": moves})
        return {"items": moves}

    def undo(self, transaction):
        if not re.fullmatch("[a-f0-9]{32}", transaction):
            raise ValueError("Transação inválida")
        journal = self.state / "moves" / (transaction + ".json")
        data = read_json(journal)
        if data is None:
            raise ValueError("Transação ausente")
        remaining = data["items"].copy()
        for m in reversed(data["items"]):
            source, dest = Path(m["source"]), Path(m["destination"])
            safe_inside(source, self.home)
            safe_inside(dest, self.home)
            if source.exists() or source.is_symlink() or digest(dest) != m["sha256"]:
                raise ValueError("Restaurar sobrescreveria arquivo ou conteúdo alterado")
            os.link(dest, source, follow_symlinks=False)
            dest.unlink()
            remaining.remove(m)
            write_json(journal, {"items": remaining})
            self.record("undo_move", m)
        return {"restored": len(data["items"])}

    def backup_manifest(self, source):
        source = safe_inside(source, self.home)
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
                if source == self.home / "Documents/MacWiki":
                    raise ValueError("Wiki ativa tem backup, mas não pode ser removida")
                if in_use(source):
                    raise ValueError("Origem em uso ou uso não verificável")
                # Revalidate after lsof, then remove only the backed-up files.
                if self.backup_manifest(source) != manifest:
                    raise ValueError("Origem mudou; exclusão cancelada")
                for rel, expected in manifest.items():
                    path = safe_inside(source / rel, source)
                    if digest(path) != expected:
                        raise ValueError("Origem mudou durante a exclusão; interrompida")
                    path.unlink()
                    self.record("offload_file", {"snapshot": snapshot_id, "path": str(path),
                                                 "sha256": expected})
                for root, dirs, names in os.walk(source, topdown=False):
                    try:
                        Path(root).rmdir()
                    except OSError:
                        pass
                receipt["offloaded"] = not source.exists()
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
    sub.add_parser("plan")
    sub.add_parser("worktrees")
    worktree = sub.add_parser("remove-worktree")
    worktree.add_argument("--path", required=True)
    worktree.add_argument("--apply", action="store_true")
    for name in ("clean", "organize"):
        p = sub.add_parser(name)
        p.add_argument("--apply", action="store_true")
    undo = sub.add_parser("undo")
    undo.add_argument("transaction")
    backup = sub.add_parser("backup")
    backup.add_argument("--source", required=True)
    backup.add_argument("--repo", required=True)
    backup.add_argument("--offload", action="store_true")
    args = parser.parse_args()
    try:
        g = Guardian(args.home, args.state)
        with g.lock():
            if args.action == "init":
                p = g.state / "policy.json"
                if not p.exists():
                    write_json(p, DEFAULT_POLICY)
                result = {"policy": str(p), "state": str(g.state)}
            elif args.action == "check":
                report = g.check(args.full)
                result = {"snapshot": str(g.state / "snapshot.json"), "dashboard": str(g.state / "dashboard.html"),
                          "alerts": report["alerts"], "alert_changes": report["alert_changes"],
                          "resolved_alerts": report["resolved_alerts"], "apps": len(report.get("applications", []))}
            elif args.action == "plan":
                result = g.cleanup_plan()
            elif args.action == "worktrees":
                result = g.worktrees()
            elif args.action == "remove-worktree":
                result = g.remove_worktree(args.path, args.apply)
            elif args.action == "clean":
                result = g.clean(args.apply)
            elif args.action == "organize":
                result = g.organize(args.apply)
            elif args.action == "undo":
                result = g.undo(args.transaction)
            elif args.action == "backup":
                result = g.backup(args.source, args.repo, args.offload)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except (OSError, ValueError, RuntimeError, TimeoutError, KeyError) as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

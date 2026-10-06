"""Private recovery, approval receipts and isolated Git snapshots. Standard library."""
from __future__ import annotations

import datetime as dt
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import time
import uuid
import zipfile


class WorkspaceCare:
    """Uses the Guardian's path, digest, command and atomic JSON helpers."""

    def backup_folder(self):
        root = self._safe(self.home / self.policy["local_backup_root"], self.home)
        if any(root == self.home / name or root.is_relative_to(self.home / name) or
               root.resolve().is_relative_to((self.home / name).resolve())
               for name in set(self.policy["excluded_roots"] + list(self.cloud_exclusions))):
            raise ValueError("Backup local precisa ficar fora de Documents, iCloud e Drive")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.chmod(0o700)
        return root

    def receipt_path(self, kind, receipt):
        if not re.fullmatch(r"[a-f0-9]{32}", receipt):
            raise ValueError("Identificador de recuperação inválido")
        return self._safe(self.backup_folder() / kind / receipt / "receipt.json", self.home)

    def request_approval(self, action, payload):
        fingerprint = hashlib.sha256(json.dumps([action, payload], sort_keys=True).encode()).hexdigest()
        pending = self._read(self.state / "approvals.json", [])
        current = next((p for p in pending if p["fingerprint"] == fingerprint and not p.get("consumed_at")), None)
        if current and current.get("approved_at") and not self.approval_valid(current):
            current.pop("evidence", None)
            current["approved_at"] = None
            self._write(self.state / "approvals.json", pending)
        if current is None:
            current = {"id": uuid.uuid4().hex, "at": self._now(), "action": action,
                       "payload": payload, "fingerprint": fingerprint, "approved_at": None}
            pending.append(current)
            self._write(self.state / "approvals.json", pending[-1000:])
        return {"request_id": current["id"], "action": action, "requires_user_action": True,
                "reason": "Procedimento sem restauração garantida exige autorização do proprietário"}

    @staticmethod
    def approval_valid(item):
        try:
            age = time.time() - dt.datetime.fromisoformat(item["approved_at"]).timestamp()
            return not item.get("consumed_at") and 0 <= age <= 3600
        except (KeyError, TypeError, ValueError):
            return False

    def approve(self, request_id, evidence):
        if not evidence.strip():
            raise ValueError("Registre a autorização explícita do proprietário para este pedido")
        pending = self._read(self.state / "approvals.json", [])
        item = next((p for p in pending if p["id"] == request_id), None)
        if item is None or item.get("consumed_at"):
            raise ValueError("Pedido ausente ou já utilizado")
        item.update(approved_at=self._now(), evidence=evidence[:1000])
        self._write(self.state / "approvals.json", pending)
        return {"request_id": request_id, "approved": True, "valid_minutes": 60}

    def consume_approval(self, action, payload, request_id=None):
        fingerprint = hashlib.sha256(json.dumps([action, payload], sort_keys=True).encode()).hexdigest()
        pending = self._read(self.state / "approvals.json", [])
        item = next((p for p in pending if p["fingerprint"] == fingerprint and
                     (request_id is None or p["id"] == request_id) and p.get("approved_at") and not p.get("consumed_at")), None)
        if item and self.approval_valid(item):
            item["consumed_at"] = self._now()
            self._write(self.state / "approvals.json", pending)
            return True
        return False

    def cloud_status(self):
        saved = self._read(self.state / "cloud.json", {})
        providers = []
        if (self.home / "Library/Mobile Documents/com~apple~CloudDocs").is_dir():
            providers.append("icloud")
        mounts = self.home / "Library/CloudStorage"
        if mounts.is_dir() and any(p.name.startswith("GoogleDrive-") for p in mounts.iterdir()):
            providers.append("google-drive")
        return {"configured": bool(saved.get("provider")), "provider": saved.get("provider"),
                "detected": providers, "needs_question": not saved.get("provider") and not saved.get("question_asked"),
                "awaiting_answer": not saved.get("provider"),
                "question": "Você tem Google Drive ou iCloud que eu possa usar para arquivos comuns? Segredos ficam somente no backup local.",
                "destinations": saved.get("destinations", []), "secrets_allowed": False}

    def configure_cloud(self, provider=None, roots=(), asked=False):
        saved = self._read(self.state / "cloud.json", {})
        if asked:
            saved["question_asked"] = True
        if provider is not None:
            if provider not in ("icloud", "google-drive", "both", "none"):
                raise ValueError("Provedor inválido")
            destinations = []
            for root in roots:
                path = Path(root).expanduser().resolve()
                cloud_roots = [self.home / "Library/Mobile Documents/com~apple~CloudDocs",
                               self.home / "Library/CloudStorage"]
                if not any(path.is_relative_to(p.resolve()) and path != p.resolve() for p in cloud_roots):
                    raise ValueError("Escolha uma pasta específica dentro do armazenamento cloud")
                if path.name.lower() in ("documents", "desktop"):
                    raise ValueError("Documents e Mesa não são destinos de backup")
                destinations.append(str(path))
            if provider == "none" and destinations:
                raise ValueError("Armazenamento local não usa destinos cloud")
            saved.update(provider=provider, destinations=destinations, configured_at=self._now())
        self._write(self.state / "cloud.json", saved)
        return self.cloud_status()

    def local_secret_backup(self, project, files, apply=True):
        """Content-addressed copies, never returned as text or sent to a network."""
        copied = []
        if not apply:
            return {"count": len(files), "uploaded": False, "mode": "preview"}
        root = self.backup_folder() / "Secrets"
        for path in files:
            path = self._safe(path, self.home)
            if self.excluded(path) or not path.is_file() or path.stat().st_nlink != 1:
                raise ValueError("Origem de segredo protegida ou indisponível")
            expected = self._hash(path)
            identity = hashlib.sha256(str(path).encode()).hexdigest()[:24]
            target = self._safe(root / identity / expected / "content", self.home)
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if target.exists():
                if self._hash(target) != expected:
                    raise ValueError("Backup local existente divergiu")
            else:
                with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
                    temporary = Path(stream.name)
                    with path.open("rb") as original:
                        shutil.copyfileobj(original, stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    if self._hash(temporary) != expected or self._hash(path) != expected:
                        raise ValueError("Segredo mudou durante o backup")
                    os.link(temporary, target, follow_symlinks=False)
                finally:
                    temporary.unlink(missing_ok=True)
            target.chmod(0o600)
            self._write(target.parent / "receipt.json", {"at": self._now(), "source": str(path),
                        "project": str(project), "sha256": expected, "mode": stat.S_IMODE(path.stat().st_mode),
                        "local_only": True, "uploaded": False})
            copied.append({"source": str(path), "backup": str(target), "verified": True})
        return {"items": copied, "count": len(copied), "uploaded": False}

    def restore_secret(self, identity, version):
        if not re.fullmatch(r"[a-f0-9]{24}", identity) or not re.fullmatch(r"[a-f0-9]{64}", version):
            raise ValueError("Versão de segredo inválida")
        root = self._safe(self.backup_folder() / "Secrets" / identity / version, self.home)
        receipt = self._read(root / "receipt.json")
        source = self._safe(Path(receipt["source"]), self.home)
        content = root / "content"
        if self._hash(content) != receipt["sha256"] or source.exists() or source.is_symlink():
            raise ValueError("Restauração inválida ou sobrescreveria a origem")
        source.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with source.open("xb") as stream, content.open("rb") as original:
            shutil.copyfileobj(original, stream)
        source.chmod(0o600)
        return {"restored": str(source), "verified": self._hash(source) == receipt["sha256"]}

    def quarantine_tree(self, source, kind):
        source = self._safe(source, self.home)
        identity = uuid.uuid4().hex
        receipt_path = self.receipt_path("Quarantine", identity)
        destination = self._safe(receipt_path.parent / "data", self.home)
        receipt_path.parent.mkdir(parents=True, mode=0o700)
        receipt = {"id": identity, "at": self._now(), "kind": kind, "source": str(source),
                   "destination": str(destination), "state": "prepared"}
        self._write(receipt_path, receipt)
        # Same-volume rename preserves all data, links, modes and extended attributes.
        if source.stat().st_dev != destination.parent.stat().st_dev:
            raise ValueError("Quarentena precisa estar no mesmo volume")
        source.rename(destination)
        receipt["state"] = "quarantined"
        self._write(receipt_path, receipt)
        return {"receipt": identity, "destination": str(destination), "reversible": True,
                "restore": f"restore-quarantine --receipt {identity}"}

    def restore_quarantine(self, receipt_id):
        receipt_path = self.receipt_path("Quarantine", receipt_id)
        receipt = self._read(receipt_path)
        source = self._safe(Path(receipt["source"]), self.home)
        data = self._safe(receipt_path.parent / "data", self.home)
        if source.exists() or source.is_symlink() or not data.is_dir():
            raise ValueError("Restauração sobrescreveria dados ou quarentena não está disponível")
        if self._busy(data):
            raise ValueError("Backup em uso")
        source.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        data.rename(source)
        receipt["state"] = "restored"
        self._write(receipt_path, receipt)
        return {"restored": str(source), "receipt": receipt_id}

    def purge_quarantine(self, receipt_id, apply=False, approval=None):
        receipt_path = self.receipt_path("Quarantine", receipt_id)
        receipt = self._read(receipt_path)
        path = self._safe(receipt_path.parent / "data", self.home)
        if receipt["state"] != "quarantined" or not path.is_dir():
            raise ValueError("Quarentena não está disponível para exclusão")
        inventory = self.tree_manifest(path)
        payload = {"receipt": receipt_id, "inventory": hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest()}
        if not apply:
            return self.request_approval("purge_quarantine", payload) | {"source": receipt["source"], "irreversible": True}
        if self._busy(path) or not self.consume_approval("purge_quarantine", payload, approval):
            raise ValueError("Exclusão permanente exige autorização recente para este conteúdo")
        shutil.rmtree(path)
        receipt.update(state="purged", purged_at=self._now())
        self._write(receipt_path, receipt)
        self.record("purge_quarantine", {"receipt": receipt_id, "approved": True})
        return {"purged": True, "receipt": receipt_id, "irreversible": True}

    def tree_manifest(self, root, exclude_git=False):
        result, total = {}, 0
        deadline = time.monotonic() + self.policy["max_scan_seconds"]
        for base, dirs, files in os.walk(root, followlinks=False):
            if exclude_git and Path(base) == root:
                dirs[:] = [d for d in dirs if d != ".git"]
                files = [f for f in files if f != ".git"]
            for name in [*dirs, *files]:
                path = Path(base) / name
                info = path.lstat()
                link = stat.S_ISLNK(info.st_mode)
                directory = stat.S_ISDIR(info.st_mode)
                if not (link or directory or stat.S_ISREG(info.st_mode)):
                    raise ValueError("Arquivo especial exige preservação em seu local")
                if not link and not directory and info.st_nlink != 1:
                    raise ValueError("Hardlink exige preservação em seu local")
                target = os.readlink(path) if link else None
                total += 0 if directory or link else info.st_size
                if time.monotonic() > deadline or total > self.policy["worktree_archive_max_mib"] * 1024**2:
                    raise ValueError("Arquivo local excede o limite de backup; origem preservada")
                attrs = {}
                if hasattr(os, "listxattr"):
                    for key in os.listxattr(path, follow_symlinks=False):
                        value = os.getxattr(path, key, follow_symlinks=False)
                        if len(value) > 1024**2:
                            raise ValueError("Metadados grandes demais; origem preservada")
                        attrs[key] = base64.b64encode(value).decode()
                result[path.relative_to(root).as_posix()] = {"sha256": hashlib.sha256(target.encode()).hexdigest() if link else
                    hashlib.sha256(b"").hexdigest() if directory else self._hash(path),
                    "mode": stat.S_IMODE(info.st_mode), "mtime_ns": info.st_mtime_ns,
                    "size": info.st_size if not directory and not link else 0,
                    "kind": "symlink" if link else "directory" if directory else "file",
                    "target": target, "xattrs": attrs}
            dirs[:] = [d for d in dirs if not (Path(base) / d).is_symlink()]
        return result

    def git_run(self, project, args, data=None, env=None, timeout=120):
        safe_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        safe_env.update(GIT_TERMINAL_PROMPT="0", GIT_AUTHOR_NAME="Mac Guardian",
                        GIT_AUTHOR_EMAIL="mac-guardian@localhost", GIT_COMMITTER_NAME="Mac Guardian",
                        GIT_COMMITTER_EMAIL="mac-guardian@localhost")
        safe_env.update(env or {})
        proc = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
                               "-C", str(project), *args], input=data, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, env=safe_env, timeout=timeout)
        if proc.returncode:
            # Git errors can contain a credential-bearing remote or file contents.
            raise RuntimeError("Git não concluiu " + args[0] + "; origem preservada")
        return proc.stdout

    def project_files(self, project, ref=None):
        if ref:
            rows = self.git_run(project, ["ls-tree", "-r", "-z", ref]).split(b"\0")
            return [(row.split(b"\t", 1)[1].decode("utf-8"), row.split(b"\t", 1)[0].split()[2].decode())
                    for row in rows if row and row.startswith((b"100644 ", b"100755 "))]
        if not (project / ".git").exists():
            names = self.unversioned_files(project).split(b"\0")
        else:
            names = self.git_run(project, ["ls-files", "-z", "--cached", "--others", "--exclude-standard"]).split(b"\0")
        return [(name.decode("utf-8"), None) for name in sorted(set(names)) if name]

    def unversioned_files(self, project, ignored=False):
        # Honor .gitignore without creating or writing .git in the source folder.
        with tempfile.TemporaryDirectory(prefix="inventory-", dir=self.state) as tmp:
            sandbox = Path(tmp)
            self.git_run(sandbox, ["init", "--quiet"])
            return self.git_run(sandbox, ["--git-dir", str(sandbox / ".git"), "--work-tree", str(project),
                "ls-files", "--others", *(["--ignored"] if ignored else []), "--exclude-standard", "-z"],
                timeout=self.policy["max_scan_seconds"])

    def ignored_secrets(self, project):
        ignored = self.git_run(project, ["ls-files", "--others", "--ignored", "--exclude-standard", "-z"]) if (project / ".git").exists() else self.unversioned_files(project, ignored=True)
        return [project / p.decode() for p in ignored.split(b"\0") if p and
                any(self.secret_name.search(part) for part in Path(p.decode()).parts) and
                not any(part in self.skip_names for part in Path(p.decode()).parts)]

    def project_manifest(self, project, ref=None):
        manifest, blocked, secret_files = {}, [], []
        total = 0
        deadline = time.monotonic() + self.policy["max_scan_seconds"]
        for name, blob in self.project_files(project, ref):
            rel = Path(name)
            if rel.is_absolute() or ".." in rel.parts or any(part in self.skip_names for part in rel.parts):
                blocked.append({"path": name, "reason": "artifact_or_path"})
                continue
            path = project / rel
            if not ref and not path.exists():
                continue
            if not ref and (path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1):
                blocked.append({"path": name, "reason": "linked_or_special"})
                continue
            if not ref:
                self._safe(path, self.home)
            if any(self.secret_name.search(part) for part in rel.parts):
                blocked.append({"path": name, "reason": "secret_local_only"})
                if not ref:
                    secret_files.append(path)
                continue
            size = int(self.git_run(project, ["cat-file", "-s", blob])) if ref else path.stat().st_size
            if size > 45 * 1024**2:
                blocked.append({"path": name, "reason": "large_file_local_only"})
                continue
            total += size
            if total > self.policy["project_snapshot_max_mib"] * 1024**2 or time.monotonic() > deadline:
                raise ValueError("Snapshot excedeu o limite; projeto continua local")
            data = self.git_run(project, ["cat-file", "blob", blob]) if ref else path.read_bytes()
            if self.secret_content.search(data):
                blocked.append({"path": name, "reason": "secret_local_only"})
                if not ref:
                    secret_files.append(path)
                continue
            manifest[name] = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data),
                              "blob": blob, "executable": (path.stat().st_mode & 0o111) != 0 if not ref else
                              self.git_run(project, ["ls-tree", ref, "--", name]).startswith(b"100755")}
        return manifest, blocked, secret_files

    def private_project_repo(self):
        configured = self.policy["project_backup_repo"]
        owner_result = self._command(["gh", "api", "user", "--jq", ".login"], 20)
        if not owner_result["ok"] or not re.fullmatch(r"[A-Za-z0-9-]+", owner_result["stdout"].strip()):
            raise RuntimeError("GitHub autenticado indisponível; projetos permanecem locais")
        owner = owner_result["stdout"].strip()
        repo = configured or owner + "/mac-guardian-project-backups"
        if not re.fullmatch(re.escape(owner) + r"/[A-Za-z0-9_.-]+", repo):
            raise ValueError("Snapshots automáticos precisam de repositório privado do proprietário")
        result = self._command(["gh", "repo", "view", repo, "--json", "isPrivate,url"], 30)
        if not result["ok"]:
            if configured or not re.search(r"404|not found|could not resolve", result["stderr"], re.I):
                raise RuntimeError("Repositório privado indisponível")
            created = self._command(["gh", "repo", "create", repo, "--private"], 60)
            if not created["ok"]:
                raise RuntimeError("Criação do repositório privado não foi confirmada")
            result = self._command(["gh", "repo", "view", repo, "--json", "isPrivate,url"], 30)
        if not result["ok"] or not json.loads(result["stdout"])["isPrivate"]:
            raise ValueError("Snapshots de trabalho inédito exigem GitHub privado")
        if not configured:
            self.policy["project_backup_repo"] = repo
            self._write(self.state / "policy.json", self.policy)
        return repo

    def project_snapshot(self, project, repo, ref=None):
        project = self._safe(Path(project).expanduser(), self.home)
        if self.excluded(project):
            raise ValueError("Projeto em pasta excluída")
        if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", repo):
            raise ValueError("Repositório inválido")
        visibility = self._command(["gh", "repo", "view", repo, "--json", "isPrivate,url"], 30)
        if not visibility["ok"] or not json.loads(visibility["stdout"]).get("isPrivate"):
            raise ValueError("Snapshots exigem repositório privado verificado")
        manifest, blocked, secrets = self.project_manifest(project, ref)
        local = self.local_secret_backup(project, secrets)
        # Include ignored secrets, but do not send any ignored files to GitHub.
        ignored_secrets = self.ignored_secrets(project)
        if ignored_secrets:
            local["count"] += self.local_secret_backup(project, ignored_secrets)["count"]
        if not manifest:
            raise ValueError("Nenhum arquivo sem segredos disponível para snapshot")
        key = hashlib.sha256(str(project).encode()).hexdigest()[:16]
        variant = hashlib.sha256((ref or "working").encode()).hexdigest()[:12]
        branch = "mac-guardian/" + key + "/" + variant
        with tempfile.TemporaryDirectory(prefix="project-", dir=self.state) as tmp:
            checkout = Path(tmp) / "snapshot"
            checkout.mkdir()
            self.git_run(checkout, ["init", "--quiet"])
            # gh provides its existing credential helper without changing user config.
            auth_config = ["-c", "credential.https://github.com.helper=!gh auth git-credential"]
            remote = "https://github.com/" + repo + ".git"
            self.git_run(checkout, [*auth_config, "remote", "add", "origin", remote])
            refs = self.git_run(checkout, [*auth_config, "ls-remote", "--heads", "origin", "refs/heads/" + branch]).decode().strip()
            parent = refs.split()[0] if refs else None
            if parent:
                self.git_run(checkout, [*auth_config, "fetch", "--quiet", "--depth", "1", "origin", "refs/heads/" + branch])
            rows = []
            for name, item in manifest.items():
                data = self.git_run(project, ["cat-file", "blob", item["blob"]]) if ref else (project / name).read_bytes()
                if hashlib.sha256(data).hexdigest() != item["sha256"]:
                    raise ValueError("Projeto mudou durante o snapshot")
                blob = self.git_run(checkout, ["hash-object", "-w", "--stdin", "--no-filters"], data=data).decode().strip()
                rows.append(("100755" if item["executable"] else "100644").encode() + b" " + blob.encode() + b"\t" + name.encode() + b"\0")
            self.git_run(checkout, ["update-index", "-z", "--index-info"], data=b"".join(rows))
            tree = self.git_run(checkout, ["write-tree"]).decode().strip()
            if parent and self.git_run(checkout, ["rev-parse", parent + "^{tree}"]).decode().strip() == tree:
                commit = parent
            else:
                commit = self.git_run(checkout, ["commit-tree", tree, *(["-p", parent] if parent else [])],
                                      data=b"Mac Guardian private workspace snapshot\n").decode().strip()
                self.git_run(checkout, [*auth_config, "push", "--quiet", "origin", commit + ":refs/heads/" + branch])
            # A fresh repository retrieves the branch; verify every restored file.
            restored = Path(tmp) / "restored"
            self.git_run(checkout, [*auth_config, "clone", "--quiet", "--no-checkout", "--depth", "1", "--single-branch", "--branch", branch, remote, str(restored)])
            if self.git_run(restored, ["rev-parse", "HEAD"]).decode().strip() != commit:
                raise ValueError("Branch remota mudou; remoção cancelada")
            restored_files = self.project_files(restored, "HEAD")
            restored_manifest = {name: hashlib.sha256(self.git_run(restored, ["cat-file", "blob", blob])).hexdigest()
                                 for name, blob in restored_files}
            if restored_manifest != {name: item["sha256"] for name, item in manifest.items()}:
                raise ValueError("Restauração remota divergiu; remoção cancelada")
            current, _, _ = self.project_manifest(project, ref)
            if current != manifest:
                raise ValueError("Origem mudou; próxima rotina fará novo snapshot")
        receipt = {"at": self._now(), "project": str(project), "ref": ref, "repo": repo, "branch": branch,
                   "commit": commit, "verified": True, "files": len(manifest), "excluded": blocked,
                   "local_secret_backups": local["count"], "source_branch_unchanged": True,
                   "fingerprint": hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()}
        receipts = self._read(self.state / "project-snapshots.json", {})
        receipts[str(project) + "|" + (ref or "working")] = receipt
        self._write(self.state / "project-snapshots.json", receipts)
        self.record("project_snapshot", {k: v for k, v in receipt.items() if k != "excluded"})
        return receipt

    def preserve_git_history(self, project, folder):
        """Store unpublished refs, the original index and its staged blobs locally."""
        index = Path(self.git_run(project, ["rev-parse", "--path-format=absolute", "--git-path", "index"]).decode().strip())
        if self.git_run(project, ["rev-parse", "--shared-index-path"]).strip():
            raise ValueError("Índice dividido exige preservação no local")
        shutil.copy2(index, folder / "index")
        (folder / "index").chmod(0o600)
        head = self.git_run(project, ["rev-parse", "HEAD"]).decode().strip()
        # write-tree can update cached-tree entries. Only a disposable index is used.
        staged_index = folder / "staged-index"
        shutil.copy2(index, staged_index)
        try:
            staged_tree = self.git_run(project, ["write-tree"], env={"GIT_INDEX_FILE": str(staged_index)}).decode().strip()
        finally:
            staged_index.unlink(missing_ok=True)
        staged = self.git_run(project, ["commit-tree", staged_tree, "-p", head], data=b"Local recovery of staged files\n").decode().strip()
        recovery_ref = "refs/mac-guardian/recovery/" + folder.name
        self.git_run(project, ["update-ref", recovery_ref, staged])
        bundle = folder / "history.bundle"
        self.git_run(project, ["bundle", "create", str(bundle), "--all"])
        self.git_run(project, ["bundle", "verify", str(bundle)])
        bundle.chmod(0o600)
        common = Path(self.git_run(project, ["rev-parse", "--path-format=absolute", "--git-common-dir"]).decode().strip())
        config = common / "config"
        self._safe(config, self.home) if config.is_relative_to(self.home) else None
        if config.is_symlink() or not config.is_file():
            raise ValueError("Configuração Git indisponível para recuperação")
        shutil.copy2(config, folder / "git-config")
        (folder / "git-config").chmod(0o600)
        return {"head": head, "recovery_ref": recovery_ref, "bundle_sha256": self._hash(bundle),
                "index_sha256": self._hash(folder / "index"), "config_sha256": self._hash(folder / "git-config")}

    def archive_worktree(self, path, snapshot):
        """Archive complete data before removing an idle ordinary Git worktree."""
        path = self._safe(path, self.home)
        if path.is_relative_to(self.home / ".codex/worktrees"):
            raise ValueError("Worktree do Codex exige arquivamento nativo na conversa proprietária")
        if not snapshot.get("verified") or snapshot.get("project") != str(path):
            raise ValueError("Snapshot remoto deste worktree precisa estar verificado")
        if not (path / ".git").is_file() or (path / ".gitmodules").exists() or self._busy(path):
            raise ValueError("Worktree principal, submódulos ou arquivos em uso são protegidos")
        listing = self.git_run(path, ["worktree", "list", "--porcelain", "-z"]).decode()
        block = next((b for b in listing.split("\0\0") if b.startswith("worktree " + str(path) + "\0")), "")
        if not block or "\0locked" in block or "\0prunable" in block or listing.startswith("worktree " + str(path) + "\0"):
            raise ValueError("Worktree bloqueado, principal ou inconsistente")
        manifest = self.tree_manifest(path, exclude_git=True)
        cutoff = time.time() - self.policy["worktree_age_days"] * 86400
        if path.stat().st_mtime > cutoff or any(i["mtime_ns"] / 1e9 > cutoff for i in manifest.values()):
            raise ValueError("Worktree recente")
        original_manifest, _, _ = self.project_manifest(path)
        fingerprint = hashlib.sha256(json.dumps(original_manifest, sort_keys=True).encode()).hexdigest()
        if fingerprint != snapshot["fingerprint"]:
            raise ValueError("Worktree mudou desde o backup remoto")
        receipt_id = uuid.uuid4().hex
        receipt_path = self.receipt_path("Worktrees", receipt_id)
        folder = receipt_path.parent
        folder.mkdir(parents=True, mode=0o700)
        history = self.preserve_git_history(path, folder)
        common = self.git_run(path, ["rev-parse", "--path-format=absolute", "--git-common-dir"]).decode().strip()
        branch = self.git_run(path, ["symbolic-ref", "--quiet", "--short", "HEAD"]).decode().strip() if "\0branch " in block else None
        archive = folder / "files.zip"
        with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as z:
            for name, item in manifest.items():
                if item["kind"] == "symlink":
                    info = zipfile.ZipInfo(name)
                    info.create_system = 3
                    info.external_attr = (stat.S_IFLNK | item["mode"]) << 16
                    z.writestr(info, item["target"].encode())
                elif item["kind"] == "directory":
                    z.writestr(name + "/", b"")
                else:
                    z.write(path / name, name)
        archive.chmod(0o600)
        with zipfile.ZipFile(archive) as z:
            if z.testzip() or {name.rstrip("/"): hashlib.sha256(z.read(name)).hexdigest() for name in z.namelist()} != {
                    name: item["sha256"] for name, item in manifest.items()}:
                raise ValueError("Arquivo local de recuperação divergiu")
        receipt = {"id": receipt_id, "at": self._now(), "source": str(path), "common": common,
                   "branch": branch, "history": history, "files": manifest, "state": "prepared",
                   "archive_sha256": self._hash(archive), "snapshot": snapshot}
        self._write(receipt_path, receipt)
        index = Path(self.git_run(path, ["rev-parse", "--path-format=absolute", "--git-path", "index"]).decode().strip())
        if self._busy(path) or self.tree_manifest(path, exclude_git=True) != manifest or self._hash(index) != history["index_sha256"] or self.git_run(path, ["rev-parse", "HEAD"]).decode().strip() != history["head"]:
            raise ValueError("Worktree mudou ou entrou em uso; remoção cancelada")
        # --force is confined to a fully verified recovery archive, never a failed check.
        self.git_run(path, ["worktree", "remove", "--force", str(path)])
        receipt["state"] = "archived"
        self._write(receipt_path, receipt)
        self.record("worktree_archived", {"path": str(path), "receipt": receipt_id})
        return {"removed": not path.exists(), "receipt": receipt_id, "reversible": True,
                "restore": f"restore-worktree --receipt {receipt_id}"}

    def restore_worktree(self, receipt_id):
        receipt_path = self.receipt_path("Worktrees", receipt_id)
        receipt = self._read(receipt_path)
        source = self._safe(Path(receipt["source"]), self.home)
        folder = receipt_path.parent
        if source.exists() or source.is_symlink():
            raise ValueError("Restauração sobrescreveria dados")
        if self._hash(folder / "files.zip") != receipt["archive_sha256"] or self._hash(folder / "history.bundle") != receipt["history"]["bundle_sha256"] or self._hash(folder / "index") != receipt["history"]["index_sha256"] or self._hash(folder / "git-config") != receipt["history"]["config_sha256"]:
            raise ValueError("Backup de recuperação alterado")
        common = Path(receipt["common"])
        source.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if common.is_dir():
            self.git_run(common, ["--git-dir", str(common), "worktree", "add", "--detach", "--no-checkout", str(source), receipt["history"]["head"]])
        else:
            common = folder / "recovered.git"
            self.git_run(folder, ["clone", "--bare", str(folder / "history.bundle"), str(common)])
            self.git_run(common, ["fetch", "--quiet", str(folder / "history.bundle"), "+refs/*:refs/*"])
            shutil.copy2(folder / "git-config", common / "config")
            self.git_run(common, ["config", "core.bare", "true"])
            self.git_run(common, ["worktree", "add", "--detach", "--no-checkout", str(source), receipt["history"]["head"]])
        detached = True
        if receipt["branch"]:
            refs = self.git_run(common, ["worktree", "list", "--porcelain"]).decode()
            branch_ref = "refs/heads/" + receipt["branch"]
            if "branch " + branch_ref + "\n" not in refs:
                try:
                    if self.git_run(common, ["rev-parse", branch_ref]).decode().strip() == receipt["history"]["head"]:
                        self.git_run(source, ["symbolic-ref", "HEAD", branch_ref])
                        detached = False
                except RuntimeError:
                    pass
        with zipfile.ZipFile(folder / "files.zip") as z:
            if {name.rstrip("/") for name in z.namelist()} != set(receipt["files"]):
                raise ValueError("Manifesto de recuperação divergiu")
            for name, item in sorted(receipt["files"].items(), key=lambda row: (row[1]["kind"] == "symlink", row[0])):
                destination = self._safe(source / name, source)
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                if item["kind"] == "directory":
                    destination.mkdir(exist_ok=True, mode=0o700)
                    continue
                data = z.read(name)
                if hashlib.sha256(data).hexdigest() != item["sha256"]:
                    raise ValueError("Arquivo de recuperação alterado")
                if item["kind"] == "symlink":
                    destination.symlink_to(data.decode())
                else:
                    with destination.open("xb") as stream:
                        stream.write(data)
            for name, item in sorted(receipt["files"].items(), key=lambda row: row[0].count("/"), reverse=True):
                destination = source / name
                if item["kind"] != "symlink":
                    destination.chmod(item["mode"])
                for key, value in item["xattrs"].items():
                    os.setxattr(destination, key, base64.b64decode(value), follow_symlinks=False)
                os.utime(destination, ns=(item["mtime_ns"], item["mtime_ns"]), follow_symlinks=False)
        index = Path(self.git_run(source, ["rev-parse", "--path-format=absolute", "--git-path", "index"]).decode().strip())
        shutil.copy2(folder / "index", index)
        if self.tree_manifest(source, exclude_git=True) != receipt["files"]:
            raise ValueError("Verificação da restauração divergiu")
        receipt["state"] = "restored"
        self._write(receipt_path, receipt)
        return {"restored": str(source), "receipt": receipt_id, "verified": True,
                "head": receipt["history"]["head"], "branch_before": receipt["branch"], "detached": detached}

    def care_for_projects(self, apply=True, deadline=None):
        deadline = deadline or time.monotonic() + self.policy["maintenance_max_seconds"]
        candidates = sorted(self.projects(), key=str)
        visits = self._read(self.state / "project-visits.json", {})
        cursors = self._read(self.state / "project-ref-cursors.json", {})
        def oldest(project):
            return visits.get(str(project), "")
        candidates.sort(key=oldest)
        results = []
        if not apply:
            return {"items": [{"project": str(p), "status": "planned"} for p in candidates], "uploaded": False}
        # Local protection works even when GitHub is temporarily unavailable.
        repo = None
        github_error = None
        if shutil.which("gh"):
            try:
                repo = self.private_project_repo()
            except (ValueError, RuntimeError, OSError, TimeoutError, subprocess.TimeoutExpired) as e:
                github_error = str(e)
        for project in candidates[:self.policy["max_projects_per_run"]]:
            if time.monotonic() > deadline - 30:
                break
            visits[str(project)] = self._now()
            try:
                _, _, secrets = self.project_manifest(project)
                secrets.extend(self.ignored_secrets(project))
                local = self.local_secret_backup(project, sorted(set(secrets)))
                if not repo:
                    results.append({"project": str(project), "status": "local_only", "secrets": local["count"],
                                    "reason": github_error or "GitHub não disponível"})
                    continue
                snapshot = self.project_snapshot(project, repo)
                extra = []
                refs = self.git_run(project, ["for-each-ref", "--format=%(refname)", "refs/heads"]).decode().splitlines() if (project / ".git").exists() else []
                offset = cursors.get(str(project), 0) % max(1, len(refs))
                refs = refs[offset:] + refs[:offset]
                processed = 0
                for ref in refs[:self.policy["max_project_refs_per_run"]]:
                    if time.monotonic() > deadline - 30:
                        break
                    if int(self.git_run(project, ["rev-list", "--count", ref, "--not", "--remotes"])):
                        extra.append(self.project_snapshot(project, repo, ref))
                    processed += 1
                cursors[str(project)] = (offset + processed) % max(1, len(refs))
                entry = {"project": str(project), "status": "verified", "snapshot": snapshot,
                         "local_refs_saved": len(extra)}
                if self.policy["auto_archive_worktrees"] and (project / ".git").is_file():
                    try:
                        entry["archive"] = self.archive_worktree(project, snapshot)
                    except (ValueError, RuntimeError, OSError, TimeoutError) as e:
                        entry["archive"] = {"removed": False, "reason": str(e)}
                results.append(entry)
            except (ValueError, RuntimeError, OSError, TimeoutError, subprocess.TimeoutExpired) as e:
                results.append({"project": str(project), "status": "preserved", "reason": str(e)})
        self._write(self.state / "projects.json", {"at": self._now(), "items": results})
        self._write(self.state / "project-visits.json", visits)
        self._write(self.state / "project-ref-cursors.json", cursors)
        return {"items": results, "verified": sum(i["status"] == "verified" for i in results),
                "github_repo": repo, "scanned": len(candidates)}

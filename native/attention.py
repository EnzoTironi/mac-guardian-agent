"""What deserves the owner's attention, and freeing space with one yes. Standard library.

The worker never deletes on its own. `space` measures what can go and prepares
one approval for exactly that inventory; `free_space` deletes it after the
owner's yes. `digest` picks at most one thing worth a text today.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import time

GIB = 1024 ** 3
MIB = 1024 ** 2
# Folders their tools rebuild on demand: (label, path under home, processes that
# must not be running while it is deleted). Deleting one costs a re-download or
# a rebuild, never a document.
REBUILDABLE = (
    ("Xcode build data", "Library/Developer/Xcode/DerivedData", ("Xcode", "xcodebuild")),
    ("Simulator caches", "Library/Developer/CoreSimulator/Caches", ("Simulator", "simctl")),
    ("Homebrew downloads", "Library/Caches/Homebrew", ("brew",)),
    ("npm cache", ".npm/_cacache", ("npm", "npx")),
    ("npx packages", ".npm/_npx", ("npm", "npx")),
    ("pip cache", "Library/Caches/pip", ("pip", "pip3")),
    ("uv cache", ".cache/uv", ("uv", "uvx")),
    ("Yarn cache", "Library/Caches/Yarn", ("yarn",)),
    ("Go build cache", "Library/Caches/go-build", ("go",)),
    ("Gradle caches", ".gradle/caches", ("gradle", "java")),
    ("Cargo download cache", ".cargo/registry/cache", ("cargo",)),
    ("CocoaPods cache", "Library/Caches/CocoaPods", ("pod",)),
)
SEVERITY = {"critical": 3, "warning": 2, "suggestion": 1, "info": 0}
# How long the same item stays quiet after a text.
QUIET_HOURS = {"critical": 24, "warning": 72, "suggestion": 24 * 30, "info": 24 * 7}
BACKUP_STALE_DAYS = 7
SPACE_PLAN_HOURS = 24


class Attention:
    """Uses the Guardian's home, policy, command, approval and JSON helpers."""

    def _processes(self):
        listing = self._command(["ps", "-axo", "comm"], 10)
        if not listing["ok"]:
            return None
        return {Path(line.strip()).name for line in listing["stdout"].splitlines()[1:] if line.strip()}

    def _du(self, path):
        result = self._command(["du", "-sk", str(path)], 60)
        try:
            return int(result["stdout"].split()[0]) * 1024 if result["ok"] else None
        except (IndexError, ValueError):
            return None

    def disk(self):
        usage = shutil.disk_usage(self.home)
        return {"free_bytes": usage.free, "total_bytes": usage.total,
                "used_percent": round(100 * (usage.total - usage.free) / usage.total, 1) if usage.total else None}

    def _identity(self, path):
        s = path.lstat()
        return {"path": str(path), "device": s.st_dev, "inode": s.st_ino}

    def space(self, record=True):
        """Measure what can be freed and prepare one approval for exactly that."""
        running = self._processes()
        rebuildable, deferred = [], []
        minimum = self.policy.get("space_min_item_mib", 50) * MIB
        targets = list(REBUILDABLE) + [("Cache", rel, ()) for rel in self.policy["cache_paths"]
                                        if not any(rel == r[1] for r in REBUILDABLE)]
        for label, rel, users in targets:
            path = self.home / rel
            try:
                if not path.is_dir() or path.is_symlink() or self.excluded(path):
                    continue
                self._safe(path, self.home)
            except (OSError, ValueError):
                continue
            if running is None or set(users) & running:
                deferred.append({"label": label, "reason": "in use right now" if running is not None else "processes unknown"})
                continue
            size = self._du(path)
            if size is None or size < minimum:
                continue
            rebuildable.append({"label": label, "kind": "contents", "bytes": size, **self._identity(path)})
        # Dependencies and build output of idle, committed projects (lockfile required).
        for item in self.cleanup_plan(record=False)["items"]:
            path = self.home / item["path"]
            if item["kind"] in ("node_modules", "target") and item["bytes"] >= minimum:
                rebuildable.append({"label": f"{item['kind']} in {Path(item['path']).parent.name}",
                                    "kind": "directory", "bytes": item["bytes"], **self._identity(path)})
        set_aside = []
        quarantine = self.home / self.policy["local_backup_root"] / "Quarantine"
        if quarantine.is_dir() and not quarantine.is_symlink():
            for receipt_path in sorted(quarantine.glob("*/receipt.json")):
                receipt = self._read(receipt_path, {}) or {}
                data = receipt_path.parent / "data"
                if receipt.get("state") == "quarantined" and data.is_dir() and not data.is_symlink():
                    size = self._du(data) or 0
                    set_aside.append({"label": "set aside earlier: " + Path(receipt.get("source", "")).name,
                                      "kind": "quarantine", "receipt": receipt_path.parent.name,
                                      "bytes": size, **self._identity(data)})
        items = sorted(rebuildable + set_aside, key=lambda i: -i["bytes"])
        trash = self.home / ".Trash"
        trash_bytes = self._du(trash) if trash.is_dir() and not trash.is_symlink() else 0
        result = {"disk": self.disk(), "items": items, "bytes": sum(i["bytes"] for i in items),
                  "deferred": deferred,
                  # Reading the Trash needs Full Disk Access; unknown is not empty.
                  "trash": {"bytes": trash_bytes} if trash_bytes is not None else {"status": "unknown"},
                  "request_id": None, "trash_request_id": None}
        if items:
            result["request_id"] = self.request_approval("free_space", self._space_payload(items))["request_id"]
        if trash_bytes and trash_bytes >= GIB:
            result["trash_request_id"] = self.request_approval("empty_trash", {"trash": self._identity(trash)})["request_id"]
        if record:
            self._write(self.state / "space-plan.json", {"at": self._now(), **result})
        return result

    @staticmethod
    def _space_payload(items):
        return {"items": sorted([i["path"], i["device"], i["inode"], i["kind"]] for i in items)}

    def free_space(self, approval):
        plan = self._read(self.state / "space-plan.json")
        if not isinstance(plan, dict) or not plan.get("items"):
            raise ValueError("Measure first with space; there is nothing approved to free")
        age = time.time() - dt.datetime.fromisoformat(plan["at"]).timestamp()
        if not 0 <= age <= SPACE_PLAN_HOURS * 3600:
            raise ValueError("That proposal is more than a day old; run space again and ask again")
        if not self.consume_approval("free_space", self._space_payload(plan["items"]), approval):
            raise ValueError("Freeing space needs the owner's recent yes for this exact proposal")
        before = self.disk()["free_bytes"]
        running = self._processes()
        users = {label: names for label, _, names in REBUILDABLE}
        results = []
        for item in plan["items"]:
            path = Path(item["path"])
            try:
                self._safe(path, self.home)
                if path.is_symlink() or not path.is_dir():
                    raise ValueError("gone or replaced since the proposal")
                s = path.lstat()
                if (s.st_dev, s.st_ino) != (item["device"], item["inode"]):
                    raise ValueError("replaced since the proposal")
                if running is None or set(users.get(item["label"], ())) & running:
                    raise ValueError("in use right now")
                if item["kind"] == "contents":
                    for child in list(path.iterdir()):
                        if child.is_dir() and not child.is_symlink():
                            shutil.rmtree(child)
                        else:
                            child.unlink()
                else:
                    if item["kind"] == "directory" and self._busy(path):
                        raise ValueError("in use right now")
                    shutil.rmtree(path)
                    if item["kind"] == "quarantine":
                        receipt_path = path.parent / "receipt.json"
                        receipt = self._read(receipt_path, {})
                        receipt.update(state="purged", purged_at=self._now())
                        self._write(receipt_path, receipt)
                results.append({"label": item["label"], "freed": True, "bytes": item["bytes"]})
            except (OSError, ValueError) as e:
                results.append({"label": item["label"], "freed": False, "reason": str(e)})
        after = self.disk()["free_bytes"]
        self._write(self.state / "space-plan.json", {})
        self.record("free_space", {"items": len(results), "freed_bytes": max(0, after - before), "approval": approval})
        return {"items": results, "freed_bytes": max(0, after - before), "free_bytes": after,
                "estimated_bytes": sum(r["bytes"] for r in results if r["freed"])}

    def empty_trash(self, approval):
        trash = self.home / ".Trash"
        if not trash.is_dir() or trash.is_symlink():
            raise ValueError("No Trash folder to empty")
        if not self.consume_approval("empty_trash", {"trash": self._identity(trash)}, approval):
            raise ValueError("Emptying the Trash needs the owner's recent yes")
        before, removed = self.disk()["free_bytes"], 0
        for child in list(trash.iterdir()):
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
            removed += 1
        after = self.disk()["free_bytes"]
        self.record("empty_trash", {"items": removed, "freed_bytes": max(0, after - before)})
        return {"removed": removed, "freed_bytes": max(0, after - before), "free_bytes": after}

    def time_machine(self):
        destinations = self._command(["tmutil", "destinationinfo"], 15)
        if destinations["code"] is None or not destinations["ok"] and not destinations["stdout"]:
            return {"status": "unknown"}
        if not re.search(r"^\s*Name\s*:", destinations["stdout"], re.M):
            return {"status": "not_configured"}
        latest = self._command(["tmutil", "latestbackup"], 15)
        match = re.search(r"(\d{4}-\d{2}-\d{2})-(\d{6})", latest["stdout"]) if latest["ok"] else None
        if not match:
            # Usually Full Disk Access is missing; a configured destination is all that is known.
            return {"status": "configured", "latest": None}
        stamp = dt.datetime.strptime(match[1] + match[2], "%Y-%m-%d%H%M%S")
        age_days = (dt.datetime.now() - stamp).total_seconds() / 86400
        return {"status": "configured", "latest": stamp.isoformat(), "age_days": round(age_days, 1)}

    def attention_items(self):
        items = []
        disk = self.disk()
        free_gib = disk["free_bytes"] / GIB
        used = disk["used_percent"] or 0
        severity = ("critical" if free_gib < self.policy["free_disk_critical_gib"] or used >= 95 else
                    "warning" if free_gib < self.policy["free_disk_warning_gib"] or used >= 90 else None)
        if severity:
            proposal = self.space()
            item = {"id": "disk", "severity": severity, "facts": {"free_gib": round(free_gib, 1), "used_percent": used}}
            if proposal["bytes"] >= GIB:
                item["proposal"] = {"action": "free_space", "request_id": proposal["request_id"],
                                    "bytes": proposal["bytes"],
                                    "biggest": [i["label"] for i in proposal["items"][:3]]}
            items.append(item)
        backup = self.time_machine()
        if backup["status"] == "configured" and backup.get("age_days") is not None and backup["age_days"] > BACKUP_STALE_DAYS:
            items.append({"id": "time-machine", "severity": "warning",
                          "facts": {"last_backup": backup["latest"], "days_ago": int(backup["age_days"])}})
        elif backup["status"] == "not_configured":
            items.append({"id": "time-machine-setup", "severity": "suggestion", "facts": {"configured": False}})
        maintenance = self._read(self.state / "maintenance.json", {}) or {}
        failed = [s["name"] for s in (maintenance.get("last_result") or {}).get("stages", []) if not s.get("ok")]
        if failed:
            items.append({"id": "maintenance:" + ",".join(sorted(failed)), "severity": "warning",
                          "facts": {"failed_stages": failed}})
        waiting = [p for p in self._read(self.state / "approvals.json", []) or []
                   if p.get("action") == "package_update" and not p.get("consumed_at")]
        if waiting:
            items.append({"id": "updates", "severity": "info", "facts": {"updates_waiting": len(waiting),
                          "packages": sorted({p["payload"]["package"] for p in waiting})[:5]}})
        return items

    def digest(self, dry_run=False):
        """At most one thing worth a text now; repeats stay quiet for a while."""
        sent = self._read(self.state / "notifications.json", {}) or {}
        now = time.time()
        chosen, quiet = None, []
        for item in sorted(self.attention_items(), key=lambda i: -SEVERITY[i["severity"]]):
            fingerprint = hashlib.sha256(json.dumps([item["id"], item["severity"]]).encode()).hexdigest()[:16]
            last = sent.get(item["id"], {})
            hours = QUIET_HOURS[item["severity"]]
            try:
                recent = now - dt.datetime.fromisoformat(last["at"]).timestamp() < hours * 3600
            except (KeyError, TypeError, ValueError):
                recent = False
            # A worse severity than the last text is news even inside the quiet window.
            if recent and last.get("fingerprint") == fingerprint or recent and SEVERITY[item["severity"]] <= SEVERITY.get(last.get("severity"), -1):
                quiet.append(item["id"])
                continue
            if chosen is None:
                chosen = item | {"fingerprint": fingerprint}
            else:
                quiet.append(item["id"])
        if chosen and not dry_run:
            sent[chosen["id"]] = {"at": self._now(), "fingerprint": chosen["fingerprint"], "severity": chosen["severity"]}
            self._write(self.state / "notifications.json", sent)
        return {"notify": chosen is not None, "item": chosen, "quiet": quiet, "disk": self.disk()}

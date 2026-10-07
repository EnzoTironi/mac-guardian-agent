#!/usr/bin/env python3
"""Produce synthetic readiness receipts, with simulated launchd and no real Mac."""
import argparse
import importlib.util
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("guardian_readiness_demo", ROOT / "native/mac_guardian.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def demo():
    cases = {}
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory) / "home"
        home.mkdir()
        g = m.Guardian(home)
        m.write_json(g.state / "snapshot.json", {"at": m.now(), "full_checked_at": m.now()})
        with patch.object(m.sys, "platform", "darwin"), \
             patch.object(m, "command", return_value={"ok": True, "stderr": ""}), \
             patch.object(m.shutil, "which", side_effect=lambda name: "/fixture/" + name if name in ("git", "gh") else None):
            cases["first-contact"] = g.setup_status()
            g.configure_cloud(asked=True)
            cases["awaiting-answer"] = g.setup_status()
            g.configure_cloud("none")
            cases["local-only"] = g.setup_status()
            g.pause(2)
            cases["paused"] = g.setup_status()
            g.resume()
            with patch.object(m, "command", return_value={"ok": False, "stderr": "fixture job absent"}):
                cases["missing-jobs"] = g.setup_status()
            m.write_json(g.state / "snapshot.json", {})
            cases["stale-collectors"] = g.setup_status()
        # Public receipts contain a fictional home, never the host's paths.
        cases = json.loads(json.dumps(cases).replace(str(home.resolve()), "/Users/demo"))
    return {"version": m.VERSION, "scope": "synthetic-native-readiness", "launchd_simulated": True,
            "real_mac_operated": False, "message_delivery_tested": False, "cases": cases}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = demo()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "cases": len(result["cases"]), "scope": result["scope"]}))

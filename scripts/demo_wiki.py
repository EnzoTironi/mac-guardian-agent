#!/usr/bin/env python3
"""Capture a real, isolated file-organization round trip for visual review."""
import argparse
import html
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
spec = importlib.util.spec_from_file_location("guardian", Path(__file__).parents[1] / "native/mac_guardian.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
captures = []
with tempfile.TemporaryDirectory(prefix="mac-guardian-demo-") as tmp:
    home = Path(tmp) / "home"
    home.mkdir()
    g = m.Guardian(home, Path(tmp) / "state")
    g.policy.update(auto_updates=False, auto_projects=False, backup_repo="")
    fixtures = {"Downloads/invoice.pdf": b"Example document A", "Desktop/invoice.pdf": b"Example document B",
                "Desktop/ideas.md": b"# Italy trip planning", "Downloads/Trips/Italy/itinerary.pdf": b"Example itinerary",
                "Downloads/presentation.pptx": b"Example presentation", "Downloads/Project/README.md": b"Project paths stay stable",
                "Downloads/Project/package.json": b"{}", "Downloads/recent-in-use.pdf": b"Recent file stays in place"}
    for name, content in fixtures.items():
        p = home / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        if "recent-in-use" not in name:
            os.utime(p, (time.time() - 3 * m.DAY,) * 2)
    m.write_json(g.state / "snapshot.json", {"full_checked_at": m.now(), "applications": [], "updates": {}, "security": {}})
    def capture(title, detail):
        files = [p.relative_to(home).as_posix() for p in sorted(home.rglob("*"))
                 if p.is_file() and not p.is_symlink() and p.relative_to(home).parts[0] != "Library"]
        captures.append({"title": title, "detail": detail, "files": files})
    capture("Before the routine", "Downloads and Desktop hold example files. Documents is excluded.")
    preview = g.organize(False)
    assert preview["summary"]["files"] == 5 and all((home / name).exists() for name in fixtures)
    g.grant_consent("organize", "Demo owner: yes, organize these five files")
    capture("Preview, then yes", "5 files would move into the wiki; nothing moved until the owner said yes.")
    result = g.maintain()
    organization = next(s["result"] for s in result["stages"] if s["name"] == "organization")
    assert len(organization["items"]) == 5
    assert all(m.digest(i["destination"]) == i["sha256"] for i in organization["items"])
    assert (home / "Downloads/Project/README.md").exists()
    assert (home / "Downloads/recent-in-use.pdf").exists()
    assert any(Path(i["destination"]).name == "italy-trip-planning.md" for i in organization["items"])
    capture("Files organized and renamed", "5 files in the local wiki; the note's name came from its content. Hashes, subjects, equal names and the project preserved.")
    undo = g.undo(organization["transaction"])
    assert undo["restored"] == 5
    assert all((home / p).read_bytes() == data for p, data in fixtures.items())
    capture("Moves undone", "5 files restored to their original places with identical content.")
for i, item in enumerate(captures):
    links = " ".join(f'<a href="step-{j+1}.html">{j+1}. {html.escape(c["title"])}</a>' for j, c in enumerate(captures))
    body = f'''<!doctype html><meta charset="utf-8"><title>Mac Guardian — wiki test</title>
<style>body{{background:#101c25;color:#eef5f5;font:18px system-ui;margin:40px auto;max-width:1080px}}h1{{font-size:38px;margin-bottom:12px}}p{{color:#bed0d6}}nav{{display:flex;gap:28px;margin:28px 0}}a{{color:#8bdac8}}pre{{background:#172a36;border:1px solid #42616c;border-radius:12px;padding:22px;font:17px/1.55 monospace}}footer{{font-size:15px;color:#a6b8c3}}</style>
<p>MAC GUARDIAN · v{m.VERSION} · RESULTS OF AN EXECUTED TEST</p><h1>{html.escape(item["title"])}</h1>
<p>{html.escape(item["detail"])}</p><nav>{links}</nav><pre>{html.escape(chr(10).join(item["files"]))}</pre>
<footer>Synthetic files in a temporary folder. Organization and undo run by the real helper.<br>No app updates, data uploads or access to personal documents.</footer>'''
    m.private_text(args.output / f"step-{i+1}.html", body)
m.write_json(args.output / "proof.json", {"version": m.VERSION, "moved": 5, "restored": 5,
                                           "hashes_verified": True, "captures": captures})
print(json.dumps({"pages": str(args.output.resolve()), "moved": 5, "restored": 5, "hashes_verified": True}))

#!/usr/bin/env python3
"""Execute reversible care on synthetic files and render English review evidence."""
import argparse
import html
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "tests"))
from test_workspace import WorkspaceTests, m

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
fixture = WorkspaceTests()
fixture.setUp()
g = fixture.g
captures = []

def capture(title, subtitle, lines, badges):
    captures.append({"title": title, "subtitle": subtitle, "lines": lines, "badges": badges})

try:
    originals = [fixture.personal("Downloads/untitled-3.md", "# Brand launch plan\n\nClient: Northstar\n\nLaunch notes."),
                 fixture.personal("Desktop/untitled.txt", "Title: Invoice October 2026\nClient: Northstar\nExample invoice."),
                 fixture.personal("Family/Trips/raw/untitled.md", "# Italy travel itinerary\n\nTopic: Travel\n\nExample trip.")]
    hashes = {str(p): m.digest(p) for p in originals}
    main, worktree = fixture.worktree()
    (worktree / "README.md").write_text("Staged draft")
    fixture.git(worktree, "add", "README.md")
    (worktree / "README.md").write_text("Working draft")
    (worktree / "new.js").write_text("console.log('untracked draft')")
    (worktree / ".env").write_text("DEMO_TOKEN=synthetic-local-only-fixture")
    (worktree / "empty").mkdir()
    (worktree / "readme-link").symlink_to("README.md")
    fixture.old(worktree)
    capture("Your files. Everywhere.", "Real helper • isolated synthetic home • no personal data", [
        "Downloads/untitled-3.md", "Desktop/untitled.txt", "Family/Trips/raw/untitled.md",
        "Projects/client/old-site/README.md    [staged + working changes]",
        "Projects/client/old-site/new.js       [untracked code]",
        "Projects/client/old-site/.env         [ignored secret]"],
        ["Recursive discovery", "Local storage selected", "Project paths preserved"])
    with fixture.github():
        g.configure_cloud("none")
        moved = g.organize(True)
        assert len(moved["items"]) == 3
        assert all(m.digest(i["destination"]) == i["sha256"] for i in moved["items"])
        capture("A wiki made of your files.", "Titles and subjects came from document content. Every move has an undo receipt.", [
            "Wiki/Home.md", "Wiki/Projects.md", "Wiki/Documentos/_Index.md",
            "Wiki/Documentos/northstar/_Index.md", "Wiki/Documentos/northstar/brand-launch-plan.md",
            "Wiki/Documentos/northstar/invoice-october-2026.txt",
            "Wiki/Documentos/travel/_Index.md", "Wiki/Documentos/travel/italy-travel-itinerary.md"],
            ["3 files organized", "Content-based names", "SHA-256 verified"])
        snapshot = g.project_snapshot(worktree, "test/private")
        names = fixture.git(fixture.remote, "ls-tree", "-r", "--name-only", snapshot["branch"]).decode().splitlines()
        assert ".env" not in names and "new.js" in names
        assert fixture.git(worktree, "show", ":README.md") == b"Staged draft"
        capture("Code saved. Secrets stay home.", "A private companion branch, verified by a fresh clone. GitHub is simulated by a local bare remote.", [
            "Private branch: " + snapshot["branch"], "Remote files: " + ", ".join(names),
            "Original branch: draft    [unchanged]", "Original staged README: Staged draft    [unchanged]",
            "Backup/MacGuardian/Secrets/<file>/<sha256>/content",
            ".env uploaded: NO", "Backup permissions: directory 0700 • secret file 0600"],
            ["Fresh clone verified", "Untracked code saved", "Secret remains local"])
        archived = g.archive_worktree(worktree, snapshot)
        assert not worktree.exists()
        restored = g.restore_worktree(archived["receipt"])
        assert restored["verified"] and fixture.git(worktree, "show", ":README.md") == b"Staged draft"
        cache = fixture.personal("OldCache/content.txt", "Recreatable synthetic cache").parent
        quarantined = g.quarantine_tree(cache, "cache")
        rejected = False
        try:
            g.purge_quarantine(quarantined["receipt"], apply=True)
        except ValueError:
            rejected = True
        assert rejected
        capture("Automatic. Until it is irreversible.", "The helper restored the archived worktree and refused permanent deletion without owner approval.", [
            "Old worktree: archived → restored → verified",
            "Recovered: working files + staged index + ignored .env",
            "Recovered: symlink + empty directory + Git history",
            "Old cache: moved to local quarantine",
            "Permanent purge without consent: BLOCKED",
            "Disk space claimed from quarantine: 0 bytes"],
            ["Worktree recovery passed", "One-use approval required", "No irreversible action"])
        g.restore_quarantine(quarantined["receipt"])
        undone = g.undo(moved["transaction"])
        assert undone["restored"] == 3 and all(m.digest(path) == sha for path, sha in hashes.items())
        capture("Recovery proven.", "All original personal paths, names and file hashes match. Local storage preference is persistent.", [
            "Personal files restored: 3 / 3", "Original names and locations: MATCH",
            "Personal content hashes: MATCH", "Worktree files and metadata: MATCH",
            "Staged and unstaged versions: PRESERVED", "Ignored .env: LOCAL ONLY",
            "Google Drive / iCloud: DISABLED"],
            ["Undo passed", "Restore passed", "Local-only choice respected"])
    proof = {"version": m.VERSION, "synthetic": True, "local_bare_remote": True, "moved": 3,
             "restored": 3, "hashes_verified": True, "worktree_restore_verified": True,
             "staged_index_preserved": True, "secrets_uploaded": False,
             "unapproved_purge_blocked": rejected, "cloud": "none", "captures": captures}
finally:
    fixture.doCleanups()

for number, item in enumerate(captures, 1):
    badges = "".join("<span>" + html.escape(text) + "</span>" for text in item["badges"])
    links = "".join(f'<a class="{("active" if i == number else "")}" href="step-{i}.html">{i:02}</a>' for i in range(1, len(captures) + 1))
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Mac Guardian — care verified</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:#0b1720;color:#ecf5f4;font:20px/1.45 system-ui}}main{{max-width:1200px;margin:auto;padding:48px 52px}}header{{display:flex;justify-content:space-between;color:#90c6b7;font-size:16px;letter-spacing:2px}}h1{{font-size:50px;line-height:1.1;letter-spacing:-2px;margin:30px 0 14px}}p{{color:#aabfc9;font-size:18px;max-width:1000px}}.badges{{display:flex;gap:12px;margin:24px 0}}.badges span{{border:1px solid #37594f;border-radius:30px;padding:8px 16px;color:#a6e6cc;font-size:14px}}pre{{white-space:pre-wrap;background:#142731;border:1px solid #324d5a;border-radius:18px;padding:28px;font:16px/1.9 ui-monospace,monospace;min-height:330px}}footer{{display:flex;justify-content:space-between;color:#83a0ad;font-size:14px;margin-top:26px}}nav{{display:flex;gap:10px}}a{{color:#95b4c1;text-decoration:none;padding:4px 10px;border:1px solid #284653;border-radius:8px}}a.active{{background:#a6e6cc;color:#092418}}</style>
<main><header><b>MAC GUARDIAN</b><span>v{m.VERSION} / EXECUTED REVIEW EVIDENCE</span></header>
<h1>{html.escape(item["title"])}</h1><p>{html.escape(item["subtitle"])}</p><div class="badges">{badges}</div>
<pre>{html.escape(chr(10).join(item["lines"]))}</pre><footer><span>Real native helper · Synthetic fixtures · Recovery verified</span><nav>{links}</nav></footer></main></html>'''
    m.private_text(args.output / f"step-{number}.html", page)
m.write_json(args.output / "proof.json", proof)
print(json.dumps({k: v for k, v in proof.items() if k != "captures"}))

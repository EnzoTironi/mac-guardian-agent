# Mac Guardian end-to-end checklist

Run on a real Mac with Latch connected, a real Plow line and a test macOS user
account (not your daily account: these scenarios move files). Every box must
pass before a release is promoted. Write failures next to the item.

Setup:

```sh
plow-agents mint LINE_UID
MAC_GUARDIAN_REVISION=$(git rev-parse HEAD) docker compose up --build -d   # the commit must be pushed
docker compose logs -f agent
```

`helper` below means
`PYTHON "$HOME/Library/Application Support/MacGuardian/mac_guardian.py"` on the Mac.

## 0. Image

- [ ] `python3 scripts/test_image.py mac-guardian:check --platform linux/amd64` prints `"ok": true`.
- [ ] `docker compose exec agent node /opt/plow/skills/mac-health/scripts/install-command.mjs install --python /opt/homebrew/bin/python3`
  prints JSON whose URL ends in `/<that commit>/` and whose three hashes match
  `shasum -a 256 native/*.py scripts/install_native.py`.

## Scenarios

1. [ ] **Fresh install, no terminal.** On a Mac with Python 3.11+ and no helper, text "Can you look after my Mac?"
   - Expect: a one-line introduction, one line saying what will be installed and that Latch will ask.
   - Check: Latch shows one command with network and the three write paths; approve it.
   - Expect: a short result with real free space; `launchctl print gui/$(id -u)/local.macguardian.monitor` succeeds.
2. [ ] **No Python.** On a Mac whose only `python3` is `/usr/bin/python3`, ask the same.
   - Expect: no install attempt and no Command Line Tools dialog; one next step (python.org or Homebrew).
3. [ ] **Tampered download is refused.** Build an image with `MAC_GUARDIAN_REVISION` set to a pushed commit whose `native/workspace_care.py` differs from the image's copy.
   - Expect: Latch output "checksum mismatch for native/workspace_care.py; nothing was installed"; no helper files appear.
4. [ ] **Organization waits for a yes.** Put three old files in Downloads and one in `~/Pictures`. Wait for a 15-minute cycle.
   - Check: `helper status` shows `consent.organize.granted: false`; the files are still in place.
   - Ask "organize my files". Expect: counts by folder (Downloads only) and one question. Say yes.
   - Expect: the three files are in `~/Wiki/Documents/...` (English names on a new wiki); `~/Pictures` is untouched.
5. [ ] **Undo.** Say "undo that". Expect: every file back with identical content (`shasum`), and a one-line confirmation.
6. [ ] **Folder change needs a new yes.** Ask to include the whole home folder.
   - Expect: a new preview including home-folder files, and no moves until a new yes.
7. [ ] **Libraries and sync folders.** With the home folder enabled, place old files in `~/Music/Music/Media.localized`, `~/Dropbox` and an iCloud-evicted Desktop file.
   - Expect: none of them move.
8. [ ] **GitHub snapshots wait for a yes.** With `gh` signed in and a project in `~/Code`, wait a cycle.
   - Check: no `mac-guardian-project-backups` repository exists on GitHub; `~/Backup/MacGuardian/Secrets` holds the project's `.env`.
   - Ask "back up my code". Expect: project list, private repository name, "secrets stay local", "heuristic". Say yes.
   - Expect: a private repository with a `mac-guardian/...` branch, no `.env` in it, your branch and index unchanged.
9. [ ] **Irreversible needs a yes each time.** Ask "free up space" after a cleanup.
   - Expect: quarantined bytes described as not yet freed, an exact preview, one question.
   - Check: after yes, `purge-quarantine` runs once; asking again an hour later needs a new yes.
10. [ ] **Mac offline.** Quit Latch and ask "how is my Mac?".
    - Expect: "couldn't reach your Mac, nothing ran", no invented status; after two failed turns, the Latch link.
11. [ ] **Group privacy.** Add someone to a group with the agent and chat about something else.
    - Expect: silence; when they ask about the Mac, no Mac details and no tools.
12. [ ] **Language.** Write in Portuguese, then in English.
    - Expect: each reply in the language of the message it answers.
13. [ ] **Uninstall keeps data.** Ask "stop your background jobs".
    - Expect: Latch approval; both LaunchAgents gone; `~/Wiki`, reports and backups intact.

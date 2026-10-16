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
4. [ ] **First useful result.** Right after scenario 1, in the same conversation.
   - Expect: free space, a space proposal if anything rebuildable is over 1 GB, the Time Machine state, at most one question.
   - Check: the agent created exactly one "Mac Guardian daily check" automation in the DM.
5. [ ] **One yes frees space.** Fill `~/Library/Developer/Xcode/DerivedData` (build any project) and the npm cache, close Xcode, ask "free some space".
   - Expect: total, the biggest items, "they rebuild themselves", one question. Say yes.
   - Check: `du -sh` of those folders is near zero and the folders still exist; the reply's freed GB matches `df -h` within a few percent; Documents untouched.
   - Ask again with Xcode open. Expect: Xcode data deferred ("in use"), the rest offered.
6. [ ] **Daily check.** Trigger the automation manually (or wait a day) on a Mac with plenty of space and a fresh backup.
   - Expect: no message. Then unplug the backup drive for over a week (or fake the date) and trigger again.
   - Expect: one text about Time Machine; triggering again the same day sends nothing.
7. [ ] **Organization only on request.** Put three old files in Downloads; wait for a cycle.
   - Check: nothing moved and the agent did not mention organizing. Ask "organize my files".
   - Expect: counts by folder and one question; on yes the files are in `~/Wiki/Documents/...`; "undo that" puts them back byte for byte.
   - Ask to include the whole home folder. Expect: a new preview including home-folder files, and no moves until a new yes.
   - With the home folder enabled, place old files in `~/Music/Music/Media.localized`, `~/Dropbox` and an iCloud-evicted Desktop file. Expect: none of them move.
8. [ ] **GitHub snapshots wait for a yes.** With `gh` signed in and a project in `~/Code`, wait a cycle.
   - Check: no `mac-guardian-project-backups` repository exists on GitHub; `~/Backup/MacGuardian/Secrets` holds the project's `.env`.
   - Ask "back up my code". Expect: project list, private repository name, "secrets stay local", "heuristic". Say yes.
   - Expect: a private repository with a `mac-guardian/...` branch, no `.env` in it, your branch and index unchanged.
9. [ ] **Upgrade from 0.3.x.** On a Mac that ran 0.3.x (quarantine present, wiki with Portuguese folders), install this version.
   - Expect: no new quarantine after a cycle; the next space proposal lists "set aside earlier" items; the wiki keeps its Portuguese folder names; earlier organization continues without a new question.
10. [ ] **Mac offline.** Quit Latch and ask "how is my Mac?".
    - Expect: "couldn't reach your Mac, nothing ran", no invented status; after two failed turns, the Latch link.
11. [ ] **Group privacy.** Add someone to a group with the agent and chat about something else.
    - Expect: silence; when they ask about the Mac, no Mac details and no tools.
12. [ ] **Language.** Write in Portuguese, then in English.
    - Expect: each reply in the language of the message it answers.
13. [ ] **Uninstall keeps data.** Ask "stop your background jobs".
    - Expect: Latch approval; both LaunchAgents gone; `~/Wiki`, reports and backups intact.

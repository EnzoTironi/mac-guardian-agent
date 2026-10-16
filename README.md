# Mac Guardian

![Your Mac has a doctor now](media/campaign-v1/images/01-your-mac-has-a-doctor.png)

Mac Guardian texts you before your disk fills, frees space with one yes, tells
you when your backups stop, and keeps your project code backed up. It runs a
small helper on your Mac through Plow Latch and talks to you over text. It never
deletes anything without your OK, and it is quiet when there is nothing to say.

[English campaign and 40-second film](media/campaign-v1/README.md) ·
[Agent Index page](https://aiworthusing.com/agent-index/mac-guardian)

A first conversation, with fictional numbers:

> **You:** Can you look after my Mac?
>
> **Mac Guardian:** I'm Mac Guardian. I'll install a small helper on your Mac:
> two background jobs, nothing uploaded. Latch will ask you to approve it.
>
> *(you tap Allow in Latch)*
>
> **Mac Guardian:** You have 38 GB free of 500 GB. I can free 14 GB of Xcode
> build data and npm cache; they rebuild themselves. Time Machine last backed
> up yesterday. Free the 14 GB?
>
> **You:** yes
>
> **Mac Guardian:** Freed 14.2 GB. You have 52 GB free now.

Then, once a day, it checks. Most days it says nothing. When something needs
you, it sends one text with one question:

> **Mac Guardian:** Your disk is 92% full (40 GB left). I can free 11 GB of
> Homebrew downloads and build folders from projects you haven't touched in a
> month. Free it?

> **Mac Guardian:** Time Machine hasn't backed up in 12 days. Plug in the backup
> drive and it will catch up.

## What it does, what it asks first, what it never does

**On its own, once installed** (every action has a receipt):

- Health every 15 minutes (disk, memory, swap, load, processes, battery, with
  30 days of history) and a full audit daily at 09:10: apps, signatures,
  update sources, Time Machine, background services and listeners.
- One daily check that texts you only for low disk (with a ready proposal), a
  stale or missing Time Machine backup, a failed routine or waiting updates.
  The same thing is not repeated for days unless it gets worse.
- Secret files from your projects (`.env`, credentials, private keys, detected
  secret-bearing files) are copied into `~/Backup/MacGuardian/Secrets`:
  owner-only, versioned by hash, never uploaded.

**Your yes every time**, for an exact list:

- **Freeing space.** Only folders their tools rebuild: Xcode build data and
  Simulator caches, Homebrew, npm, pip, uv, Yarn, Go, Gradle, Cargo and
  CocoaPods caches, and `node_modules`/`target` of committed projects idle for
  30 days. Anything in use is skipped. One yes frees the whole list. Your
  documents are never on it.
- **Emptying the Trash**, as its own question. Also deleting backups, app and
  package updates (no guaranteed downgrade), installers, and security or
  service changes. An approval matches that exact list, expires after an hour
  and is used once.

**One yes, then automatically:**

- **Private GitHub snapshots of project code.** Working changes, untracked code
  and unpublished branch tips go to private branches in
  `YOUR-LOGIN/mac-guardian-project-backups`, verified from a fresh clone. Your
  branch, index and files are never changed. Without this yes, no repository is
  created and no code leaves the Mac.
- **Organizing files, only if you ask.** It shows how many files would move
  from Downloads and Desktop into `~/Wiki/CATEGORY/SUBJECT`, named from their
  content, and every move can be undone. It never offers this on its own.

**Never:** deleting or moving anything on a schedule; touching Documents,
iCloud Drive, CloudStorage, sync folders such as Dropbox and OneDrive, app media
libraries, projects, vaults or system and app internals; uploading secrets
anywhere; forcing sudo, killing apps, accepting licenses or rebooting.

## Install

Mac Guardian needs [Plow Latch](https://plow.co/download/latch) on the Mac and
Python 3.11 or newer there (Homebrew's `python3` or the
[python.org installer](https://www.python.org/downloads/macos/)).

1. Open the [Agent Index page](https://aiworthusing.com/agent-index/mac-guardian)
   and tap **Text this agent**. This appears once Plow enables one-click deploy
   for this image; until then, run it yourself as below.
2. Text it. On your first Mac request it checks your Mac through Latch and
   installs its helper. You approve that once in Latch; you never open a terminal.
3. In that same conversation you get your free space, what can be freed and
   whether Time Machine is running, with at most one question. It then sets up
   its daily check in your chat.

To stop it: ask it to stop its background jobs (the uninstall keeps your wiki,
reports and backups), or remove the agent's line in Plow.

### Manual install from a terminal

```sh
git clone --branch v0.4.0 --depth 1 https://github.com/EnzoTironi/mac-guardian-agent.git
cd mac-guardian-agent
python3 -m unittest discover -s tests
python3 scripts/install_native.py           # --uninstall removes the jobs, keeps data
```

Configuration lives in `~/Library/Application Support/MacGuardian/state/policy.json`.
Reinstalling keeps every choice, consent, wiki and backup.

## Run locally

Needs Docker with Compose 2.24+ and [plow-agents](https://github.com/plow-pbc/plow-agents).

```sh
plow-agents login
plow-agents lines                      # pick a free line
plow-agents mint LINE_UID              # writes ./plow-credentials (never committed)
MAC_GUARDIAN_REVISION=$(git rev-parse HEAD) docker compose up --build -d
docker compose logs -f agent           # wait for the identity line, then text the number
```

`MAC_GUARDIAN_REVISION` must be a commit that is pushed to GitHub: the Mac
installs the helper from that commit and checks it against the image. The local
dashboard proxy listens on `127.0.0.1:3012` (`HOST_PORT` changes it) and grants
admin access to anyone who can reach it. `docker compose down` keeps state;
`down -v` starts fresh. Do not mount your home folder, the Docker socket or
GitHub credentials into the agent.

## Deploy

```sh
python3 scripts/configure_listing.py --slug YOUR_SLUG --name 'Your Agent' --blurb 'One line'
python3 scripts/build_publish.py ghcr.io/YOU/mac-guardian-agent:v0.4.0 --push
plow-agents profile --show
```

`build_publish.py` refuses a dirty tree or an unpushed commit, builds with that
commit pinned, runs the isolated image tests, and pushes with `plow-agents`.
CI does the same on `main` and version tags for Intel and Apple Silicon and
prints the immutable digest and the `plow-agents image promote` command. Keep
the package public and check anonymous pull. A Plow admin enables one-click
deploy from your UID, slug and digest; later releases use
`plow-agents image push IMAGE --promote SLUG`. The image keeps the base boot and
its five-minute usage reporter, which free hosting requires.

## How it works

Two parts: a conversation container on Plow's OpenClaw base (identity,
transport, usage reporting inherited) and a native Python helper on the Mac,
run every 15 minutes by launchd, that keeps measuring while the container is
stopped. A daily Plow automation asks the helper for its digest and turns the
one item worth saying, if any, into a text. Latch carries each command, with declared paths and network, and the
owner approves on the Mac. Deterministic work (checks, receipts, consent,
approvals, hashes, recovery) lives in the helper; the model reads ambiguous
content and talks.

- [Architecture](docs/architecture.md): install path, consent, wiki, quarantine,
  snapshots, worktree archives, security observations.
- [Verification and limits](docs/verification.md): what each test proves and does not.
- [Review rules](REVIEW.md) and [Meetly patterns](docs/meetly-patterns.md).
- [Manual end-to-end checks](checks/manual-scenarios.md) on a real Mac.

Things to say: "How is my Mac?", "Free some space", "Empty the Trash", "Is my
backup working?", "Back up my code", "Organize my files", "Undo that", "Pause for
two hours", "Resume", "Stop your background jobs".

## Known limitations

- Needs Python 3.11+ on the Mac; without it nothing installs until you add one.
- Latch must be connected for any Mac work; the agent reports an unreachable
  Mac instead of guessing. Whether Latch's sandbox allows `launchctl` for the
  install has not been verified on a real Mac in this release.
- Secret detection is heuristic (names and common key formats), not a guarantee.
  Private GitHub is not encryption.
- The daily check runs as a Plow automation in your chat; if the Mac or Latch is
  asleep at that time, that day's check is skipped. Low disk is caught at the
  next check, not the moment it happens.
- The Time Machine check reads `tmutil`; without Full Disk Access the date of the
  last backup can be unknown, and then it says nothing rather than guess. The
  Trash size has the same limit.
- Local secret backups do not protect against losing the Mac; Time Machine does.
- If you ask for file organization on an iCloud-synced Desktop, moved files stop
  syncing; placeholders are skipped, downloaded files are moved like any other.
- No cloud-file transfer: Mac Guardian does not move files to Drive or iCloud.
- Update coverage is incomplete for unknown sources; signatures and Gatekeeper
  do not prove the absence of malware; app updates have no guaranteed downgrade.

## Development

```sh
python3 -m unittest discover -s tests -v       # safety, consent, install, prompt contract
node --test tests/runtime/*.test.mjs           # image tests skip outside the image
docker build --platform linux/amd64 --build-arg MAC_GUARDIAN_REVISION=$(git rev-parse HEAD) -t mac-guardian:check .
python3 scripts/test_image.py mac-guardian:check --platform linux/amd64
python3 scripts/demo_workspace.py --output private/workspace-demo
```

Tests use isolated homes and local Git remotes; none touch your real home,
GitHub or launchd. Bumping the base image:

1. Pick a newer `base-<full sha>` tag from the
   [registry](https://gallery.ecr.aws/e1h7x4a2/plow-cloud-agents) and read its index digest.
2. Update the `FROM` line (tag and digest) and its comment.
3. Copy that commit's `prompt/AGENTS.md` from
   [plow-openclaw-agent](https://github.com/plow-pbc/plow-openclaw-agent) to
   `tests/fixtures/base-AGENTS.md`, and update `BASE_COMMIT` and `BASE_SHA256` in
   `tests/test_prompt_contract.py`.
4. Run the tests; carry any base sentence they report into `prompt/AGENTS.md`.
5. Build and run the image tests above, then the manual scenarios.

`private/`, `.env`, `plow-credentials` and listing settings stay out of Git and
the Docker build context. Public evidence uses synthetic files only.

## License

MIT, see [LICENSE](LICENSE). Plow, OpenClaw, Caddy, Mole and Vorssaint keep their
own licenses.

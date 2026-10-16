# Mac Guardian

![Your Mac has a doctor now](media/campaign-v1/images/01-your-mac-has-a-doctor.png)

Mac Guardian looks after your Mac and talks with you about it by text. It
watches storage, memory, apps and updates, clears old caches into a restorable
quarantine, organizes your loose files into a wiki on your own Mac (with undo),
keeps local copies of your secrets, and, if you say yes, saves your project code
to a private GitHub repository. Anything that cannot be undone waits for your OK.

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
> **Mac Guardian:** Done. You have 24 GB free and nothing needs you right now. I
> can move 37 files from Downloads and Desktop into a Wiki folder, sorted by
> type and subject and named from their contents. Every move can be undone.
> Go ahead?
>
> **You:** yes
>
> **Mac Guardian:** Done: 37 files are in ~/Wiki. Say undo and they go back.

After that it stays quiet, and writes again only for critical storage, a
confirmed risk or a decision that is yours.

## What it does, what it asks first, what it never does

**On its own, once installed** (every action has a receipt or an undo):

- Health every 15 minutes (disk, memory, swap, load, processes, battery, with
  30 days of history) and a full audit daily at 09:10: apps, signatures,
  update sources, background services and listeners.
- Old caches and build output move into `~/Backup/MacGuardian/Quarantine` on the
  same disk. That is restorable and frees **zero bytes** until you approve deletion.
- Secret files from your projects (`.env`, credentials, private keys, detected
  secret-bearing files) are copied into `~/Backup/MacGuardian/Secrets`:
  owner-only, versioned by hash, never uploaded.
- Changed background services are investigated and logged; observed is not trusted.

**After one yes from you**, then automatically:

- **Organizing files.** It shows how many files would move from which folders,
  then moves stable files into `~/Wiki/CATEGORY/SUBJECT` with an index page in
  every folder, and names them from their content (titles, clients, dates
  written in the document). New installs organize **Downloads and Desktop**. The
  whole home folder, or another folder, is your choice, and changing the
  folders needs a new preview and yes.
- **Private GitHub snapshots of project code.** Working changes, untracked code
  and unpublished branch tips go to private branches in
  `YOUR-LOGIN/mac-guardian-project-backups`, verified from a fresh clone. Your
  branch, index and files are never changed. Without this yes, no repository is
  created and no code leaves the Mac.

**Your yes every time**, for the exact preview: deleting quarantine, emptying
Trash, deleting backups, app and package updates (no guaranteed downgrade),
installers, and security or service changes. An approval matches that exact
content, expires after an hour and is used once.

**Never:** moving files from Documents, iCloud Drive, CloudStorage or sync
folders such as Dropbox and OneDrive; touching app media libraries (Music, TV,
Photo Booth, iMovie and similar), projects, vaults, VM bundles or system and
app internals; downloading cloud placeholders just to move them; uploading
secrets anywhere; forcing sudo, killing apps, accepting licenses or rebooting.

## Install

Mac Guardian needs [Plow Latch](https://plow.co/download/latch) on the Mac and
Python 3.11 or newer there (Homebrew's `python3` or the
[python.org installer](https://www.python.org/downloads/macos/)).

1. Open the [Agent Index page](https://aiworthusing.com/agent-index/mac-guardian)
   and tap **Text this agent**. This appears once Plow enables one-click deploy
   for this image; until then, run it yourself as below.
2. Text it. On your first Mac request it checks your Mac through Latch and
   installs its helper. You approve that once in Latch; you never open a terminal.
3. It asks one question about Google Drive or iCloud for ordinary files, and
   shows the organization preview. Local care starts right away either way.

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
run every 15 minutes by launchd, that keeps working while the container is
stopped. Latch carries each command, with declared paths and network, and the
owner approves on the Mac. Deterministic work (checks, receipts, consent,
approvals, hashes, recovery) lives in the helper; the model reads ambiguous
content and talks.

- [Architecture](docs/architecture.md): install path, consent, wiki, quarantine,
  snapshots, worktree archives, security observations.
- [Verification and limits](docs/verification.md): what each test proves and does not.
- [Review rules](REVIEW.md) and [Meetly patterns](docs/meetly-patterns.md).
- [Manual end-to-end checks](checks/manual-scenarios.md) on a real Mac.

Things to say: "How is my Mac?", "What used space today?", "Organize my files",
"Undo the last organization", "Pause for two hours", "Resume", "Back up my
code", "Restore that worktree", "Stop your background jobs".

## Known limitations

- Needs Python 3.11+ on the Mac; without it nothing installs until you add one.
- Latch must be connected for any Mac work; the agent reports an unreachable
  Mac instead of guessing. Whether Latch's sandbox allows `launchctl` for the
  install has not been verified on a real Mac in this release.
- Secret detection is heuristic (names and common key formats), not a guarantee.
  Private GitHub is not encryption.
- Quarantine frees no space until a deletion is approved. Local backups do not
  protect against losing the Mac.
- Moving files out of an iCloud-synced Desktop stops them syncing; placeholders
  are skipped, but downloaded files on that Desktop are moved like any other.
- No cloud-file transfer yet: a Drive or iCloud answer is recorded for later.
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

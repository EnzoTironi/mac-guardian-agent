# Mac Guardian

![Your Mac has a doctor now](media/campaign-v1/images/01-your-mac-has-a-doctor.png)

[English campaign and 40-second HyperFrames film](media/campaign-v1/README.md)

Mac Guardian maintains your Mac quietly and answers by conversation. It organizes
personal files into a physical wiki, names them from their content, preserves
project work on private GitHub branches and keeps secrets in a local Backup
folder. Reversible work runs automatically. Procedures without guaranteed
restoration require your approval.

Its voice is warm, direct and practical. It answers useful requests first, takes
the next authorized step, explains results briefly and stays quiet when there is
nothing actionable. The personality follows the Plow base's
[new default persona](https://github.com/plow-pbc/plow-openclaw-agent/blob/8644de7470f670086ef991787ae979ec8bb5e047/prompt/AGENTS.md),
adapted to Mac care with concrete conversation examples. Style changes preserve
storage choices, permissions and notification rules. This release updates the
conversation prompt; the native maintenance worker remains v0.3.0. The upstream
personality controls are still under review and are not included in this image.
[Conversation fixtures and exact model responses](evidence/personality-v0.3.1.json)
show the evaluated voice using fictional receipts, without external delivery.

Built on the official Plow OpenClaw image. The native macOS worker continues
while the conversation container is stopped. Public name: **Mac Guardian**;
Agent Index slug: `mac-guardian`. This project's code is MIT. Upstream OpenClaw,
Plow, Caddy, Mole and Vorssaint retain their own licenses.

## Automatic care

- Every 15 minutes: disk, memory, swap, load, CPU/RAM processes and battery, with
  up to 30 days of local history. A daily full audit runs at 09:10 local time.
- Recursive organization of eligible personal files across the home directory,
  including Downloads, Desktop and nested folders. Files live in
  `~/Wiki/CATEGORY/SUBJECT`, with linked Markdown indexes at every folder level.
- Descriptive names from local text, Office titles, PDF text, OCR and media tags.
  Explicit client/project subjects determine the destination. The conversational
  agent reviews ambiguous cases and applies a matching hash and recorded reason.
- Journaled moves and names, collision preservation and recovery after interruption.
- Private project snapshots: working changes, untracked code and unpublished
  local branch tips, without switching the user's branch or changing their index.
  Projects without Git can also be saved without initializing their source folder.
- Local versioned secret backups in `~/Backup/MacGuardian/Secrets`, hash-verified,
  deduplicated and owner-only. `.env`, `.envrc`, `.npmrc`, credentials, private keys
  and detected secret-bearing files never enter project snapshots.
- Old eligible caches/build artifacts move to a restorable quarantine. Ordinary
  old worktrees are archived only after a verified private snapshot and a complete
  local recovery copy of files, ignored data, Git history and staged changes.
- Update-source checks, app/signature inventory, background jobs/listeners and
  persistent investigation queues. Notifications occur only for actionable issues.

For example, `Family/Client/raw/untitled.md` containing a heading
`# Brand launch plan` and `Client: Northstar` becomes
`~/Wiki/Documentos/northstar/brand-launch-plan.md`. The wiki contains the actual
file, its subject index, category navigation and `Home.md`. `Projects.md` links to
source projects in their original locations. Health reports are separate.

The worker waits for two hours without changes and checks open files. Source
projects, existing vaults, configurations, system/app libraries and VM bundles
retain their paths. `Documents`, `Library/Mobile Documents` and
`Library/CloudStorage`, including aliases to those roots, are excluded.
Files with insufficient context wait for further review rather than receiving
invented names. Local secret detection is heuristic, not an exhaustive guarantee.

## Recovery and permission

Reversible operations run within the enabled policy without a fresh approval.
Quarantine is a same-volume move: it preserves metadata and frees **zero bytes**.
Permanent deletion, emptying Trash, deleting backups and procedures without
complete rollback require explicit consent for the specific preview.
Approval IDs bind to exact content/version, expire after one hour and are used once.

Homebrew/App Store updates are checked automatically. This version requires
approval before upgrades because a complete downgrade is not guaranteed. After
approval, it verifies official sources, idle apps/dependencies and the updater
result. Pinned packages, unknown taps, installer hooks, sudo, licenses and restarts
are preserved or deferred. Unknown update sources stay pending; signatures and
Gatekeeper checks do not prove malware absence.

Ordinary secondary worktrees need both verified remote code and a complete local
recovery archive: dirty/untracked/ignored files, secrets, symlinks, empty folders,
modes, timestamps, xattrs, history/refs, Git config and the original index. Failed,
busy, recent, locked, oversized, special-file, hardlink, submodule and split-index
cases remain in place. **Codex worktrees use the native managed archive in their
owning chat.** No manual forced removal can bypass preservation checks.

The local Backup folder is `0700`; secret content and receipts are `0600`. Local
recovery does not protect against loss of the device. Backups are retained until
explicit deletion is approved. Private GitHub is not encryption.

## Install on the Mac

Requires macOS, Python 3.11+ and Git. Authenticated `gh` enables private project
preservation. Optional `pdftotext`, Tesseract and `ffprobe` improve local extraction.

```sh
git clone --branch v0.3.1 --depth 1 https://github.com/EnzoTironi/mac-guardian-agent.git
cd mac-guardian-agent
python3 -m unittest discover -s tests -v
python3 scripts/install_native.py
```

The installer copies both native modules and installs two LaunchAgents. It
preserves existing policy choices, wiki, reports and backups on reinstall.
Configuration is in `~/Library/Application Support/MacGuardian/state/policy.json`.
New installations cover the home tree; old custom root choices remain unchanged.
To remove the jobs while preserving data:

```sh
python3 scripts/install_native.py --uninstall
```

## Storage preference and projects

On first contact the agent asks once about Google Drive or iCloud for ordinary
files. It records the answer and continues local care while awaiting it. Choosing
local-only keeps personal files and reports local. Recording a cloud destination
is preparation; cloud transfer is not implemented in this version. Secret backups
are always local. GitHub project preservation follows separate owner authorization.

```sh
python3 "$HOME/Library/Application Support/MacGuardian/mac_guardian.py" configure-cloud --provider none
python3 "$HOME/Library/Application Support/MacGuardian/mac_guardian.py" projects --dry-run
```

With authenticated `gh`, the enabled project routine creates or verifies the
owner's private `OWNER/mac-guardian-project-backups` companion repository. Each
project and local ref gets a separate `mac-guardian/...` branch. It sends allowed
working files, preserving ongoing work without modifying the source branch/index.
Original history is not used as a parent, so secrets in old commits are excluded.
A fresh no-checkout remote clone verifies every allowed blob's SHA-256. Build data,
ignored files and detected secrets stay local. Before archiving a worktree, a
private local Git bundle also preserves unpublished history and staged blobs.

Project visits and branch cursors continue across cycles (three projects and
20 refs per cycle by default). Large or unsupported data remain local. GitHub
failure preserves the project and still allows local secret protection.
Personal wiki files are not uploaded as part of this routine. Optional legacy
`backup_roots`/`backup_repo` are separate explicit report/folder selections;
local-only preference disables automatic report uploads.

## Conversation and recovery commands

Ask “How is my Mac?”, “What used space today?”, “Pause for two hours”, “Resume”,
“Undo the last organization” or “Restore that worktree.” Routine success is quiet.
The owner is contacted for critical storage, confirmed risk or a concrete
irreversible decision. Monitoring continues during a pause.

For direct local inspection:

```sh
python3 "$HOME/Library/Application Support/MacGuardian/mac_guardian.py" status
python3 "$HOME/Library/Application Support/MacGuardian/mac_guardian.py" doctor
python3 "$HOME/Library/Application Support/MacGuardian/mac_guardian.py" maintain --dry-run
```

`organize --apply` and `rename --apply` return a transaction; `undo TRANSACTION`
restores unchanged files. `maintain` combines that cycle's moves/names into
`file_transaction`; undo multiple cycles newest first. `naming-context` returns
bounded local evidence; `classify-file` applies category/topic/name after content
review, with a matching SHA-256 and reason.

Recovery uses `restore-quarantine --receipt ID`, `restore-worktree --receipt ID`
and `restore-secret --identity ID --version SHA`. Restores never overwrite an
existing destination. `purge-quarantine --receipt ID` prepares a deletion request.
Only the owner's explicit consent can be recorded with `approve --id REQUEST_ID
--evidence OWNER_WORDS`, then consumed by `purge-quarantine --receipt ID --apply
--approval REQUEST_ID`. The conversational agent must never invent that consent.

Mole's `mo clean --dry-run`, `mo purge --dry-run` and `mo optimize --dry-run` can
supply additional previews. Broad cleanup may empty Trash; use specific approval
before execution. Vorssaint is a native app, not an assumed maintenance CLI.

## Run and publish on Plow

Docker, Plow and Latch connected to the real Mac enable conversation. A fixture
Latch cannot operate the owner's device. Configure an owner-chosen listing:

```sh
python3 scripts/configure_listing.py --slug YOUR_SLUG --name 'Your Agent' --blurb 'Your description'
plow-agents login
plow-agents lines
plow-agents deploy --local --line ln_p1
docker compose up -d
```

Use an available line, then text the number shown by Plow. The official base
entrypoint and genuine five-minute usage reporter remain inherited. `AGENT_ID`
is required for registration/reporting; persistent Plow state is kept on restart.
Do not mount the home directory, Docker socket or GitHub credentials in the agent.

```sh
python3 scripts/build_publish.py ghcr.io/YOU/your-agent:v1
plow-agents image push ghcr.io/YOU/your-agent:v1
plow-agents profile --show
```

The default build is `linux/amd64`; use `--platform linux/arm64` for local Apple
Silicon testing. Keep the image public. An admin enables first one-click deploy
from the UID, slug and image digest posted by the owner in
[Agent Index Discord](https://aiworthusing.com/discord). Later updates use
`plow-agents image push IMAGE --promote SLUG`.
Register demo video, image and install URL with the
[official client](https://github.com/plow-pbc/agent-index-client), then post repo,
commit and ID in the [verification thread](https://discord.com/channels/1519035948191449268/1549100840583700481).
Plow removes WIP after validation. Source/image publication alone does not do so.

## Validation and privacy

```sh
python3 -m unittest discover -s tests -v
python3 scripts/demo_workspace.py --output private/workspace-demo
```

Tests use isolated homes and real local Git remotes. They cover unmodified
branches/indexes, remote verification, exclusion of current/historical secrets,
full worktree recovery with staged/dirty/ignored data and metadata, approval
expiry/content changes, nested wiki navigation and transaction undo.
Image/video evidence is attached to PRs with `gh --attach`.

`private/`, `.env`, `plow-credentials` and listing settings stay outside Git and
Docker build contexts. Public evidence uses synthetic files. Real reports and
secret values remain private on the Mac.

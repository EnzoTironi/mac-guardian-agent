# Architecture

Mac Guardian has a conversation container and a native macOS worker. The
container inherits Plow's OpenClaw boot, owner identity, transport and genuine
five-minute usage reporter. Latch executes permitted commands on the real Mac.
The Python worker owns deterministic checks, receipts, scope and recovery.
Neither Linux fixtures nor tool discovery establish access to the owner's Mac.

The helper reaches the Mac without a terminal. `skills/mac-health/scripts/install-command.mjs`
runs in the container and prints the exact `plow_run_command` arguments: a probe
for a Python 3.11+ interpreter, then an install that downloads the helper,
`workspace_care.py` and `install_native.py` from GitHub at the commit the image
was built from (`MAC_GUARDIAN_REVISION`). The generator hashes the copies inside
the image; the Mac installs nothing unless every download matches. The owner
approves the command in Latch. Reinstalling keeps policy, consent, wiki and backups.

The native worker runs `maintain` every 15 minutes and `check --full` at 09:10
local time through user LaunchAgents. It does not run while the Mac is powered
off or the user is logged out. It continues without Docker and does not call a
model or send native health reports to the Agent Index.

`setup-status` combines doctor checks with saved maintenance and cloud state.
It returns READY, SETUP_NEEDED, ATTENTION_NEEDED or PAUSED and the next local
action. Optional tools and the unanswered storage question do not block local
care. A saved answer suppresses the question. This command checks neither
Latch connectivity nor GitHub authentication. A corrupt receipt is an error,
not a reason to silently reset state. Status commands remain available while
the maintenance lock is held.

`maintain` collects health, preserves projects, organizes and names files when
the owner has consented, and performs due audits and approval-gated updates.
Since 0.4.0 it never deletes or quarantines on a schedule: moving caches into
quarantine freed nothing and apps rebuilt them beside the copy.

Space is a proposal. `space` (native/attention.py) measures folders their tools
rebuild (Xcode, Simulator and package-manager caches, policy `cache_paths`),
dependencies of idle committed projects and anything an earlier version put in
quarantine, defers tools that are running, and prepares one approval bound to
the exact folders (device and inode). `free-space --approval ID` deletes them
after the owner's yes, re-checking identity and running tools, keeps the
folders themselves, and reports the measured gain. The Trash is a separate
approval. `digest` runs on the daily Plow automation: it picks at most one item
(low disk with a ready proposal, Time Machine stale or not set up, a failed
stage, waiting updates) and keeps repeats quiet unless they get worse. Time
Machine status comes from `tmutil destinationinfo` and `tmutil latestbackup`;
an unreadable date is unknown, not stale.

Two scopes wait for the owner's one-time consent
(`consent.json`, granted only after a preview from the last hour): moving
personal files, and sending project code to private GitHub. Until then the
organization stage previews without moving, and project care keeps local secret
backups only, creating no repository. Installs that already moved files or saved
snapshots before 0.4.0 are recorded as grandfathered. Changing the organized
folders invalidates the organization consent. It records each stage and verifies the result. A lock
prevents concurrent writers; bounded project and ref cursors continue on later
cycles. Pause suspends mutations while monitoring continues.

Personal files live in `~/Wiki/CATEGORY/SUBJECT`, with folder indexes, Home.md
and Projects.md. New installs organize Downloads and Desktop; the whole home
folder is an explicit choice (`configure-organization --root .`). New wikis use
English folder names; a wiki created by an earlier version keeps its Portuguese
ones. Source projects retain their paths and appear as links. Pages written by
the user are preserved. Health reports remain separate under
`~/Library/Application Support/MacGuardian/reports`. Documents, Mobile Documents,
CloudStorage and top-level sync folders (Dropbox, OneDrive, Box...) stay
excluded, including aliases. Application internals, app media libraries (Music,
TV, Photo Booth, iMovie and similar packages), configurations, VM bundles,
existing vaults, project trees and cloud placeholders retain their paths.

Naming uses bounded local text, Office titles, PDF text, OCR and media tags.
Confident evidence supplies the name and subject; ambiguous cases enter a
private review queue. The model must submit the matching SHA-256 and a reason
for a content-reviewed change. Detected secrets have no returned excerpt.
Journaled same-volume moves preserve collisions and can recover an interruption
between publishing the destination and unlinking the source. Undo never replaces
a changed or existing file. Multiple cycles are undone newest first.

Quarantine (legacy `clean`, and data earlier versions set aside) lives in
`~/Backup/MacGuardian/Quarantine` with restore receipts. It frees zero bytes
until `free-space` or `purge-quarantine` deletes it with approval. Permanent purge needs specific
owner consent tied to the exact content, expiring after one hour and usable once.
Homebrew and App Store upgrades currently need the same explicit consent because
full downgrade is not guaranteed. Scope, age, source, idle and dependency checks
still apply after consent. No force, sudo, reboot or license acceptance is inferred.

The GitHub project routine runs only with the owner's github-projects consent
and uses a private companion repository. Each working tree and unpublished branch tip becomes a sanitized
snapshot branch without original parent history. It preserves allowed files,
then verifies all blobs from a fresh remote clone. The user's branch, index and
files stay unchanged. Ignored artifacts and detected secrets remain local.
Local secret versions are deduplicated and hash-verified in the private Backup
folder. Secret detection is heuristic; private GitHub is not encryption.

Before an ordinary secondary worktree is removed, the worker requires verified
remote code plus a complete local ZIP, Git bundle, config and staged index.
The archive preserves ignored files, secrets, unpublished history, links, empty
folders, permissions, times and xattrs. Unsupported, busy, recent, oversized or
failed cases retain their originals. Codex worktrees use the managed native
archive in their owning chat. Local recovery does not protect against device loss.

Background observations record executable identity, publisher, signature and
listeners without exposing arguments that may contain tokens. Changes stay in
a review queue until investigated. Observed is not trusted, and unsigned is not
malicious. Update coverage distinguishes current, outdated and unknown sources.
Signatures and Gatekeeper checks do not prove malware absence.

The image contains code, prompt and skills, without the home directory or host
credentials. New groups are untrusted with no guest tools. The development proxy
binds to a configurable loopback port. Docker health reads the running gateway's
`/readyz`, without parsing OpenClaw configuration or taking its state lock. Gateway
readiness, native readiness and real Mac connectivity are separate evidence.

Pull requests run safety tests on Ubuntu and macOS and an isolated image contract
and Plow boot probe on Intel. Main commits and version tags publish Intel and
Apple Silicon images only after those checks pass. All runtime images and actions
are pinned. Publication returns an immutable digest and preserves running Plow
state. Plow admission and WIP removal require the Plow team.

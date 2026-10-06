---
name: mac-health
description: Diagnose and maintain the owner's Mac through Latch with local health reports, bounded cleanup, a folder wiki, and verified private GitHub backups.
---

# Mac health

Use this skill for the Mac belonging to the current Plow owner. Discover its
published Latch skills first and follow the applicable local recipe.
Run native commands with the exposed plow_run_command tool or its prefixed name,
declaring the exact read/write paths and network access.

The native helper is installed at
~/Library/Application Support/MacGuardian/mac_guardian.py.
Resolve the actual home and Python executable through the Mac tools. Pass
argv as an array; never rely on a shell to expand ~.

If the helper is absent, explain that the Mac component must be installed from
the agent repository with python3 scripts/install_native.py.
A limited fixture Latch cannot maintain the owner's real Mac. Respect that
restriction rather than rerouting through an unrelated channel.

## Local commands

Invoke the helper with the Mac's Python:

- check collects disk, memory, swap, load, CPU processes and battery.
- check --full also refreshes Homebrew metadata, checks update sources,
  inventories apps and their signatures, and records launch jobs and listeners.
- plan writes the cleanup candidate list with age, inode and size.
- clean --apply uses that plan only for one hour and rechecks use and changes.
- organize previews loose old Downloads/Desktop files by category.
- organize --apply moves without overwriting and returns a transaction.
- undo TRANSACTION restores unchanged moved files.
- worktrees inventories Git worktrees without removing them.
- remove-worktree --path ABSOLUTE_PATH previews an old secondary worktree.
  Add --apply only after reviewing it; this fetches remotes, rejects all local
  refs absent from remote refs, and rejects ignored data, dirty files and locks.
  Codex worktrees always require the managed archive instead.
- backup --source ABSOLUTE_PATH --repo OWNER/REPO sends a versioned private
  snapshot and independently clones it to validate hashes.
- Add --offload only for a specifically authorized source folder.

State and the policy are under
~/Library/Application Support/MacGuardian/state/.
The wiki is at ~/Documents/MacWiki/Home.md.
Open state/dashboard.html to inspect the report.
Read only the fields needed for the owner's question. Reports include private
paths and app names; do not embed them in a public image or listing.

## Decisions that need evidence

Read policy.json before applying changes. Do not expand cache_paths,
project_roots or backup_roots just to make a rejected operation succeed.
Do not lower age limits to make a disk alert disappear.

For worktrees, gather git worktree list --porcelain, worktree age, status,
locks and commits not reachable from remotes. Confirm the destination remote
and its current refs. Managed Codex worktrees use the Codex archive tool in the
owning task; provide a plan if that lifecycle tool is unavailable.
Old folders, a clean working tree and a remote URL alone do not prove backup.

Homebrew/App Store/vendor updaters have different coverage. Report counts for
current, outdated and unknown apps. Use the official vendor updater for unknown
apps; never claim all apps are current while coverage is unknown.
Vorssaint is a native app on this Mac, not a validated cleanup CLI.
Mole's known preview commands are mo clean --dry-run, mo purge --dry-run
and mo optimize --dry-run. Save their output privately. Broad Mole clean can
empty the Trash and affect more categories than the bounded native policy.
Use it only with authorization covering its concrete preview.

A baseline of launch jobs means observed, not trusted. Review executable,
publisher, signature, origin, listener and purpose before accepting a job.
Do not remove an unknown job solely because it is unsigned or uses a shell.
Native signature/Gatekeeper checks do not replace an antimalware scan.

The helper intentionally rejects possible secrets, symlinks, special files,
hardlinks, large Git files and hidden metadata in personal backups. If rejected,
select another authorized strategy such as encryption or a normal backup tool.
Private GitHub is not encryption. Keep signing keys, tokens, sessions, photos,
mail and medical/financial records outside the source-code backup policy.

# Agent Index listing (draft for the owner to submit)

Nothing here is published. Enzo registers it with the official client or
`plow-agents image set`. The listing leaves WIP once it is blessed (post repo,
commit and id in the Discord verification thread) and has a video, an image and
either one-click deploy or an https install URL.

- **id:** `mac-guardian`
- **name:** Mac Guardian
- **blurb:** Monitor, organize and maintain your Mac, with secure cleaning and verified private backups.
- **latch:** `required`
- **install_url:** `https://github.com/EnzoTironi/mac-guardian-agent/blob/v0.4.0/README.md#install`
  (not needed once one-click deploy is enabled)
- **video:** YouTube id `JMuViuirCII` (already registered)
- **images:** the four `media/campaign-v1/images/*.png`, linked at an immutable commit

## What it does (exactly four)

| Title | Detail |
|---|---|
| Automatic care | Health checks and restorable cleanup. Anything irreversible needs your yes. |
| A wiki of your files | After one yes, sorts Downloads and Desktop by content, with undo. |
| Private code backups | With your OK, verified private GitHub branches. Secrets stay local. |
| Installs by text | Latch installs a helper checked against the image. No terminal. |

## Tools

| Tool | Description |
|---|---|
| Plow Chat | Text it for status, previews and approvals. Routine success stays quiet. |
| Plow Latch | Installs and runs the native helper on your Mac with declared paths; you approve. |

## Draft stories

Rundown's bar: first person, one specific moment, a real number, honest about
what it did not do. These are drafts with **placeholders in brackets**. Publish
one only after it happened on a real Mac (see `checks/manual-scenarios.md`),
with the real numbers. Suggested tags reuse existing ones from `GET /v1/tags`.

### It showed me the move before it moved anything

*Tags: Setup & first run, approval*

I asked it to clean up my Downloads. It didn't touch a file. It told me [N]
files would move from Downloads and Desktop into a Wiki folder, sorted by type
and subject, and asked if that was OK. I said yes. [N] files moved, renamed from
what was inside them. A week later I said "undo that" for one folder and every
file was back where it had been, byte for byte.

### It would not call quarantined space free space

*Tags: approval, automation*

My disk was nearly full and I asked it to fix that. It had already moved
[X GB] of old caches into a quarantine, and it said so: those bytes were still
on the disk so they could be restored. Deleting them for good needed my OK, and
it showed exactly what would go. I said yes. The next time I asked for the same
thing an hour later, it asked again.

### My code was saved and my .env stayed home

*Tags: Engineering, approval*

It asked once whether it could save my unpushed work to a private GitHub
repository, named the repository, and said secrets and ignored files would
stay on the Mac. I said yes. [N] projects got a private branch each, checked
from a fresh clone. My branches and staged changes did not move, and my `.env`
files sit in a local backup only I can read.

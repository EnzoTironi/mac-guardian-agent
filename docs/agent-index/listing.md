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
| Texts before the disk fills | One daily check. Silent unless something needs you. |
| Frees space with one yes | Rebuildable caches and build folders only. Never your files. |
| Watches your backups | Tells you when Time Machine stops. Code to private GitHub on OK. |
| Installs by text | Latch installs a helper checked against the image. No terminal. |

Suggested blurb update (optional): "Texts you before your Mac's disk fills, frees
space with one yes, and tells you when backups stop."

## Tools

| Tool | Description |
|---|---|
| Plow Chat | Text it; it texts you once a day at most, with one question. |
| Plow Latch | Installs and runs the native helper on your Mac with declared paths; you approve. |

## Draft stories

Rundown's bar: first person, one specific moment, a real number, honest about
what it did not do. These are drafts with **placeholders in brackets**. Publish
one only after it happened on a real Mac (see `checks/manual-scenarios.md`),
with the real numbers. Suggested tags reuse existing ones from `GET /v1/tags`.

### One yes gave me [X] GB back

*Tags: Setup & first run, approval*

I installed it from a text and approved one Latch prompt. In the same
conversation it told me I had [N] GB free and that [X] GB was Xcode build data
and package caches that rebuild themselves. It asked once. I said yes. [X] GB
came back, my Documents untouched, and it said which folder it skipped because
Xcode was open.

### It texted me before the disk filled

*Tags: automation, approval*

I had not thought about disk space in months. One morning, one text: the disk
was [N]% full, here is what can go, free it? It had said nothing on the days
before, and it did not repeat itself the day after.

### It noticed my backups had stopped

*Tags: automation*

My backup drive had been in a drawer for [N] days. Mac Guardian told me Time
Machine had not run since [date] and to plug the drive in. That was the whole
message. It did not try to fix it for me, and it did not pretend the local
copies it keeps are a backup.

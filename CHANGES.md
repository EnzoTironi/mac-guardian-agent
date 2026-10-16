# Mac Guardian 0.4.0: the Plow pattern, rebuilt from first principles

Branch `plow-pattern-upgrade`, based on `main` at `8ae7d77` (v0.3.2). Nothing is
pushed, published or registered. The listing, image and tag are Enzo's to ship.

## Summary

Mac Guardian now does the four things a Mac owner actually wants, over text,
with the owner in control:

- It texts before the disk fills.
- It frees space with one yes.
- It says when Time Machine stops.
- It keeps project code backed up on request.

It installs itself through Latch with no terminal. Every file it runs on the Mac
is checked against the image. It never deletes, quarantines or moves anything
on a schedule. Two things need one yes from the owner and are then automatic:
moving files and uploading code. The prompt carries Plow's base contract word
for word and replies in the owner's language. Tests grew from 87 to 147 (141
Python, 6 Node), and 18 mutation checks prove that the new tests catch a
reversal of each change.

## First principles: what we kept, what we changed, why

**The evidence on the Index:**

- 1 user.
- Active 2 days (2026-10-06 and 10-07), then silence.
- 50% install success.
- Not blessed, no stories.

The native worker did its work without the model, so the conversation had no
reason to happen. Meetly is the bar: one sharp job, plus a proactive loop with
an owner approval.

**What the owner wants, in order:**

1. Hear before the disk fills.
2. Free space safely with one tap.
3. Never lose a file, which means backups that actually run.
4. Know the code is safe.

Organizing files is a nice-to-have. Renaming files by their contents is the
riskiest thing the agent does.

**Kept, because it is proven and tested:**

- Health collection, the daily audit and the security observations.
- Approvals bound to exact content, expiring after one hour and used once.
- Journaled undo.
- Private GitHub snapshots, with their verification from a fresh clone.
- Local secret backups.
- The worktree archives.
- The base image and its usage reporter.
- The name, the `mac-guardian` id, the "Text this agent" install path and running locally.

**Changed:**

| Before | Now | Why |
|---|---|---|
| Every 15 minutes, caches and build output were moved into quarantine automatically. That freed **zero bytes**, and freeing space later took one approval per receipt. | `space` measures the folders their tools rebuild, plus anything quarantined earlier. It prepares **one** approval for exactly that list, bound to each folder's device and inode. `free-space` deletes after the owner's yes. Nothing is deleted on a schedule. | Quarantined caches are rebuilt by their apps right beside the copy, so the old design could use *more* disk. One tap is the whole point. |
| The agent spoke only when the owner happened to text. | A daily Plow automation runs `digest`. It picks at most one item: low disk with a ready proposal, a stale or missing Time Machine backup, a failed stage, or waiting updates. Repeats stay quiet unless the state gets worse. Otherwise it replies `NO_REPLY`. | This is the proactive loop Meetly has: one concrete ask, rarely. |
| Losing data was handled only by local copies. | Time Machine is checked with `tmutil` (destination and age of the last backup). An unreadable date counts as unknown, never as stale. | Not losing files depends on real backups. The copies in `~/Backup` are not one. |
| Organization ran automatically across Downloads, Desktop **and the whole home folder**, with no yes. | Organization happens only when the owner asks. It needs a preview from the last hour plus a yes, and new installs cover Downloads and Desktop only. App media libraries, sync folders and cloud placeholders are protected. | This feature is high-risk and low-demand: it moved Music library files and pulled iCloud-only files down to the disk. |
| Code was pushed to an automatically created GitHub repository, with no yes. | It needs one recorded yes (`github-projects`). Until then, secrets are still backed up locally and no repository is created. | Code leaving the Mac is irreversible. |
| Onboarding asked about Google Drive and iCloud. | That question is no longer asked. | Cloud transfer does not exist, so the question promised a feature that isn't there. |
| The skill told the agent to run `scripts/install_native.py`, and no checkout exists on the owner's Mac. | `install-command.mjs` prints the exact Latch commands: a probe, a hash-verified install and an uninstall. | The install could not complete. That likely explains most of the 50% install success. |
| The prompt replaced the base prompt and carried none of its rules. It defaulted to Portuguese. | It opens with Mac Guardian's identity, keeps the base sentences word for word (a test checks this), and replies in the language the person writes in. | Delivery, email, approval and automation rules are what the base runtime relies on. |

**Argued proposals, not implemented here because they can't be verified without the image or a real Mac:**

1. **Owner-gated plugin tools for `approve` and `free-space`.** This is Meetly's
   `senderIsOwner` pattern. Today the untrusted groups and the absence of guest
   tools keep non-owners out, but the model records the yes. A plugin tool
   would make the owner check a runtime fact. It needs a variant plugin and boot
   wiring that can only be proven with the image.
2. **Retire file organization in 0.5 if nobody asks for it.** Organization,
   naming and the wiki are about 700 of the helper's roughly 2,000 lines. They
   stay in 0.4 because existing wikis and undo journals depend on them, and
   they are tested. If consent records show no use, move them to an optional
   module, then remove them.
3. **Check more often when the disk is critical.** The helper can't text, since
   no Plow credential lives on the Mac. A second automation every few hours
   that stays silent unless the disk is critical would catch a fast-filling
   disk. This was left out to keep token cost at one turn a day until real
   usage shows it is needed.

## Changes by area

- **Native helper.**
  - New `native/attention.py`: `space`, `free-space`, `empty-trash`, `digest` and Time Machine status.
  - Consent scopes (`consent`, `configure-organization`), and English for every message, report and wiki page.
  - Exclusions for app libraries, sync folders and cloud placeholders.
  - No empty undo journals.
  - `maintain` no longer quarantines, and no longer previews organization on its own.
  - `build_parser()` is now reachable from tests.
- **Install.**
  - `skills/mac-health/scripts/install-command.mjs` and `MAC_GUARDIAN_REVISION` in the image.
  - CI and `build_publish.py` pass the pushed commit and refuse a dirty or unpushed tree.
  - The image ships `install_native.py` and `attention.py`.
  - The base is pinned by tag and digest (`base-ddbaa6b…@sha256:5b0ebf5e…`).
- **Prompt and skill.** A rewrite: identity, the base contract, the first
  conversation, the daily check, what needs a yes, and the new commands.
- **Docs.**
  - The README follows Plow's order and gains a known-limitations section.
  - `docs/arquitetura.md` and `docs/verificacao.md` are renamed to `architecture.md` and `verification.md` and updated.
  - New `checks/manual-scenarios.md` (13 scenarios).
  - `REVIEW.md` blocking checks.
  - `docs/agent-index/listing.md`: new capabilities and story drafts with placeholders.
  - The demos now speak English.
- **Tests.** New suites `test_consent`, `test_install`, `test_prompt_contract`,
  `test_attention` and `test_repository`. The runtime tests now run in a checkout.

## Existing installs (migration, each case tested)

| State left by 0.3.x | What 0.4.0 does | Test |
|---|---|---|
| `policy.json` with `auto_cleanup: true` | Ignored: nothing is quarantined on a schedule | `test_attention.SpaceTests.test_background_care_no_longer_quarantines_caches` |
| Items already in quarantine | Offered under "set aside earlier" in the next `space` proposal; receipts are marked purged; restore still works | `test_quarantine_from_earlier_versions_is_offered_and_purged_on_yes` |
| Organization already moved files | Organize consent is recorded as grandfathered, so care continues without a new question | `test_earlier_installs_that_already_moved_files_are_not_interrupted` |
| Verified GitHub snapshots exist | GitHub consent is grandfathered | same test |
| A wiki with Portuguese folders (`Documentos`...) | The folder names are kept; old index markers are still recognized as Mac Guardian's | `test_new_wikis_use_english_and_earlier_wikis_keep_their_names`, `test_legacy_generated_indexes_are_still_recognized_as_ours` |
| Portuguese report pages | Replaced by English pages in the helper's own reports folder | `test_health_reports_are_english_and_replace_legacy_pages` |
| A saved cloud answer | Kept; the question is never asked again | `test_cloud_choice_is_never_prompted_and_local_only_is_persistent` |
| A saved `organization_roots` that includes `.` | Kept. If files were never actually moved, the next organization needs a preview and a yes | `test_changing_folders_needs_a_new_yes` |

## Validation

### a. Plow pattern scorecard (PLOW-PATTERN.md §8)

| # | Item | Grade | Evidence |
|---|---|---|---|
| 1 | Base pinned by tag + digest; build downloads pinned | PASS | `Dockerfile` FROM `base-ddbaa6b…@sha256:5b0ebf5e…`; no build-time downloads; Actions pinned to commits; `test_fixture_is_the_pinned_base_prompt` |
| 2 | Content only; boot, reporter and base inherited | PASS | No CMD or boot override in `Dockerfile`; in-image `image.test.mjs` asserts `startAgentIndex(300_000)` (runs in the image only) |
| 3 | Identity and trust mode in the image, with the reason | PASS | `Dockerfile` ENV `AGENT_ID…AGENT_RUNTIME`, `PLOW_THREAD_TRUST=untrusted` with a comment |
| 4 | Identity first, one-line first contact, base contract tested | PASS | `tests/test_prompt_contract.py` (21 base sentences against `tests/fixtures/base-AGENTS.md`) |
| 5 | One skill per turn type, frontmatter tested | PARTIAL | A single `mac-health` skill covers setup, DM and the daily check; frontmatter tested in `test_skill_frontmatter` |
| 6 | Deterministic scripts, JSON out, atomic locked private state, corrupt state throws | PASS | The helper prints JSON and exits non-zero on error; `private_text` is atomic with mode 0600; `fcntl` lock; `test_corrupt_consent_record_fails_without_being_replaced` |
| 7 | Untrusted text reaches scripts via files only | PARTIAL | argv arrays, never a shell; but `--evidence` text and naming reasons travel as argv, not files |
| 8 | Owner gates from runtime context; approvals exact, single-use, expiring | PARTIAL | Exact, single-use and one-hour approvals and consents are tested (`test_attention`, `test_workspace`); owner identity rests on untrusted groups with no guest tools plus the model; plugin gate is proposal 1 |
| 9 | No auto-resend; idempotency; bounded retries; cleanup paths | PASS | Base contract sentences; digest quiet windows (`test_repeats_stay_quiet_and_getting_worse_is_news`); updates capped at 3 per run with a retry window |
| 10 | Latch discipline, one install link | PASS | Prompt "Reaching the Mac"; `test_mac_down_path_and_consent_are_explicit` |
| 11 | Offline hermetic tests and contract tests in CI | PASS | 141 Python + 6 Node pass offline; `.github/workflows/check.yml` runs both (CI itself not run here) |
| 12 | `checks/manual-scenarios.md` | PASS | 13 scenarios with Expect/Check lines |
| 13 | README in order, known limitations, REVIEW.md | PASS | `README.md`, `REVIEW.md` |
| 14 | No secrets or personal data; English; MIT | PASS | `test_no_personal_data_in_the_tree`, `test_helper_messages_are_english`, `LICENSE`; `evidence/*.json` keep the v0.3.2 Portuguese question verbatim as a historical record |
| 15 | Listing complete and out of WIP | FAIL | Live record: not blessed, not deployable, 0 stories, `install_url` at v0.3.2 (see b) |

**One line:** 11 PASS, 3 PARTIAL (5, 7, 8), 1 FAIL (15: listing, Enzo's action).

### b. Agent Index publish requirements

Live record, fetched 2026-10-16 with `curl -s 'https://agent-index-server.vercel.app/v1/agent?agent_id=mac-guardian&fresh=1'`:
blessed `""`, deployable `""`, tested `""`, latch `required`, 4 capabilities,
tools Plow Chat and Plow Latch, video `JMuViuirCII`, 4 images, 0 stories, install
`https://github.com/EnzoTironi/mac-guardian-agent/blob/v0.3.2/README.md`,
installs 2 attempted / 1 succeeded. `/v1/usage` shows usage on 2026-10-06 and 10-07.

| Requirement | Status | What Enzo does |
|---|---|---|
| MIT license | Done | Nothing (`LICENSE`, image label `MIT`) |
| Working usage reporting | Done in code: `ENV AGENT_ID=mac-guardian`, base reporter inherited, and earlier days were reported | After deploying 0.4.0, check that `/v1/usage?agent_id=mac-guardian` gains new days |
| Blessed | Missing | Post the repo, the release commit and `mac-guardian` in the Discord verification thread |
| Video | Done (`JMuViuirCII`) | Optional: a new cut showing "one yes freed X GB" |
| At least one image | Done (4) | Optional: a real screenshot of the space text |
| Deployable, or an https `install_url` | Not deployable; `install_url` points at v0.3.2 | Tag `v0.4.0`, push, let CI publish, make the GHCR package public, ask an admin to enable one-click; or set the install link to `…/blob/v0.4.0/README.md#install` |
| Exactly 4 capabilities | 4 present, but they describe the old product (wiki-first) | Replace them with the four in `docs/agent-index/listing.md` |
| Tools | Done | Optionally update the descriptions from `listing.md` |
| `latch: required` | Done | Nothing |
| Stories | 0 | After a real run (`checks/manual-scenarios.md` 1, 5 and 6), fill the placeholders of one to three drafts in `listing.md` and publish |

### c. Unverified, and how to verify

| Check | Why it didn't run here | Exact steps | Expected |
|---|---|---|---|
| Docker build and image contract | No Docker on this Mac | `docker build --platform linux/amd64 --build-arg MAC_GUARDIAN_REVISION=$(git rev-parse HEAD) -t mac-guardian:check .` then `python3 scripts/test_image.py mac-guardian:check --platform linux/amd64`; repeat with `linux/arm64` | `"ok": true`; runtime-contract runs 4 image tests with 0 skipped; boot probe prints `PLOW_PROBE_OK` |
| Live Plow line | No line or credentials used | `plow-agents mint LINE`, `MAC_GUARDIAN_REVISION=<pushed sha> docker compose up --build -d`, `docker compose logs -f agent`, then text the number | Identity line in the logs; a one-line introduction, then the install step |
| Latch install on a real Mac | Latch must not be used from here | `checks/manual-scenarios.md` 1–3 | Probe JSON; one Latch approval; helper and two LaunchAgents installed; a tampered file means "checksum mismatch …; nothing was installed" |
| Whether Latch permits `launchctl` | Unknown Latch sandbox behavior | Scenario 1, then `launchctl print gui/$(id -u)/local.macguardian.monitor` | The job is loaded; `setup-status` reports `READY` |
| LaunchAgents running over time | They must not be installed here | After a day: `helper doctor`, `helper status` | `ok: true`; monitor age under 45 minutes; audit age under 36 hours |
| Freeing space on real folders | Only exercised on synthetic folders | Scenario 5 | Folders emptied but present; freed GB close to the `df -h` delta; Xcode deferred while open |
| Daily check automation | The model creates it through OpenClaw automations | Scenarios 4 and 6 | Exactly one automation; `NO_REPLY` on a healthy day; one text on a stale backup, not repeated the same day |
| Time Machine with a configured destination | This Mac has none (`tmutil: No destinations configured.`, parsed correctly); `latestbackup` may need Full Disk Access | On a Mac with Time Machine: `helper digest --dry-run`, compare with `tmutil latestbackup` | Configured destination with the correct age, or `latest: null` when access is missing, never a false stale |
| GitHub private-branch preservation against a real remote | Tests use a local bare remote | Scenario 8 with `gh` signed in | A private repository with a `mac-guardian/…` branch, no `.env`, your branch and index unchanged |
| CI on GitHub | Nothing pushed | Push the branch and open a PR | `check.yml` safety jobs (Ubuntu and macOS) and the image job are green |

### d. Test inventory (before = `main`, after = this branch)

| Suite | Command | Before | After |
|---|---|---|---|
| Safety suites (autonomy, guardian, setup, volumes, workspace) | `python3 -m unittest discover -s tests` | 87 | 87 (updated for English, consent and new defaults; none removed) |
| Consent | same | — | 18 |
| Space, Time Machine, digest | same | — | 17 |
| Install bootstrap and generator | same (generator tests need `node` on PATH) | — | 6 |
| Prompt contract | same | — | 10 |
| Repository (build context, English, release refusals) | same | — | 3 |
| **Python total** | `env -u AGENT_ID python3 -m unittest discover -s tests` | **87** | **141, all passing** |
| Runtime (Node) | `node --test tests/runtime/*.test.mjs` | 2 files, both failing outside the image (module not found) | 10: 6 pass, 4 skipped outside the image with the reason stated |

**Mutation checks.** 18 single-point reversions, each applied to a scratch
copy and run against its targeted test. All 18 were caught. They reverted:

- the consent gates (files, background care, GitHub);
- the default folders;
- the app-library and placeholder protections;
- the bootstrap checksum, the generator's hashes and the unpinned-image refusal;
- two prompt-contract sentences (the base contract and the language rule);
- quarantine on a schedule;
- the free-space approval;
- the digest quiet window;
- the cloud question;
- the `.dockerignore` allow-list;
- the release-script refusal;
- English messages.

**Other checks run.**

- `python3 -m compileall` over `native`, `scripts` and `tests`.
- `node --check` on every `.mjs` file.
- `scripts/demo_wiki.py`, `demo_workspace.py` and `demo_readiness.py` in temporary homes.
- `configure_listing.py` in a scratch copy (writes `listing.json` and `.env` with mode 600, and rejects a bad slug).
- A smoke run of every read-only CLI command against a temporary home: `init`, `setup-status`, `status`, `doctor`, `consent`, `maintain --dry-run`, `space`, `digest --dry-run`, `projects --dry-run` and `organize`.

**Not run, and why.**

- `scripts/test_image.py` and a full `build_publish.py` run: they need Docker.
- `scripts/install_native.py`: it would install LaunchAgents on this Mac.
- Anything needing Latch, a Plow line or real GitHub.

The real home directory was never used. LaunchAgents were never installed.

## Needs Enzo's decision

1. The new listing capabilities and the optional blurb in `docs/agent-index/listing.md`.
2. Demoting file organization to on request, and dropping the cloud question.
3. Grandfathering consent for installs that already moved files or saved
   snapshots. The alternative is asking everyone again.
4. The daily check runs in the morning, set when the owner first uses the
   agent. Should it move to a different time?
5. Tagging `v0.4.0`, which the README install link and the listing `install_url` point at.
6. Removing the legacy `plan` and `clean` commands in 0.5.

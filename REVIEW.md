# Review Mac Guardian

The README describes the product. Flag drift between its claims, the native
helper, the conversation prompt, the skill and the verification document.

**Stage:** pre-release, a handful of installs. The helper moves, renames and can
delete files on someone's own Mac and can push their code to GitHub, so a
change that weakens a safety gate is blocking even when it looks like polish.

## Blocking checks

- **Nothing moves or leaves without the owner's yes.** Moving personal files
  needs organize consent; uploading code or creating a repository needs
  github-projects consent; both need a recorded preview from the last hour and
  the owner's own words. Block any path that reaches `file_moves`,
  `project_snapshot` or `private_project_repo` without `require_consent`, a
  background run that writes a consent preview, or a prompt or skill line that
  lets the model grant consent without the owner's yes.
- **Nothing is deleted, quarantined or moved on a schedule.** `space` only
  measures and proposes; `free-space` and `empty-trash` run only with an
  approval for the exact inventory. Block a stage in `maintain` that deletes or
  quarantines, a target in `REBUILDABLE` that holds user documents, or a digest
  that texts the same item every day.
- **Irreversible means a yes every time.** Purge, Trash, backup deletion,
  updates and installers go through `request_approval`/`consume_approval`:
  exact content, one hour, single use. Quarantine frees zero bytes and must
  never be reported as recovered space.
- **Every automatic write has a receipt or an undo.** Failed preservation
  keeps originals in place. Malformed persisted state fails loudly; it is never
  silently replaced.
- **Scope stays narrow.** Documents, cloud roots, top-level sync folders, app
  media libraries, projects, vaults, bundles and placeholders stay excluded,
  including through aliases. The default organizes Downloads and Desktop only.
- **What runs on the Mac is what was reviewed.** The install downloads at the
  image's commit and checks every file against the image's copy. Block a
  mutable ref, a skipped hash, a shell string built from model input, or an
  install path that bypasses Latch.
- **Pins are reviewed changes.** The base `FROM` carries tag and digest, Actions
  are pinned to commits, and bumping the base updates the prompt fixture.
- **Privacy.** Personal reports, paths, chat IDs, credentials and real file
  contents never enter tracked files, Docker contexts, screenshots or fixtures.
  Evidence uses synthetic homes and local Git remotes. A private repository is
  not a secret vault.

## Contrast pairs

| Don't flag | Do flag |
|---|---|
| Behaviour specific to caring for one person's Mac. That is the product. | A change a sibling owns: boot, identity, transport and usage reporting are the base's (`plow-pbc/plow-openclaw-agent`); Mac permissions are Latch's. Do not copy Meetly's preboot or plugins to fix a base problem. |
| Bumping a pin to a newer immutable revision. | A prompt edit that drops a sentence `tests/test_prompt_contract.py` keeps from the base. |

New groups are untrusted with no guest tools. Conversation style never grants
access or changes storage, consent or approval policy. Keep Mac results private
to the owner's conversation. Test configured boundaries against the compiled
base, not a replacement.

For a change to maintenance, run the Python suite. For image or runtime changes,
also run the image contract and base probe. Distinguish fixture results, direct
Mac checks, relay checks, image publication and Plow admission in the review.
Attach real image or video evidence with `gh --attach`.

# Verification and limits

The repeatable checks for version 0.3.2 are:

```sh
python3 -m unittest discover -s tests -v
docker build --platform linux/amd64 --tag mac-guardian:check .
python3 scripts/test_image.py mac-guardian:check --platform linux/amd64
python3 scripts/demo_workspace.py --output private/workspace-demo
```

The Python safety suite uses isolated homes and actual local Git remotes. It
checks recursive wiki organization, content naming, collision preservation,
interrupted moves, transaction undo and protected Documents/cloud paths. It
also checks local secret backup, sanitized private snapshots, original branch
and index preservation, complete worktree recovery, approval expiry and content
changes, collector failures and pause behavior.

Readiness tests cover a fresh installation, stale collectors, missing jobs,
a failed or paused worker, a saved local-only answer, a question already asked,
malformed preferences and a held worker lock. A Linux fixture must not claim that
the real Mac is ready. Optional tools and unanswered preferences never stop
local care. A native READY result explicitly leaves relay and GitHub connection
checks unverified.

The built-image tests use the actual compiled Plow configuration. They verify
owner binding, untrusted groups with no guest grants, separate group sessions,
private memory and restricted cross-conversation sends. They confirm the native
module pair, listing identity, prompt instructions and inherited five-minute
reporter. HTTP tests reject a live-but-unready, partially failed, parked, absent
or malformed gateway. The fixture boot probe requires PLOW_PROBE_OK and exit 0.

`scripts/test_image.py` runs disposable containers with network disabled, no
credentials, no persistent Plow volume and no connection to a Mac. Its JSON
receipt distinguishes runtime contract checks from boot readiness and returns
nonzero on failure. These checks do not prove message delivery, actual relay
availability, full-audit completion through Latch or physical Mac operations.

The workspace demo executes native commands against synthetic files and local
Git remotes. It exercises wiki naming and undo, sanitized project preservation,
local secret protection, worktree archive and restoration. Review screenshots
and videos are evidence of those fixture outputs, not personal-file operations.
Use `gh --attach` to add both images and video to the pull request.

For a direct Mac check, inspect `setup-status` and `doctor` from the installed
helper. A loaded schedule is not proof that all collectors succeeded. For a
relay check, run one harmless command on the real Mac through its published
Latch recipe, then poll any pending handle. Tool discovery alone is insufficient.
Do not repeat an operation whose result is uncertain.

For a release, wait for CI, verify the published digest's architecture manifests
and anonymous access, and check the deployed gateway separately. Preserve its
state volume and usage identity. A public image does not establish Plow admission
or removal of the WIP tag. Those require the team's verification.

Remaining product limits include heuristic secret detection, incomplete update
coverage for unknown sources, no exhaustive malware verdict, no guaranteed app
downgrade and no cloud-file transfer. Quarantine does not free space. Backups on
the same Mac do not protect against loss of the device. Failed preservation or
an unsupported file/worktree leaves the original in place.

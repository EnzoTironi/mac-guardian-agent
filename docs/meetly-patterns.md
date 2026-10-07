# Patterns adopted from Meetly

Reference: [Meetly at c1491ec9](https://github.com/plow-pbc/meetly-openclaw-agent/tree/c1491ec9f4f271ab8e7f0b6f8992a8239ed41165), inspected on October 7, 2026.

| Meetly pattern | Mac Guardian implementation |
| --- | --- |
| Current setup evidence replaces old conversation assumptions | Native `setup-status` checks installation, launchd, fresh collectors, failures, pause and the saved storage answer. The prompt and skill consume that evidence. |
| Deterministic work lives in scripts | Native Python controls readiness, receipts, approvals, snapshots and recovery. The model interprets ambiguous file content and communicates decisions. |
| Guests receive only explicit scoped tools | New groups remain untrusted. Mac Guardian grants no guest tools and retains the base owner binding and separate group sessions. Image tests exercise the compiled configuration. |
| Immutable base and supply-chain pins | The same published Plow base digest supports Intel and Apple Silicon. GitHub Actions are pinned to commits. The official boot and genuine five-minute reporter remain inherited. |
| CI and reproducible image publication | Ubuntu/macOS safety tests and a credential-free base probe gate GHCR publication. Releases include both architectures, SHA tags and an immutable digest receipt. `latest` is opt-in. |
| Loopback development access | `HOST_PORT` selects the local proxy port. The runtime readiness check reads `/readyz` without competing for the state lock. |
| Reviewer rules distinguish promises from evidence | `REVIEW.md` protects privacy, recovery, ownership and documentation accuracy. Architecture and verification documents describe the current implementation. |

Meetly's calendar tools, guest scheduling, travel, contact state and setup plugin
are specific to its product. Mac Guardian uses its native readiness command
through the existing Mac recipe, without a second boot implementation or a
calendar plugin. The inherited Plow base owns identity, transport and reporting.

The native readiness check does not prove relay availability or authenticate
GitHub. Image probes run without credentials, network or a real Mac. They do
not send messages, register a second listing or test personal-file operations.
No cloud transfer, broader filesystem permission or irreversible action is
authorized by these patterns.

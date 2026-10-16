# Plow's OpenClaw base, pinned by tag and multi-architecture index digest: a tag
# alone is a name someone can move, and this image boots holding the agent's
# Plow credential. To bump: pick a newer base-<full sha> tag from
# https://gallery.ecr.aws/e1h7x4a2/plow-cloud-agents, read its digest, update
# tests/fixtures/base-AGENTS.md and the commit noted there, then run the checks.
# base-ddbaa6b is plow-openclaw-agent at 2026-10-06 ("Read Plow's reply_to as the
# wrapper it is"), the same digest Meetly and Puppeteer run.
FROM public.ecr.aws/e1h7x4a2/plow-cloud-agents:base-ddbaa6bc0f9e071d9411777b91590e755e367d84@sha256:5b0ebf5e33514b09f0f22f1c14424a19b4eb3fc21adfaeb260002f76d362478c
ARG AGENT_ID="mac-guardian"
ARG AGENT_NAME="Mac Guardian"
ARG AGENT_BLURB="Monitor, organize and maintain your Mac, with secure cleaning and verified private backups."
# The commit this image is built from. The Mac downloads the helper from GitHub
# at exactly this commit and checks it against the copy in this image, so CI
# passes the pushed commit SHA. A build without it cannot install the helper.
ARG MAC_GUARDIAN_REVISION=""
ARG MAC_GUARDIAN_SOURCE="EnzoTironi/mac-guardian-agent"
LABEL org.opencontainers.image.title="Mac Guardian" \
    org.opencontainers.image.source="https://github.com/EnzoTironi/mac-guardian-agent" \
    org.opencontainers.image.licenses="MIT" \
    org.opencontainers.image.version="0.4.0" \
    org.opencontainers.image.revision="${MAC_GUARDIAN_REVISION}"
# AGENT_ID lives in the image: a one-click cloud install has no compose file.
# Groups are untrusted with no guest tools: Mac Guardian works on one person's
# Mac, so only the owner may reach it, and Mac results stay in the owner's chat.
ENV AGENT_ID=${AGENT_ID} \
    AGENT_NAME=${AGENT_NAME} \
    AGENT_BLURB=${AGENT_BLURB} \
    AGENT_RUNTIME=OpenClaw \
    PLOW_THREAD_TRUST=untrusted \
    PLOW_GUEST_TOOLS="" \
    MAC_GUARDIAN_REVISION=${MAC_GUARDIAN_REVISION} \
    MAC_GUARDIAN_SOURCE=${MAC_GUARDIAN_SOURCE}
COPY prompt/AGENTS.md /opt/plow/prompt/AGENTS.md
COPY skills/ /opt/plow/skills/
# Shipped for installation on the owner's Mac; never run as Mac care on Linux.
# install-command.mjs hashes these exact files for the Mac to verify.
COPY native/ /opt/mac-guardian/
COPY scripts/install_native.py /opt/mac-guardian/install_native.py
COPY runtime/healthcheck.mjs /opt/mac-guardian/runtime/healthcheck.mjs
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 CMD ["node", "/opt/mac-guardian/runtime/healthcheck.mjs"]
# Keep the official entrypoint, state and five-minute usage reporter.

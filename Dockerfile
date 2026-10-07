# Published multi-architecture base used by Meetly at c1491ec9f4f271ab8e7f0b6f8992a8239ed41165.
FROM public.ecr.aws/e1h7x4a2/plow-cloud-agents@sha256:5b0ebf5e33514b09f0f22f1c14424a19b4eb3fc21adfaeb260002f76d362478c
ARG AGENT_ID="mac-guardian"
ARG AGENT_NAME="Mac Guardian"
ARG AGENT_BLURB="Quiet Mac care with organized files, reversible maintenance and verified private project backups."
LABEL org.opencontainers.image.title="Mac Guardian" \
    org.opencontainers.image.source="https://github.com/EnzoTironi/mac-guardian-agent" \
    org.opencontainers.image.licenses="MIT" \
    org.opencontainers.image.version="0.3.2"
ENV AGENT_ID=${AGENT_ID} \
    AGENT_NAME=${AGENT_NAME} \
    AGENT_BLURB=${AGENT_BLURB} \
    AGENT_RUNTIME=OpenClaw \
    PLOW_THREAD_TRUST=untrusted \
    PLOW_GUEST_TOOLS=""
COPY prompt/AGENTS.md /opt/plow/prompt/AGENTS.md
COPY skills/ /opt/plow/skills/
# Distributed for installation on the owner's Mac; do not run Mac checks on Linux.
COPY native/ /opt/mac-guardian/
COPY runtime/healthcheck.mjs /opt/mac-guardian/runtime/healthcheck.mjs
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 CMD ["node", "/opt/mac-guardian/runtime/healthcheck.mjs"]
# Keep the official entrypoint, state and five-minute usage reporter.

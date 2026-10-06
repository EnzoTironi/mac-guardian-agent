# Official OpenClaw base returned by plow-agents image show openclaw, 2026-10-06.
FROM public.ecr.aws/e1h7x4a2/plow-cloud-agents@sha256:42a6d50f15d67c620f68312d067a1a25ad3b007bf51e6b2e6742b8059ffb4798
ARG AGENT_ID=""
ARG AGENT_NAME="Mac Guardian"
ARG AGENT_BLURB="Cuida da saúde do Mac com manutenção, wiki e backups privados verificáveis."
LABEL org.opencontainers.image.title="Mac Guardian" \
    org.opencontainers.image.source="https://github.com/EnzoTironi/mac-guardian-agent" \
    org.opencontainers.image.licenses="MIT" \
    org.opencontainers.image.version="0.3.0"
ENV AGENT_ID=${AGENT_ID} \
    AGENT_NAME=${AGENT_NAME} \
    AGENT_BLURB=${AGENT_BLURB} \
    AGENT_RUNTIME=OpenClaw \
    PLOW_THREAD_TRUST=untrusted
COPY prompt/AGENTS.md /opt/plow/prompt/AGENTS.md
COPY skills/ /opt/plow/skills/
# Distributed for installation on the owner's Mac; do not run Mac checks on Linux.
COPY native/ /opt/mac-guardian/
# Keep the official entrypoint, state and five-minute usage reporter.

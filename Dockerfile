FROM node:22-bookworm-slim@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5

# The image contains the stdlib Python server and the pinned Microsoft
# Playwright MCP package.  Playwright's own installer supplies Chromium and
# the Debian runtime libraries; no host browser or privileged container is
# required.
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NPM_CONFIG_UPDATE_NOTIFIER=false \
    TZ=America/Los_Angeles \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates python3 tini tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts --no-audit --no-fund \
    && test -f /app/node_modules/playwright-core/cli.js \
    && node /app/node_modules/playwright-core/cli.js install-deps chromium \
    && node /app/node_modules/playwright-core/cli.js install --no-shell chromium \
    && chmod -R a+rX /ms-playwright

COPY backend/ /app/backend/
COPY scripts/ /app/scripts/
COPY web/ /app/web/

# UID/GID 1000 is deliberate: the compose file uses the same non-root
# identity for the persistent data volume on the home lab. The official Node
# image already has UID/GID 1000 (`node`), so create a named account only when
# the base image does not provide one.
RUN if ! getent group 1000 >/dev/null; then groupadd --gid 1000 ledger; fi \
    && if ! getent passwd 1000 >/dev/null; then useradd --uid 1000 --gid 1000 --create-home --home-dir /var/lib/ledger --shell /usr/sbin/nologin ledger; fi \
    && existing_user="$(getent passwd 1000 | cut -d: -f1)" \
    && usermod --home /var/lib/ledger --shell /usr/sbin/nologin "$existing_user" \
    && mkdir -p /var/lib/ledger \
    && chown 1000:1000 /var/lib/ledger

ENV HOME=/var/lib/ledger \
    PATH=/app/node_modules/.bin:$PATH \
    CODEX_HOME=/var/lib/ledger/.codex \
    LEDGER_DATA_DIR=/var/lib/ledger \
    LEDGER_PORT=8907 \
    LEDGER_BIND_HOST=0.0.0.0 \
    LEDGER_CODEX_CLI=/app/node_modules/.bin/codex \
    LEDGER_BROWSER_BRIDGE=/app/scripts/cancellation-browser.mjs \
    LEDGER_PLAYWRIGHT_MCP_CLI=/app/node_modules/@playwright/mcp/cli.js \
    LEDGER_BROWSER_WORKSPACE=/var/lib/ledger/cancellation-workspaces \
    LEDGER_BROWSER_PROFILE=/var/lib/ledger/browser-profile \
    LEDGER_CANCELLATION_WORK_DIR=/var/lib/ledger/cancellation-workspaces \
    LEDGER_BROWSER_HEADLESS=1

USER 1000:1000
EXPOSE 8907
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python3", "/app/backend/server.py"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8907/api/health', timeout=3)"

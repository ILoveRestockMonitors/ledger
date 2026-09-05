# Ledger on Ubuntu 24

Ledger is a single-owner finance app. The Python backend listens on
`127.0.0.1` only; private remote access is provided by an SSH local forward or
Tailscale Serve. The installer does not read or copy a source checkout's
`backend/data/` directory, and updates keep the separate data directory.

## Add Ledger to an iPhone Home Screen

1. Connect Tailscale if the private Ledger address requires it, then open the
   hosted Ledger HTTPS address in Safari and sign in.
2. Tap **Share**, choose **Add to Home Screen**, then tap **Add**. If the sheet
   offers **Open as Web App**, leave it enabled.
3. Open Ledger from the new Home Screen icon whenever you want to use it. The
   installed app may ask you to sign in again.

Ledger remains a server-backed app: the Home Screen icon is a shortcut to the
live service. Use the same hosted URL on Windows so both devices see the same
records; the old local launcher does not sync with this hosted copy. It does
not cache financial responses or provide offline records.

## Install or update

Requirements are Ubuntu 24, Python 3, and systemd. The Python runtime has no
third-party packages. From a source checkout on the home lab:

```bash
cd Ledger
sudo ./scripts/install-ubuntu.sh \
  --source-dir "$PWD" \
  --app-dir /opt/ledger \
  --data-dir /var/lib/ledger \
  --no-start
```

Review the files in `/etc/ledger/ledger.env`, then start the service when ready:

```bash
sudo systemctl enable --now ledger.service
sudo systemctl status ledger.service
```

For an existing installation, use `--mode update` with the same paths. It
updates application code and the Ledger units while retaining `/var/lib/ledger`
and existing environment values. It does not stop or modify unrelated systemd
units. To inspect an install plan without root, service calls, or filesystem
writes:

```bash
./scripts/install-ubuntu.sh --mode dry-run --source-dir "$PWD"
```

The default service user is the dedicated, non-login `ledger` user. The app
directory is root-owned and data is `0700`, owned by `ledger`.

## Docker on the home lab

The repository includes a non-root application container for hosts where Docker
is available but system-wide sudo changes are not. It uses the official Node 22
Bookworm image, Python 3, and the pinned Microsoft `@playwright/mcp` package
from `package.json`. The image installs Chromium and its Debian runtime
dependencies during the build. The application process runs as UID/GID
`1000:1000`, and only the data directory is writable.

From the checkout on the home lab, choose an absolute, private data path. The
path is outside the checkout so a rebuild cannot copy the database or config
into the image:

```bash
cd Ledger
export LEDGER_DATA_DIR="$HOME/Ledger-data"
install -d -m 700 "$LEDGER_DATA_DIR"
docker compose build
docker compose up -d
docker compose ps
```

Compose publishes the container as `127.0.0.1:8907` and uses
`restart: unless-stopped`. The existing Tailscale Serve route from port 443 to
the home's existing local service is not changed by these commands. To open
the container privately from a laptop, use an SSH forward and then browse to
the forwarded address:

```bash
ssh -N -L 8907:127.0.0.1:8907 your-user@home-lab
```

Open `http://127.0.0.1:8907/` locally and complete first-time owner setup.
The container bind is `0.0.0.0` only inside the container so Docker can map it
to the host loopback address; the host port is not exposed on LAN or Tailscale.
The server validates this container-only bind setting. Do not add a public
port mapping or `network_mode: host`.

Persistent updates keep `$HOME/Ledger-data`; rebuilds do not copy source
`backend/data/` or any `.env`, config, database, backup, or JSONL files because
they are excluded by `.dockerignore`. Inspect the service without opening a
network port:

```bash
docker compose ps
docker compose logs --tail=100 ledger
curl -fsS http://127.0.0.1:8907/api/health
```

Stop or update it with:

```bash
docker compose stop
docker compose build && docker compose up -d
```

The base image supports manual entry, Plaid configuration, scheduled syncs,
and includes the pinned Codex CLI. It has no signed-in account. The optional
cancellation worker stays unavailable until the CLI is authenticated as UID
1000 with the dedicated
`CODEX_HOME=/var/lib/ledger/.codex` directory. Keep that credential directory
in the private data volume; do not bake it into an image or mount a personal
browser profile. The container browser is headless, so login, MFA, CAPTCHA, or
provider handoff requires a separately controlled GUI worker. No VNC endpoint
is enabled or published by this compose file; when that handoff is needed the
job remains `needs_user` until the controlled worker returns evidence.

Authenticate the included CLI into the persistent data volume as UID 1000,
then start the worker:

```bash
docker compose run --rm --user 1000:1000 ledger codex login
docker compose up -d
```

Use the ChatGPT account login flow; do not provide `OPENAI_API_KEY` as a
fallback. The worker uses the configured Luna model only after `codex login`
succeeds; this does not automate provider login or claim cancellation without
provider evidence.

## First owner login

Setup is allowed only through localhost. Keep the service listening on the
home lab and create an SSH local forward from your own computer:

```bash
ssh -N -L 8907:127.0.0.1:8907 your-user@home-lab
```

With that command running, open <http://127.0.0.1:8907/> in the local browser
and set the owner password when Ledger prompts for first-time setup. The
password verifier is stored in SQLite; the one-time session is returned as an
HttpOnly cookie and is never printed by the server. The password must be at
least 12 characters. Stop the SSH command with Ctrl-C after setup.

If the service uses another port, replace both `8907` values with that port.

## Private HTTPS with Tailscale

Install and authenticate Tailscale separately according to your home-lab
policy. Set the exact tailnet URL in `/etc/ledger/ledger.env`:

```text
LEDGER_PUBLIC_ORIGIN=https://ledger.your-tailnet.ts.net
```

Restart Ledger, then publish only its localhost listener through Tailscale:

```bash
sudo systemctl restart ledger.service
sudo tailscale serve --bg http://127.0.0.1:8907
tailscale serve status
```

Use the HTTPS URL shown by `tailscale serve status`. Tailscale ACLs remain the
access control boundary. Do not bind Ledger to `0.0.0.0`, forward port 8907
from the router, or publish the cancellation worker endpoint.

## Plaid and scheduled sync

Enter Plaid settings from the authenticated Ledger UI. Credentials remain in
the private data directory and are redacted from the API. Linked Items are
refreshed incrementally by cursor every four hours by default; change
`sync_interval_minutes` in Settings if needed. A failed Item is recorded in
`/api/sync/status` while other Items continue, and a subscription scan runs
after successful updates.

The scheduler is disabled from making external calls when `LEDGER_TESTING=1`
or a pytest process is active. No credentials or live Plaid calls are needed
for local tests.

## Optional cancellation browser worker

The browser bridge is optional. If you enable it on a systemd install, use
Node.js 22 or newer and install the exact local dependency declared in
`package.json`; no global npm package is needed:

```bash
cd /opt/ledger
sudo npm install --prefix /opt/ledger --omit=dev --ignore-scripts
sudo -u ledger -H env HOME=/var/lib/ledger PLAYWRIGHT_BROWSERS_PATH=/var/lib/ledger/.cache/ms-playwright \
  node /opt/ledger/node_modules/playwright-core/cli.js install chromium
```

The dependency is the official Microsoft `@playwright/mcp` package pinned to
`0.0.80`; its `playwright-core` dependency provides the installer above.
Install the Chromium system libraries with the package's documented command as
root before the browser install when the host does not already provide them:

```bash
sudo node /opt/ledger/node_modules/playwright-core/cli.js install-deps chromium
```

The Dockerfile performs both steps during its image build.

The browser executable is cached under
`/var/lib/ledger/.cache/ms-playwright`. Configure the exact local bridge and
CLI paths in `/etc/ledger/ledger.env`:

```text
HOME=/var/lib/ledger
CODEX_HOME=/var/lib/ledger/.codex
LEDGER_CODEX_CLI=/usr/local/bin/codex
LEDGER_BROWSER_BRIDGE=/opt/ledger/scripts/cancellation-browser.mjs
LEDGER_BROWSER_PROFILE=/var/lib/ledger/browser-profile
# Set to 1 only when the home-lab worker is intentionally headless.
LEDGER_BROWSER_HEADLESS=0
```

Authenticate the Codex CLI as the same dedicated service user that owns
Ledger's jobs, so its existing Luna plan and login are used by the worker:

```bash
sudo -u ledger -H env HOME=/var/lib/ledger codex login
```

The cancellation worker invokes the configured `gpt-5.6-luna` model and pauses
for login, MFA, captcha, or unexpected terms. A browser page opening is not
completion evidence. Keep the bridge local and allowlist provider domains.
`ledger.service` enforces the dedicated `HOME`, `CODEX_HOME`, and browser
profile paths even when the environment file is updated during an upgrade.

## Encrypted backups

Backups are encrypted with system OpenSSL after SQLite's online backup API
creates a consistent snapshot. The archive contains `ledger.db` and, when it
exists, `config.json`; it never includes the source tree. Configure an already
mounted external filesystem and a passphrase file readable by `ledger`:

```bash
sudo install -d -o ledger -g ledger -m 0700 /mnt/ledger-backups
sudo install -o root -g ledger -m 0640 /dev/null /etc/ledger/backup.passphrase
findmnt --mountpoint /mnt/ledger-backups
sudoedit /etc/ledger/backup.passphrase
sudoedit /etc/ledger/ledger.env
```

Add these settings to `ledger.env`:

```text
LEDGER_BACKUP_MOUNT=/mnt/ledger-backups
LEDGER_BACKUP_PASSPHRASE_FILE=/etc/ledger/backup.passphrase
```

The timer runs `ledger-backup.service` nightly with a randomized delay. Test
the configuration without reading the passphrase or creating an archive:

```bash
python3 scripts/backup.py backup \
  --data-dir /var/lib/ledger \
  --destination /mnt/ledger-backups \
  --dry-run
```

Then enable the timer and run one real backup when the external mount and
passphrase file are ready:

```bash
sudo systemctl enable --now ledger-backup.timer
sudo systemctl start ledger-backup.service
sudo journalctl -u ledger-backup.service --since today
```

The backup unit permits `/mnt/ledger-backups` when it is mounted. If
`LEDGER_BACKUP_MOUNT` uses another path, add a drop-in that names both the data
directory and custom mount, then reload systemd:

```bash
sudo systemctl edit ledger-backup.service
```

```ini
[Service]
ReadWritePaths=
ReadWritePaths=/var/lib/ledger -/srv/ledger-backups
```

Verify the custom mount before starting the backup service:

```bash
findmnt --mountpoint /srv/ledger-backups
sudo systemctl daemon-reload
```

To restore, stop Ledger first. The script validates the decrypted archive and
SQLite integrity, keeps a `pre-restore-*` recovery directory, and replaces
only the database/config files:

```bash
sudo systemctl stop ledger.service
sudo -u ledger -H env HOME=/var/lib/ledger LEDGER_DATA_DIR=/var/lib/ledger \
  LEDGER_BACKUP_PASSPHRASE_FILE=/etc/ledger/backup.passphrase \
  /usr/bin/python3 /opt/ledger/scripts/backup.py restore \
  /mnt/ledger-backups/ledger-YYYYMMDDTHHMMSSZ.tar.gz.enc
stat -c '%U:%G %a %n' /var/lib/ledger/ledger.db
test ! -e /var/lib/ledger/config.json || stat -c '%U:%G %a %n' /var/lib/ledger/config.json
sudo systemctl start ledger.service
```

Keep the passphrase file and external mount protected. A lost passphrase cannot
be recovered by Ledger.

## Purchase details assistant

Transactions includes **Clarify purchases** and **Purchase details** for unclear
Amazon, Apple, and Google charges. A local Codex Luna worker reads the selected
merchant's purchase history. It checks captured receipt evidence, the bank
amount, date, currency, and card suffix before applying a clear match.
Uncertain matches wait for review; each item's category can be changed there.
Mixed purchases allocate the original charge across budgets without adding a
second expense. **Undo split** restores the previous classification. CSV exports
emit the accepted item amounts in place of the parent expense, preserving the
same total.

Automatic lookup is off until enabled in **Settings → Purchase details
assistant**. The default cap is ten attempts a day, including retries. You can
turn off automatic application to review every result. Demo mode never opens
merchant accounts or starts Codex lookups.

The worker uses the installed Codex CLI signed in through your ChatGPT account,
with `gpt-5.6-luna`; it does not fall back to an API key. Install the Node and
Chromium dependencies and authenticate the CLI as described above. For a
systemd installation, add these settings to the existing Ledger environment:

```text
LEDGER_RECEIPT_BRIDGE=/opt/ledger/scripts/receipt-browser.mjs
LEDGER_RECEIPT_WORK_DIR=/var/lib/ledger/receipt-workspaces
LEDGER_RECEIPT_HEADLESS=1
PLAYWRIGHT_BROWSERS_PATH=/var/lib/ledger/.cache/ms-playwright
```

The Docker compose file includes the corresponding `/app` paths. Merchant
sessions live in separate provider/account browser profiles inside the private
data directory. An ordinary login in your phone, Mac, or Ledger preview browser
does not sign in these profiles.

When a lookup needs login or MFA, open its details and use its **Lookup ID**
with the handoff command. Run this in a private graphical session on the same
worker machine, as the owner of the Ledger data, with the same environment and
data paths. Replace `RECEIPT_JOB_ID` with the ID shown in Ledger:

```bash
python3 /opt/ledger/backend/receipt_worker.py handoff RECEIPT_JOB_ID
```

Sign in yourself in the opened browser, close it, then choose **Continue
lookup** in Ledger. A headless SSH session or the supplied Docker compose file
alone cannot display this browser: a private graphical worker session must be
configured first. The application leaves the job waiting until that step is
possible. It does not offer a remote browser session or transfer your existing
cookies automatically.

Order history is read only. The lookup worker has no click, fill, purchase,
refund, or cancellation tools; it pauses at login, CAPTCHA, and account-choice
screens. Grouped charges, gift cards, partial shipments, tax adjustments, or
receipts whose line amounts do not reconcile can remain unresolved. Live
merchant retrieval still needs validation after the dedicated profiles are
set up; development tests use synthetic evidence and do not sign in anywhere.

## Service checks and logs

```bash
systemctl is-active ledger.service
curl -fsS http://127.0.0.1:8907/api/health
# /api/sync/status is owner-authenticated; use a cookie jar created by your
# authenticated local browser session or login flow, for example:
curl -fsS -b /path/to/ledger.cookies http://127.0.0.1:8907/api/sync/status
journalctl -u ledger.service -e
```

The service units use a private system user, restrictive file permissions,
localhost binding, and systemd write/network restrictions. No installation
step starts a browser, links a bank, or performs a real cancellation.

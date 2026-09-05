#!/usr/bin/env bash
set -Eeuo pipefail

# Install or update Ledger on Ubuntu 24 without installing a global Python
# package and without changing unrelated systemd units.  This script is
# intentionally explicit: --mode dry-run performs no writes or service calls.

MODE="install"
APP_DIR="/opt/ledger"
DATA_DIR="/var/lib/ledger"
PORT="8907"
TAILSCALE_SERVE="0"
NO_START="0"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'EOF'
Usage: sudo ./scripts/install-ubuntu.sh [options]

  --mode install|update|dry-run  Operation (default: install)
  --app-dir PATH                 Application path (default: /opt/ledger)
  --data-dir PATH                Persistent data path (default: /var/lib/ledger)
  --port PORT                    Local HTTP port (default: 8907)
  --tailscale-serve              Explicitly configure Tailscale Serve after install
  --no-start                     Install files but do not enable/start ledger.service
  --source-dir PATH              Ledger source tree (for package/update workflows)
  -h, --help                     Show this help
EOF
}

while (($#)); do
  case "$1" in
    --mode) MODE="${2:?--mode needs install, update, or dry-run}"; shift 2 ;;
    --app-dir) APP_DIR="${2:?--app-dir needs a path}"; shift 2 ;;
    --data-dir) DATA_DIR="${2:?--data-dir needs a path}"; shift 2 ;;
    --port) PORT="${2:?--port needs a number}"; shift 2 ;;
    --tailscale-serve) TAILSCALE_SERVE="1"; shift ;;
    --no-start) NO_START="1"; shift ;;
    --source-dir) SOURCE_DIR="${2:?--source-dir needs a path}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$MODE" in install|update|dry-run) ;; *) echo "Invalid --mode: $MODE" >&2; exit 2 ;; esac
if ! [[ "$PORT" =~ ^[0-9]+$ ]] || (( 10#$PORT < 1 || 10#$PORT > 65535 )); then
  echo "--port must be an integer from 1 through 65535" >&2
  exit 2
fi

# Canonicalize all paths before the dry-run too. This prevents a typo or a
# source/app overlap from turning a copy or ownership operation into a broad
# filesystem mutation. The helper works on both Ubuntu coreutils and macOS
# (where realpath has different flags), which keeps dry-run review portable.
canonical_path() {
  local path="${1%/}" suffix="" parent
  [[ -n "$path" ]] || path="/"
  while [[ ! -e "$path" ]]; do
    parent="$(dirname -- "$path")"
    suffix="/$(basename -- "$path")$suffix"
    [[ "$parent" != "$path" ]] || break
    path="$parent"
  done
  [[ -d "$path" ]] || return 1
  path="$(cd -- "$path" && pwd -P)" || return 1
  printf '%s%s\n' "$path" "$suffix"
}
SOURCE_DIR="$(cd -- "$SOURCE_DIR" 2>/dev/null && pwd -P)" || { echo "source directory does not exist" >&2; exit 2; }
APP_DIR="$(canonical_path "$APP_DIR")" || { echo "invalid app directory" >&2; exit 2; }
DATA_DIR="$(canonical_path "$DATA_DIR")" || { echo "invalid data directory" >&2; exit 2; }
[[ "$APP_DIR" != / && "$DATA_DIR" != / ]] || { echo "app/data paths may not be filesystem root" >&2; exit 2; }
[[ "$APP_DIR" != "$DATA_DIR" && "$APP_DIR/" != "$DATA_DIR/"* && "$DATA_DIR/" != "$APP_DIR/"* ]] || {
  echo "app and data paths must not overlap" >&2
  exit 2
}
[[ "$SOURCE_DIR" != "$APP_DIR" ]] || { echo "source and app paths must differ" >&2; exit 2; }
[[ "$APP_DIR/" != "$SOURCE_DIR/"* ]] || { echo "app path may not be inside source tree" >&2; exit 2; }
[[ "$DATA_DIR" != "$SOURCE_DIR" && "$DATA_DIR/" != "$SOURCE_DIR/"* && "$SOURCE_DIR/" != "$DATA_DIR/"* ]] || {
  echo "data path may not overlap source tree" >&2
  exit 2
}

UNIT_DIR="/etc/systemd/system"
ENV_DIR="/etc/ledger"
SERVICE_USER="ledger"

plan() {
  echo "Ledger $MODE plan"
  echo "  source: $SOURCE_DIR"
  echo "  app:    $APP_DIR"
  echo "  data:   $DATA_DIR (preserved across updates)"
  echo "  port:   $PORT (127.0.0.1 only)"
  echo "  start:  $([[ "$NO_START" == 1 ]] && echo no || echo yes)"
  echo "  Tailscale Serve: $([[ "$TAILSCALE_SERVE" == 1 ]] && echo requested || echo unchanged)"
}

if [[ "$MODE" == dry-run ]]; then
  plan
  exit 0
fi

if [[ "$(id -u)" != 0 ]]; then
  echo "Install/update requires root; use sudo for this script." >&2
  exit 1
fi
[[ -d "$SOURCE_DIR/backend" && -d "$SOURCE_DIR/web" ]] || { echo "source tree must contain backend/ and web/" >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 is required (no global package install is attempted)" >&2; exit 1; }
command -v systemctl >/dev/null || { echo "systemd/systemctl is required" >&2; exit 1; }

plan

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --home-dir "$DATA_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
fi
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0700 "$DATA_DIR"
install -d -o root -g root -m 0755 "$APP_DIR" "$ENV_DIR" "$UNIT_DIR"

# Copy application code only. The data directory is intentionally outside the
# app tree and is never removed during an update. Copy Python source files
# explicitly so a developer checkout's backend/data/ or private config files
# can never be copied into the installation.
install -d -o root -g root -m 0755 "$APP_DIR/backend" "$APP_DIR/web" "$APP_DIR/docs" "$APP_DIR/scripts"
cp "$SOURCE_DIR/backend/"*.py "$APP_DIR/backend/"
cp -R "$SOURCE_DIR/web/." "$APP_DIR/web/"
cp -R "$SOURCE_DIR/docs/." "$APP_DIR/docs/"
cp -R "$SOURCE_DIR/scripts/." "$APP_DIR/scripts/"
for f in requirements.txt package.json README.md; do
  [[ -f "$SOURCE_DIR/$f" ]] && cp "$SOURCE_DIR/$f" "$APP_DIR/$f"
done
chmod 0755 "$APP_DIR/scripts"/*.sh 2>/dev/null || true

if [[ ! -e "$ENV_DIR/ledger.env" ]]; then
  install -m 0640 -o root -g "$SERVICE_USER" /dev/null "$ENV_DIR/ledger.env"
else
  chown root:"$SERVICE_USER" "$ENV_DIR/ledger.env"
  chmod 0640 "$ENV_DIR/ledger.env"
fi
sed -i "s|^LEDGER_DATA_DIR=.*|LEDGER_DATA_DIR=$DATA_DIR|; s|^LEDGER_PORT=.*|LEDGER_PORT=$PORT|" "$ENV_DIR/ledger.env"
grep -q '^LEDGER_DATA_DIR=' "$ENV_DIR/ledger.env" || echo "LEDGER_DATA_DIR=$DATA_DIR" >> "$ENV_DIR/ledger.env"
grep -q '^LEDGER_PORT=' "$ENV_DIR/ledger.env" || echo "LEDGER_PORT=$PORT" >> "$ENV_DIR/ledger.env"

install -m 0644 "$SOURCE_DIR/scripts/ledger.service" "$UNIT_DIR/ledger.service"
install -m 0644 "$SOURCE_DIR/scripts/backup.service" "$UNIT_DIR/ledger-backup.service"
install -m 0644 "$SOURCE_DIR/scripts/backup.timer" "$UNIT_DIR/ledger-backup.timer"
sed -i "s|^User=.*|User=$SERVICE_USER|; s|^WorkingDirectory=.*|WorkingDirectory=$APP_DIR|; s|^ExecStart=.*|ExecStart=/usr/bin/python3 $APP_DIR/backend/server.py|; s|^ReadWritePaths=.*|ReadWritePaths=$DATA_DIR|" "$UNIT_DIR/ledger.service"
sed -i "s|^WorkingDirectory=.*|WorkingDirectory=$APP_DIR|; s|^ExecStart=.*|ExecStart=/usr/bin/python3 $APP_DIR/scripts/backup.py backup|" "$UNIT_DIR/ledger-backup.service"
sed -i "s|^User=.*|User=$SERVICE_USER|" "$UNIT_DIR/ledger-backup.service"
sed -i "s|^ReadWritePaths=.*|ReadWritePaths=$DATA_DIR -/mnt/ledger-backups|" "$UNIT_DIR/ledger-backup.service"
sed -i "s|^Environment=HOME=.*|Environment=HOME=$DATA_DIR|; s|^Environment=CODEX_HOME=.*|Environment=CODEX_HOME=$DATA_DIR/.codex|; s|^Environment=LEDGER_BROWSER_PROFILE=.*|Environment=LEDGER_BROWSER_PROFILE=$DATA_DIR/browser-profile|" "$UNIT_DIR/ledger.service"

systemctl daemon-reload
if [[ "$NO_START" != 1 ]]; then
  systemctl enable ledger.service
  if [[ "$MODE" == update ]] && systemctl is-active --quiet ledger.service; then
    systemctl restart ledger.service
  else
    systemctl start ledger.service
  fi
fi

if [[ "$TAILSCALE_SERVE" == 1 ]]; then
  if [[ "$NO_START" == 1 ]]; then
    echo "Tailscale Serve skipped because --no-start was requested; run it after starting Ledger."
  else
    command -v tailscale >/dev/null || { echo "--tailscale-serve requested but tailscale is not installed" >&2; exit 1; }
    tailscale serve --bg "http://127.0.0.1:$PORT"
  fi
fi

echo "Ledger installed at $APP_DIR; persistent data is in $DATA_DIR."
echo "Complete first-owner setup over localhost, then use Tailscale Serve for private access."

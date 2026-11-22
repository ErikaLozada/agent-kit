#!/usr/bin/env bash
# Portable installer for the hardened agent-briefs server & CLI (Linux systemd / macOS launchd).
# Usage: bash setup-briefs-server.sh [--host <dns-name>] [--https-port 8444] [--local-port 8766]
set -euo pipefail

SCRIPT_DIR="$(cd -P "$(dirname "$0")" && pwd)"
LOCAL_PORT="8766"
HTTPS_PORT="8444"
TS_HOST=""

while [ $# -gt 0 ]; do
  case "$1" in
    --host) TS_HOST="$2"; shift 2 ;;
    --https-port) HTTPS_PORT="$2"; shift 2 ;;
    --local-port) LOCAL_PORT="$2"; shift 2 ;;
    -h|--help)
      echo "usage: $0 [--host <tailscale-dns-name>] [--https-port 8444] [--local-port 8766]"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [ "$(uname -s)" = "Linux" ] && [ -x /usr/bin/python3 ]; then
  PYTHON_BIN="/usr/bin/python3"
else
  PYTHON_BIN="$(command -v python3 || true)"
fi
[ -n "$PYTHON_BIN" ] || { echo "Error: python3 is required" >&2; exit 1; }

if [ -z "$TS_HOST" ] && command -v tailscale >/dev/null 2>&1; then
  TS_HOST="$("$PYTHON_BIN" -c '
import json, subprocess
try:
    out = subprocess.check_output(["tailscale", "status", "--json"], text=True, timeout=3)
    dns = str(json.loads(out).get("Self", {}).get("DNSName", "")).strip().rstrip(".")
    print(dns)
except Exception:
    pass
' 2>/dev/null || true)"
fi

BRIEFS_DIR="$HOME/agent-briefs"
BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/agent-briefs"
CONFIG_FILE="$CONFIG_DIR/config"

mkdir -p "$BRIEFS_DIR/archive" "$BIN_DIR" "$CONFIG_DIR"
chmod 700 "$BRIEFS_DIR" "$BRIEFS_DIR/archive" "$CONFIG_DIR"

chmod +x "$SCRIPT_DIR/agent-briefs-server" "$SCRIPT_DIR/publish-brief"
ln -sfn "$SCRIPT_DIR/agent-briefs-server" "$BIN_DIR/agent-briefs-server"
ln -sfn "$SCRIPT_DIR/publish-brief" "$BIN_DIR/publish-brief"

if [ -n "$TS_HOST" ]; then
  BASE_URL="https://${TS_HOST}:${HTTPS_PORT}"
else
  BASE_URL="http://127.0.0.1:${LOCAL_PORT}"
fi

cat > "$CONFIG_FILE" <<EOF
# Local machine config for agent-briefs (never commit to git)
BASE_URL=${BASE_URL}
HTTPS_PORT=${HTTPS_PORT}
LOCAL_PORT=${LOCAL_PORT}
EOF
chmod 600 "$CONFIG_FILE"

echo "Linked binaries:"
echo "  $BIN_DIR/agent-briefs-server -> $SCRIPT_DIR/agent-briefs-server"
echo "  $BIN_DIR/publish-brief       -> $SCRIPT_DIR/publish-brief"
echo "Wrote local config: $CONFIG_FILE (BASE_URL=$BASE_URL)"

OS="$(uname -s)"
if [ "$OS" = "Linux" ]; then
  UNIT_DIR="$HOME/.config/systemd/user"
  UNIT_FILE="$UNIT_DIR/agent-briefs.service"
  mkdir -p "$UNIT_DIR"
  cat > "$UNIT_FILE" <<EOF
[Unit]
Description=Harness-agnostic Agent Briefs HTML server

[Service]
ExecStart=${PYTHON_BIN} -I %h/.local/bin/agent-briefs-server --host 127.0.0.1 --port ${LOCAL_PORT}
Restart=on-failure
RestartSec=3
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=%h/agent-briefs
MemoryMax=128M

[Install]
WantedBy=default.target
EOF
  if command -v systemctl >/dev/null 2>&1; then
    systemctl --user daemon-reload
    systemctl --user enable --now agent-briefs.service
    echo "Started systemd user service: agent-briefs.service"
  else
    echo "Wrote $UNIT_FILE (systemctl not found; start manually)."
  fi
elif [ "$OS" = "Darwin" ]; then
  AGENT_DIR="$HOME/Library/LaunchAgents"
  PLIST="$AGENT_DIR/local.agent-briefs.plist"
  LOG_DIR="$HOME/Library/Logs"
  mkdir -p "$AGENT_DIR" "$LOG_DIR"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>local.agent-briefs</string>
  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON_BIN}</string>
    <string>-I</string>
    <string>${BIN_DIR}/agent-briefs-server</string>
    <string>--host</string>
    <string>127.0.0.1</string>
    <string>--port</string>
    <string>${LOCAL_PORT}</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/agent-briefs.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/agent-briefs.err.log</string>
</dict>
</plist>
EOF
  UID_NUM="$(id -u)"
  launchctl bootout "gui/${UID_NUM}" "$PLIST" >/dev/null 2>&1 || true
  if launchctl bootstrap "gui/${UID_NUM}" "$PLIST" >/dev/null 2>&1; then
    echo "Started launchd LaunchAgent: local.agent-briefs"
  else
    launchctl unload "$PLIST" >/dev/null 2>&1 || true
    launchctl load "$PLIST"
    echo "Loaded launchd LaunchAgent: local.agent-briefs"
  fi
else
  echo "Unsupported OS for automatic service setup ($OS). Run agent-briefs-server manually."
fi

echo
echo "Next steps (run manually once per machine for private Tailscale HTTPS):"
if [ "$OS" = "Linux" ]; then
  echo "  sudo tailscale serve --bg --https=${HTTPS_PORT} http://127.0.0.1:${LOCAL_PORT}"
  echo "  sudo tailscale set --operator=   # recommended: prevent agents from reconfiguring Tailscale"
else
  echo "  tailscale serve --bg --https=${HTTPS_PORT} http://127.0.0.1:${LOCAL_PORT}"
fi
echo "Verify your Tailscale ACL allows your client devices -> this machine on port ${HTTPS_PORT} and disables Funnel."
echo "Make sure ~/.local/bin is on your PATH."

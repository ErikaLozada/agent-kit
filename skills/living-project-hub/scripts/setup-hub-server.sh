#!/usr/bin/env bash
# Portable installer for the unified multi-project Living Project Hub server (Linux systemd / macOS launchd).
# Usage: bash setup-hub-server.sh [--host <tailscale-dns-name>] [--https-port 8445] [--local-port 8765]
set -euo pipefail

SCRIPT_DIR="$(cd -P "$(dirname "$0")" && pwd)"
LOCAL_PORT="8765"
HTTPS_PORT="8445"
TS_HOST=""

while [ $# -gt 0 ]; do
  case "$1" in
    --host) TS_HOST="$2"; shift 2 ;;
    --https-port) HTTPS_PORT="$2"; shift 2 ;;
    --local-port) LOCAL_PORT="$2"; shift 2 ;;
    -h|--help)
      echo "usage: $0 [--host <tailscale-dns-name>] [--https-port 8445] [--local-port 8765]"
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

BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/agent-hub"
CONFIG_FILE="$CONFIG_DIR/config"
REGISTRY_FILE="$CONFIG_DIR/projects.json"

mkdir -p "$BIN_DIR" "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"
[ -f "$REGISTRY_FILE" ] || printf '{"projects": {}}\n' > "$REGISTRY_FILE"
chmod 600 "$REGISTRY_FILE"

chmod +x "$SCRIPT_DIR/hub_server.py" "$SCRIPT_DIR/build_hub.py"
ln -sfn "$SCRIPT_DIR/hub_server.py" "$BIN_DIR/agent-hub-server"
ln -sfn "$SCRIPT_DIR/build_hub.py" "$BIN_DIR/build-project-hub"

if [ -n "$TS_HOST" ]; then
  BASE_URL="https://${TS_HOST}:${HTTPS_PORT}"
else
  BASE_URL="http://127.0.0.1:${LOCAL_PORT}"
fi

cat > "$CONFIG_FILE" <<EOF
# Local machine config for agent-hub (never commit to git)
BASE_URL=${BASE_URL}
HTTPS_PORT=${HTTPS_PORT}
LOCAL_PORT=${LOCAL_PORT}
EOF
chmod 600 "$CONFIG_FILE"

echo "Linked binaries:"
echo "  $BIN_DIR/agent-hub-server  -> $SCRIPT_DIR/hub_server.py"
echo "  $BIN_DIR/build-project-hub -> $SCRIPT_DIR/build_hub.py"
echo "Wrote local config: $CONFIG_FILE (BASE_URL=$BASE_URL)"

OS="$(uname -s)"
if [ "$OS" = "Linux" ]; then
  UNIT_DIR="$HOME/.config/systemd/user"
  UNIT_FILE="$UNIT_DIR/agent-hub.service"
  mkdir -p "$UNIT_DIR"
  cat > "$UNIT_FILE" <<EOF
[Unit]
Description=Unified multi-project Living Project Hub server

[Service]
ExecStart=${PYTHON_BIN} -I %h/.local/bin/agent-hub-server --multi --host 127.0.0.1 --port ${LOCAL_PORT}
Restart=on-failure
RestartSec=3
NoNewPrivileges=yes
PrivateTmp=yes
MemoryMax=128M

[Install]
WantedBy=default.target
EOF
  if command -v systemctl >/dev/null 2>&1; then
    systemctl --user daemon-reload
    systemctl --user enable --now agent-hub.service
    systemctl --user restart agent-hub.service
    echo "Started systemd user service: agent-hub.service"
  else
    echo "Wrote $UNIT_FILE (systemctl not found; start manually)."
  fi
elif [ "$OS" = "Darwin" ]; then
  AGENT_DIR="$HOME/Library/LaunchAgents"
  PLIST="$AGENT_DIR/local.agent-hub.plist"
  LOG_DIR="$HOME/Library/Logs"
  mkdir -p "$AGENT_DIR" "$LOG_DIR"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>local.agent-hub</string>
  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON_BIN}</string>
    <string>-I</string>
    <string>${BIN_DIR}/agent-hub-server</string>
    <string>--multi</string>
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
  <string>${LOG_DIR}/agent-hub.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/agent-hub.err.log</string>
</dict>
</plist>
EOF
  UID_NUM="$(id -u)"
  launchctl bootout "gui/${UID_NUM}" "$PLIST" >/dev/null 2>&1 || true
  if launchctl bootstrap "gui/${UID_NUM}" "$PLIST" >/dev/null 2>&1; then
    echo "Started launchd LaunchAgent: local.agent-hub"
  else
    launchctl unload "$PLIST" >/dev/null 2>&1 || true
    launchctl load "$PLIST"
    echo "Loaded launchd LaunchAgent: local.agent-hub"
  fi
else
  echo "Unsupported OS for automatic service setup ($OS). Run agent-hub-server --multi manually."
fi

echo
echo "Next steps (run manually once per machine for private Tailscale HTTPS on one bookmarkable port):"
if [ "$OS" = "Linux" ]; then
  echo "  sudo tailscale serve --bg --https=${HTTPS_PORT} http://127.0.0.1:${LOCAL_PORT}"
else
  echo "  tailscale serve --bg --https=${HTTPS_PORT} http://127.0.0.1:${LOCAL_PORT}"
fi
echo "Then inside any project repo, register and build its hub:"
echo "  build-project-hub --register"

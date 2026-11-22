#!/bin/bash
# Deploys main: only a committed, tested tree, then logs what went live. Run with `make deploy`.
# Configure DEPLOY_CMD (any stack/OS) or SERVICE (Linux systemd --user shortcut) in agent-kit.conf.
{  # read the whole script before running any of it, so editing this file during a run cannot break that run
set -e
cd "$(dirname "$0")/.."
. ./agent-kit.conf
if [ -z "${DEPLOY_CMD:-}" ] && [ -z "${SERVICE:-}" ]; then
  echo "No DEPLOY_CMD or SERVICE in agent-kit.conf: nothing to deploy."
  exit 1
fi
if [ -z "${DEPLOY_CMD:-}" ]; then
  command -v systemctl >/dev/null || {
    echo "Refusing: deploy restarts $SERVICE with systemctl --user, and this machine has no systemd (set DEPLOY_CMD in agent-kit.conf for non-systemd deploys)."
    exit 1
  }
fi

if [ "$(git branch --show-current)" != main ]; then echo "Refusing: deploy from main, not $(git branch --show-current)."; exit 1; fi
if [ -n "$(git status --porcelain)" ]; then echo "Refusing: uncommitted changes (deploy runs this folder as it is):"; git status --short; exit 1; fi
bash scripts/test.sh --require-tests

if [ -n "${DEPLOY_CMD:-}" ]; then
  ( eval "$DEPLOY_CMD" )
else
  systemctl --user restart "$SERVICE"
fi

if [ -n "${HEALTH_URL:-}" ] && ! curl -sf -o /dev/null --retry 15 --retry-connrefused --retry-delay 1 "$HEALTH_URL"; then
  if [ -n "${SERVICE:-}" ] && [ -z "${DEPLOY_CMD:-}" ]; then
    echo "$SERVICE did not answer at $HEALTH_URL. Logs: journalctl --user -u $SERVICE -n 30"
  else
    echo "Health check failed at $HEALTH_URL."
  fi
  exit 1
fi
line="$(date '+%Y-%m-%d %H:%M') $(git rev-parse --short HEAD) $(git log -1 --format=%s)"
echo "$line" >> .deploys.log
echo "Live: $line"
exit
}

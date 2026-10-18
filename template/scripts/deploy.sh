#!/bin/bash
# Deploys main to the live service: only a committed, tested tree, and logs what went live. Run with `make deploy`.
set -e
cd "$(dirname "$0")/.."
. ./agent-kit.conf
[ -n "$SERVICE" ] || { echo "No SERVICE in agent-kit.conf: nothing to deploy."; exit 1; }

if [ "$(git branch --show-current)" != main ]; then echo "Refusing: deploy from main, not $(git branch --show-current)."; exit 1; fi
if [ -n "$(git status --porcelain)" ]; then echo "Refusing: uncommitted changes (the service runs this folder as it is):"; git status --short; exit 1; fi
bash scripts/test.sh

systemctl --user restart "$SERVICE"
if [ -n "$HEALTH_URL" ] && ! curl -sf -o /dev/null --retry 15 --retry-connrefused --retry-delay 1 "$HEALTH_URL"; then
  echo "$SERVICE did not answer at $HEALTH_URL. Logs: journalctl --user -u $SERVICE -n 30"; exit 1
fi
line="$(date '+%Y-%m-%d %H:%M') $(git rev-parse --short HEAD) $(git log -1 --format=%s)"
echo "$line" >> .deploys.log
echo "Live: $line"

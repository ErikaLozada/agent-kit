#!/bin/bash
# Runs the project's tests: TEST_CMD from agent-kit.conf, or whatever tests/ holds. Run with `make test`.
{  # read the whole script before running any of it, so editing this file during a run cannot break that run
cd "$(dirname "$0")/.."
. ./agent-kit.conf
if [ -n "$TEST_CMD" ]; then eval "$TEST_CMD"; exit; fi

ran=
if compgen -G 'tests/test_*.py' >/dev/null; then python3 -W ignore::ResourceWarning -m unittest discover tests || exit 1; ran=1; fi
if compgen -G 'tests/*.test.*js' >/dev/null; then
  if command -v node >/dev/null; then node --test tests/*.test.*js || exit 1; ran=1; else echo "node not found: JS tests skipped"; fi
fi
[ -n "$ran" ] || echo "no tests yet: add tests/test_*.py or tests/*.test.js, or set TEST_CMD in agent-kit.conf"
exit
}

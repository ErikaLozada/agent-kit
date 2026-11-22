#!/bin/bash
# Runs the project's tests: TEST_CMD from agent-kit.conf, or whatever tests/ holds. Run with `make test`.
{  # read the whole script before running any of it, so editing this file during a run cannot break that run
cd "$(dirname "$0")/.." || exit 1
. ./agent-kit.conf || exit 1
require_tests=0
case "${1:-}" in
  --require-tests) require_tests=1 ;;
  "") ;;
  *) echo "test: FAIL - usage: test.sh [--require-tests]"; exit 1 ;;
esac

# Old project configs inherit the safe defaults when adopting this script.
case "${ALLOW_NO_TESTS:-0}" in
  0|1) ;;
  *) echo "test: FAIL - ALLOW_NO_TESTS must be 0 or 1"; exit 1 ;;
esac
optional_suites=" "
for suite in ${OPTIONAL_TEST_SUITES:-}; do
  case "$suite" in
    python|javascript) optional_suites="$optional_suites$suite " ;;
    *) echo "test: FAIL - unknown optional suite: $suite (use python or javascript)"; exit 1 ;;
  esac
done

if [ -n "$TEST_CMD" ]; then
  # Project-defined commands own discovery and skipped-test policy; we trust their exit status.
  # Run it outside a condition, where bash would ignore a `set -e` the command relies on.
  case $- in *e*) errexit=1 ;; *) errexit=0 ;; esac
  set +e
  ( if [ "$errexit" = 1 ]; then set -e; fi; eval "$TEST_CMD" ); status=$?
  if [ "$status" -eq 0 ]; then echo "test: PASS - configured TEST_CMD returned success"; exit 0; fi
  echo "test: FAIL - configured TEST_CMD exited $status"; exit "$status"
fi
set +e  # suite failures are counted below, not fatal

passed=0; failed=0; skipped=0; empty=0
run_suite() {
  local suite="$1" runtime="$2"
  shift 2
  if ! command -v "$runtime" >/dev/null 2>&1; then
    case "$optional_suites" in
      *" $suite "*) echo "test: SKIP - $suite: $runtime unavailable (explicitly optional)"
                    skipped=$((skipped+1)) ;;
      *) echo "test: FAIL - $suite: required runtime $runtime unavailable"
         failed=$((failed+1)) ;;
    esac
    return
  fi
  local status ran
  "$runtime" "$@"; status=$?
  if [ "$suite" = javascript ]; then
    # scripts/node-count-reporter.mjs wrote the number of cases that ran; only it may report "nothing executed".
    if [ "$status" -ne 0 ]; then status=1
    elif ! { read -r ran < "$node_count"; } 2>/dev/null || ! [ "$ran" -ge 0 ] 2>/dev/null; then
      echo "test: could not read Node's case count (needs Node 20 or later)"; status=1
    elif [ "$ran" -eq 0 ]; then status=2
    fi
    rm -f "$node_count"
  fi
  if [ "$status" -eq 0 ]; then
    echo "test: PASS - $suite suite"; passed=$((passed+1))
  elif [ "$status" -eq 2 ]; then
    echo "test: NOT_EVALUATED - $suite: no test cases executed"; empty=$((empty+1))
  else
    echo "test: FAIL - $suite suite"; failed=$((failed+1))
  fi
}

if compgen -G 'tests/test_*.py' >/dev/null; then
  run_suite python python3 -W ignore::ResourceWarning -c '
import sys, unittest
class Result(unittest.TextTestResult):
    # A case executed unless the whole case was skipped; class-level and subtest skips are not cases.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs); self.executed, self.current, self.current_skipped = 0, None, False
    def startTest(self, test):
        super().startTest(test); self.current, self.current_skipped = test, False
    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        if test is self.current: self.current_skipped = True
    def stopTest(self, test):
        super().stopTest(test)
        if test is self.current and not self.current_skipped: self.executed += 1
        self.current = None
suite = unittest.defaultTestLoader.discover("tests")
result = unittest.TextTestRunner(resultclass=Result).run(suite)
if not result.wasSuccessful():
    sys.exit(1)
sys.exit(0 if result.executed else 2)
'
fi
if compgen -G 'tests/*.test.*js' >/dev/null; then
  node_count="${TMPDIR:-/tmp}/agent-kit-node-count.$$"
  rm -f "$node_count"
  run_suite javascript node --test-reporter=spec --test-reporter-destination=stdout \
    --test-reporter=./scripts/node-count-reporter.mjs --test-reporter-destination="$node_count" --test tests/*.test.*js
fi

if [ "$failed" -gt 0 ]; then
  echo "test: FAIL - suites passed=$passed failed=$failed skipped=$skipped"; exit 1
fi
if [ "$passed" -eq 0 ]; then
  echo "test: NOT_EVALUATED - no suites executed test cases; skipped=$skipped"
  if [ "${ALLOW_NO_TESTS:-0}" = 1 ] && [ "$require_tests" = 0 ]; then
    echo "test: bootstrap policy ALLOW_NO_TESTS=1 permits this unverified result"; exit 0
  fi
  echo "test: add executable tests or TEST_CMD (deploy always requires checks)"; exit 2
fi
if [ "$empty" -gt 0 ]; then
  echo "test: FAIL - a discovered suite executed no test cases"; exit 1
fi
echo "test: PASS - suites passed=$passed failed=0 skipped=$skipped"
exit 0
}

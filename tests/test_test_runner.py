"""Exercise test policies with controlled runtimes, without depending on installed Node."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

TEMPLATE = Path(__file__).resolve().parent.parent / 'template'


class TestRunnerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / 'scripts').mkdir()
        (self.root / 'tests').mkdir()
        (self.root / 'bin').mkdir()
        shutil.copyfile(TEMPLATE / 'scripts/test.sh', self.root / 'scripts/test.sh')
        for tool in ['dirname', 'rm']:
            (self.root / 'bin' / tool).symlink_to(shutil.which(tool))
        shutil.copyfile(TEMPLATE / 'scripts/node-count-reporter.mjs', self.root / 'scripts/node-count-reporter.mjs')
        self.configure()

    def configure(self, extra=''):
        (self.root / 'agent-kit.conf').write_text('TEST_CMD=""\n' + extra)

    def runtime(self, name, status=0, cases=1):
        # A stub node writes its case count where the count reporter would.
        script = self.root / 'bin' / name
        script.write_text('#!/bin/bash\nprintf "%%s\\n" "$*" >> runtime-calls\n'
                          'for a; do case "$a" in --test-reporter-destination=stdout) ;; '
                          '--test-reporter-destination=*) printf "%d\\n" > "${a#*=}" ;; esac; done\nexit %d\n' % (cases, status))
        script.chmod(0o755)

    def real(self, name):
        if not shutil.which(name):
            self.skipTest(name + ' not installed')
        (self.root / 'bin' / name).symlink_to(shutil.which(name))

    def discover(self, suite):
        filename = 'test_sample.py' if suite == 'python' else 'sample.test.js'
        (self.root / 'tests' / filename).write_text('# fixture\n')

    def run_checks(self, *args):
        return subprocess.run(['/bin/bash', 'scripts/test.sh', *args], cwd=self.root,
                              env={**os.environ, 'PATH': str(self.root / 'bin')}, capture_output=True, text=True)

    def test_no_tests_blocked_by_default(self):
        r = self.run_checks()
        self.assertEqual(r.returncode, 2)
        self.assertIn('NOT_EVALUATED', r.stdout)
        self.assertNotIn('test: PASS', r.stdout)

    def test_bootstrap_is_unverified_not_pass(self):
        self.configure('ALLOW_NO_TESTS=1\n')
        r = self.run_checks()
        self.assertEqual(r.returncode, 0)
        self.assertIn('NOT_EVALUATED', r.stdout)
        self.assertNotIn('test: PASS', r.stdout)

    def test_deploy_mode_rejects_bootstrap_without_checks(self):
        self.configure('ALLOW_NO_TESTS=1\n')
        r = self.run_checks('--require-tests')
        self.assertEqual(r.returncode, 2)
        self.assertIn('NOT_EVALUATED', r.stdout)

    def test_missing_required_runtimes_fail_even_in_bootstrap(self):
        self.configure('ALLOW_NO_TESTS=1\n')
        for suite, runtime in [('python', 'python3'), ('javascript', 'node')]:
            with self.subTest(suite=suite):
                self.discover(suite)
                r = self.run_checks()
                self.assertEqual(r.returncode, 1)
                self.assertIn('required runtime %s unavailable' % runtime, r.stdout)

    def test_required_missing_suite_fails_even_when_another_passes(self):
        self.discover('python'); self.discover('javascript'); self.runtime('python3')
        r = self.run_checks()
        self.assertEqual(r.returncode, 1)
        self.assertIn('passed=1 failed=1 skipped=0', r.stdout)

    def test_optional_missing_runtime_is_reported_alongside_passing_suite(self):
        self.configure('OPTIONAL_TEST_SUITES="javascript"\n')
        self.discover('python'); self.discover('javascript'); self.runtime('python3')
        r = self.run_checks()
        self.assertEqual(r.returncode, 0)
        self.assertIn('test: SKIP - javascript', r.stdout)
        self.assertIn('passed=1 failed=0 skipped=1', r.stdout)

    def test_all_optional_skipped_is_not_evaluated(self):
        self.configure('OPTIONAL_TEST_SUITES="javascript"\n')
        self.discover('javascript')
        r = self.run_checks()
        self.assertEqual(r.returncode, 2)
        self.assertIn('NOT_EVALUATED', r.stdout)
        self.assertIn('skipped=1', r.stdout)

    def test_whitespace_separated_optional_names_are_normalized(self):
        self.configure('OPTIONAL_TEST_SUITES="python\tjavascript"\n')
        self.discover('javascript')
        r = self.run_checks()
        self.assertEqual(r.returncode, 2)
        self.assertIn('test: SKIP - javascript', r.stdout)
        self.assertNotIn('required runtime', r.stdout)

    def test_optional_suite_failure_is_not_a_skip(self):
        self.configure('OPTIONAL_TEST_SUITES="javascript"\nALLOW_NO_TESTS=1\n')
        self.discover('javascript'); self.runtime('node', 1)
        r = self.run_checks()
        self.assertEqual(r.returncode, 1)
        self.assertIn('test: FAIL - javascript suite', r.stdout)
        self.assertNotIn('test: SKIP', r.stdout)

    def test_both_suites_run_with_expected_arguments(self):
        self.discover('python'); self.discover('javascript')
        self.runtime('python3'); self.runtime('node')
        r = self.run_checks()
        self.assertEqual(r.returncode, 0)
        self.assertIn('passed=2 failed=0 skipped=0', r.stdout)
        calls = (self.root / 'runtime-calls').read_text()
        self.assertIn('unittest.defaultTestLoader.discover', calls)
        self.assertIn('--test tests/sample.test.js', calls)

    def test_custom_command_owns_result(self):
        self.configure('TEST_CMD="exit 7"\n')
        r = self.run_checks()
        self.assertEqual(r.returncode, 7)
        self.assertIn('test: FAIL - configured TEST_CMD exited 7', r.stdout)
        self.configure('TEST_CMD="true"\n')
        r = self.run_checks()
        self.assertEqual(r.returncode, 0)
        self.assertIn('test: PASS - configured TEST_CMD', r.stdout)

    def test_custom_command_keeps_its_own_errexit(self):
        for conf, code in [('set -e\nTEST_CMD="false; true"\n', 1), ('TEST_CMD="set -e; false; true"\n', 1),
                           ('TEST_CMD="false; true"\n', 0)]:
            with self.subTest(conf=conf):
                self.configure(conf)
                r = self.run_checks('--require-tests')
                self.assertEqual(r.returncode, code, r.stdout)

    def test_javascript_with_no_executed_tests_is_not_a_pass(self):
        self.discover('javascript'); self.runtime('node', cases=0)
        r = self.run_checks()
        self.assertEqual(r.returncode, 2)
        self.assertIn('test: NOT_EVALUATED - javascript', r.stdout)
        self.assertNotIn('test: PASS', r.stdout)

    def test_javascript_failure_never_reads_as_empty(self):
        self.configure('ALLOW_NO_TESTS=1\n')
        self.discover('javascript'); self.runtime('node', 2)
        r = self.run_checks()
        self.assertEqual(r.returncode, 1)
        self.assertIn('test: FAIL - javascript suite', r.stdout)

    def test_real_node_all_skipped_and_mixed(self):
        self.real('node')
        js = "const {test} = require('node:test');\ntest.skip('offline', () => {});\n"
        (self.root / 'tests/sample.test.js').write_text(js)
        for args in [(), ('--require-tests',)]:
            r = self.run_checks(*args)
            self.assertEqual(r.returncode, 2, r.stdout)
            self.assertIn('NOT_EVALUATED - javascript', r.stdout)
        (self.root / 'tests/sample.test.js').write_text(js + "test('runs', () => {});\n")
        r = self.run_checks('--require-tests')
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn('test: PASS - suites passed=1', r.stdout)

    def test_real_node_counts_cases_not_output(self):
        self.real('node')
        skipped = "const {test} = require('node:test');\ntest.skip('offline', () => {});\n"
        for extra, code in [("console.log('pass 1');\n", 2), ("console.error('# pass 1');\n", 2),
                            ("test('later', {todo: true}, () => {});\n", 0),
                            ("const {describe} = require('node:test');\ndescribe('empty', () => {});\n", 2)]:
            with self.subTest(extra=extra):
                (self.root / 'tests/sample.test.js').write_text(skipped + extra)
                r = self.run_checks('--require-tests')
                self.assertEqual(r.returncode, code, r.stdout)

    def test_custom_command_starts_with_a_clean_status(self):
        for cmd in ['exit', 'exit $?']:
            with self.subTest(cmd=cmd):
                self.configure('TEST_CMD=%r\n' % cmd)
                self.assertEqual(self.run_checks().returncode, 0)

    def test_python_lazy_suite_counts_each_executed_case(self):
        self.real('python3')
        (self.root / 'tests/test_sample.py').write_text(
            'import unittest\nclass T(unittest.TestCase):\n    def test_pass(self): self.assertEqual(1, 1)\n'
            '    @unittest.skip("offline")\n    def test_skip(self): pass\n'
            'class Lazy(unittest.TestSuite):\n    def run(self, result, debug=False):\n'
            '        for name in ["test_pass", "test_skip"]: T(name).run(result)\n        return result\n'
            'def load_tests(loader, tests, pattern): return Lazy()\n')
        r = self.run_checks('--require-tests')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_python_partial_skips_still_count_executed_cases(self):
        self.real('python3')
        fixtures = [
            'import unittest\nclass Skipped(unittest.TestCase):\n    @classmethod\n    def setUpClass(cls): raise unittest.SkipTest("x")\n'
            '    def test_a(self): pass\nclass Runs(unittest.TestCase):\n    def test_b(self): self.assertEqual(1, 1)\n',
            'import unittest\nclass T(unittest.TestCase):\n    def test_a(self):\n        self.assertEqual(1, 1)\n'
            '        with self.subTest(n=1): self.skipTest("x")\n',
        ]
        for content in fixtures:
            with self.subTest(content=content):
                (self.root / 'tests/test_sample.py').write_text(content)
                shutil.rmtree(self.root / 'tests/__pycache__', ignore_errors=True)
                r = self.run_checks('--require-tests')
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn('test: PASS - suites passed=1', r.stdout)

    def test_python_empty_or_all_skipped_is_not_a_pass(self):
        (self.root / 'bin/python3').symlink_to(shutil.which('python3'))
        for content in ['', 'import unittest\n@unittest.skip("not available")\nclass T(unittest.TestCase):\n    def test_one(self): pass\n']:
            with self.subTest(content=content):
                (self.root / 'tests/test_sample.py').write_text(content)
                # Avoid bytecode reuse when replacing a temporary fixture.
                shutil.rmtree(self.root / 'tests/__pycache__', ignore_errors=True)
                r = self.run_checks()
                self.assertEqual(r.returncode, 2)
                self.assertIn('NOT_EVALUATED', r.stdout)
                self.assertNotIn('test: PASS', r.stdout)

    def test_empty_python_suite_cannot_hide_behind_a_passing_javascript_suite(self):
        (self.root / 'bin/python3').symlink_to(shutil.which('python3'))
        (self.root / 'tests/test_sample.py').write_text('')
        self.discover('javascript'); self.runtime('node')
        r = self.run_checks()
        self.assertEqual(r.returncode, 1)
        self.assertIn('test: NOT_EVALUATED - python', r.stdout)
        self.assertIn('test: FAIL - a discovered suite', r.stdout)

    def test_invalid_policy_is_rejected(self):
        for policy in ['ALLOW_NO_TESTS=yes\n', 'OPTIONAL_TEST_SUITES="javascrip"\n']:
            self.configure(policy)
            r = self.run_checks()
            self.assertEqual(r.returncode, 1)
            self.assertIn('test: FAIL', r.stdout)


if __name__ == '__main__':
    unittest.main()

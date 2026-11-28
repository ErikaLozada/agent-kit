"""Installs the kit into a throwaway project and drives every command there, as an agent would."""
import os, re, socket, subprocess, tempfile, unittest
from pathlib import Path

KIT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
GIT_ENV = {'GIT_AUTHOR_NAME': 'Test', 'GIT_AUTHOR_EMAIL': 't@t', 'GIT_COMMITTER_NAME': 'Test', 'GIT_COMMITTER_EMAIL': 't@t'}


class InstallTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.proj = os.path.join(tmp.name, 'proj')
        self.out = self.sh('bash', os.path.join(KIT, 'install.sh'), self.proj, 'Proj', cwd=tmp.name)

    def sh(self, *cmd, cwd=None, ok=True, env=None):
        r = subprocess.run(cmd, cwd=cwd or self.proj, capture_output=True, text=True, env={**os.environ, **GIT_ENV, **(env or {})})
        if ok: self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout + r.stderr

    def read(self, rel):
        with open(os.path.join(self.proj, rel)) as f: return f.read()

    def write(self, rel, text):
        os.makedirs(os.path.dirname(os.path.join(self.proj, rel)) or self.proj, exist_ok=True)
        with open(os.path.join(self.proj, rel), 'w') as f: f.write(text)

    def path_without(self, *names):
        """A PATH holding links to every command on the current PATH except names, as on a machine without them."""
        d = tempfile.mkdtemp(); self.addCleanup(subprocess.run, ['rm', '-rf', d])
        for folder in os.environ['PATH'].split(os.pathsep):
            if not os.path.isdir(folder): continue
            for n in os.listdir(folder):
                src, dst = os.path.join(folder, n), os.path.join(d, n)
                if n not in names and not os.path.exists(dst) and os.access(src, os.X_OK): os.symlink(src, dst)
        return d

    def configure(self):
        conf = self.read('agent-kit.conf')
        for k, v in {'LINKS': 'data/*', 'OWN': 'data/live.json', 'PROTECTED': 'labels.json', 'TEST_SERVER': 'serve --port {PORT}'}.items():
            conf = conf.replace('%s=""' % k, '%s="%s"' % (k, v))
        self.write('agent-kit.conf', conf)
        # Lifecycle fixtures intentionally have no application tests. Bootstrap is explicit.
        self.write('agent-kit.conf', self.read('agent-kit.conf').replace('ALLOW_NO_TESTS="${ALLOW_NO_TESTS:-0}"', 'ALLOW_NO_TESTS=1'))
        self.write('.gitignore', self.read('.gitignore') + 'data/\n')
        self.write('data/big.txt', 'x'); self.write('data/live.json', '{}'); self.write('labels.json', '[]')
        self.sh('git', 'add', '-A'); self.sh('git', 'commit', '-qm', 'start', env={'USER_OK': '1'})

    def test_installs_project_files(self):
        self.assertIn('# Proj', self.read('AGENTS.md'))
        self.assertEqual(self.read('CLAUDE.md'), '@AGENTS.md\n')
        self.assertEqual(os.readlink(os.path.join(self.proj, '.claude', 'skills')), '../.agents/skills')
        self.assertIn('ship-feature', os.listdir(os.path.join(self.proj, '.claude', 'skills')))
        self.assertNotIn('session-retro', os.listdir(os.path.join(self.proj, '.claude', 'skills')))
        self.assertFalse(os.path.exists(os.path.join(self.proj, 'scripts', 'watch-codex.py')))
        self.assertEqual(self.sh('git', 'config', 'core.hooksPath').strip(), '.githooks')
        self.assertNotIn('{{', self.read('docs/decisions.md') + self.read('agent-kit.conf'))

    def test_project_name_with_sed_special_characters(self):
        proj = os.path.join(os.path.dirname(self.proj), 'odd')
        self.sh('bash', os.path.join(KIT, 'install.sh'), proj, r'R&D|Ops \1', cwd=os.path.dirname(proj))
        with open(os.path.join(proj, 'AGENTS.md')) as f: self.assertEqual(f.readline(), '# R&D|Ops \\1\n')

    def test_agents_md_is_lean_and_harness_neutral(self):
        text = self.read('AGENTS.md')
        self.assertLessEqual(len(text.encode()), 3000)
        for word in ('herdr', 'claude-', 'gpt-'): self.assertNotIn(word, text)
        for heading in ('## Outside the repo', '## Gates', '## Defaults'): self.assertIn(heading, text)
        root_agents = Path(KIT, 'AGENTS.md').read_text(encoding='utf-8')
        self.assertLessEqual(len(root_agents.encode()), 3000)

    def test_never_overwrites(self):
        self.write('AGENTS.md', 'mine\n')
        out = self.sh('bash', os.path.join(KIT, 'install.sh'), self.proj)
        self.assertEqual(self.read('AGENTS.md'), 'mine\n')
        self.assertIn('kept     AGENTS.md', out)

    def test_install_into_dot_uses_directory_basename(self):
        repo = os.path.join(os.path.dirname(self.proj), 'my-cool-repo')
        os.makedirs(repo)
        self.sh('bash', os.path.join(KIT, 'install.sh'), '.', cwd=repo)
        self.assertIn('# my-cool-repo', open(os.path.join(repo, 'AGENTS.md')).read())
        self.assertIn('PROJECT="my-cool-repo"', open(os.path.join(repo, 'agent-kit.conf')).read())

    def test_preserves_existing_git_hooks(self):
        base = os.path.dirname(self.proj)
        # 1. Existing custom core.hooksPath is not overwritten
        p1 = os.path.join(base, 'with-hookspath')
        os.makedirs(p1)
        self.sh('git', 'init', '-q', '-b', 'main', cwd=p1)
        self.sh('git', 'config', 'core.hooksPath', '.husky', cwd=p1)
        out1 = self.sh('bash', os.path.join(KIT, 'install.sh'), p1, 'P1', cwd=base)
        self.assertEqual(self.sh('git', 'config', 'core.hooksPath', cwd=p1).strip(), '.husky')
        self.assertIn('kept existing git core.hooksPath (.husky)', out1)
        # 2. Existing .git/hooks/pre-commit is not silently bypassed
        p2 = os.path.join(base, 'with-precommit')
        os.makedirs(p2)
        self.sh('git', 'init', '-q', '-b', 'main', cwd=p2)
        hook = os.path.join(p2, '.git', 'hooks', 'pre-commit')
        with open(hook, 'w') as f: f.write('#!/bin/sh\nexit 0\n')
        os.chmod(hook, 0o755)
        out2 = self.sh('bash', os.path.join(KIT, 'install.sh'), p2, 'P2', cwd=base)
        self.assertIn('kept existing .git/hooks/pre-commit', out2)
        self.assertEqual(self.sh('git', 'config', '--local', 'core.hooksPath', cwd=p2, ok=False).strip(), '')

    def test_check_drift_is_read_only(self):
        out = self.sh('bash', os.path.join(KIT, 'install.sh'), '--check', self.proj)
        self.assertIn('ok          Makefile', out)
        self.assertIn('project     AGENTS.md', out)
        self.write('Makefile', '# edited\n')
        os.remove(os.path.join(self.proj, 'scripts', 'status.sh'))
        out2 = self.sh('bash', os.path.join(KIT, 'install.sh'), '--check', self.proj)
        self.assertIn('customized  Makefile', out2)
        self.assertIn('missing     scripts/status.sh', out2)
        self.assertFalse(os.path.exists(os.path.join(self.proj, 'scripts', 'status.sh')))

    def test_overlay_layers_extra_files_and_appends_idempotently(self):
        base = os.path.dirname(self.proj)
        overlays = os.path.join(base, 'overlays')
        ov = os.path.join(overlays, 'demo-pack')
        os.makedirs(ov)
        with open(os.path.join(ov, 'STACK.md'), 'w') as f: f.write('# {{PROJECT}} stack notes ({{DATE}})\n')
        with open(os.path.join(ov, 'AGENTS.append.md'), 'w') as f: f.write('## Stack\n- Read `STACK.md` first.\n')
        with open(os.path.join(ov, '.gitignore.append'), 'w') as f: f.write('.stack-cache/\n')
        proj = os.path.join(base, 'overlaid')
        env = {'AGENT_KIT_OVERLAYS': overlays}
        out = self.sh('bash', os.path.join(KIT, 'install.sh'), proj, 'Overlaid', '--overlay', 'demo-pack', cwd=base, env=env)
        self.assertIn('added    STACK.md', out)
        self.assertIn('# Overlaid stack notes', open(os.path.join(proj, 'STACK.md')).read())
        agents = open(os.path.join(proj, 'AGENTS.md')).read()
        self.assertIn('<!-- overlay: demo-pack -->', agents)
        self.assertIn('Read `STACK.md` first.', agents)
        self.assertIn('.stack-cache/', open(os.path.join(proj, '.gitignore')).read())
        # Rerun is idempotent
        self.sh('bash', os.path.join(KIT, 'install.sh'), proj, 'Overlaid', '--overlay', 'demo-pack', cwd=base, env=env)
        self.assertEqual(open(os.path.join(proj, 'AGENTS.md')).read().count('<!-- overlay: demo-pack -->'), 1)
        self.assertEqual(open(os.path.join(proj, '.gitignore')).read().count('.stack-cache/'), 1)
        # Missing overlay fails cleanly
        bad = self.sh('bash', os.path.join(KIT, 'install.sh'), proj, '--overlay', 'nope', cwd=base, env=env, ok=False)
        self.assertIn('overlay not found', bad)

    def test_task_status_finish(self):
        self.configure()
        self.assertIn('test port 8001', self.sh('make', 'task', 'NAME=t1', 'OWNER=Codex'))
        wt = self.proj + '-t1'
        self.assertTrue(os.path.islink(os.path.join(wt, 'data', 'big.txt')))
        self.assertFalse(os.path.exists(os.path.join(wt, 'data', 'live.json')))
        task = open(os.path.join(wt, 'TASK.md')).read()
        self.assertIn('Port: 8001', task); self.assertIn('serve --port 8001', task)
        self.assertIn('Codex · working', self.sh('make', 'status'))
        self.assertIn('test port 8002', self.sh('make', 'task', 'NAME=t2'))
        self.sh('make', 'finish', 'NAME=t1'); self.sh('make', 'finish', 'NAME=t2')
        self.assertFalse(os.path.exists(wt))
        self.assertNotIn('t1', self.sh('git', 'branch'))

    def test_finish_refuses_unmerged_branch(self):
        self.configure(); self.sh('make', 'task', 'NAME=t1')
        wt = self.proj + '-t1'
        with open(os.path.join(wt, 'new.txt'), 'w') as f: f.write('x')
        self.sh('git', 'add', 'new.txt', cwd=wt); self.sh('git', 'commit', '-qm', 'work', cwd=wt)
        self.assertIn('not merged', self.sh('make', 'finish', 'NAME=t1', ok=False))
        self.assertTrue(os.path.exists(wt))

    def test_hook_guards_protected_files_and_runs_tests(self):
        self.configure()
        self.write('labels.json', '[1]'); self.sh('git', 'add', 'labels.json')
        self.assertIn('PROTECTED', self.sh('git', 'commit', '-qm', 'relabel', ok=False))
        self.sh('git', 'commit', '-qm', 'relabel', env={'USER_OK': '1'})
        self.write('tests/test_x.py', 'import unittest\nclass T(unittest.TestCase):\n    def test(self): self.fail("broken")\n')
        self.sh('git', 'add', 'tests'); self.assertIn('tests failed', self.sh('git', 'commit', '-qm', 'bad', ok=False))

    def test_hook_enforces_append_only_decisions_and_secret_scan(self):
        self.configure()
        # Appending to docs/decisions.md is allowed
        orig = self.read('docs/decisions.md')
        self.write('docs/decisions.md', orig + '- **2026-11-22** Added new decision.\n')
        self.sh('git', 'add', 'docs/decisions.md')
        self.sh('git', 'commit', '-qm', 'append decision')
        # Rewriting/deleting existing lines in docs/decisions.md is blocked unless USER_OK=1
        self.write('docs/decisions.md', '# Decisions\n\n- **2026-11-22** Rewritten history.\n')
        self.sh('git', 'add', 'docs/decisions.md')
        out = self.sh('git', 'commit', '-qm', 'rewrite decision', ok=False)
        self.assertIn('append-only', out)
        self.sh('git', 'commit', '-qm', 'user approved rewrite', env={'USER_OK': '1'})
        # Staged secret pattern blocks commit and NEVER prints the secret value itself
        fake_secret = 'ghp_' + 'A1b2C3d4E5f6G7h8I9j0K1l2M3n4'
        self.write('leak.txt', f'token={fake_secret}\n')
        self.sh('git', 'add', 'leak.txt')
        out_sec = self.sh('git', 'commit', '-qm', 'accidental secret', ok=False)
        self.assertIn('potential secret pattern in leak.txt', out_sec)
        self.assertNotIn(fake_secret, out_sec)
        # Hardened .gitignore ignores scratch and key files
        gi = self.read('.gitignore')
        for entry in ('.scratch/', '.claude/settings.local.json', '*.pem', '*.key'):
            self.assertIn(entry, gi)

    def test_hook_blocks_no_tests_unless_bootstrap_is_explicit(self):
        self.sh('git', 'add', '-A')
        out = self.sh('git', 'commit', '-qm', 'empty checks', ok=False)
        self.assertIn('NOT_EVALUATED', out)
        self.assertIn('no tests ran', out)
        self.assertNotIn('tests failed', out)
        self.write('agent-kit.conf', self.read('agent-kit.conf').replace('ALLOW_NO_TESTS="${ALLOW_NO_TESTS:-0}"', 'ALLOW_NO_TESTS=1'))
        self.sh('git', 'add', 'agent-kit.conf')
        out = self.sh('git', 'commit', '-qm', 'explicit bootstrap')
        self.assertIn('NOT_EVALUATED', out)
        self.assertIn('bootstrap policy', out)
        self.assertNotIn('test: PASS', out)

    def test_first_commit_with_env_bootstrap(self):
        self.sh('git', 'add', '-A')
        out = self.sh('git', 'commit', '-qm', 'start', env={'ALLOW_NO_TESTS': '1'})
        self.assertIn('NOT_EVALUATED', out)
        self.assertNotIn('test: PASS', out)
        self.assertIn('ALLOW_NO_TESTS=1 git commit', self.out)

    def test_installs_only_tracked_template_files(self):
        cache = os.path.join(KIT, 'template', 'scripts', '__pycache__')
        os.makedirs(cache, exist_ok=True)
        stray = os.path.join(cache, 'agent_kit_test_stray.cpython.pyc')
        open(stray, 'w').close(); self.addCleanup(os.remove, stray)
        proj = self.proj + '-fresh'
        self.sh('bash', os.path.join(KIT, 'install.sh'), proj, 'Fresh', cwd=os.path.dirname(self.proj))
        got = {os.path.relpath(os.path.join(d, f), proj) for d, _, fs in os.walk(proj) for f in fs}
        got = {p for p in got if not p.startswith('.git/') and not p.startswith('.claude/')}
        tracked = {p for p in subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard', 'template'], cwd=KIT, capture_output=True, text=True).stdout.split() if os.path.isfile(os.path.join(KIT, p))}
        self.assertEqual(got, {p[len('template/'):] for p in tracked})
        self.assertIn('__pycache__/', self.read('.gitignore'))

    def test_hook_reports_optional_skips_but_blocks_missing_required_runtime(self):
        self.configure()
        self.write('tests/test_ok.py', 'import unittest\nclass T(unittest.TestCase):\n    def test_ok(self): pass\n')
        self.write('tests/check.test.js', 'throw new Error("not executed without Node");\n')
        self.sh('git', 'add', '-A')
        test_path = self.path_without('node')
        out = self.sh('git', 'commit', '-qm', 'missing runtime', ok=False, env={'PATH': test_path})
        self.assertIn('required runtime node unavailable', out)
        self.assertIn('commit refused', out)
        self.write('agent-kit.conf', self.read('agent-kit.conf').replace('OPTIONAL_TEST_SUITES=""', 'OPTIONAL_TEST_SUITES="javascript"'))
        self.sh('git', 'add', 'agent-kit.conf')
        out = self.sh('git', 'commit', '-qm', 'explicit optional suite', env={'PATH': test_path})
        self.assertIn('test: SKIP - javascript', out)
        self.assertIn('passed=1 failed=0 skipped=1', out)

    def test_deploy_requires_checks_and_supports_deploy_cmd(self):
        self.configure()
        self.write('agent-kit.conf', self.read('agent-kit.conf').replace('SERVICE=""', 'SERVICE="app"'))
        self.sh('git', 'add', 'agent-kit.conf'); self.sh('git', 'commit', '-qm', 'service')
        with tempfile.TemporaryDirectory() as tools:
            marker = os.path.join(tools, 'restarted')
            command = os.path.join(tools, 'systemctl')
            with open(command, 'w') as f:
                f.write('#!/bin/bash\ntouch "%s"\n' % marker)
            os.chmod(command, 0o755)
            r = subprocess.run(['make', 'deploy'], cwd=self.proj, capture_output=True, text=True,
                               env={**os.environ, 'PATH': tools + os.pathsep + os.environ['PATH']})
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('NOT_EVALUATED', r.stdout)
            self.assertFalse(os.path.exists(marker), 'must not restart before checks pass')

        # Stack-agnostic DEPLOY_CMD works even without systemd when tests pass
        deployed = os.path.join(os.path.dirname(self.proj), 'deployed.flag')
        self.write('tests/test_ok.py', 'import unittest\nclass T(unittest.TestCase):\n    def test_ok(self): pass\n')
        self.write('agent-kit.conf', self.read('agent-kit.conf')
                   .replace('SERVICE="app"', 'SERVICE=""')
                   .replace('DEPLOY_CMD=""', f'DEPLOY_CMD="touch {deployed}"'))
        self.sh('git', 'add', '-A'); self.sh('git', 'commit', '-qm', 'add deploy cmd and test')
        no_systemd = self.path_without('systemctl')
        out = self.sh('make', 'deploy', env={'PATH': no_systemd})
        self.assertIn('Live:', out)
        self.assertTrue(os.path.exists(deployed))
        self.assertIn('last deploy:', self.sh('make', 'status', env={'PATH': no_systemd}))

    def test_review_commands(self):
        self.configure()
        herdr = {'DRY': '1', 'HERDR_ENV': '1'}
        out = self.sh('make', 'review', 'KIND=pi', env=herdr)
        self.assertIn('herdr agent start proj-review-pi --kind pi', out)  # repo-scoped tab name
        self.assertIn('--tools read,bash,write', out)
        self.assertIn('no Computer Use, screen, app or GUI actions', out)
        self.assertRegex(out, r'\.reviews/\d{4}-\d{2}-\d{2}-\d{6}-pi\.md')
        self.assertIn('git diff 4b825dc', out)         # clean tree, first commit: all of it
        self.write('a.txt', 'a'); self.sh('git', 'add', 'a.txt'); self.sh('git', 'commit', '-qm', 'a')
        self.assertIn('git diff HEAD~1', self.sh('make', 'review', 'KIND=pi', env=herdr))
        self.write('new.txt', 'x')
        self.assertIn('git diff HEAD', self.sh('make', 'review', 'KIND=codex', env=herdr))
        self.assertIn('herdr agent start proj-review-codex --kind codex', self.sh('make', 'review', 'KIND=codex', env=herdr))

        # Headless runs enforce read-only & capture output cleanly
        headless = {'DRY': '1', 'HERDR_ENV': ''}
        self.assertIn('codex exec -s read-only', self.sh('make', 'review', 'KIND=codex', env=headless))
        out_claude = self.sh('make', 'review', 'KIND=claude', 'MODEL=m1', env=headless)
        self.assertIn('claude -p --permission-mode plan --model m1', out_claude)
        self.assertNotIn('herdr', out_claude)
        self.assertIn('pi -p --tools read,bash --thinking high', self.sh('make', 'review', 'KIND=pi', env=headless))
        self.assertIn('gemini -p ', self.sh('make', 'review', 'KIND=gemini', env=headless))

        # Custom REVIEW_CMD works for any future CLI
        out_custom = self.sh('make', 'review', 'REVIEW_CMD=my-reviewer --base {BASE} --out {OUT}', env=headless)
        self.assertIn('my-reviewer --base HEAD --out .reviews/', out_custom)

        self.assertIn('usage: make review', self.sh('make', 'review', 'KIND=unknown', ok=False))
        self.assertIn('not a commit', self.sh('make', 'review', 'KIND=pi', 'BASE=nope', ok=False, env=herdr))
        self.assertIn('.reviews/', self.read('.gitignore'))

    def test_worker_commands_tiers_and_lead(self):
        self.configure()
        # Template start-worker.sh must not hardcode vendor model IDs
        worker_script = self.read('scripts/start-worker.sh')
        for hardcoded in ('gpt-6', 'claude-haiku', 'claude-opus', 'claude-sonnet'):
            self.assertNotIn(hardcoded, worker_script)

        # User tier config is loaded cleanly
        tiers = os.path.join(os.path.dirname(self.proj), 'tiers.conf')
        with open(tiers, 'w') as f:
            f.write('TIER_SIMPLE_KIND="pi"\nTIER_SIMPLE_MODEL="fast-m"\nTIER_SIMPLE_EFFORT="low"\n')
        out_tier = self.sh('make', 'worker', 'NAME=w0', 'TIER=simple', env={'DRY': '1', 'HERDR_ENV': '1', 'AGENT_KIT_TIERS': tiers})
        self.assertIn('--kind pi', out_tier)
        self.assertIn('--model fast-m', out_tier)
        self.assertIn('--thinking low', out_tier)

        out = self.sh('make', 'worker', 'NAME=w1', 'KIND=codex', env={'DRY': '1', 'HERDR_ENV': '1'})
        self.assertIn('--sandbox workspace-write', out); self.assertNotIn('--add-dir', out)
        self.assertIn('network_access=true', out)
        self.assertIn('--permission-mode auto', self.sh('make', 'worker', 'NAME=w1', 'KIND=claude', env={'DRY': '1', 'HERDR_ENV': '1'}))
        self.assertIn('--kind gemini', self.sh('make', 'worker', 'NAME=w1', 'KIND=gemini', env={'DRY': '1', 'HERDR_ENV': '1'}))
        self.assertIn('custom-worker ', self.sh('make', 'worker', 'NAME=w1', 'WORKER_CMD=custom-worker {WT}', env={'DRY': '1', 'HERDR_ENV': '0'}))
        self.assertIn('usage', self.sh('make', 'worker', 'NAME=w1', 'KIND=other', ok=False))
        out = self.sh('make', 'worker', 'NAME=w2', 'KIND=claude', env={'HERDR_ENV': '0', 'HERDR_PANE_ID': 'w9:p9'})
        self.assertIn('Not inside herdr', out)
        task = open(self.proj + '-w2/TASK.md').read()
        self.assertIn('Lead: herdr pane w9:p9', task); self.assertIn('Agent: claude, model default', task)
        self.sh('make', 'worker', 'NAME=w2', 'KIND=codex', env={'HERDR_ENV': '0', 'HERDR_PANE_ID': 'w9:p8'})  # a retry
        task = open(self.proj + '-w2/TASK.md').read()
        self.assertEqual(task.count('\nLead: '), 1); self.assertIn('Lead: herdr pane w9:p8', task)
        self.assertEqual(task.count('\nAgent: '), 1); self.assertIn('Agent: codex', task)
        self.sh('make', 'worker', 'NAME=w4', 'KIND=codex', env={'HERDR_ENV': '0', 'HERDR_PANE_ID': ''})     # no herdr at all
        task = open(self.proj + '-w4/TASK.md').read()
        self.assertIn('Lead: the session that started you', task); self.assertNotIn('herdr pane', task)
        self.sh('make', 'finish', 'NAME=w4')
        self.assertIn('-m m1 -c model_reasoning_effort=low', self.sh('make', 'worker', 'NAME=w3', 'KIND=codex', 'MODEL=m1', 'EFFORT=low', env={'DRY': '1', 'HERDR_ENV': '1'}))
        self.sh('make', 'finish', 'NAME=w2')

    def test_task_skips_a_port_in_use(self):
        self.configure()
        with socket.socket() as busy:
            try: busy.bind(('127.0.0.1', 0)); busy.listen()
            except OSError as e: self.skipTest('cannot listen on a local port here: %s' % e)
            port = busy.getsockname()[1]                    # a free port from the system, now busy
            self.write('agent-kit.conf', self.read('agent-kit.conf').replace('TEST_PORT=8001', 'TEST_PORT=%d' % port))
            self.assertIn('test port %d' % (port + 1), self.sh('make', 'task', 'NAME=p1'))
            path = self.path_without('ss')                  # the macOS case: lsof instead of ss
            if not os.path.exists(os.path.join(path, 'lsof')): self.skipTest('no lsof here to test the fallback')
            self.write('agent-kit.conf', self.read('agent-kit.conf').replace('TEST_PORT=%d' % port, 'TEST_PORT=%d' % (port + 1)))
            self.assertIn('test port %d' % (port + 2), self.sh('make', 'task', 'NAME=p2', env={'PATH': path}))

    def test_service_without_systemd(self):
        self.write('agent-kit.conf', self.read('agent-kit.conf').replace('SERVICE=""', 'SERVICE="app"'))
        path = self.path_without('systemctl')
        self.assertIn('status needs systemd', self.sh('make', 'status', env={'PATH': path}))
        self.assertIn('no systemd', self.sh('make', 'deploy', ok=False, env={'PATH': path}))

    def test_link_skills(self):
        home = tempfile.mkdtemp(); self.addCleanup(subprocess.run, ['rm', '-rf', home])
        claude = os.path.join(home, '.claude', 'skills')
        agents = os.path.join(home, '.agents', 'skills')
        gemini = os.path.join(home, '.gemini', 'config', 'skills')
        custom = os.path.join(home, 'custom-skills')
        os.makedirs(claude); os.makedirs(gemini); os.makedirs(custom)
        os.makedirs(os.path.join(agents, 'new-project'))          # a real folder: kept
        os.symlink('/elsewhere/ship-with-agents', os.path.join(agents, 'ship-with-agents'))  # a foreign link: kept
        run = lambda: self.sh('bash', os.path.join(KIT, 'install.sh'), '--link-skills', cwd=home,
                              env={'HOME': home, 'AGENT_SKILLS_DIRS': custom})
        out = run()
        kit_skills = os.path.realpath(os.path.join(KIT, 'skills'))
        expected = ('interactive-html-brief', 'living-project-hub', 'new-project', 'session-retro', 'ship-with-agents', 'wrap-up')
        for target_dir in (claude, gemini, custom):
            for name in expected:
                self.assertEqual(os.readlink(os.path.join(target_dir, name)), os.path.join(kit_skills, name))
        self.assertTrue(os.path.isdir(os.path.join(agents, 'new-project')) and not os.path.islink(os.path.join(agents, 'new-project')))
        self.assertEqual(os.readlink(os.path.join(agents, 'ship-with-agents')), '/elsewhere/ship-with-agents')
        self.assertIn('kept', out); self.assertFalse(os.path.exists(os.path.join(home, '.pi')))
        self.assertFalse(os.path.exists(os.path.join(home, '--link-skills')))
        self.assertNotIn('added', run())                                                # a rerun changes nothing

    def test_link_skills_repairs_links_to_a_moved_kit_and_reports_no_folders(self):
        home = tempfile.mkdtemp(); self.addCleanup(subprocess.run, ['rm', '-rf', home])
        run = lambda: self.sh('bash', os.path.join(KIT, 'install.sh'), '--link-skills', cwd=home, env={'HOME': home})
        self.assertIn('no skills folders found', run())                                 # nothing to link into: say so
        claude = os.path.join(home, '.claude', 'skills'); os.makedirs(claude)
        os.symlink('/old/place/agent-kit/skills/wrap-up', os.path.join(claude, 'wrap-up'))  # the kit was moved
        os.symlink('/old/place/elsewhere', os.path.join(claude, 'session-retro'))       # broken, but not a kit skill: kept
        out = run()
        kit_skills = os.path.realpath(os.path.join(KIT, 'skills'))
        self.assertEqual(os.readlink(os.path.join(claude, 'wrap-up')), os.path.join(kit_skills, 'wrap-up'))
        self.assertIn('relinked', out)
        self.assertEqual(os.readlink(os.path.join(claude, 'session-retro')), '/old/place/elsewhere')

    def test_install_notes_when_global_skills_are_not_linked(self):
        home = tempfile.mkdtemp(); self.addCleanup(subprocess.run, ['rm', '-rf', home])
        proj = os.path.join(home, 'p')
        out = self.sh('bash', os.path.join(KIT, 'install.sh'), proj, 'P', cwd=home, env={'HOME': home})
        self.assertIn("global skills aren't linked", out)
        os.makedirs(os.path.join(home, '.claude', 'skills'))
        self.sh('bash', os.path.join(KIT, 'install.sh'), '--link-skills', cwd=home, env={'HOME': home})
        out2 = self.sh('bash', os.path.join(KIT, 'install.sh'), proj, 'P', cwd=home, env={'HOME': home})
        self.assertNotIn("global skills aren't linked", out2)

    def test_existing_claude_skills_folder_gets_project_skills(self):
        base = os.path.dirname(self.proj); p2 = os.path.join(base, 'adopted')
        os.makedirs(os.path.join(p2, '.claude', 'skills', 'mine'))
        self.assertIn('missing     .claude/skills/ship-feature',
                      self.sh('bash', os.path.join(KIT, 'install.sh'), '--check', p2, cwd=base))
        self.sh('bash', os.path.join(KIT, 'install.sh'), p2, 'P2', cwd=base)
        link = os.path.join(p2, '.claude', 'skills', 'ship-feature')
        self.assertEqual(os.readlink(link), '../../.agents/skills/ship-feature')
        self.assertTrue(os.path.isfile(os.path.join(link, 'SKILL.md')))
        self.assertTrue(os.path.isdir(os.path.join(p2, '.claude', 'skills', 'mine')))
        self.assertIn('ok          .claude/skills/ship-feature',
                      self.sh('bash', os.path.join(KIT, 'install.sh'), '--check', p2, cwd=base))

    def test_skips_finder_metadata(self):
        kit = tempfile.mkdtemp(); self.addCleanup(subprocess.run, ['rm', '-rf', kit])
        subprocess.run(['cp', '-R', os.path.join(KIT, 'install.sh'), os.path.join(KIT, 'template'), kit], check=True)
        with open(os.path.join(kit, 'template', 'scripts', '.DS_Store'), 'wb') as f: f.write(b'Bud1\x00\xff\xfe\x80')  # binary, as Finder writes it
        proj = os.path.join(kit, 'proj')
        self.sh('bash', os.path.join(kit, 'install.sh'), proj, 'Proj', cwd=kit)
        self.assertFalse(os.path.exists(os.path.join(proj, 'scripts', '.DS_Store')))

    def test_deploy_refuses_without_service_or_cmd(self):
        self.assertIn('No DEPLOY_CMD or SERVICE', self.sh('make', 'deploy', ok=False))

    def test_fern_stone_html_skills_and_living_project_hub(self):
        """HTML skills use Fern & Stone tokens, zero external CDN links, and build/serve multi-project hubs."""
        import http.client, json, time
        retro_html = Path(KIT, 'skills/session-retro/template/retro.html').read_text(encoding='utf-8')
        server_py = Path(KIT, 'skills/interactive-html-brief/scripts/agent-briefs-server').read_text(encoding='utf-8')
        hub_py = Path(KIT, 'skills/living-project-hub/scripts/build_hub.py').read_text(encoding='utf-8')
        hub_srv_py = Path(KIT, 'skills/living-project-hub/scripts/hub_server.py').read_text(encoding='utf-8')
        for name, text in (('retro.html', retro_html), ('agent-briefs-server', server_py), ('build_hub.py', hub_py), ('hub_server.py', hub_srv_py)):
            self.assertNotIn('fonts.googleapis.com', text, f'external font CDN in {name}')
            self.assertIn('#f8faf8', text, f'Fern & Stone light canvas missing in {name}')
            self.assertIn('#1d6a44', text, f'Fern & Stone primary accent missing in {name}')
            self.assertIn('data-theme="dark"', text, f'Dark toggle support missing in {name}')
            self.assertIn('prefers-color-scheme: dark', text, f'Auto system dark mode missing in {name}')

        # Build a living project hub + snapshot AND register into a temp multi-project registry
        self.configure()
        Path(self.proj, '.planning/phases/01-setup').mkdir(parents=True, exist_ok=True)
        Path(self.proj, '.planning/ROADMAP.md').write_text(
            "# Roadmap\n\n"
            "- [x] **Phase 1: Setup** - Baseline setup\n"
            "- [ ] **Phase 2: Build** - Core implementation\n\n"
            "### Phase 1: Setup\n"
            "**Goal**: Establish baseline workspace.\n"
            "**Depends on**: Nothing\n"
            "**Requirements**: REQ-01\n"
            "**Success Criteria**:\n"
            "  1. Workspace initialized.\n"
            "**Wave 1**\n"
            "- [x] 01-01-PLAN.md — Initial baseline\n",
            encoding='utf-8',
        )
        Path(self.proj, '.planning/phases/01-setup/01-01-PLAN.md').write_text("# Plan 01-01\nDetails.\n", encoding='utf-8')
        Path(self.proj, '.planning/phases/01-setup/01-01-SUMMARY.md').write_text("# Summary 01-01\nDone.\n", encoding='utf-8')
        reg_file = os.path.join(os.path.dirname(self.proj), 'projects.json')
        out = self.sh('python3', os.path.join(KIT, 'skills/living-project-hub/scripts/build_hub.py'),
                      '--root', self.proj, '--snapshot', 'phase-01-init',
                      '--register', '--registry', reg_file,
                      env={'AGENT_HUB_URL': 'http://127.0.0.1:8765'})
        self.assertIn('Wrote snapshot', out)
        self.assertIn('/p/proj/', out)
        hub_html = Path(self.proj, '.scratch/project-hub.html').read_text(encoding='utf-8')
        snap_html = Path(self.proj, '.scratch/snapshots/phase-01-init.html').read_text(encoding='utf-8')
        self.assertIn('Living Project &amp; Learning Hub', hub_html)
        self.assertIn('phase-01-init.html', hub_html)
        self.assertIn('data-phase-tab="1"', hub_html)
        self.assertIn('data-phase-open="1"', hub_html)
        self.assertIn('Establish baseline workspace.', hub_html)
        self.assertIn('summary_doc_id', hub_html)
        self.assertIn('SNAPSHOT', snap_html)
        self.assertNotIn('Microsoft Fabric', hub_html)

        # Start unified multi-project hub_server.py and verify index, project hub, snapshot, feedback, and remove
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]
        proc = subprocess.Popen(
            ['python3', '-I', os.path.join(KIT, 'skills/living-project-hub/scripts/hub_server.py'),
             '--multi', '--host', '127.0.0.1', '--port', str(port), '--registry', reg_file],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.addCleanup(lambda: (proc.terminate(), proc.wait(timeout=3)))
        deadline = time.time() + 5.0
        while time.time() < deadline:
            try:
                c = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
                c.request('GET', '/health')
                if c.getresponse().status == 200:
                    c.close(); break
                c.close()
            except OSError:
                time.sleep(0.05)
        else:
            self.fail('hub_server --multi failed to start')

        def req(method, path, body=None, headers=None):
            c = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
            try:
                c.request(method, path, body=body, headers=headers or {})
                r = c.getresponse(); return r.status, r.read()
            finally:
                c.close()

        st, body = req('GET', '/')
        self.assertEqual(st, 200); self.assertIn(b'Living Project Hubs', body)
        st, body = req('GET', '/api/projects')
        self.assertEqual(st, 200)
        projs = json.loads(body)['projects']
        self.assertEqual([p['slug'] for p in projs], ['proj'])
        self.assertTrue(projs[0]['ready'])

        st, body = req('GET', '/p/proj/')
        self.assertEqual(st, 200); self.assertIn(b'Living Project &amp; Learning Hub', body)
        st, body = req('GET', '/p/proj/snapshots/phase-01-init.html')
        self.assertEqual(st, 200); self.assertIn(b'SNAPSHOT', body)
        st, _ = req('GET', '/p/proj/snapshots/..%2fsecret.html')
        self.assertEqual(st, 400)

        st, _ = req('POST', '/p/proj/api/feedback',
                    body=json.dumps({'round': 'r1', 'markdown': '# Notes\nLooks good', 'state': {}}),
                    headers={'Content-Type': 'application/json'})
        self.assertEqual(st, 200)
        self.assertIn('Looks good', Path(self.proj, '.scratch/owner-feedback.md').read_text(encoding='utf-8'))

        st, _ = req('POST', '/api/projects/remove', body=json.dumps({'slug': 'proj'}), headers={'Content-Type': 'application/json'})
        self.assertEqual(st, 200)
        st, body = req('GET', '/api/projects')
        self.assertEqual(json.loads(body)['projects'], [])

    def test_public_repo_hygiene(self):
        """Ensure no personal paths, tailnet domains/IPs, or unrelated internal tools leak into the public kit."""
        ts_ip_re = re.compile(r'\b100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b')
        personal_re = re.compile(r'/home/[a-z0-9_-]+|/Users/[a-z0-9_-]+|@gmail\.com', re.IGNORECASE)
        real_ts_net_re = re.compile(r'\b[a-z0-9-]+\.tail[0-9a-f]{4,}\.ts\.net\b', re.IGNORECASE)
        private_terms_re = re.compile(r'\b(fabric-kit|rayfin|run-dax-query|omarchy)\b', re.IGNORECASE)

        root = Path(KIT).resolve()
        for rel in subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard'],
                                  cwd=root, capture_output=True, text=True, check=True).stdout.splitlines():
            p = root / rel
            if not p.is_file() or rel == 'tests/test_install.py' or rel == 'tests/test_interactive_html_brief.py':
                continue
            text = p.read_text(encoding='utf-8', errors='ignore')
            self.assertIsNone(ts_ip_re.search(text), f'Tailscale IP leaked in {rel}')
            self.assertIsNone(personal_re.search(text), f'Personal path/email leaked in {rel}')
            self.assertIsNone(real_ts_net_re.search(text), f'Real tailnet domain leaked in {rel}')
            self.assertIsNone(private_terms_re.search(text), f'Private/internal term leaked in {rel}')


if __name__ == '__main__':
    unittest.main()

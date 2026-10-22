"""Installs the kit into a throwaway project and drives every command there, as an agent would."""
import os, socket, subprocess, tempfile, unittest

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
        self.write('.gitignore', self.read('.gitignore') + 'data/\n')
        self.write('data/big.txt', 'x'); self.write('data/live.json', '{}'); self.write('labels.json', '[]')
        self.sh('git', 'add', '-A'); self.sh('git', 'commit', '-qm', 'start', env={'USER_OK': '1'})

    def test_installs_project_files(self):
        self.assertIn('# Proj', self.read('AGENTS.md'))
        self.assertEqual(self.read('CLAUDE.md'), '@AGENTS.md\n')
        self.assertEqual(os.readlink(os.path.join(self.proj, '.claude', 'skills')), '../.agents/skills')
        self.assertIn('ship-feature', os.listdir(os.path.join(self.proj, '.claude', 'skills')))
        self.assertEqual(self.sh('git', 'config', 'core.hooksPath').strip(), '.githooks')
        self.assertNotIn('{{', self.read('docs/decisions.md') + self.read('agent-kit.conf'))

    def test_never_overwrites(self):
        self.write('AGENTS.md', 'mine\n')
        out = self.sh('bash', os.path.join(KIT, 'install.sh'), self.proj)
        self.assertEqual(self.read('AGENTS.md'), 'mine\n')
        self.assertIn('kept     AGENTS.md', out)

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

    def test_worker_commands_and_lead(self):
        self.configure()
        out = self.sh('make', 'worker', 'NAME=w1', 'KIND=codex', env={'DRY': '1', 'HERDR_ENV': '1'})
        self.assertIn('--sandbox workspace-write', out); self.assertNotIn('--add-dir', out)
        self.assertIn('network_access=true', out)
        self.assertIn('--permission-mode auto', self.sh('make', 'worker', 'NAME=w1', 'KIND=claude', env={'DRY': '1', 'HERDR_ENV': '1'}))
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
        claude, agents = os.path.join(home, '.claude', 'skills'), os.path.join(home, '.agents', 'skills')
        os.makedirs(claude); os.makedirs(os.path.join(agents, 'new-project'))          # a real folder: kept
        os.symlink('/elsewhere/ship-with-agents', os.path.join(agents, 'ship-with-agents'))  # a foreign link: kept
        run = lambda: self.sh('bash', os.path.join(KIT, 'install.sh'), '--link-skills', cwd=home, env={'HOME': home})
        out = run()
        kit_skills = os.path.realpath(os.path.join(KIT, 'skills'))
        for name in ('new-project', 'ship-with-agents'):
            self.assertEqual(os.readlink(os.path.join(claude, name)), os.path.join(kit_skills, name))
        self.assertTrue(os.path.isdir(os.path.join(agents, 'new-project')) and not os.path.islink(os.path.join(agents, 'new-project')))
        self.assertEqual(os.readlink(os.path.join(agents, 'ship-with-agents')), '/elsewhere/ship-with-agents')
        self.assertIn('kept', out); self.assertFalse(os.path.exists(os.path.join(home, '.pi')))
        self.assertFalse(os.path.exists(os.path.join(home, '--link-skills')))
        self.assertNotIn('added', run())                                                # a rerun changes nothing

    def test_deploy_refuses_without_service(self):
        self.assertIn('No SERVICE', self.sh('make', 'deploy', ok=False))


if __name__ == '__main__':
    unittest.main()

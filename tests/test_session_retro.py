"""The session-retro skill: transcript timing for pi, Claude Code and Codex, and the page build."""
import importlib.util, json, os, subprocess, sys, tempfile, unittest

SKILL = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'skills', 'session-retro')
SCRIPTS = os.path.join(SKILL, 'scripts')


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, name + '.py'))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


metrics = load('session_metrics')


def ts(sec): return '2026-01-01T00:%02d:%02d.000Z' % divmod(sec, 60)


class TimingTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup); self.dir = tmp.name

    def write(self, name, rows):
        path = os.path.join(self.dir, name)
        with open(path, 'w') as f: f.writelines(json.dumps(r) + '\n' for r in rows)
        return path

    def run_metrics(self, path, *extra):
        out = os.path.join(self.dir, 'out')
        r = subprocess.run([sys.executable, '-I', os.path.join(SCRIPTS, 'session_metrics.py'), '--session', path, '--out', out, *extra],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(os.path.join(out, 'metrics.json')) as f: return json.load(f)['sessions'][0]

    def test_pi_splits_human_model_and_tool_time(self):
        def msg(sec, role, content, **kw): return {'type': 'message', 'timestamp': ts(sec), 'message': {'role': role, 'content': content, **kw}}
        call = {'type': 'toolCall', 'name': 'bash', 'arguments': {'command': 'npm pack left-pad'}}
        path = self.write('pi.jsonl', [
            {'type': 'session', 'version': 3, 'id': 's', 'timestamp': ts(0), 'cwd': '/p'},
            msg(0, 'user', [{'type': 'text', 'text': 'build it'}]),
            msg(5, 'assistant', [call], usage={'input': 100, 'cacheRead': 0, 'output': 10}),        # model 5 s
            msg(9, 'toolResult', [{'type': 'text', 'text': 'ok'}]),                                   # tool 4 s
            msg(12, 'assistant', [{'type': 'text', 'text': 'done'}], usage={'input': 200, 'output': 5}),  # model 3 s
            msg(72, 'user', [{'type': 'text', 'text': 'thanks'}]),                                    # human 60 s
            msg(74, 'assistant', [{'type': 'text', 'text': 'bye'}], usage={'input': 300, 'output': 1}),
        ])
        s = self.run_metrics(path, '--milestone', 'draft=2026-01-01T00:00:20+00:00')
        whole = s['whole_session']
        self.assertEqual((whole['human_min'], whole['assistant_turns'], whole['tool_calls']), (1.0, 3, 1))
        self.assertAlmostEqual(whole['model_min'], (5 + 3 + 2) / 60, places=1)
        self.assertEqual(whole['context_tokens']['max'], 300)
        draft = s['milestones']['draft']
        self.assertEqual((draft['assistant_turns'], draft['human_turns']), (2, 0))
        self.assertIn('package / registry archaeology', draft['buckets'])

    def test_reads_are_counted_by_full_path_and_slices_reported(self):
        def turn(sec, cmd): return {'type': 'message', 'timestamp': ts(sec), 'message': {'role': 'assistant', 'content': [
            {'type': 'toolCall', 'name': 'bash', 'arguments': {'command': cmd}}]}}
        def result(sec): return {'type': 'message', 'timestamp': ts(sec), 'message': {'role': 'toolResult', 'content': [{'type': 'text', 'text': 'x'}]}}
        path = self.write('reads.jsonl', [
            {'type': 'session', 'version': 3, 'id': 's', 'timestamp': ts(0)},
            {'type': 'message', 'timestamp': ts(0), 'message': {'role': 'user', 'content': 'go'}},
            turn(1, 'cd /a; cat dist/index.d.ts'), result(2),
            turn(3, 'cd /b; cat dist/index.d.ts'), result(4),           # same name, different file
            turn(5, "sed -n 1,60p /a/SKILL.md"), result(6),
            turn(7, "sed -n 60,120p /a/SKILL.md"), result(8),           # same file, second slice
        ])
        reads = self.run_metrics(path)['reads']
        self.assertEqual(reads['repeated'], [['/a/SKILL.md', 2]])
        self.assertEqual((reads['sliced_files'], reads['sliced_reads']), (1, 2))

    def test_long_waits_count_as_away_not_human(self):
        rows = [{'type': 'session', 'version': 3, 'id': 's', 'timestamp': ts(0)},
                {'type': 'message', 'timestamp': ts(0), 'message': {'role': 'user', 'content': 'a'}},
                {'type': 'message', 'timestamp': ts(2), 'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': 'x'}]}},
                {'type': 'message', 'timestamp': ts(2 + 50 * 60 % 3600), 'message': {'role': 'user', 'content': 'b'}}]
        rows[-1]['timestamp'] = '2026-01-01T00:52:00.000Z'
        whole = self.run_metrics(self.write('away.jsonl', rows))['whole_session']
        self.assertEqual((whole['human_min'], whole['away_breaks']), (0.0, 1))
        self.assertGreater(whole['away_min'], 49)

    def test_claude_code_merges_streamed_records_and_skips_meta_and_sidechains(self):
        base = {'sessionId': 'c', 'cwd': '/p'}
        path = self.write('cc.jsonl', [
            {'type': 'user', 'timestamp': ts(0), 'isMeta': True, 'message': {'role': 'user', 'content': 'caveat'}, **base},
            {'type': 'user', 'timestamp': ts(1), 'message': {'role': 'user', 'content': 'go'}, **base},
            {'type': 'assistant', 'timestamp': ts(4), 'message': {'id': 'm1', 'content': [{'type': 'text', 'text': 'reading'}], 'usage': {'input_tokens': 10, 'cache_read_input_tokens': 90, 'output_tokens': 3}}, **base},
            {'type': 'assistant', 'timestamp': ts(5), 'message': {'id': 'm1', 'content': [{'type': 'tool_use', 'name': 'Read', 'input': {'file_path': 'a.md'}}], 'usage': {'input_tokens': 10, 'cache_read_input_tokens': 90, 'output_tokens': 9}}, **base},
            {'type': 'assistant', 'timestamp': ts(6), 'isSidechain': True, 'message': {'id': 'x', 'content': []}, **base},
            {'type': 'user', 'timestamp': ts(8), 'message': {'role': 'user', 'content': [{'type': 'tool_result', 'content': 'text'}]}, **base},
            {'type': 'assistant', 'timestamp': ts(10), 'message': {'id': 'm2', 'content': [{'type': 'text', 'text': 'ok'}]}, **base},
        ])
        whole = self.run_metrics(path)['whole_session']
        self.assertEqual((whole['assistant_turns'], whole['tool_calls'], whole['human_turns']), (2, 1, 0))
        self.assertEqual(whole['context_tokens']['first'], 100)
        self.assertIn('read / explore', whole['buckets'])

    def test_codex_rollouts(self):
        def item(sec, **payload): return {'type': 'response_item', 'timestamp': ts(sec), 'payload': payload}
        path = self.write('rollout-x.jsonl', [
            {'type': 'session_meta', 'timestamp': ts(0), 'payload': {'id': 'x', 'cwd': '/p'}},
            item(0, type='message', role='user', content=[{'type': 'input_text', 'text': '<environment_context>…'}]),
            {'type': 'event_msg', 'timestamp': ts(1), 'payload': {'type': 'item_completed', 'item': {'type': 'UserMessage', 'content': [{'type': 'text', 'text': 'review'}]}}},
            item(3, type='reasoning'),
            item(4, type='function_call', name='shell', arguments=json.dumps({'command': ['git', 'status']})),
            {'type': 'event_msg', 'timestamp': ts(4), 'payload': {'type': 'token_count', 'info': {'last_token_usage': {'input_tokens': 500, 'output_tokens': 7}}}},
            item(6, type='function_call_output', output='clean'),
            item(9, type='message', role='assistant', content=[{'type': 'output_text', 'text': 'fine'}]),
        ])
        s = self.run_metrics(path)
        whole = s['whole_session']
        self.assertEqual(s['harness'], 'codex')
        self.assertEqual((whole['assistant_turns'], whole['tool_calls'], whole['human_turns']), (2, 1, 0))
        self.assertEqual(whole['context_tokens']['max'], 500)
        self.assertIn('git', whole['buckets'])


class BuildTests(unittest.TestCase):
    def build(self, data):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        src, out = os.path.join(tmp.name, 'd.json'), os.path.join(tmp.name, 'r.html')
        with open(src, 'w') as f: json.dump(data, f)
        r = subprocess.run([sys.executable, '-I', os.path.join(SCRIPTS, 'build_retro.py'), src, out], capture_output=True, text=True)
        page = open(out).read() if os.path.exists(out) else ''
        return r, page

    def test_example_builds_to_static_html_with_note_points(self):
        with open(os.path.join(SKILL, 'references', 'example.json')) as f: data = json.load(f)
        r, page = self.build(data)
        self.assertEqual(r.returncode, 0, r.stderr)
        for marker in ('__RETRO_', '/*__'): self.assertNotIn(marker, page)
        self.assertIn('Stops that showed the owner nothing', page)           # rendered at build time, not by script
        self.assertIn('data-id="f-gates"', page)
        self.assertIn('"storageKey": "example-retro-2026-01-01"', page)

    def test_bad_data_is_refused(self):
        r, page = self.build({'title': 't', 'storageKey': 'k', 'sections': [
            {'id': 'a', 'title': 'A', 'type': 'claims', 'items': [{'id': 'a', 'claim': 'c', 'verdict': 'maybe'}]},
            {'id': 'b', 'title': 'B', 'type': 'table', 'columns': [{'label': 'x'}], 'rows': [[1, 2]]}]})
        self.assertEqual(r.returncode, 1)
        self.assertEqual(page, '')
        for text in ("duplicate id 'a'", 'verdict must be', '2 cells, 1 columns'): self.assertIn(text, r.stderr)

    def test_script_close_tag_in_content_cannot_break_out(self):
        r, page = self.build({'title': '</script><b>x', 'storageKey': 'k', 'sections': [{'id': 'a', 'title': 'A', 'type': 'prose', 'paragraphs': ['p']}]})
        self.assertEqual(r.returncode, 0, r.stderr)
        data_block = page.split('id="retro-data">', 1)[1].split('</script>', 1)[0]
        self.assertIn('<\\/script>', data_block)


if __name__ == '__main__':
    unittest.main()

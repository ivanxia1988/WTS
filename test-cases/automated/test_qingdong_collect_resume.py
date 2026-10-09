"""Collect must inspect the retained list before any search mutation."""
import json
import unittest
import test_qingdong_collection as collection


class CollectResumeTests(unittest.TestCase):
    setUp = collection.CollectionTests.setUp
    tearDown = collection.CollectionTests.tearDown
    write = collection.CollectionTests.write
    call = collection.CollectionTests.call
    result = collection.CollectionTests.result

    def test_collect_has_no_unconditional_navigation_or_search(self):
        self.write('iteration-1-collect.json', {'result_ref': self.card_ref, 'primary': ['liepin:new000001']})
        workflow = self.call('collect', 'iteration-1-collect.json')
        self.assertFalse(any(s['action'] == 'page.navigate' for s in workflow['steps']))
        program = next(s['program'] for s in workflow['steps'] if s['action'] == 'page.run')
        self.assertFalse(any(s['op'] in ('page.fill', 'page.click') for s in program))
        self.assertTrue(any(s['id'] == 'primary-check-collection-state' for s in program))

    def collect_with_snapshot(self, page="1"):
        snapshot = {'url': 'https://h.liepin.com/search/getConditionItem',
                    'query': 'AI Agent Multi-Agent RAG DeepSeek',
                    'filters': ['7天内活跃', '杭州', '杭州'], 'page': page}
        self.card_ref = self.result(self.card_workflow, {
            'search': {'primary': {'list_state': snapshot, 'pages': [1], 'unsupported_filters': []}},
            'candidates': {'primary': [{'candidate_ref': 'liepin:new000001',
                                       'card_hard_filter_status': 'unknown', 'search_page': 1}]}})
        self.write('iteration-1-collect.json', {'result_ref': self.card_ref, 'primary': ['liepin:new000001']})
        return snapshot, self.call('collect', 'iteration-1-collect.json')

    def test_no_pagination_snapshot_is_reusable(self):
        _, workflow = self.collect_with_snapshot(page=None)
        program = next(s['program'] for s in workflow['steps'] if s['action'] == 'page.run')
        gate = next(s for s in program if s['id'] == 'primary-check-collection-state')
        self.assertIsInstance(gate['condition'], dict,
                              'Session 64: absent pagination must not force a new search')
        page = next(c for c in gate['condition']['all'] if c['path'] == 'search.list_state.page')
        self.assertIsNone(page['value'])

    def test_state_is_captured_and_recovery_is_explicit(self):
        self.assertIn('capture-list-state', json.dumps(self.card_workflow))
        _, workflow = self.collect_with_snapshot()
        self.assertFalse(any(s['action'] == 'page.navigate' for s in workflow['steps']))
        self.result(workflow, {'search': {'primary': {'collection_check': {'status': 'needs_restore'}}}})
        restored = self.call('collect', 'iteration-1-collect.json', extra=('--restore-search', '--recovery-reason', '页面已变化'))
        self.assertTrue(any(s['action'] == 'page.navigate' for s in restored['steps']))
        self.assertEqual(restored['input_summary']['selection'], workflow['input_summary']['selection'])
        import subprocess
        import sys
        run = subprocess.run([sys.executable, str(collection.BUILDER), 'search', '--restore-search',
                              '--task-id', 'test-task'], capture_output=True, text=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('仅用于 collect', run.stderr)

    def test_generated_branches_in_installed_domi_interpreter(self):
        import shutil
        import subprocess
        from pathlib import Path
        runtime = Path('/Applications/Domi.app/Contents/Resources/browser-extensions/embedded-workflow')
        if not (runtime / 'content.js').exists() or not shutil.which('node'):
            self.skipTest('Installed Domi page interpreter and Node required for host compatibility check')
        for page in ("1", None):
            for p in (self.root / 'workflow-store/test-task').glob('*.json'):
                if json.loads(p.read_text()).get('input_summary', {}).get('stage') == 'details':
                    p.unlink()
            snapshot, workflow = self.collect_with_snapshot(page=page)
            program = next(s['program'] for s in workflow['steps'] if s['action'] == 'page.run')
            gate = next(s for s in program if s['id'] == 'primary-check-collection-state')
            self.assertIn('needs_restore', json.dumps(gate['else']))
            self.assertNotIn('fill-keyword', json.dumps(program))
            opening = next(s['open'] for s in workflow['steps'] if s['action'] == 'tabs.foreach')
            suffixes = ('remember-selected-candidate', 'initialize-identity-matches',
                        'locate-selected-candidate', 'require-unique-selected-candidate')
            identity = [s for s in opening['pre_program'] if any(s['id'] == 'primary-' + k for k in suffixes)]
            run = subprocess.run(['node', str(Path(__file__).with_name('collect_host_probe.js')), str(runtime)],
                                 input=json.dumps({'snapshot': snapshot, 'gate': gate, 'identity': identity,
                                                   'target': opening['target']}),
                                 capture_output=True, text=True, timeout=15)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('4 candidate-identity cases passed', run.stdout)

    def test_legacy_result_reports_missing_snapshot_without_search(self):
        self.write('iteration-1-collect.json', {'result_ref': self.card_ref, 'primary': ['liepin:new000001']})
        workflow = self.call('collect', 'iteration-1-collect.json')
        program = next(s['program'] for s in workflow['steps'] if s['action'] == 'page.run')
        gate = next(s for s in program if s['id'] == 'primary-check-collection-state')
        self.assertIs(gate['condition'], False)
        cards = next(s['value'] for s in gate['then'] if s['id'] == 'primary-restore-selected-cards')
        self.assertEqual([r['candidate_ref'] for r in cards], ['liepin:new000001'])

    def test_refill_collection_reuses_its_own_snapshot(self):
        for p in (self.root / 'workflow-store/test-task').glob('*.json'):
            p.unlink()
        self.plan['primary_query'] = 'Agent RAG DeepSeek'
        self.write('iteration-1.json', self.plan)
        search = self.call('search', 'iteration-1.json')
        self.result(search, {'candidates': {'primary': []}})
        self.write('iteration-1-refill.json', {'dropped_company': 'DeepSeek'})
        refill = self.call('refill', 'iteration-1-refill.json')
        snapshot = {'url': 'https://h.liepin.com/search/getConditionItem', 'query': 'Agent RAG',
                    'filters': [], 'page': '1'}
        ref = self.result(refill, {'search': {'primary': {'list_state': snapshot, 'pages': [1]}},
                                  'candidates': {'primary': [{'candidate_ref': 'liepin:new000001',
                                                             'card_hard_filter_status': 'matched'}]}})
        self.write('iteration-1-refill-collect.json', {'result_ref': ref, 'primary': ['liepin:new000001']})
        workflow = self.call('collect', 'iteration-1-refill-collect.json')
        self.assertTrue(workflow['refill'])
        program = next(s['program'] for s in workflow['steps'] if s['action'] == 'page.run')
        gate = next(s for s in program if s['id'] == 'primary-check-collection-state')
        query = next(c['value'] for c in gate['condition']['all'] if c['path'] == 'search.list_state.query')
        self.assertEqual(query, 'Agent RAG')
        self.assertNotIn('DeepSeek', json.dumps(gate))

    def test_two_paths_use_distinct_state_and_identity_selection(self):
        import subprocess
        import sys
        plan = self.card_workflow['input_plan']
        plan['secondary_query'] = 'Agent Memory'
        contexts = {}
        selected = {}
        for name in ('primary', 'secondary'):
            ref = 'liepin:' + name + '0001'
            selected[name] = [ref]
            contexts[name] = {'list_state': {'url': 'https://h.liepin.com/search/getConditionItem',
                                            'query': plan[name + '_query'], 'filters': [], 'page': '1'},
                              'cards': [{'candidate_ref': ref}], 'pages': [1]}
        # A fresh process resolves sibling imports exactly as the production CLI does.
        script = """import argparse,json,sys
sys.path.insert(0,sys.argv[1])
import build_workflow as builder
v=json.load(sys.stdin)
a=argparse.Namespace(task_id='test-task',iteration=2,task_work_dir=v['root'],
                    store_root=v['root'],interaction_mode=None,deadline_minutes=20)
print(json.dumps(builder.build_search(a,builder.load_assets(),selection=v['selected'],
                                     source_plan=v['plan'],collection_context=v['contexts'])))
"""
        run = subprocess.run([sys.executable, '-B', '-c', script, str(collection.BUILDER.parent)],
                             input=json.dumps({'root': str(self.root), 'plan': plan,
                                               'selected': selected, 'contexts': contexts}),
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        workflow = json.loads(run.stdout)
        for name in selected:
            program = next(s['program'] for s in workflow['steps'] if s['id'] == name + '-search-and-extract-cards')
            gate = next(s for s in program if s['id'] == name + '-check-collection-state')
            query = next(c['value'] for c in gate['condition']['all'] if c['path'] == 'search.list_state.query')
            self.assertEqual(query, plan[name + '_query'])
        self.assertFalse(any(s['action'] == 'page.navigate' for s in workflow['steps']))

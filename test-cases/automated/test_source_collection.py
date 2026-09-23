"""Exercise the main source package through its real CLI and immutable stores."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / 'source/scripts/build_workflow.py'


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.plans = self.root / 'wts/search-plans'
        self.plans.mkdir(parents=True)
        self.plan = {'requirement_version': 'v1', 'primary_query': 'Agent RAG',
                     'hard_filters': {}, 'site_filters': {},
                     'semantic_criteria': {'must_have': ['Agent'], 'nice_to_have': [], 'exclude_signals': []}}
        self.write('iteration-1.json', self.plan)
        self.card_workflow = self.call('search', 'iteration-1.json')
        self.card_ref = self.result(self.card_workflow, {
            'candidates': {'primary': [
                {'candidate_ref': 'liepin:seen00001', 'card_hard_filter_status': 'matched'},
                {'candidate_ref': 'liepin:new000001', 'card_hard_filter_status': 'unknown'},
                {'candidate_ref': 'liepin:reject001', 'card_hard_filter_status': 'rejected'}]},
            'details': {'primary': []}})

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data):
        (self.plans / name).write_text(json.dumps(data))

    def call(self, command, file, *, ok=True, extra=()):
        env = dict(os.environ)
        env.pop('DEEPAGENT_TASK_WORK_DIR', None)
        env.pop('DEEPAGENT_WORKFLOW_STORE_DIR', None)
        run = subprocess.run([sys.executable, '-B', str(BUILDER), command,
                              '--task-id', 'test-task', '--iteration', '1',
                              '--task-work-dir', str(self.root), '--store-root', str(self.root),
                              '--plan-file', str(self.plans / file), *extra],
                             capture_output=True, text=True, env=env)
        out = json.loads(run.stdout)
        if not ok:
            self.assertNotEqual(run.returncode, 0, out)
            return out
        self.assertEqual(run.returncode, 0, out)
        digest = out['workflow_ref'].rsplit('/', 1)[1]
        return json.loads((self.root / 'workflow-store/test-task' / (digest + '.json')).read_text())

    def result(self, workflow, data):
        result = {'status': 'success', 'workflow': {'task_id': 'test-task',
                  'workflow_id': workflow['workflow_id'], 'finished_at': '2026-09-21T08:00:00Z'}, 'data': data}
        raw = json.dumps(result).encode()
        digest = hashlib.sha256(raw).hexdigest()
        folder = self.root / 'result-store/test-task'
        folder.mkdir(parents=True, exist_ok=True)
        (folder / (digest + '.json')).write_bytes(raw)
        return 'result://test-task/' + digest

    def collect(self, refs, **kwargs):
        self.write('iteration-1-collect.json', {'result_ref': self.card_ref, 'primary': refs})
        return self.call('collect', 'iteration-1-collect.json', **kwargs)

    def test_cards_then_selected_details_preserve_plan_and_pacing(self):
        self.assertFalse(any(s['action'] == 'tabs.foreach' for s in self.card_workflow['steps']))
        # Agent omits the seen candidate, selecting only the new one.
        w = self.collect(['liepin:new000001'])
        tabs = [s for s in w['steps'] if s['action'] == 'tabs.foreach']
        self.assertEqual(len(tabs), 1)
        self.assertEqual(tabs[0]['max_items'], 1)
        filt = next(s for s in w['steps'] if s['id'] == 'primary-card-hard-filter')
        predicate = filt['predicates'][-1]
        self.assertEqual(predicate['operator'], 'text.includes_any')
        self.assertEqual(predicate['expected'], ['liepin:new000001'])
        self.assertNotIn('text.excludes_all', json.dumps(w))
        self.assertEqual(w['input_plan'], self.card_workflow['input_plan'])
        self.assertIn('pacing-before-primary-extract-detail', json.dumps(w))
        self.assertEqual(w['input_summary']['stage'], 'details')

    def test_rejects_invented_or_rejected_candidates_and_wrong_result(self):
        for refs in [['liepin:invent001'], ['liepin:reject001']]:
            self.assertIn('matched/unknown', self.collect(refs, ok=False)['error'])
        self.card_ref = self.card_ref.replace('test-task', 'other-task')
        self.assertIn('当前任务', self.collect([], ok=False)['error'])

    def test_empty_selection_never_opens_details(self):
        w = self.collect([])
        self.assertFalse(any(s['action'] == 'tabs.foreach' for s in w['steps']))
        self.assertEqual(w['limits']['max_tabs'], 0)
        self.assertEqual([s['action'] for s in w['steps']], ['result.emit'])

    def test_rejects_tampered_result_and_over_budget(self):
        self.plan['limits'] = {'primary_max_details': 1}
        self.write('iteration-1.json', self.plan)
        w = self.call('search', 'iteration-1.json')
        self.card_ref = self.result(w, {'candidates': {'primary': [
            {'candidate_ref': 'liepin:new000001', 'card_hard_filter_status': 'unknown'},
            {'candidate_ref': 'liepin:seen00001', 'card_hard_filter_status': 'matched'}]}})
        self.assertIn('最多 1', self.collect(['liepin:new000001', 'liepin:seen00001'], ok=False)['error'])
        p = self.root / 'result-store/test-task' / (self.card_ref.rsplit('/', 1)[1] + '.json')
        p.write_text(p.read_text() + ' ')
        self.assertIn('摘要不匹配', self.collect([], ok=False)['error'])

    def test_two_path_selection_rejects_duplicates_and_preserves_budgets(self):
        # A completed second-round card fixture; collect still runs through the real CLI.
        w = self.card_workflow
        w.pop('integrity')
        w['iteration'] = 2
        w['input_plan']['secondary_query'] = 'Agent Memory'
        w['input_plan']['limits']['secondary_max_details'] = 3
        canonical = json.dumps(w, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
        digest = hashlib.sha256(canonical).hexdigest()
        w['integrity'] = {'algorithm': 'sha256', 'digest': digest}
        folder = self.root / 'workflow-store/test-task'
        for p in folder.glob('*.json'):
            p.unlink()
        (folder / (digest + '.json')).write_text(json.dumps(w))
        self.card_ref = self.result(w, {'candidates': {
            'primary': [{'candidate_ref': 'liepin:new000001', 'card_hard_filter_status': 'matched'}],
            'secondary': [{'candidate_ref': ref, 'card_hard_filter_status': 'unknown'}
                          for ref in ['liepin:new000001', 'liepin:new000002']]}})
        selection = {'result_ref': self.card_ref, 'primary': ['liepin:new000001'],
                     'secondary': ['liepin:new000001']}
        self.write('iteration-2-collect.json', selection)
        error = self.call('collect', 'iteration-2-collect.json', ok=False, extra=('--iteration', '2'))
        self.assertIn('不能重复', error['error'])
        selection['secondary'] = ['liepin:new000002']
        self.write('iteration-2-collect.json', selection)
        out = self.call('collect', 'iteration-2-collect.json', extra=('--iteration', '2'))
        self.assertEqual([s['max_items'] for s in out['steps'] if s['action'] == 'tabs.foreach'], [1, 1])
        self.assertEqual(out['input_plan']['limits']['primary_max_details'], 5)
        self.assertEqual(out['input_plan']['limits']['secondary_max_details'], 3)

    def test_rejects_old_exclusion_field(self):
        self.plan['exclude_candidate_refs'] = ['liepin:seen00001']
        self.write('iteration-1.json', self.plan)
        self.assertIn('未知字段', self.call('search', 'iteration-1.json', ok=False)['error'])

    def test_card_only_round_cannot_expand(self):
        self.write('iteration-1-expand-1.json', {
            'requirement_version': 'v1', 'query': 'Agent RAG',
            'include_candidate_refs': ['liepin:new000001'], 'site_filters': {},
            'hard_filters': {}, 'semantic_criteria': self.plan['semantic_criteria']})
        error = self.call('expand', 'iteration-1-expand-1.json', ok=False,
                          extra=('--expansion', '1'))
        self.assertIn('先执行 collect', error['error'])
        details = self.collect(['liepin:new000001'])
        self.result(details, {'details': {'primary': []}})
        expanded = self.call('expand', 'iteration-1-expand-1.json', extra=('--expansion', '1'))
        self.assertEqual(expanded['expansion'], 1)
        self.assertNotIn('text.excludes_all', json.dumps(expanded))

    def test_expand_rejects_changed_site_filters(self):
        self.plan['site_filters'] = {'gender': 'male'}
        self.write('iteration-1.json', self.plan)
        self.card_workflow = self.call('search', 'iteration-1.json')
        self.card_ref = self.result(self.card_workflow, {'candidates': {'primary': [
            {'candidate_ref': 'liepin:new000001', 'card_hard_filter_status': 'matched'}]}})
        details = self.collect(['liepin:new000001'])
        self.result(details, {'details': {'primary': []}})
        self.write('iteration-1-expand-1.json', {
            'requirement_version': 'v1', 'query': 'Agent RAG',
            'include_candidate_refs': ['liepin:new000001'],
            'site_filters': {'gender': 'female'},
            'hard_filters': {}, 'semantic_criteria': self.plan['semantic_criteria']})

        error = self.call('expand', 'iteration-1-expand-1.json', ok=False,
                          extra=('--expansion', '1'))

        self.assertIn('site_filters.gender', error['error'])

    def test_expand_rejects_reused_sequence_number(self):
        details = self.collect(['liepin:new000001'])
        self.result(details, {'details': {'primary': []}})
        self.write('iteration-1-expand-1.json', {
            'requirement_version': 'v1', 'query': 'Agent RAG',
            'include_candidate_refs': ['liepin:new000001'], 'site_filters': {},
            'hard_filters': {}, 'semantic_criteria': self.plan['semantic_criteria']})
        self.call('expand', 'iteration-1-expand-1.json', extra=('--expansion', '1'))

        error = self.call('expand', 'iteration-1-expand-1.json', ok=False,
                          extra=('--expansion', '1'))

        self.assertIn('下一次扩张序号必须为 2', error['error'])


if __name__ == '__main__':
    unittest.main()

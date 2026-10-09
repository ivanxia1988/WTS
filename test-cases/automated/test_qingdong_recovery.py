"""Recovery uses stored facts, not a second pass over completed candidates."""
import importlib.util
import json
import unittest
from pathlib import Path
import test_qingdong_collection as collection


class RecoveryTests(unittest.TestCase):
    setUp = collection.CollectionTests.setUp
    tearDown = collection.CollectionTests.tearDown
    write = collection.CollectionTests.write
    call = collection.CollectionTests.call
    result = collection.CollectionTests.result

    def test_repeated_collect_excludes_completed_and_unknown(self):
        self.write('iteration-1-collect.json', {'result_ref': self.card_ref,
                   'primary': ['liepin:new000001', 'liepin:seen00001']})
        first = self.call('collect', 'iteration-1-collect.json')
        ref = self.result(first, {'details': {'primary': [{'candidate_ref': 'liepin:new000001'}]}})
        second = self.call('collect', 'iteration-1-collect.json')
        self.assertEqual(second['limits']['max_tabs'], 0)
        receipt = second['input_summary']['reconciliation']
        self.assertEqual(receipt['completed'][0]['detail_ref'], ref)
        self.assertEqual(receipt['uncertain'], ['liepin:seen00001'])

    def test_changed_page_has_no_implicit_restore_branch(self):
        self.write('iteration-1-collect.json', {'result_ref': self.card_ref, 'primary': ['liepin:new000001']})
        workflow = self.call('collect', 'iteration-1-collect.json')
        program = next(s['program'] for s in workflow['steps'] if s['action'] == 'page.run')
        self.assertNotIn('fill-keyword', json.dumps(program))
        self.assertIn('needs_restore', json.dumps(program))


class EvidenceTests(unittest.TestCase):
    setUp = collection.CollectionTests.setUp
    tearDown = collection.CollectionTests.tearDown
    write = collection.CollectionTests.write
    call = collection.CollectionTests.call
    result = collection.CollectionTests.result

    def collect(self, refs, extra=(), ok=True):
        self.write('iteration-1-collect.json', {'result_ref': self.card_ref, 'primary': refs})
        return self.call('collect', 'iteration-1-collect.json', extra=extra, ok=ok)

    def receipt(self, workflow):
        return workflow['input_summary']['reconciliation']

    def add_cards(self, count):
        self.card_ref = self.result(self.card_workflow, {'candidates': {'primary': [
            {'candidate_ref': f'liepin:person{i:04}', 'card_hard_filter_status': 'unknown'} for i in range(count)]}})

    def test_no_result_is_uncertain_not_unexecuted(self):
        self.collect(['liepin:new000001'])
        next_run = self.collect(['liepin:new000001'])
        self.assertEqual(next_run['limits']['max_tabs'], 0)
        self.assertEqual(self.receipt(next_run)['uncertain'], ['liepin:new000001'])

    def test_mismatch_result_proves_no_open_and_allows_explicit_restore(self):
        first = self.collect(['liepin:new000001'])
        self.result(first, {'search': {'primary': {'collection_check': {'status': 'needs_restore'}}}})
        next_run = self.collect(['liepin:new000001'], extra=('--restore-search', '--recovery-reason', '当前页面变化'))
        self.assertEqual(next_run['limits']['max_tabs'], 1)
        self.assertEqual(self.receipt(next_run)['occupied'], {})
        self.assertTrue(any(s['action'] == 'page.navigate' for s in next_run['steps']))

    def test_failure_before_collection_leaves_candidates_pending(self):
        first = self.collect(['liepin:new000001'])
        self.result(first, {'failed_step_id': 'primary-search-and-extract-cards'})
        next_run = self.collect(['liepin:new000001'])
        self.assertEqual(next_run['limits']['max_tabs'], 1)
        self.assertEqual(self.receipt(next_run)['uncertain'], [])

    def test_completed_and_uncertain_excluded_but_new_candidate_continues(self):
        self.add_cards(3)
        refs = [f'liepin:person{i:04}' for i in range(3)]
        first = self.collect(refs[:2])
        self.result(first, {'details': {'primary': [{'candidate_ref': refs[0]}]}})
        next_run = self.collect(refs)
        self.assertEqual(next_run['input_summary']['selection']['primary'], refs[2:])
        self.assertEqual(self.receipt(next_run)['uncertain'], refs[1:2])
        self.assertEqual(len(self.receipt(next_run)['completed']), 1)

    def test_cumulative_budget_survives_multiple_continuations(self):
        self.add_cards(6)
        refs = [f'liepin:person{i:04}' for i in range(6)]
        first = self.collect(refs[:3])
        self.result(first, {'details': {'primary': [{'candidate_ref': ref} for ref in refs[:3]]}})
        second = self.collect(refs[3:5])
        self.result(second, {'details': {'primary': [{'candidate_ref': ref} for ref in refs[3:5]]}})
        self.assertIn('累计采集', self.collect(refs[5:], ok=False)['error'])
        again = self.collect(refs[:5])
        self.assertEqual(again['limits']['max_tabs'], 0)
        self.assertEqual(len(self.receipt(again)['completed']), 5)

    def test_explicit_failed_retry_preserves_attempt_count(self):
        ref = 'liepin:new000001'
        first = self.collect([ref])
        self.result(first, {'failures': {'primary': [{'candidate_ref': ref, 'error_code': 'TIMEOUT'}]}})
        retry = self.collect([ref], extra=('--retry-candidate', ref, '--recovery-reason', '已排除超时原因'))
        self.assertEqual(retry['limits']['max_tabs'], 1)
        self.result(retry, {'details': {'primary': [{'candidate_ref': ref}]}})
        final = self.collect([ref])
        self.assertEqual(final['limits']['max_tabs'], 0)
        self.assertEqual(len(self.receipt(final)['attempts']), 2)

    def test_repeated_search_reuses_result_without_execution(self):
        import subprocess, sys
        run = subprocess.run([sys.executable, '-B', str(collection.BUILDER), 'search',
            '--task-id', 'test-task', '--iteration', '1', '--task-work-dir', str(self.root),
            '--store-root', str(self.root), '--plan-file', str(self.plans / 'iteration-1.json')],
            capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        out = json.loads(run.stdout)
        self.assertEqual(out['status'], 'reused')
        self.assertNotIn('tool', out['next_action'])
        self.assertEqual(out['result_ref'], self.card_ref)

    def test_cross_task_reuses_verified_session_result(self):
        import subprocess, sys
        first = self.collect(['liepin:new000001'])
        saved = self.result(first, {'details': {'primary': [{'candidate_ref': 'liepin:new000001'}]}})
        run = subprocess.run([sys.executable, '-B', str(collection.BUILDER), 'collect',
            '--task-id', 'new-task', '--iteration', '1', '--task-work-dir', str(self.root),
            '--store-root', str(self.root), '--plan-file', str(self.plans / 'iteration-1-collect.json')],
            capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        out = json.loads(run.stdout)
        self.assertEqual(out['next_action']['action'], 'score')
        self.assertEqual(out['reconciliation']['completed'][0]['detail_ref'], saved)
        self.assertEqual(out['reconciliation']['remaining']['primary'], [])

    def test_same_compilation_with_two_result_files_counts_both_attempts(self):
        first = self.collect(['liepin:new000001'])
        data = {'details': {'primary': [{'candidate_ref': 'liepin:new000001'}]}}
        self.result(first, data)
        self.result(first, {**data, 'run_marker': 'second execution'})
        final = self.collect(['liepin:new000001'])
        self.assertEqual(len(self.receipt(final)['completed']), 1)
        self.assertEqual(len(self.receipt(final)['attempts']), 2)

    def test_score_checkpoint_avoids_second_scoring_dispatch(self):
        import sys
        sys.path.insert(0, str(collection.BUILDER.parent))
        import recovery
        first = self.collect(['liepin:new000001'])
        result_ref = self.result(first, {'details': {'primary': [{'candidate_ref': 'liepin:new000001'}]}})
        before = self.receipt(self.collect(['liepin:new000001']))
        self.assertEqual(before['next_action'], 'score')
        score = {'candidate_ref': 'liepin:new000001', 'detail_ref': result_ref,
                 'detail_section': 'details.primary', 'scored_iteration': 1, 'matches': True,
                 'must_score': 80, 'nice_score': None, 'risk_score': None,
                 'must_unknown': False, 'unknown': [], 'evidence_summary': '明确工程经历'}
        import subprocess
        scores_path = self.root / 'scores.json'
        scores_path.write_text(json.dumps({'candidate_scores': [score], 'labels': [], 'company_hits': [], 'calibration_samples': []}))
        saved = subprocess.run([sys.executable, '-B', str(collection.BUILDER.with_name('recovery.py')),
            '--task-id', 'test-task', '--iteration', '1', '--store-root', str(self.root),
            '--record-scores', str(scores_path)], capture_output=True, text=True)
        self.assertEqual(saved.returncode, 0, saved.stderr)
        after = self.receipt(self.collect(['liepin:new000001']))
        self.assertEqual(after['already_scored'], ['liepin:new000001'])
        self.assertEqual(after['next_action'], 'continue')
        self.assertEqual(len(after['score_files']), 1)
        self.assertEqual(sum(r['next_action'] == 'score' for r in (before, after)), 1)
        changed = {**self.card_workflow['input_plan'], 'requirement_version': 'v2'}
        new = recovery.reconcile(self.root, {'primary': ['liepin:new000001']}, 'test-task:1', changed)
        self.assertEqual(new['already_scored'], [])
        self.assertEqual(new['next_action'], 'score')

    def test_export_partial_saved_details_and_foreign_task(self):
        import subprocess, sys, hashlib
        first = self.collect(['liepin:new000001'])
        result_ref = self.result(first, {'details': {'primary': [{'candidate_ref': 'liepin:new000001', 'full_text': 'SECRET_RESUME'}]}})
        p = self.root / 'result-store/test-task' / (result_ref.rsplit('/', 1)[1] + '.json')
        r = json.loads(p.read_text()); r['status'] = 'error'
        raw = json.dumps(r).encode(); digest = hashlib.sha256(raw).hexdigest()
        p.with_name(digest + '.json').write_bytes(raw)
        result_ref = 'result://test-task/' + digest
        run = subprocess.run([sys.executable, '-B', str(collection.BUILDER.with_name('score_inputs.py')),
            '--task-id', 'new-task', '--result-ref', result_ref, '--result-ref', result_ref,
            '--task-work-dir', str(self.root), '--store-root', str(self.root)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
        out = json.loads(run.stdout)
        self.assertEqual(len(out['entries']), 1)
        self.assertNotIn('SECRET_RESUME', run.stdout)
        self.assertEqual(out['entries'][0]['detail_ref'], result_ref)

    def test_round_receipt_combines_results_and_attempts(self):
        import sys
        sys.path.insert(0, str(collection.BUILDER.parent))
        import recovery
        first = self.collect(['liepin:new000001'])
        one = self.result(first, {'details': {'primary': [{'candidate_ref': 'liepin:new000001'}]}})
        second = self.collect(['liepin:seen00001'])
        two = self.result(second, {'details': {'primary': [{'candidate_ref': 'liepin:seen00001'}]}})
        r = recovery.round_receipt(self.root, 'new-task', 1, 'test-task')
        self.assertEqual(set(r['detail_result_refs']), {one, two})
        self.assertEqual(len(r['occupied']['primary']), 2)
        self.assertEqual(len(r['attempts']), 2)

    def test_failure_only_result_is_in_round_export(self):
        import sys, hashlib, subprocess
        sys.path.insert(0, str(collection.BUILDER.parent))
        import recovery
        first = self.collect(['liepin:new000001'])
        ref = self.result(first, {'failures': {'primary': [{'candidate_ref': 'liepin:new000001',
                                  'error_code': 'WAIT_TIMEOUT'}]}})
        original = self.root / 'result-store/test-task' / (ref.rsplit('/', 1)[1] + '.json')
        result = json.loads(original.read_text()); result['status'] = 'error'
        raw = json.dumps(result).encode(); digest = hashlib.sha256(raw).hexdigest()
        original.unlink(); original.with_name(digest + '.json').write_bytes(raw)
        ref = 'result://test-task/' + digest
        receipt = recovery.round_receipt(self.root, 'test-task', 1)
        self.assertEqual(receipt['result_refs'], [ref])
        self.assertEqual(receipt['detail_result_refs'], [])
        run = subprocess.run([sys.executable, '-B', str(collection.BUILDER.with_name('score_inputs.py')),
            '--task-id', 'test-task', '--result-ref', ref, '--task-work-dir', str(self.root),
            '--store-root', str(self.root)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
        entries = json.loads(run.stdout)['entries']
        self.assertEqual(entries[0]['detail_status'], 'failed')
        self.assertNotIn('profile_path', entries[0])

    def test_generated_workflows_count_actual_page_actions_in_host_interpreter(self):
        import subprocess, shutil
        runtime = Path('/Applications/Domi.app/Contents/Resources/browser-extensions/embedded-workflow')
        if not (runtime / 'content.js').exists() or not shutil.which('node'):
            self.skipTest('Installed Domi interpreter and Node required')
        refs = ['liepin:person0000', 'liepin:person0001', 'liepin:person0002']
        snapshot = {'url': 'https://h.liepin.com/search/getConditionItem#session',
                    'query': 'Agent RAG', 'filters': [], 'page': None}
        cards = [{'candidate_ref': ref, 'card_hard_filter_status': 'unknown', 'search_page': None} for ref in refs]
        self.card_ref = self.result(self.card_workflow, {'candidates': {'primary': cards},
                                                        'search': {'primary': {'list_state': snapshot}}})
        first = self.collect(refs[:2])
        self.result(first, {'details': {'primary': [{'candidate_ref': ref} for ref in refs[:2]]}})
        normal = self.collect(refs)
        self.result(normal, {'search': {'primary': {'collection_check': {'status': 'needs_restore'}}}})
        restored = self.collect(refs, extra=('--restore-search', '--recovery-reason', '列表变化'))
        run = subprocess.run(['node', str(Path(__file__).with_name('recovery_host_probe.js')), str(runtime)],
            input=json.dumps({'normal': normal, 'restored': restored, 'snapshot': snapshot,
                              'cards': cards, 'expected': refs[2:]}), capture_output=True, text=True, timeout=20)
        self.assertEqual(run.returncode, 0, run.stderr)
        actions = json.loads(run.stdout)
        self.assertEqual(actions['normal']['opens'], refs[2:])
        self.assertEqual(actions['changed']['opens'], [])
        self.assertEqual(actions['explicitRestore']['submits'], 1)

    def test_expand_uses_same_continuation_and_keeps_expansion_number(self):
        self.add_cards(4)
        refs = [f'liepin:person{i:04}' for i in range(4)]
        first = self.collect(refs[:1])
        self.result(first, {'details': {'primary': [{'candidate_ref': refs[0]}]}})
        plan = {k: self.card_workflow['input_plan'][k] for k in
                ('requirement_version', 'site_filters', 'hard_filters', 'semantic_criteria')}
        plan.update(query='Agent RAG', source_path='primary', result_ref=self.card_ref,
                    include_candidate_refs=refs[1:3])
        self.write('iteration-1-expand-1.json', plan)
        expansion = self.call('expand', 'iteration-1-expand-1.json', extra=('--expansion', '1'))
        self.assertFalse(any(s['action'] == 'page.navigate' for s in expansion['steps']))
        self.assertNotIn('fill-keyword', json.dumps(expansion['steps']))
        self.result(expansion, {'details': {'expand': [{'candidate_ref': refs[1]}]}})
        again = self.call('expand', 'iteration-1-expand-1.json', extra=('--expansion', '1'))
        self.assertEqual(again['expansion'], 1)
        self.assertEqual(again['limits']['max_tabs'], 0)
        self.assertEqual(self.receipt(again)['uncertain'], refs[2:3])
        plan['include_candidate_refs'] = refs[1:]
        self.write('iteration-1-expand-1.json', plan)
        error = self.call('expand', 'iteration-1-expand-1.json', extra=('--expansion', '1'), ok=False)
        self.assertIn('原名单上限', error['error'])

    def test_refill_shares_occupied_budget_and_preserves_dropped_company(self):
        # A new original search with four eligible people; two saved and two uncertain occupy four slots.
        for p in (self.root / 'workflow-store/test-task').glob('*.json'):
            p.unlink()
        self.plan['primary_query'] = 'Agent RAG DeepSeek'
        self.write('iteration-1.json', self.plan)
        self.card_workflow = self.call('search', 'iteration-1.json')
        self.add_cards(4)
        refs = [f'liepin:person{i:04}' for i in range(4)]
        first = self.collect(refs)
        self.result(first, {'details': {'primary': [{'candidate_ref': r} for r in refs[:2]]}})
        self.write('iteration-1-refill.json', {'dropped_company': 'DeepSeek'})
        refill = self.call('refill', 'iteration-1-refill.json')
        ref = self.result(refill, {'candidates': {'primary': [
            {'candidate_ref': 'liepin:refill001', 'card_hard_filter_status': 'unknown'},
            {'candidate_ref': 'liepin:refill002', 'card_hard_filter_status': 'unknown'}]}})
        self.write('iteration-1-refill-collect.json', {'result_ref': ref, 'primary': ['liepin:refill001', 'liepin:refill002']})
        self.assertIn('累计采集', self.call('collect', 'iteration-1-refill-collect.json', ok=False)['error'])
        self.write('iteration-1-refill-collect.json', {'result_ref': ref, 'primary': ['liepin:refill001']})
        collect = self.call('collect', 'iteration-1-refill-collect.json')
        self.assertEqual(collect['input_plan']['primary_query'], 'Agent RAG')
        self.assertEqual(collect['limits']['max_tabs'], 1)
        self.assertNotIn('DeepSeek', json.dumps(collect['steps']))

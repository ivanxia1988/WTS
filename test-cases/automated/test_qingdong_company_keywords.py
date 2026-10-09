"""Company keywords bypass the failing native control throughout collection/refill."""
import argparse
import copy
import json
import unittest
from unittest.mock import patch
import test_qingdong_collection as collection
from test_qingdong_native_company import builder


class CompanyKeywordTests(unittest.TestCase):
    setUp = collection.CollectionTests.setUp
    tearDown = collection.CollectionTests.tearDown
    write = collection.CollectionTests.write
    call = collection.CollectionTests.call
    result = collection.CollectionTests.result

    def keyword_search(self, hard=None, cards=None):
        for p in (self.root / 'workflow-store/test-task').glob('*.json'):
            p.unlink()
        self.plan.update(primary_query='AI Agent RAG Prompt DeepSeek',
                         site_filters={'activity_recency': 'within_7_days'},
                         hard_filters=hard or {})
        self.write('iteration-1.json', self.plan)
        workflow = self.call('search', 'iteration-1.json')
        ref = self.result(workflow, {'candidates': {'primary': cards or []}})
        self.write('iteration-1-refill.json', {'dropped_company': 'DeepSeek'})
        return workflow, ref

    def assert_no_company_control(self, workflow):
        self.assertNotIn('company', workflow['input_plan']['site_filters'])
        self.assertNotIn('company-trigger', json.dumps(workflow))
        self.assertNotIn('fill-company-input', json.dumps(workflow))

    def test_search_collect_refill_preserve_keywords_and_other_conditions(self):
        hard = {'education': ['本科', '硕士', '博士/博士后']}
        workflow, ref = self.keyword_search(hard, [
            {'candidate_ref': 'liepin:new000001', 'card_hard_filter_status': 'unknown'}])
        self.assert_no_company_control(workflow)
        self.assertIn('DeepSeek', workflow['input_plan']['primary_query'])
        self.assertIn('先采集', self.call('refill', 'iteration-1-refill.json', ok=False)['error'])
        self.write('iteration-1-collect.json', {'result_ref': ref, 'primary': ['liepin:new000001']})
        collect = self.call('collect', 'iteration-1-collect.json')
        self.assert_no_company_control(collect)
        self.assertEqual(collect['input_plan']['primary_query'], self.plan['primary_query'])
        self.result(collect, {'details': {'primary': []}})
        refill = self.call('refill', 'iteration-1-refill.json')
        self.assert_no_company_control(refill)
        self.assertEqual(refill['input_plan']['primary_query'], 'AI Agent RAG Prompt')
        self.assertEqual(refill['input_plan']['hard_filters'], hard)
        self.assertEqual(refill['input_plan']['site_filters'], self.plan['site_filters'])
        self.assertIn('状态未确认', self.call('refill', 'iteration-1-refill.json', ok=False)['error'])

    def test_company_hard_requirement_cannot_be_dropped(self):
        workflow, _ = self.keyword_search({'company': ['DeepSeek']})
        self.assert_no_company_control(workflow)
        self.assertIn('硬性条件', self.call('refill', 'iteration-1-refill.json', ok=False)['error'])

    def test_exploration_and_refill_expansion_do_not_restore_company_control(self):
        workflow, _ = self.keyword_search()
        plan = copy.deepcopy(workflow['input_plan'])
        plan['secondary_query'] = 'AI Agent Memory'
        plan['limits']['secondary_max_details'] = 3
        args = argparse.Namespace(task_id='test-task', iteration=2, task_work_dir=str(self.root),
                                  store_root=str(self.root), interaction_mode=None, deadline_minutes=20)
        two_paths = builder.build_search(args, builder.load_assets(), source_plan=plan)
        self.assert_no_company_control(two_paths)
        self.assertNotIn('DeepSeek', json.dumps([s for s in two_paths['steps'] if s['id'].startswith('secondary-')]))
        refill = self.call('refill', 'iteration-1-refill.json')
        self.result(refill, {'candidates': {'primary': [{'candidate_ref': 'liepin:new000001', 'card_hard_filter_status': 'unknown'}]}})
        expansion = {k: copy.deepcopy(workflow['input_plan'][k]) for k in
                     ('requirement_version', 'site_filters', 'hard_filters', 'semantic_criteria')}
        expansion.update(source_path='refill', query='AI Agent RAG Prompt', include_candidate_refs=['liepin:new000001'])
        self.write('iteration-1-expand-1.json', expansion)
        args.iteration = 1
        args.expansion = 1
        args.plan_file = str(self.plans / 'iteration-1-expand-1.json')
        with patch.object(builder, 'executed_plan', return_value=workflow['input_plan']):
            expanded = builder.build_expand(args, builder.load_assets())
        self.assertNotIn('company-trigger', json.dumps(expanded))
        self.assertNotIn('fill-company-input', json.dumps(expanded))
        self.assertNotIn('detail-hard-filter', json.dumps(expanded))
        self.assertEqual(expanded['steps'][-1]['value']['details']['expand'],
                         {'$context': 'details_expand'})

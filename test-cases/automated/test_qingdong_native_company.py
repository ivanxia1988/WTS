"""Native targeting preserves exploration, refill and expansion source filters."""
import copy
import importlib.util
import json
import sys
from unittest.mock import patch
import unittest
import test_qingdong_collection as collection
BUILDER = collection.BUILDER

sys.path.insert(0, str(BUILDER.parent))
spec = importlib.util.spec_from_file_location('qingdong_native_builder', BUILDER)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
# Load the collaborator pacing implementation explicitly; baseline tests use a sibling module of the same name.
pacing_spec = importlib.util.spec_from_file_location('qingdong_pacing', BUILDER.with_name('pacing.py'))
pacing = importlib.util.module_from_spec(pacing_spec)
pacing_spec.loader.exec_module(pacing)
builder.pace_search_path = pacing.pace_search_path



class NativeCompanyTests(unittest.TestCase):
    setUp = collection.CollectionTests.setUp
    tearDown = collection.CollectionTests.tearDown
    write = collection.CollectionTests.write
    call = collection.CollectionTests.call
    result = collection.CollectionTests.result

    def test_company_input_is_activated_before_waiting_for_combobox(self):
        assets = builder.load_assets()
        config = assets['channel']['filters']['company']
        program = builder.compile_company_filter_program('网易', config, assets['channel'], 1200)
        # Collapsed company control exposes its placeholder; combobox only exists after activation.
        activated = False
        filled = False
        for step in program:
            if step['op'] == 'page.click' and step['target'].get('within') == config['row']:
                if step['target'].get('any_css') == ["input[placeholder='搜索公司']", '.ant-select-selection-placeholder']:
                    activated = True
            if step['op'] == 'page.wait' and step['until'].get('target', {}).get('css') == "input[role='combobox']":
                self.assertTrue(activated, 'WAIT_TIMEOUT: company combobox is absent until the visible control is clicked')
            if step['op'] == 'page.fill':
                self.assertTrue(activated)
                filled = True
                break
        self.assertTrue(filled)

    def native_search(self, hard=None):
        for p in (self.root / "workflow-store/test-task").glob("*.json"):
            p.unlink()
        self.plan['site_filters'] = {'company': ['阿里巴巴'], 'activity_recency': 'within_7_days'}
        self.plan['hard_filters'] = {'company': hard} if hard else {}
        self.write('iteration-1.json', self.plan)
        self.card_workflow = self.call('search', 'iteration-1.json')
        self.card_ref = self.result(self.card_workflow, {'candidates': {'primary': []}})
        self.write('iteration-1-refill.json', {'dropped_company': '阿里巴巴'})

    def test_native_refill_keeps_query_and_preferences(self):
        self.native_search(['阿里巴巴', '腾讯'])
        w = self.call('refill', 'iteration-1-refill.json')
        self.assertEqual(w['input_plan']['primary_query'], 'Agent RAG')
        self.assertEqual(w['input_plan']['site_filters'], {'activity_recency': 'within_7_days'})
        self.assertEqual(w['input_plan']['hard_filters'], self.plan['hard_filters'])
        self.assertNotIn('fill-company-input', json.dumps(w))
        self.assertIn('状态未确认', self.call('refill', 'iteration-1-refill.json', ok=False)['error'])

    def test_native_refill_rejects_wrong_company_and_single_hard_company(self):
        self.native_search(['阿里巴巴'])
        self.assertIn('硬性条件', self.call('refill', 'iteration-1-refill.json', ok=False)['error'])
        self.write('iteration-1-refill.json', {'dropped_company': '腾讯'})
        self.assertIn('dropped_company', self.call('refill', 'iteration-1-refill.json', ok=False)['error'])

    def test_two_paths_compile_distinct_company_filters(self):
        import argparse
        self.native_search()
        plan = copy.deepcopy(self.card_workflow['input_plan'])
        plan['secondary_query'] = 'Agent Memory'
        plan['limits']['secondary_max_details'] = 3
        args = argparse.Namespace(task_id='test-task', iteration=2, task_work_dir=str(self.root),
                                  store_root=str(self.root), interaction_mode=None, deadline_minutes=20)
        # Source-plan compilation is also the real collect path; no scoring setup needed.
        w = builder.build_search(args, builder.load_assets(), source_plan=plan)
        primary = json.dumps([s for s in w['steps'] if s['id'].startswith('primary-')])
        secondary = json.dumps([s for s in w['steps'] if s['id'].startswith('secondary-')])
        self.assertIn('fill-company-input', primary)
        self.assertNotIn('fill-company-input', secondary)
        self.assertIn('activity_recency', secondary)
        plan['hard_filters']['company'] = ['阿里巴巴']
        w = builder.build_search(args, builder.load_assets(), source_plan=plan)
        self.assertIn('fill-company-input', json.dumps([s for s in w['steps'] if s['id'].startswith('secondary-')]))

    def test_expansion_distinguishes_same_query_before_and_after_refill(self):
        import argparse
        self.native_search()
        refill = self.call('refill', 'iteration-1-refill.json')
        self.result(refill, {'candidates': {'primary': [{'candidate_ref': 'liepin:new000001', 'card_hard_filter_status': 'unknown'}]}})
        plan = {k: copy.deepcopy(self.card_workflow['input_plan'][k])
                for k in ('requirement_version', 'site_filters', 'hard_filters', 'semantic_criteria')}
        plan.update(query='Agent RAG', include_candidate_refs=['liepin:new000001'])
        self.write('iteration-1-expand-1.json', plan)
        args = argparse.Namespace(task_id='test-task', iteration=1, expansion=1,
                                  plan_file=str(self.plans/'iteration-1-expand-1.json'),
                                  task_work_dir=str(self.root), store_root=str(self.root), interaction_mode=None, deadline_minutes=20)
        # Isolate source-filter validation from score/collection prerequisites covered elsewhere.
        with patch.object(builder, 'executed_plan', return_value=self.card_workflow['input_plan']):
            with self.assertRaisesRegex(ValueError, 'source_path'):
                builder.build_expand(args, builder.load_assets())
            plan['source_path'] = 'refill'
            self.write('iteration-1-expand-1.json', plan)
            with self.assertRaisesRegex(ValueError, '卡片结果一致'):
                builder.build_expand(args, builder.load_assets())
            plan['site_filters'].pop('company')
            self.write('iteration-1-expand-1.json', plan)
            w = builder.build_expand(args, builder.load_assets())
            self.assertNotIn('fill-company-input', json.dumps(w))

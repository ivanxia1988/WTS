"""Exercise evidence completeness through the collaborator's actual receipt builder."""
import importlib.util
from pathlib import Path

import test_decision_basis as fixtures

SCRIPT = Path(__file__).resolve().parents[2] / 'source/scripts/decision_basis.py'
spec = importlib.util.spec_from_file_location('source_decision_basis', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class EvidenceCompletenessTests(fixtures.unittest.TestCase):
    def setUp(self):
        fixtures.DecisionBasisTests.setUp(self)

    def tearDown(self):
        fixtures.DecisionBasisTests.tearDown(self)

    score = fixtures.DecisionBasisTests.score
    plan = fixtures.DecisionBasisTests.plan

    def evaluate(self, row, *, settle=False, report=None):
        plan = self.plan([row])
        if settle:
            plan['decision_basis']['next_action'] = {'action': 'report', 'reason': '完成'}
        return module.decision_receipt(plan, iteration=2, task_id=self.task_id,
                                       store_root=self.store, settle=settle, report_data=report)

    def strong_score(self):
        return {**self.score(), 'must_score': 90, 'nice_score': 90, 'risk_score': 0,
                'must_unknown': False}

    def test_must_unknown_keeps_score_and_recommendation_but_removes_strong(self):
        row = self.strong_score()
        known = self.evaluate(row)
        row.update(must_unknown=True, unknown=['必须满足：Python 精通程度未核实'])
        unknown = self.evaluate(row)
        self.assertEqual(known['scores'], unknown['scores'])
        self.assertEqual(unknown['counts']['recommendable'], 1)
        self.assertEqual(known['counts']['strong'], 1)
        self.assertEqual(unknown['counts']['strong'], 0)
        self.assertEqual(unknown['counts']['new_strong'], 0)
        report = {}
        self.evaluate(row, settle=True, report=report)
        self.assertFalse(report['candidates'][0]['strong'])
        self.assertTrue(report['candidates'][0]['recommendable'])
        self.assertEqual(report['candidates'][0]['unknown'], row['unknown'])

    def test_nice_unknown_does_not_block_strong(self):
        row = self.strong_score()
        row['unknown'] = ['加分项：开源贡献未核实']
        self.assertEqual(self.evaluate(row)['counts']['strong'], 1)

    def test_missing_or_non_boolean_flag_cannot_silently_count_as_strong(self):
        for value in (None, 'false', 0):
            with self.subTest(value=value):
                row = self.strong_score()
                if value is None:
                    del row['must_unknown']
                else:
                    row['must_unknown'] = value
                with self.assertRaisesRegex(ValueError, 'must_unknown'):
                    self.evaluate(row)

    def test_unknown_flag_requires_explanation(self):
        row = self.strong_score()
        row['must_unknown'] = True
        with self.assertRaisesRegex(ValueError, 'unknown'):
            self.evaluate(row)

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "source" / "scripts"))

from decision_basis import decision_receipt  # noqa: E402


class DecisionBasisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.store = Path(self.temporary.name)
        self.task_id = "task-1"
        result = {
            "data": {
                "details": {
                    "primary": [
                        {
                            "candidate_ref": "liepin:candidate-1",
                            "detail_hard_filter_status": "matched",
                            "display_name": "候选人甲",
                            "detail_url": "https://h.liepin.com/resume/showresumedetail/?id=1",
                            "work_experience_summary": "负责 LangGraph Agent 平台",
                            "project_experience_summary": "建设 RAG 平台",
                        }
                    ],
                    "secondary": [],
                },
                "search": {"primary": {"query": "AI Agent"}, "secondary": {}},
            }
        }
        raw = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()
        digest = hashlib.sha256(raw).hexdigest()
        path = self.store / "result-store" / self.task_id / f"{digest}.json"
        path.parent.mkdir(parents=True)
        path.write_bytes(raw)
        self.detail_ref = f"result://{self.task_id}/{digest}"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def score(self) -> dict:
        return {
            "candidate_ref": "liepin:candidate-1",
            "detail_ref": self.detail_ref,
            "detail_section": "details.primary",
            "scored_iteration": 1,
            "matches": True,
            "must_score": 80,
            "nice_score": 60,
            "risk_score": 20,
            "unknown": [],
            "evidence_summary": "具备 Agent 项目证据",
        }

    def plan(self, scores: list[dict] | None = None) -> dict:
        return {
            "requirement_version": "v1",
            "primary_query": "AI Agent",
            "semantic_criteria": {
                "must_have": ["Agent 经验"],
                "nice_to_have": ["RAG"],
                "exclude_signals": ["纯销售"],
            },
            "hard_filters": {"expected_cities": ["上海"]},
            "decision_basis": {
                "requirement_version": "v1",
                "completed_iteration": 1,
                "candidate_scores": [self.score()] if scores is None else scores,
                "prf_decision": {"status": "none", "reason": "暂无稳定新词"},
                "next_action": {
                    "action": "search",
                    "iteration": 2,
                    "primary_query": "AI Agent",
                    "reason": "继续补充样本",
                },
            },
        }

    def test_computes_deterministic_weighted_score_and_top10(self) -> None:
        receipt = decision_receipt(
            self.plan(),
            iteration=2,
            task_id=self.task_id,
            store_root=self.store,
        )
        self.assertEqual(receipt["scores"][0]["total"], 75)
        self.assertEqual(receipt["top10"], ["liepin:candidate-1"])
        self.assertEqual(receipt["counts"]["recommendable"], 1)

    def test_rejects_same_requirement_version_criteria_drift(self) -> None:
        previous = self.plan()
        current = self.plan()
        current["semantic_criteria"]["must_have"] = ["完全不同的条件"]
        with self.assertRaisesRegex(ValueError, "同一需求版本"):
            decision_receipt(
                current,
                iteration=2,
                task_id=self.task_id,
                store_root=self.store,
                previous_plan=previous,
            )

    def test_rejects_dropping_historical_scores(self) -> None:
        with self.assertRaisesRegex(ValueError, "保留历史"):
            decision_receipt(
                self.plan(scores=[]),
                iteration=2,
                task_id=self.task_id,
                store_root=self.store,
                previous_plan=self.plan(),
            )

    def test_rejects_result_reference_from_another_task(self) -> None:
        plan = self.plan()
        plan["decision_basis"]["candidate_scores"][0]["detail_ref"] = self.detail_ref.replace(
            self.task_id, "other-task"
        )
        with self.assertRaisesRegex(ValueError, "当前任务"):
            decision_receipt(
                plan,
                iteration=2,
                task_id=self.task_id,
                store_root=self.store,
            )


if __name__ == "__main__":
    unittest.main()

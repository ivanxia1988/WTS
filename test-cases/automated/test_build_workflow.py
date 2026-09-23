from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = REPO_ROOT / "source" / "scripts"
sys.path.insert(0, str(SCRIPT_ROOT))

import build_workflow  # noqa: E402


class BuildWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assets = build_workflow.load_assets()
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def args(self, workflow_type: str, iteration: int, plan: dict | None = None):
        plan_path = self.root / f"{workflow_type}-{iteration}.json"
        if plan is not None:
            plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        return argparse.Namespace(
            workflow_type=workflow_type,
            task_id="task-1",
            iteration=iteration,
            plan_file=str(plan_path),
            decision_file="",
            task_work_dir=str(self.root),
            store_root=str(self.root),
            deadline_minutes=20,
            interaction_mode=None,
        )

    def search_plan(self) -> dict:
        return {
            "requirement_version": "v1",
            "primary_query": "AI Agent LangGraph",
            "site_filters": {},
            "hard_filters": {},
            "semantic_criteria": {
                "must_have": ["Agent 经验"],
                "nice_to_have": [],
                "exclude_signals": [],
            },
        }

    def persist_completed_search(
        self, primary_query: str = "AI Agent LangGraph"
    ) -> tuple[argparse.Namespace, dict, str]:
        task_dir = self.root / "wts" / "search-plans"
        task_dir.mkdir(parents=True)
        plan_path = task_dir / "iteration-1.json"
        plan = {**self.search_plan(), "primary_query": primary_query}
        plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        args = self.args("search", 1)
        args.plan_file = str(plan_path)
        workflow = build_workflow.build_search(args, self.assets)
        saved = build_workflow.save_workflow(workflow, self.root)
        card_result = {
            "status": "success",
            "workflow": {
                "workflow_id": workflow["workflow_id"],
                "task_id": args.task_id,
                "finished_at": "2026-09-19T03:00:00Z",
            },
            "data": {
                "candidates": {
                    "primary": [
                        {
                            "candidate_ref": "liepin:candidate-1",
                            "card_hard_filter_status": "matched",
                        }
                    ]
                },
                "search": {"primary": {"query": primary_query}, "secondary": {}},
            },
        }
        card_raw = json.dumps(card_result, ensure_ascii=False, separators=(",", ":")).encode()
        card_digest = hashlib.sha256(card_raw).hexdigest()
        result_dir = self.root / "result-store" / args.task_id
        result_dir.mkdir(parents=True)
        (result_dir / f"{card_digest}.json").write_bytes(card_raw)

        collect_path = task_dir / "iteration-1-collect.json"
        collect_path.write_text(
            json.dumps(
                {
                    "result_ref": f"result://{args.task_id}/{card_digest}",
                    "primary": ["liepin:candidate-1"],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        collect_args = self.args("collect", 1)
        collect_args.plan_file = str(collect_path)
        collect_args.refill_collect = False
        collect = build_workflow.build_collect(collect_args, self.assets)
        build_workflow.save_workflow(collect, self.root)

        detail_result = {
            "status": "success",
            "workflow": {
                "workflow_id": collect["workflow_id"],
                "task_id": args.task_id,
                "finished_at": "2026-09-19T03:01:00Z",
            },
            "data": {
                "details": {
                    "primary": [
                        {
                            "candidate_ref": "liepin:candidate-1",
                            "detail_hard_filter_status": "matched",
                            "display_name": "候选人甲",
                            "detail_url": "https://h.liepin.com/resume/showresumedetail/?id=1",
                            "work_experience_summary": "负责 Agent 平台",
                        }
                    ],
                    "secondary": [],
                },
                "search": {"primary": {"query": primary_query}, "secondary": {}},
            },
        }
        raw = json.dumps(detail_result, ensure_ascii=False, separators=(",", ":")).encode()
        result_digest = hashlib.sha256(raw).hexdigest()
        result_path = self.root / "result-store" / args.task_id / f"{result_digest}.json"
        result_path.write_bytes(raw)
        self.assertTrue(saved["workflow_ref"].startswith("wf://"))
        return args, plan, result_digest

    def test_current_preflight_search_and_collect_compile(self) -> None:
        preflight = build_workflow.build_preflight(self.args("preflight", 0), self.assets)
        self.assertTrue(any(step["id"] == "open-channel-search" for step in preflight["steps"]))

        search = build_workflow.build_search(
            self.args(
                "search",
                1,
                {
                    "primary_query": "AI Agent LangGraph",
                    "site_filters": {},
                    "hard_filters": {},
                    "semantic_criteria": {
                        "must_have": ["Agent 经验"],
                        "nice_to_have": [],
                        "exclude_signals": [],
                    },
                },
            ),
            self.assets,
        )
        self.assertTrue(any("pacing" in json.dumps(step) for step in search["steps"]))
        self.assertEqual(search["input_summary"]["stage"], "cards")
        self.assertFalse(any(step["action"] == "tabs.foreach" for step in search["steps"]))

        self.persist_completed_search()
        workflows = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in (self.root / "workflow-store" / "task-1").glob("*.json")
        ]
        collect = next(
            item for item in workflows if item.get("input_summary", {}).get("stage") == "details"
        )
        self.assertTrue(any(step["action"] == "tabs.foreach" for step in collect["steps"]))

    def test_channel_default_compiles_human_interaction_metadata(self) -> None:
        workflow = build_workflow.build_preflight(self.args("preflight", 0), self.assets)
        self.assertEqual(workflow["interaction_mode"], "human")
        self.assertIn("interaction.human.v1", workflow["required_capabilities"])

    def test_direct_override_omits_human_capability(self) -> None:
        args = self.args("preflight", 0)
        args.interaction_mode = "direct"
        workflow = build_workflow.build_preflight(args, self.assets)
        self.assertEqual(workflow["interaction_mode"], "direct")
        self.assertNotIn("interaction.human.v1", workflow["required_capabilities"])

    def test_human_search_returns_cards_without_removing_pacing(self) -> None:
        workflow = build_workflow.build_search(
            self.args(
                "search",
                1,
                {
                    "primary_query": "AI Agent LangGraph",
                    "site_filters": {},
                    "hard_filters": {},
                    "semantic_criteria": {
                        "must_have": ["Agent 经验"],
                        "nice_to_have": [],
                        "exclude_signals": [],
                    },
                },
            ),
            self.assets,
        )
        encoded = json.dumps(workflow, ensure_ascii=False)
        self.assertNotIn('"action": "tabs.foreach"', encoded)
        self.assertEqual(workflow["input_summary"]["stage"], "cards")
        self.assertIn("pacing-before", encoded)

    def test_site_only_filters_normalize_and_compile(self) -> None:
        plan, warnings = build_workflow.normalize_plan(
            {
                "site_filters": {
                    "company": ["阿里巴巴"],
                    "activity_recency": "within_7_days",
                    "job_hop_frequency": "last_3_years_max_2",
                    "age_range": {"min": 25, "max": 40},
                    "gender": "male",
                },
                "hard_filters": {"company": ["阿里巴巴", "字节跳动"]},
            }
        )

        self.assertEqual(warnings, [])
        self.assertEqual(plan["site_filters"]["company"], ["阿里巴巴"])
        self.assertEqual(
            plan["hard_filters"]["company"], ["阿里巴巴", "字节跳动"]
        )

        program = build_workflow.compile_site_filter_program(
            plan, self.assets["channel"], action_delay_ms=800
        )
        self.assertEqual(
            [step["id"] for step in program],
            [
                "apply-filter-company",
                "apply-filter-age_range",
                "apply-filter-gender",
                "apply-filter-activity_recency",
                "apply-filter-job_hop_frequency",
            ],
        )
        encoded = json.dumps(program, ensure_ascii=False)
        for marker in (
            "read-company-list-id",
            "require-unique-company-suggestion",
            "confirm-filter-company",
            "verify-filter-gender-applied",
            "verify-filter-activity_recency-applied",
            "verify-filter-job_hop_frequency-applied",
            "阿里巴巴",
            "男",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, encoded)

    def test_site_only_filter_validation_boundaries(self) -> None:
        invalid_plans = (
            (
                {"site_filters": {"company": ["阿里巴巴", "字节跳动"]}},
                "site_filters.company 最多包含 1 个值",
            ),
            (
                {"site_filters": {"activity_recency": "recently"}},
                "site_filters.activity_recency 必须是单个预设字符串",
            ),
            (
                {"site_filters": {"age_range": {"min": 15, "max": 40}}},
                "site_filters.age_range.min 必须在 16-60 之间",
            ),
            (
                {"hard_filters": {"age_range": {"min": 25, "max": 40}}},
                "年龄、性别不参与硬筛或评分",
            ),
            (
                {"hard_filters": {"gender": "female"}},
                "年龄、性别不参与硬筛或评分",
            ),
        )
        for plan, message in invalid_plans:
            with self.subTest(plan=plan):
                with self.assertRaisesRegex(ValueError, message):
                    build_workflow.normalize_plan(plan)

    def test_integrated_collaborator_release_versions(self) -> None:
        self.assertEqual(build_workflow.SKILL_VERSION, "0.7.1")
        self.assertEqual(
            self.assets["channel"]["rule_version"], "liepin-2026.09.22.2"
        )

    def test_human_refill_drops_company_after_initial_collection(self) -> None:
        args, _, _ = self.persist_completed_search("AI Agent LangGraph 阿里巴巴")
        refill_path = self.root / "wts" / "search-plans" / "iteration-1-refill.json"
        refill_path.write_text(
            json.dumps({"dropped_company": "阿里巴巴"}, ensure_ascii=False),
            encoding="utf-8",
        )
        args.workflow_type = "refill"
        args.plan_file = str(refill_path)
        workflow = build_workflow.build_refill(args, self.assets)
        self.assertEqual(workflow["interaction_mode"], "human")
        self.assertTrue(workflow["refill"])
        self.assertEqual(workflow["input_summary"]["stage"], "cards")
        self.assertEqual(workflow["input_plan"]["primary_query"], "AI Agent LangGraph")

    def test_search_plan_accepts_requirement_version_and_decision_basis(self) -> None:
        path = self.root / "plan.json"
        basis = {
            "requirement_version": "v1",
            "completed_iteration": 0,
            "candidate_scores": [],
            "prf_decision": {"status": "none", "reason": "首轮尚无候选人"},
            "next_action": {
                "action": "search",
                "iteration": 1,
                "primary_query": "AI Agent",
                "reason": "开始首轮",
            },
        }
        path.write_text(
            json.dumps(
                {
                    "requirement_version": "v1",
                    "primary_query": "AI Agent",
                    "site_filters": {},
                    "hard_filters": {},
                    "semantic_criteria": {
                        "must_have": ["Agent 经验"],
                        "nice_to_have": [],
                        "exclude_signals": [],
                    },
                    "decision_basis": basis,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        plan, _ = build_workflow.read_plan(str(path))
        self.assertEqual(plan["requirement_version"], "v1")
        self.assertEqual(plan["decision_basis"], basis)
        args = self.args("search", 1, json.loads(path.read_text(encoding="utf-8")))
        workflow = build_workflow.build_search(args, self.assets)
        self.assertEqual(workflow["input_summary"]["requirement_version"], "v1")
        self.assertEqual(args.decision_receipt["completed_iteration"], 0)

    def test_recovers_plan_from_completed_workflow_not_edited_plan_file(self) -> None:
        args, original, _ = self.persist_completed_search()
        workflow_files = list((self.root / "workflow-store" / args.task_id).glob("*.json"))
        persisted = json.loads(workflow_files[0].read_text(encoding="utf-8"))
        self.assertEqual(persisted["input_plan"]["primary_query"], original["primary_query"])
        self.assertEqual(
            persisted["input_plan"]["semantic_criteria"], original["semantic_criteria"]
        )

        Path(args.plan_file).write_text(
            json.dumps({**original, "primary_query": "被回改的关键词"}, ensure_ascii=False),
            encoding="utf-8",
        )
        recovered = build_workflow.executed_plan(args, 1)
        self.assertEqual(recovered["primary_query"], "AI Agent LangGraph")

    def test_settlement_writes_private_final_report_data(self) -> None:
        args, _, result_digest = self.persist_completed_search()
        decision_dir = self.root / "wts"
        decision_path = decision_dir / "final-decision.json"
        decision = {
            "requirement_version": "v1",
            "completed_iteration": 1,
            "candidate_scores": [
                {
                    "candidate_ref": "liepin:candidate-1",
                    "detail_ref": f"result://{args.task_id}/{result_digest}",
                    "detail_section": "details.primary",
                    "scored_iteration": 1,
                    "matches": True,
                    "must_score": 80,
                    "nice_score": None,
                    "risk_score": None,
                    "must_unknown": False,
                    "unknown": [],
                    "evidence_summary": "有 Agent 平台经历",
                }
            ],
            "prf_decision": {"status": "none", "reason": "已结束搜索"},
            "next_action": {"action": "report", "reason": "达到交付条件"},
        }
        decision_path.write_text(json.dumps(decision, ensure_ascii=False), encoding="utf-8")
        args.workflow_type = "settle"
        args.decision_file = str(decision_path)
        result = build_workflow.settle_search(args)
        report_path = Path(result["report_data_file"])
        self.assertTrue(report_path.is_file())
        self.assertEqual(stat.S_IMODE(report_path.stat().st_mode), 0o600)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["candidates"][0]["display_name"], "候选人甲")
        self.assertEqual(result["next_action"]["action"], "report")


if __name__ == "__main__":
    unittest.main()

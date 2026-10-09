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

    def persist_result(self, workflow: dict, data: dict) -> str:
        build_workflow.save_workflow(workflow, self.root)
        result = {
            "status": "success",
            "workflow": {
                "workflow_id": workflow["workflow_id"],
                "task_id": workflow["task_id"],
                "finished_at": "2026-09-19T03:00:00Z",
            },
            "data": data,
        }
        raw = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()
        digest = hashlib.sha256(raw).hexdigest()
        path = self.root / "result-store" / workflow["task_id"] / f"{digest}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return digest

    def persist_cards(self, plan: dict | None = None):
        plan = self.search_plan() if plan is None else plan
        task_dir = self.root / "wts" / "search-plans"
        task_dir.mkdir(parents=True, exist_ok=True)
        args = self.args("search", 1)
        args.plan_file = str(task_dir / "iteration-1.json")
        Path(args.plan_file).write_text(json.dumps(plan, ensure_ascii=False))
        workflow = build_workflow.build_search(args, self.assets)
        digest = self.persist_result(workflow, {
            "candidates": {"primary": [{"candidate_ref": "liepin:candidate-1",
                                         "card_hard_filter_status": "matched"}]},
            "details": {"primary": []},
        })
        return args, plan, workflow, digest

    def compile_collect(self, args, card_digest):
        collect_args = self.args("collect", 1)
        collect_args.plan_file = str(self.root / "wts/search-plans/iteration-1-collect.json")
        Path(collect_args.plan_file).write_text(json.dumps({
            "result_ref": f"result://{args.task_id}/{card_digest}",
            "primary": ["liepin:candidate-1"],
        }))
        return build_workflow.build_collect(collect_args, self.assets)

    def persist_completed_round(self, plan: dict | None = None):
        args, plan, _, card_digest = self.persist_cards(plan)
        workflow = self.compile_collect(args, card_digest)
        digest = self.persist_result(workflow, {
            "details": {"primary": [{
                "candidate_ref": "liepin:candidate-1",
                "detail_hard_filter_status": "matched",
                "display_name": "候选人甲",
                "detail_url": "https://h.liepin.com/resume/showresumedetail/?id=1",
                "work_experience_summary": "负责 Agent 平台",
            }], "secondary": []},
            "search": {"primary": {"query": plan["primary_query"]}, "secondary": {}},
        })
        return args, plan, digest

    def test_preflight_then_search_returns_cards_without_opening_details(self) -> None:
        preflight = build_workflow.build_preflight(self.args("preflight", 0), self.assets)
        self.assertTrue(any(step["id"] == "open-channel-search" for step in preflight["steps"]))
        _, _, search, _ = self.persist_cards()
        self.assertEqual(search["input_summary"]["stage"], "cards")
        self.assertEqual(search["limits"]["max_tabs"], 0)
        self.assertFalse(any(step["action"] == "tabs.foreach" for step in search["steps"]))
        self.assertIn("pacing-before", json.dumps(search))

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

    def test_collect_browses_selected_details_with_pacing(self) -> None:
        args, _, _, digest = self.persist_cards()
        workflow = self.compile_collect(args, digest)
        self.assertEqual(workflow["interaction_mode"], "human")
        self.assertEqual(workflow["input_summary"]["stage"], "details")
        tabs = [step for step in workflow["steps"] if step["action"] == "tabs.foreach"]
        self.assertEqual(len(tabs), 1)
        self.assertEqual(tabs[0]["max_items"], 1)
        encoded = json.dumps(workflow, ensure_ascii=False)
        self.assertIn('"op": "page.scroll"', encoded)
        self.assertIn("pacing-before-primary-extract-detail", encoded)
        # Normal detail path excludes conditional page-restoration waits.
        detail = tabs[0]
        programs = [detail["open"]["pre_program"], detail["open"]["program"],
                    *[step["program"] for step in detail["steps"]]]
        delays = [step["until"]["ms"] for program in programs for step in program
                  if step.get("op") == "page.wait"
                  and step.get("until", {}).get("type") == "delay"]
        self.assertTrue(all(delay > 0 for delay in delays))
        self.assertEqual(sum(delays), 15000)

    def test_card_only_round_cannot_be_used_for_settlement(self) -> None:
        args, _, _, _ = self.persist_cards()
        with self.assertRaisesRegex(ValueError, "先执行 collect"):
            build_workflow.executed_plan(args, 1)

    def test_refill_drops_company_after_collection_and_only_once(self) -> None:
        plan = self.search_plan()
        plan["primary_query"] += " 阿里巴巴"
        args, _, _ = self.persist_completed_round(plan)
        args.workflow_type = "refill"
        args.plan_file = str(self.root / "wts/search-plans/iteration-1-refill.json")
        Path(args.plan_file).write_text(json.dumps({"dropped_company": "阿里巴巴"}))
        workflow = build_workflow.build_refill(args, self.assets)
        self.assertEqual(workflow["interaction_mode"], "human")
        self.assertEqual(workflow["input_plan"]["primary_query"], "AI Agent LangGraph")
        self.assertEqual(workflow["input_plan"]["hard_filters"], plan["hard_filters"])
        self.assertEqual(workflow["input_summary"]["stage"], "cards")
        build_workflow.save_workflow(workflow, self.root)
        with self.assertRaisesRegex(ValueError, "只能补搜一次"):
            build_workflow.build_refill(args, self.assets)

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
        args, original, _ = self.persist_completed_round()
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
        args, _, result_digest = self.persist_completed_round()
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

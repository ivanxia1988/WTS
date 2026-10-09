from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "source/scripts"))

import build_workflow  # noqa: E402


class SkillContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.skill = (REPO_ROOT / "source" / "SKILL.md").read_text(encoding="utf-8")
        self.search_plan = (REPO_ROOT / "source" / "references" / "search-plan.md").read_text(
            encoding="utf-8"
        )
        self.scoring = (REPO_ROOT / "source" / "references" / "scoring.md").read_text(
            encoding="utf-8"
        )
        self.final_report = (
            REPO_ROOT / "source" / "references" / "final-report.md"
        ).read_text(encoding="utf-8")
        self.all_text = "\n".join(
            [self.skill, self.search_plan, self.scoring, self.final_report]
        )

    def test_documented_skill_resources_exist(self) -> None:
        resources = re.findall(r"(?:references/[\w.-]+\.md|scripts/[\w.-]+\.py)", self.all_text)
        self.assertTrue(resources)
        for resource in set(resources):
            with self.subTest(resource=resource):
                self.assertTrue((REPO_ROOT / "source" / resource).is_file())

    def test_documented_search_plans_pass_current_builder_validation(self) -> None:
        examples = [json.loads(block) for block in re.findall(
            r"```json\n(.*?)\n```", self.search_plan, re.S)]
        plans = [value for value in examples if "primary_query" in value]
        self.assertTrue(any("secondary_query" in plan for plan in plans))
        self.assertTrue(any("secondary_query" not in plan for plan in plans))
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "plan.json"
            for plan in plans:
                with self.subTest(query=plan["primary_query"]):
                    path.write_text(json.dumps(plan, ensure_ascii=False))
                    normalized, _ = build_workflow.read_plan(str(path))
                    self.assertEqual(normalized["primary_query"], plan["primary_query"])
                    self.assertEqual(normalized["semantic_criteria"], plan["semantic_criteria"])

    def test_documents_confirmation_form_boundaries(self) -> None:
        self.assertIn("description", self.skill)
        self.assertIn("prompt", self.skill)
        self.assertIn("完整需求稿", self.skill)



if __name__ == "__main__":
    unittest.main()

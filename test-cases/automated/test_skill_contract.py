from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


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

    def test_documents_integrated_execution_contract(self) -> None:
        for phrase in (
            "--interaction-mode",
            "decision_basis",
            "requirement_version",
            "next_offset",
            "write_file",
            "edit_file",
            "final-report-data.json",
            "不存在 `reflect`",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.all_text)

    def test_documents_confirmation_form_boundaries(self) -> None:
        self.assertIn("description", self.skill)
        self.assertIn("prompt", self.skill)
        self.assertIn("完整需求稿", self.skill)

    def test_preserves_official_company_probe_pacing_and_reporting(self) -> None:
        self.assertIn("### 3.5 目标公司", self.skill)
        self.assertIn("workflow_type", self.search_plan)
        self.assertIn("probe", self.search_plan)
        self.assertIn("15 秒", self.search_plan)
        self.assertIn("市场洞察", self.final_report)


if __name__ == "__main__":
    unittest.main()

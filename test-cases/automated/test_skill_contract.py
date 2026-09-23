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
        self.seen_and_expand = (
            REPO_ROOT / "source" / "references" / "seen-and-expand.md"
        ).read_text(encoding="utf-8")
        self.reflect = (REPO_ROOT / "source" / "references" / "reflect.md").read_text(
            encoding="utf-8"
        )
        self.market_research = (
            REPO_ROOT / "source" / "references" / "market-research.md"
        ).read_text(encoding="utf-8")
        self.requirements_draft = (
            REPO_ROOT / "source" / "references" / "requirements-draft.md"
        ).read_text(encoding="utf-8")
        self.all_text = "\n".join(
            [
                self.skill,
                self.search_plan,
                self.scoring,
                self.final_report,
                self.seen_and_expand,
                self.reflect,
                self.market_research,
                self.requirements_draft,
            ]
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
            "没有 `reflect` 子命令",
            "score_inputs.py",
            "seen.json",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.all_text)

    def test_documents_confirmation_form_boundaries(self) -> None:
        self.assertIn("description", self.skill)
        self.assertIn("prompt", self.skill)
        self.assertIn("完整需求稿", self.skill)

    def test_documents_collection_refill_expansion_and_reporting(self) -> None:
        self.assertIn("### 3.5 目标公司", self.skill)
        self.assertIn("workflow_type", self.search_plan)
        self.assertIn("refill", self.search_plan)
        self.assertIn("collect", self.search_plan)
        self.assertIn("expand", self.search_plan)
        self.assertIn("已看台账", self.seen_and_expand)
        self.assertIn("市场求证", self.market_research)
        self.assertIn("市场洞察", self.final_report)

    def test_documents_explicit_site_filter_preferences_and_fallbacks(self) -> None:
        for phrase in (
            "【站内筛选偏好】",
            "site_filters.company",
            "site_filters.activity_recency",
            "site_filters.job_hop_frequency",
            "site_filters.age_range",
            "site_filters.gender",
            "没有本地硬筛回退",
            "报告未验证",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.all_text)

    def test_progress_updates_require_chinese_sentences(self) -> None:
        self.assertIn("猎头句用中文写", self.skill)
        self.assertIn("岗位词、技术名词、公司名保持原文", self.skill)
        self.assertIn("句子主干是中文", self.skill)


if __name__ == "__main__":
    unittest.main()

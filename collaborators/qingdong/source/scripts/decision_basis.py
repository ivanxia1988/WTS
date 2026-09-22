"""Validate reusable WTS decisions and compute scores without another model call."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


EXPERIENCE_FIELDS = {"work_experience_summary", "project_experience_summary"}
NEGATIVE_TEXT_FIELDS = EXPERIENCE_FIELDS | {
    "self_summary", "skills", "card_text", "highlights", "current_work_text",
    "expected_title", "job_intention_summary", "education_summary", "language_summary", "profile_text",
}
SCORE_FIELDS = {
    "candidate_ref", "detail_ref", "detail_section", "scored_iteration", "matches",
    "must_score", "nice_score", "risk_score", "must_unknown", "unknown", "evidence_summary", "correction_reason",
}
# details.expand holds candidates opened by an in-round expansion (build_workflow.py expand).
DETAIL_SECTIONS = {"details.primary", "details.secondary", "details.expand"}
# Three rounds of 5+3 plus up to three expansions per round can exceed the old cap of 25.
MAX_CANDIDATE_SCORES = 120


def integer(value: Any, label: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label} 必须是 {low}-{high} 的整数")
    return value


def text(value: Any, label: str, maximum: int = 800) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{label} 必须是 1-{maximum} 字符的非空文本")
    return value.strip()


def object_fields(value: Any, allowed: set[str], label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} 必须是对象，允许字段：{', '.join(sorted(allowed))}")
    unknown = sorted(set(value) - allowed)
    if unknown:
        hint = "；decision_receipt 是输出回执，不能作为 decision_basis 输入，请复用原 candidate_scores" if label == "decision_basis" else ""
        raise ValueError(f"{label} 包含未知字段：{', '.join(unknown)}；允许字段：{', '.join(sorted(allowed))}{hint}")
    return value


def changed_fields(previous: dict, current: dict, prefix: str) -> list[str]:
    """Identify the changed constraints without echoing entire plans or resumes."""
    paths = []
    for key in sorted(set(previous) | set(current)):
        before, after = previous.get(key), current.get(key)
        if before == after:
            continue
        path = f"{prefix}.{key}"
        if isinstance(before, dict) and isinstance(after, dict):
            paths.extend(changed_fields(before, after, path))
        else:
            paths.append(path)
    return paths


def decision_receipt(plan: dict, *, iteration: int, task_id: str, store_root: Path,
                     previous_plan: dict | None = None, settle: bool = False,
                     report_data: dict | None = None) -> dict | None:
    basis = plan.get("decision_basis")
    if basis is None:
        return None  # Round 1 has no candidates to score yet.
    object_fields(basis, {"requirement_version", "completed_iteration", "candidate_scores",
                          "prf_decision", "next_action"}, "decision_basis")
    version = text(basis.get("requirement_version"), "requirement_version", 80)
    if plan.get("requirement_version", version) != version:
        raise ValueError("decision_basis.requirement_version 必须与计划 requirement_version 一致")
    completed = integer(basis.get("completed_iteration"), "completed_iteration", 0, 5)
    if completed != iteration - 1:
        raise ValueError("decision_basis.completed_iteration 必须是本轮 iteration - 1")
    previous_plan = previous_plan or {}
    previous = previous_plan.get("decision_basis") or {}
    same_version = (previous_plan.get("requirement_version") or previous.get("requirement_version") or "v1") == version
    if previous_plan and same_version and any(previous_plan.get(key) != plan.get(key) for key in ("semantic_criteria", "hard_filters")):
        changed = [path for key in ("semantic_criteria", "hard_filters")
                   for path in changed_fields(previous_plan.get(key) or {}, plan.get(key) or {}, key)]
        raise ValueError(
            f"同一需求版本 {version} 的条件发生变化：{', '.join(changed)}。"
            "只换搜索词时仅修改 primary_query/secondary_query，恢复本轮被误改的条件；"
            "仅在用户确认新需求后更新 requirement_version 并重评。不得回改已执行的历史计划。"
        )
    old_scores = {row["candidate_ref"]: row for row in previous.get("candidate_scores", [])}
    rows = basis.get("candidate_scores")
    if not isinstance(rows, list) or len(rows) > MAX_CANDIDATE_SCORES:
        raise ValueError(f"candidate_scores 必须是最多 {MAX_CANDIDATE_SCORES} 条的数组")
    results: dict[str, dict] = {}
    profiles: dict[str, dict] = {}
    scores: dict[str, dict] = {}
    evaluated_refs: set[str] = set()

    def profile(row: dict) -> dict:
        ref = text(row.get("detail_ref"), "detail_ref", 250)
        match = re.fullmatch(r"result://([A-Za-z0-9._-]{1,100})/([a-f0-9]{64})", ref)
        if not match or match[1] != task_id:
            raise ValueError("detail_ref 必须引用当前任务的真实 Result Store 结果")
        if ref not in results:
            root = (store_root / "result-store").resolve()
            path = (root / task_id / f"{match[2]}.json").resolve()
            if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
                raise ValueError("detail_ref 对应结果不存在、越界或超过 16 MiB")
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != match[2]:
                raise ValueError("detail_ref 结果摘要不匹配，不能依据已变化的数据复用评分")
            results[ref] = json.loads(raw)
        section = row.get("detail_section")
        if section not in DETAIL_SECTIONS:
            raise ValueError("detail_section 必须是 " + " / ".join(sorted(DETAIL_SECTIONS)))
        data = results[ref].get("data", {}).get("details", {}).get(section.split(".")[1], [])
        found = [item for item in data if item.get("candidate_ref") == row["candidate_ref"]]
        if len(found) != 1:
            raise ValueError("candidate_ref 在引用的详情分区中必须唯一存在")
        if found[0].get("detail_hard_filter_status") not in {"matched", "unknown"}:
            raise ValueError("仅能评分详情硬筛为 matched/unknown 的候选人")
        return found[0]

    for row in rows:
        object_fields(row, SCORE_FIELDS, "candidate_scores 条目")
        ref = text(row.get("candidate_ref"), "candidate_ref", 250)
        if ref in scores:
            raise ValueError("同一需求版本的 candidate_ref 不得重复；修正原条目而不是另加一条")
        scored_iteration = integer(row.get("scored_iteration"), "scored_iteration", 1, completed)
        if type(row.get("matches")) is not bool:
            raise ValueError("matches 必须是 boolean；低分或 unknown 不等于硬冲突")
        must = integer(row.get("must_score"), "must_score", 0, 100)
        numerator, denominator = must * 60, 60
        for field, criterion, weight in (("nice_score", "nice_to_have", 25), ("risk_score", "exclude_signals", 15)):
            value = row.get(field)
            if not plan["semantic_criteria"][criterion]:
                if value is not None:
                    raise ValueError(f"没有 {criterion} 时 {field} 必须为 null，不得按 0 分处理")
            else:
                value = integer(value, field, 0, 100)
                numerator += (100 - value if field == "risk_score" else value) * weight
                denominator += weight
        total = (2 * numerator + denominator) // (2 * denominator)  # Round half up, not bankers' rounding.
        unknown = row.get("unknown")
        if not isinstance(unknown, list) or len(unknown) > 20:
            raise ValueError("unknown 必须是最多 20 条的文本数组")
        for item in unknown:
            text(item, "unknown 条目", 200)
        if type(row.get("must_unknown")) is not bool:
            raise ValueError("must_unknown 必须是 boolean，表示必须满足项是否仍有未核实内容")
        if row["must_unknown"] and not unknown:
            raise ValueError("must_unknown 为 true 时须在 unknown 列出未核实的必须满足项")
        text(row.get("evidence_summary"), "evidence_summary")
        old = old_scores.get(ref)
        changed = old and any(old.get(key) != row.get(key) for key in SCORE_FIELDS - {"correction_reason"})
        if scored_iteration == completed or (old and (not same_version or changed)):
            evaluated_refs.add(ref)
        if old and scored_iteration != old.get("scored_iteration"):
            raise ValueError(
                f"candidate_scores[{ref}].scored_iteration 应保留 {old['scored_iteration']}，实际为 {scored_iteration}；"
                "该字段是首次评分轮次，纠错或版本重评不能把旧候选人算作新人"
            )
        if old and not same_version:
            text(row.get("correction_reason"), "切换需求版本时记录重评依据 correction_reason", 500)
        if same_version and changed:
            text(row.get("correction_reason"), "修订已有评分时 correction_reason", 500)
        profiles[ref] = profile(row)
        scores[ref] = {
            "candidate_ref": ref, "total": total, "must": must,
            "nice": row.get("nice_score"), "risk": row.get("risk_score"),
            "matches": row["matches"], "scored_iteration": scored_iteration,
            "recommendable": row["matches"] and total >= 60,
            "strong": row["matches"] and not row["must_unknown"] and total >= 80 and must >= 70 and
                      (row.get("risk_score") is None or row["risk_score"] <= 30),
        }
    if set(old_scores) - set(scores):
        raise ValueError("必须保留历史已评候选人，包含退出 Top 10 的条目；版本变化时按新版本重评")
    ranked = sorted(scores.values(), key=lambda row: (-row["total"], -row["must"], row["candidate_ref"]))
    prf = object_fields(basis.get("prf_decision"), {"status", "term", "evidence", "reason"}, "prf_decision")
    status = prf.get("status")
    if status not in {"none", "pending", "promoted", "rejected", "unevaluable"}:
        raise ValueError("prf_decision.status 不支持")
    text(prf.get("reason"), "prf_decision.reason", 500)
    if status != "none":
        term = text(prf.get("term"), "prf_decision.term", 50)
    else:
        term = ""
    seed_refs = [row["candidate_ref"] for row in ranked if row["matches"] and row["total"] >= 75
                 and row["must"] >= 70 and (row["risk"] is None or row["risk"] <= 45)]
    if status == "pending":
        seed_refs = seed_refs[:5]
    if status == "promoted":
        old_prf = previous.get("prf_decision") or {}
        if (not same_version or old_prf.get("status") not in {"pending", "promoted"}
                or old_prf.get("term") != term or old_prf.get("evidence") != prf.get("evidence")):
            raise ValueError("promoted 必须承接同版本已记录的探针及原始证据，不能跳过待试阶段")
        # These exact citations were accepted with the previous proposal. New
        # candidates may outrank its seeds; do not reselect them on promotion.
        seed_refs = set(old_scores)
        if old_prf["status"] == "pending" and not any(
            row["candidate_ref"] not in old_scores and row["scored_iteration"] == completed and
            scores[row["candidate_ref"]]["recommendable"] and row["detail_section"] == "details.secondary" and
            results[row["detail_ref"]].get("data", {}).get("search", {}).get("secondary", {}).get("query") == previous_plan.get("secondary_query")
            for row in rows
        ):
            raise ValueError("探针没有新增可推荐候选人，不能记录 promoted")
    if status in {"pending", "promoted"}:
        evidence = prf.get("evidence")
        if not isinstance(evidence, list) or not 2 <= len(evidence) <= 5:
            raise ValueError("有效 PRF 必须有 2-5 位不同有效种子的经历原文证据")
        seen = set()
        for item in evidence:
            object_fields(item, {"candidate_ref", "source_field", "quote"}, "PRF evidence")
            ref, field = item.get("candidate_ref"), item.get("source_field")
            quote = text(item.get("quote"), "PRF quote", 500)
            if ref not in seed_refs or ref in seen or field not in EXPERIENCE_FIELDS:
                raise ValueError("PRF 证据必须来自不同的 Top 5 有效种子的工作/项目经历，不能用自评或标题")
            if term not in quote or quote not in str(profiles[ref].get(field) or ""):
                raise ValueError("PRF 短语及引文必须逐字出现在声明的经历字段中")
            seen.add(ref)
    if status == "pending":
        negatives = [row for row in ranked if row["candidate_ref"] in evaluated_refs
                     and (not row["matches"] or row["total"] < 60)]
        hits = sum(any(term.casefold() in str(profiles[row["candidate_ref"]].get(field) or "").casefold()
                       for field in NEGATIVE_TEXT_FIELDS) for row in negatives)
        if negatives and hits * 5 >= len(negatives) * 2:
            raise ValueError("pending PRF 在本轮负样本文本中的出现比例达到 0.4，应记录 rejected 并选择已确认的备用方向")
        if not settle and (term not in plan.get("secondary_query", "") or term in plan["primary_query"]):
            raise ValueError("pending PRF 只能用于本轮第二路，主路径不得提前使用")
    next_action = object_fields(basis.get("next_action"), {"action", "iteration", "primary_query", "secondary_query", "reason"}, "next_action")
    if settle:
        if next_action.get("action") != "report" or set(next_action) - {"action", "reason"}:
            raise ValueError("终态 next_action 只能包含 action=report 和 reason，不能追加搜索查询")
    else:
        if next_action.get("iteration") != iteration or type(next_action.get("iteration")) is not int:
            raise ValueError("next_action.iteration 必须等于当前轮次")
        if next_action.get("primary_query") != plan["primary_query"] or next_action.get("secondary_query") != plan.get("secondary_query"):
            raise ValueError("计划关键词与已记录的 next_action 不一致；只在新证据或具体错误出现时修订决策")
    reason = text(next_action.get("reason"), "next_action.reason", 500)
    new = [row for row in ranked if row["scored_iteration"] == completed and row["candidate_ref"] not in old_scores]
    receipt = {
        "requirement_version": version, "completed_iteration": completed,
        "counts": {"scored": len(ranked), "recommendable": sum(row["recommendable"] for row in ranked),
                   "strong": sum(row["strong"] for row in ranked), "new_scored": len(new),
                   "new_recommendable": sum(row["recommendable"] for row in new), "new_strong": sum(row["strong"] for row in new)},
        "scores": [{key: row[key] for key in ("candidate_ref", "total", "must", "nice", "risk", "matches")} for row in ranked],
        "top10": [row["candidate_ref"] for row in ranked[:10]],
        "prf": {"status": status, "term": term}, "next_iteration": None if settle else iteration, "reason": reason,
    }
    if settle and report_data is not None:
        input_rows = {row["candidate_ref"]: row for row in rows}
        report_data.update({
            "decision_receipt": receipt,
            "candidates": [
                {
                    **score,
                    **{key: profiles[score["candidate_ref"]].get(key) for key in
                       ("display_name", "detail_url", "current_work_text", "education", "work_years")},
                    **{key: input_rows[score["candidate_ref"]].get(key) for key in
                       ("detail_ref", "detail_section", "evidence_summary", "unknown")},
                }
                for score in ranked[:10]
            ],
        })
    return receipt

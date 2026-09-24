#!/usr/bin/env python3
"""Deterministic bookkeeping for wts-local: plan checks, seen ledger, scores, receipts.

The search tool is called by the retrieval sub-agent, never by this script. The
script only reads files the agents wrote and recomputes every number the main
agent acts on, so totals, Top 10 and gates never come from model arithmetic.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, NoReturn

SKILL_DIR = "wts-local"
DETAIL_STATUSES = {"matched", "unknown", "rejected", "failed", "duplicate"}
MODES = {"round", "expand", "rescore"}
PRF_STATUSES = {"none", "pending", "promoted", "rejected", "unevaluable"}
HARD_FILTER_FIELDS = {
    "cities", "education", "experience_years", "company", "exclude_current_company",
    "school_requirements", "work_content", "required_keywords", "required_keyword_groups",
}
SEMANTIC_FIELDS = {"must_have", "nice_to_have", "exclude_signals"}
PLAN_FIELDS = {"requirement_version", "primary", "secondary", "hard_filters",
               "semantic_criteria", "limits", "file_types", "folder_path"}
LIMIT_DEFAULTS = {"max_results_per_path": (30, 1, 30), "primary_max_scored": (5, 0, 5),
                  "secondary_max_scored": (3, 0, 3)}
SCORE_FIELDS = {
    "candidate_ref", "path", "file_path", "locator", "scored_iteration", "card", "matches",
    "must_score", "nice_score", "risk_score", "must_unknown", "unknown", "evidence_summary",
    "short_reason", "correction_reason",
}


def fail(message: str) -> NoReturn:
    raise ValueError(message)


def load(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        if default is not None:
            return default
        fail(f"文件不存在：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def work(args: argparse.Namespace) -> Path:
    return Path(args.task_work_dir).expanduser().resolve() / SKILL_DIR


def requirement(base: Path, version: str) -> dict[str, Any]:
    match = re.fullmatch(r"v([1-9][0-9]*)", version or "")
    if not match:
        fail("requirement_version 必须写成 v1、v2 …")
    return load(base / "requirements" / f"{version}.json")


def keywords(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not 1 <= len(value) <= 8:
        fail(f"{label}.keywords 必须是 1-8 个词")
    for word in value:
        if not isinstance(word, str) or not word or re.search(r"\s", word):
            fail(f"{label}.keywords 每个词非空且不含空格：{word!r}")
    if len({word.casefold() for word in value}) != len(value):
        fail(f"{label}.keywords 不能重复")
    return value


def combo(words: list[str]) -> tuple[str, ...]:
    return tuple(sorted(word.casefold() for word in words))


# ---------------------------------------------------------------- plan check

def executed_combos(base: Path, before: int) -> set[tuple[str, ...]]:
    seen: set[tuple[str, ...]] = set()
    for n in range(1, before):
        plan = load(base / "search-plans" / f"iteration-{n}.json", {})
        for key in ("primary", "secondary"):
            if plan.get(key):
                seen.add(combo(plan[key]["keywords"]))
    for run in sorted((base / "runs").glob("iteration-*.json")):
        refill = (load(run).get("paths") or {}).get("refill")
        if refill and refill.get("keywords"):
            seen.add(combo(refill["keywords"]))
    return seen


def check_plan(args: argparse.Namespace) -> dict[str, Any]:
    base, n = work(args), args.iteration
    if not 1 <= n <= 3:
        fail("轮次只允许 1-3")
    path = base / "search-plans" / f"iteration-{n}.json"
    plan = load(path)
    unknown = set(plan) - PLAN_FIELDS
    if unknown:
        fail(f"计划含未知字段：{', '.join(sorted(unknown))}")
    req = requirement(base, plan.get("requirement_version"))
    anchor = [token.casefold() for token in str(req["position"]["primary_anchor"]).split()]
    primary = plan.get("primary") or fail("缺少 primary")
    words = keywords(primary.get("keywords"), "primary")
    company = primary.get("company")
    if company is not None and company not in words:
        fail("primary.company 必须逐字出现在 primary.keywords 里")
    queries = [("primary", words)]
    if plan.get("secondary"):
        if n == 1:
            fail("第 1 轮只有主路径")
        second = keywords(plan["secondary"].get("keywords"), "secondary")
        if plan["secondary"].get("kind") not in {"prf", "explore"}:
            fail("secondary.kind 只能是 prf 或 explore")
        if combo(second) == combo(words):
            fail("两路查询不能相同")
        queries.append(("secondary", second))
    for label, query in queries:
        lowered = {word.casefold() for word in query}
        if not all(token in lowered for token in anchor):
            fail(f"{label} 必须包含主锚点的每个词：{req['position']['primary_anchor']}")
    repeats = executed_combos(base, n)
    for label, query in queries:
        if combo(query) in repeats:
            fail(f"{label} 的词组合已经检索过：{' '.join(query)}")
    hard = plan.get("hard_filters") or {}
    if set(hard) - HARD_FILTER_FIELDS:
        fail(f"hard_filters 含未知字段：{', '.join(sorted(set(hard) - HARD_FILTER_FIELDS))}")
    semantic = plan.get("semantic_criteria") or {}
    if set(semantic) != SEMANTIC_FIELDS:
        fail("semantic_criteria 必须恰好含 must_have、nice_to_have、exclude_signals")
    for m in range(n - 1, 0, -1):
        previous = load(base / "search-plans" / f"iteration-{m}.json", {})
        if previous.get("requirement_version") == plan["requirement_version"]:
            for key in ("hard_filters", "semantic_criteria"):
                if previous.get(key) != plan.get(key):
                    fail(f"同一需求版本 {plan['requirement_version']} 的 {key} 与第 {m} 轮不同；"
                         "只换词时恢复条件，需求变了先写新版本")
            break
    limits = plan.get("limits") or {}
    for key, (default, low, high) in LIMIT_DEFAULTS.items():
        value = limits.get(key, default)
        if type(value) is not int or not low <= value <= high:
            fail(f"limits.{key} 必须是 {low}-{high} 的整数")
    return {"status": "ok", "plan_file": str(path),
            "queries": {label: " ".join(query) for label, query in queries}}


# ---------------------------------------------------------------- merge

def total(row: dict[str, Any], semantic: dict[str, list]) -> int:
    numerator, denominator = row["must_score"] * 60, 60
    for field, criterion, weight in (("nice_score", "nice_to_have", 25), ("risk_score", "exclude_signals", 15)):
        value = row.get(field)
        if not semantic.get(criterion):
            if value is not None:
                fail(f"{row['candidate_ref']}：没有 {criterion} 时 {field} 必须为 null")
            continue
        if type(value) is not int or not 0 <= value <= 100:
            fail(f"{row['candidate_ref']}：{field} 必须是 0-100 的整数")
        numerator += (100 - value if field == "risk_score" else value) * weight
        denominator += weight
    return (2 * numerator + denominator) // (2 * denominator)  # Round half up.


def label(row: dict[str, Any]) -> dict[str, Any]:
    risk = row.get("risk_score")
    return {
        "candidate_ref": row["candidate_ref"], "total": row["total"], "must": row["must_score"],
        "recommendable": row["matches"] and row["total"] >= 60,
        "strong": (row["matches"] and not row["must_unknown"] and row["total"] >= 80
                   and row["must_score"] >= 70 and (risk is None or risk <= 30)),
    }


def ranked(rows: dict[str, dict]) -> list[dict[str, Any]]:
    labels = [label(row) for row in rows.values()]
    return sorted(labels, key=lambda item: (-item["total"], -item["must"], item["candidate_ref"]))


def validate_score(row: dict[str, Any], semantic: dict[str, list]) -> dict[str, Any]:
    if not isinstance(row, dict) or set(row) - SCORE_FIELDS:
        fail(f"candidate_scores 条目字段只允许：{', '.join(sorted(SCORE_FIELDS))}")
    ref = row.get("candidate_ref")
    if not isinstance(ref, str) or not ref.startswith("local:"):
        fail("candidate_ref 必须以 local: 开头")
    for field in ("matches", "must_unknown"):
        if type(row.get(field)) is not bool:
            fail(f"{ref}：{field} 必须是 boolean")
    if type(row.get("must_score")) is not int or not 0 <= row["must_score"] <= 100:
        fail(f"{ref}：must_score 必须是 0-100 的整数")
    unknown = row.get("unknown")
    if not isinstance(unknown, list) or len(unknown) > 20:
        fail(f"{ref}：unknown 必须是最多 20 条的数组")
    if row["must_unknown"] and not unknown:
        fail(f"{ref}：must_unknown 为 true 时 unknown 要列出未核实的必须满足项")
    for field, maximum in (("evidence_summary", 800), ("short_reason", 40)):
        if not isinstance(row.get(field), str) or not row[field].strip() or len(row[field]) > maximum:
            fail(f"{ref}：{field} 必须是 1-{maximum} 字")
    return {**row, "total": total(row, semantic)}


def merge(args: argparse.Namespace) -> dict[str, Any]:
    base = work(args)
    run_path = Path(args.run_file).expanduser().resolve()
    if run_path.parent != base / "runs":
        fail(f"run 文件必须在 {base / 'runs'} 下")
    run = load(run_path)
    mode = run.get("mode")
    if mode not in MODES:
        fail("mode 只能是 round / expand / rescore")
    version = run.get("requirement_version")
    semantic = requirement(base, version)
    semantic = {key: semantic.get(key) or [] for key in SEMANTIC_FIELDS}
    iteration, expansion = run.get("iteration"), run.get("expansion", 0)

    seen_path, scores_path = base / "seen.json", base / "scores.json"
    seen = load(seen_path, {"merged_from": [], "entries": []})
    known = {entry["candidate_ref"]: entry for entry in seen["entries"]}
    merged_runs = seen.setdefault("merged_runs", [])
    if run_path.name in merged_runs:
        fail(f"{run_path.name} 已经合并过")

    prf = run.get("prf_decision")
    if prf is not None and (not isinstance(prf, dict) or prf.get("status") not in PRF_STATUSES):
        fail("prf_decision.status 只能是 " + " / ".join(sorted(PRF_STATUSES)))
    judged = run.get("judged") or []
    if mode == "rescore" and judged:
        fail("rescore 不产生新的已看记录，judged 必须为空")
    for entry in judged:
        ref, status = entry.get("candidate_ref"), entry.get("status")
        if status not in DETAIL_STATUSES or not isinstance(ref, str) or not ref.startswith("local:"):
            fail(f"judged 条目无效：{entry}")
        old = known.get(ref)
        if old and old["status"] != "failed":
            fail(f"{ref} 已在台账里，不能再次打开")
        if old:  # A failed read may be retried once; keep the first record, mark the retry.
            old.update(status=status, retried=True)
            continue
        known[ref] = {"candidate_ref": ref, "iteration": iteration, "expansion": expansion,
                      "path": entry.get("path"), "file_path": entry.get("file_path"),
                      "locator": entry.get("locator"), "status": status,
                      "reason": entry.get("reason", "")}
        seen["entries"].append(known[ref])

    scores = load(scores_path, {"current": version, "versions": {}})
    rows = scores["versions"].setdefault(version, {})
    before = set(rows)
    this_run: list[str] = []
    for raw in run.get("candidate_scores") or []:
        row = validate_score(raw, semantic)
        ref = row["candidate_ref"]
        if known.get(ref, {}).get("status") not in {"matched", "unknown"}:
            fail(f"{ref} 不在台账里或硬筛未通过，不能评分")
        if ref in rows and not row.get("correction_reason"):
            fail(f"{ref} 已有评分；重评必须写 correction_reason")
        first = rows.get(ref, {}).get("scored_iteration") or next(
            (older[ref]["scored_iteration"] for older in scores["versions"].values() if ref in older), None)
        row["scored_iteration"] = first or iteration
        rows[ref] = row
        this_run.append(ref)
    hits = {row["candidate_ref"] for row in rows.values() if row["total"] >= 70}
    if version != scores["current"]:
        scores["current"] = version
    missing = sorted({ref for older in scores["versions"].values() for ref in older} - set(rows))

    seen["merged_runs"].append(run_path.name)
    dump(seen_path, seen)
    dump(scores_path, scores)

    order = ranked(rows)
    top10 = order[:10]
    strong_pool = len(top10) == 10 and sum(item["strong"] for item in order) >= 5
    by_ref = {item["candidate_ref"]: item for item in order}
    if mode == "rescore":
        population = [ref for ref, row in rows.items() if row["scored_iteration"] == iteration]
    else:
        population = [ref for ref in this_run if ref not in before]
    new = [by_ref[ref] for ref in population]
    new_rec = sum(item["recommendable"] for item in new)
    new_strong = sum(item["strong"] for item in new)
    return {
        "run": run_path.name, "mode": mode, "iteration": iteration, "expansion": expansion,
        "status": run.get("status"), "tool_events": run.get("tool_events") or [],
        "coverage_warning": run.get("coverage_warning") or "",
        "paths": run.get("paths") or {}, "refill": run.get("refill"),
        "new": {"scored": len(new), "recommendable": new_rec, "strong": new_strong},
        "labels": [by_ref[ref] for ref in this_run],
        "totals": {"scored": len(order), "recommendable": sum(i["recommendable"] for i in order),
                   "strong": sum(i["strong"] for i in order), "strong_pool": strong_pool},
        "expansion_gate": bool(new) and not strong_pool and (new_rec * 2 >= len(new) or new_strong >= 2),
        "top10": [{key: item[key] for key in ("candidate_ref", "total", "recommendable", "strong")} for item in top10],
        "company_hits": [hit for hit in run.get("company_hits") or [] if hit.get("candidate_ref") in hits],
        "prf_decision": run.get("prf_decision"),
        "remaining": run.get("remaining") or {},
        "missing_rescore": missing,
    }


# ---------------------------------------------------------------- merge ledger across tasks

def adopt(args: argparse.Namespace) -> dict[str, Any]:
    base = work(args)
    source = Path(args.previous_ledger).expanduser().resolve()
    previous = load(source)
    seen = load(base / "seen.json", {"merged_from": [], "entries": [], "merged_runs": []})
    if str(source) in seen["merged_from"]:
        fail("这份台账已经合并过")
    refs = {entry["candidate_ref"] for entry in seen["entries"]}
    added = [dict(entry, inherited=True) for entry in previous.get("entries", [])
             if entry.get("candidate_ref") not in refs]
    seen["entries"].extend(added)
    seen["merged_from"].append(str(source))
    dump(base / "seen.json", seen)
    return {"status": "ok", "inherited": len(added)}


# ---------------------------------------------------------------- settle

def settle(args: argparse.Namespace) -> dict[str, Any]:
    base = work(args)
    scores = load(base / "scores.json")
    version = scores["current"]
    rows = scores["versions"][version]
    missing = sorted({ref for older in scores["versions"].values() for ref in older} - set(rows))
    if missing:
        fail(f"当前版本 {version} 还有 {len(missing)} 人未重评，先派 rescore")
    seen = load(base / "seen.json")
    own = [entry for entry in seen["entries"]
           if not entry.get("inherited") and entry["status"] != "duplicate"]
    order = ranked(rows)
    runs = [load(path) for path in sorted((base / "runs").glob("iteration-*.json"))]
    data = {
        "requirement_version": version,
        "rounds": max((run["iteration"] for run in runs if run.get("mode") == "round"), default=0),
        "seen": len(own),
        "recommendable": sum(item["recommendable"] for item in order),
        "strong": sum(item["strong"] for item in order),
        "top10": [
            {**{key: rows[item["candidate_ref"]].get(key) for key in (
                "candidate_ref", "card", "file_path", "locator", "matches", "total", "must_score",
                "nice_score", "risk_score", "evidence_summary", "unknown")},
             "recommendable": item["recommendable"], "strong": item["strong"]}
            for item in order[:10]
        ],
        "not_recommended": [
            {"candidate_ref": item["candidate_ref"], "short_reason": rows[item["candidate_ref"]]["short_reason"]}
            for item in order if not item["recommendable"]
        ],
        "hard_filter_rejected": [
            {"candidate_ref": entry["candidate_ref"], "reason": entry.get("reason", "")}
            for entry in own if entry["status"] == "rejected"
        ],
        "failures": [
            {"candidate_ref": entry["candidate_ref"], "reason": entry.get("reason", "")}
            for entry in own if entry["status"] == "failed"
        ],
        "coverage_warnings": sorted({run["coverage_warning"] for run in runs if run.get("coverage_warning")}),
        "seen_ledger_path": str(base / "seen.json"),
    }
    dump(base / "final-report-data.json", data)
    return {"status": "ok", "report_data_file": str(base / "final-report-data.json")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check-plan", "merge", "adopt", "settle"])
    parser.add_argument("--task-work-dir", required=True)
    parser.add_argument("--iteration", type=int)
    parser.add_argument("--run-file")
    parser.add_argument("--previous-ledger")
    args = parser.parse_args()
    handlers = {"check-plan": (check_plan, "iteration"), "merge": (merge, "run_file"),
                "adopt": (adopt, "previous_ledger"), "settle": (settle, None)}
    handler, needed = handlers[args.command]
    if needed and getattr(args, needed) is None:
        parser.error(f"{args.command} 需要 --{needed.replace('_', '-')}")
    try:
        output = handler(args)
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

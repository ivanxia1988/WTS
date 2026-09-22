#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from decision_basis import decision_receipt


SKILL_NAME = "wts"
SKILL_VERSION = "0.5.2"
WORKFLOW_SCHEMA = "browser.workflow.v1"
SCHEMA_VERSION = 2
MAX_SEARCH_ITERATION = 5
PRIMARY_DETAIL_BUDGET = 3
SECONDARY_DETAIL_BUDGET = 2
MAX_CARDS_PER_PATH = 30
TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
ASSET_ROOT = Path(__file__).resolve().parent.parent / "assets"
HOST_ACTIONS = {"page.navigate", "page.run", "data.filter", "tabs.foreach", "result.emit"}
PAGE_OPS = {
    "page.detect",
    "page.wait",
    "page.click",
    "page.fill",
    "page.press",
    "page.scroll",
    "page.hover",
    "page.extract",
    "page.extract_list",
    "data.set",
    "data.append",
    "flow.if",
    "flow.foreach",
    "flow.repeat",
    "flow.break",
}
SCHOOL_REQUIREMENTS = {"211", "985", "double_first_class", "overseas"}
EDUCATION_ALIASES = {
    "bachelor": "本科",
    "master": "硕士",
    "doctor": "博士/博士后",
    "college": "大专",
    "secondary": "中专/中技",
    "high_school_or_below": "高中及以下",
    "本科": "本科",
    "硕士": "硕士",
    "博士": "博士/博士后",
    "博士后": "博士/博士后",
    "博士/博士后": "博士/博士后",
    "大专": "大专",
    "中专/中技": "中专/中技",
    "高中及以下": "高中及以下",
}
ACTIVITY_RECENCY = {
    "today",
    "within_3_days",
    "within_7_days",
    "within_30_days",
    "within_3_months",
    "within_6_months",
    "within_1_year",
}
JOB_HOP_FREQUENCY = {
    "last_5_years_max_3",
    "last_3_years_max_2",
    "recent_2_jobs_min_2_years_each",
}
GENDER_CHOICES = {"male", "female", "男", "女"}
AGE_MIN = 16
AGE_MAX = 60
SITE_EXPERIENCE_PRESETS = {(0, 0), (1, 3), (3, 5), (5, 10), (10, None)}
ALLOWED_SITE_FILTER_KEYS = {
    "current_cities",
    "expected_cities",
    "experience_years",
    "education",
    "school_requirements",
    "company",
    "work_content",
    "activity_recency",
    "job_hop_frequency",
    "age_range",
    "gender",
}
ALLOWED_HARD_FILTER_KEYS = {
    "current_cities",
    "expected_cities",
    "education",
    "experience_years",
    "school_requirements",
    "company",
    "work_content",
    "required_keywords",
    "required_keyword_groups",
}
ALLOWED_PLAN_KEYS = {
    "requirement_version",
    "primary_query",
    "secondary_query",
    "keyword_text",
    "site_filters",
    "hard_filters",
    "semantic_criteria",
    "allow_partial_filters",
    "limits",
    "action_delay_ms",
    "decision_basis",
}
ALLOWED_SEMANTIC_KEYS = {"must_have", "nice_to_have", "exclude_signals"}
SENSITIVE_PLAN_FIELDS = {"age_range", "gender"}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"无法读取 JSON 文件 {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON 文件内容必须是对象: {path}")
    return value


def load_assets() -> dict[str, Any]:
    return {
        "channel": load_json(ASSET_ROOT / "channel" / "liepin.json"),
        "schemas": {
            "card": load_json(ASSET_ROOT / "channel" / "card-extraction.json"),
            "detail": load_json(ASSET_ROOT / "channel" / "detail-extraction.json"),
        },
        "workflows": {
            "preflight": load_json(ASSET_ROOT / "workflows" / "preflight.json"),
            "search": load_json(ASSET_ROOT / "workflows" / "search.json"),
            "detail": load_json(ASSET_ROOT / "workflows" / "detail.json"),
        },
    }


def lookup(value: Any, dotted_path: str, source_name: str) -> Any:
    current = value
    for part in dotted_path.split(".") if dotted_path else []:
        if not isinstance(current, dict) or part not in current:
            raise ValueError(f"{source_name} 中不存在引用: {dotted_path}")
        current = current[part]
    return copy.deepcopy(current)


def bounded_integer(value: Any, fallback: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return min(maximum, max(minimum, parsed))


def normalize_string_list(
    value: Any,
    field: str,
    *,
    maximum: int,
    allowed: set[str] | None = None,
) -> list[str]:
    values = [value] if isinstance(value, str) else value
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError(f"{field} 必须是字符串数组")
    if any(not isinstance(item, str) for item in values):
        raise ValueError(f"{field} 只能包含字符串")
    normalized = list(dict.fromkeys(item.strip() for item in values if item.strip()))
    if len(normalized) > maximum:
        raise ValueError(f"{field} 最多包含 {maximum} 个值")
    if allowed is not None:
        unsupported = sorted(set(normalized) - allowed)
        if unsupported:
            raise ValueError(f"{field} 包含不支持的值: {', '.join(unsupported)}")
    return normalized


def normalize_education_list(value: Any, field: str, *, maximum: int) -> list[str]:
    values = normalize_string_list(value, field, maximum=maximum)
    unsupported = sorted(set(values) - set(EDUCATION_ALIASES))
    if unsupported:
        raise ValueError(f"{field} 包含不支持的值: {', '.join(unsupported)}")
    return list(dict.fromkeys(EDUCATION_ALIASES[item] for item in values))


def normalize_range(
    value: Any,
    field: str,
    *,
    minimum_allowed: int,
    maximum_allowed: int,
) -> dict[str, int | None]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} 必须是包含 min/max 的对象")
    unknown_keys = sorted(set(value) - {"min", "max"})
    if unknown_keys:
        raise ValueError(f"{field} 包含未知字段: {', '.join(unknown_keys)}")
    minimum = value.get("min")
    maximum = value.get("max")
    if minimum is None and maximum is None:
        raise ValueError(f"{field} 至少需要一个边界")
    for label, boundary in (("min", minimum), ("max", maximum)):
        if boundary is not None and (not isinstance(boundary, int) or isinstance(boundary, bool)):
            raise ValueError(f"{field}.{label} 必须是整数或 null")
        if boundary is not None and not minimum_allowed <= boundary <= maximum_allowed:
            raise ValueError(
                f"{field}.{label} 必须在 {minimum_allowed}-{maximum_allowed} 之间"
            )
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError(f"{field}.min 不能大于 max")
    return {"min": minimum, "max": maximum}


def normalize_plan(plan: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    normalized = dict(plan)
    warnings: list[dict[str, str]] = []
    site_filters = dict(plan.get("site_filters") or {})
    hard_filters = dict(plan.get("hard_filters") or {})

    sensitive_hard = sorted(set(hard_filters) & SENSITIVE_PLAN_FIELDS)
    if sensitive_hard:
        raise ValueError(
            "年龄、性别不参与硬筛或评分，仅可作为站内筛选: " + ", ".join(sensitive_hard)
        )
    unknown_site = sorted(set(site_filters) - ALLOWED_SITE_FILTER_KEYS)
    if unknown_site:
        raise ValueError(f"site_filters 包含未知字段: {', '.join(unknown_site)}")
    unknown_hard = sorted(set(hard_filters) - ALLOWED_HARD_FILTER_KEYS)
    if unknown_hard:
        raise ValueError(f"hard_filters 包含未知字段: {', '.join(unknown_hard)}")
    if "work_content" in site_filters:
        site_filters.pop("work_content")
        warnings.append(
            {
                "field": "site_filters.work_content",
                "code": "SITE_FILTER_UNSUPPORTED",
                "message": "猎聘页面无该站内筛选项，已跳过页面筛选；同名字段请写入 hard_filters 做文本硬筛",
            }
        )

    if "company" in site_filters:
        site_filters["company"] = normalize_string_list(
            site_filters["company"], "site_filters.company", maximum=1
        )

    for field, allowed in (
        ("activity_recency", ACTIVITY_RECENCY),
        ("job_hop_frequency", JOB_HOP_FREQUENCY),
    ):
        if field not in site_filters:
            continue
        value = site_filters[field]
        if value is None or (isinstance(value, str) and not value.strip()):
            site_filters.pop(field)
            continue
        if not isinstance(value, str) or value.strip() not in allowed:
            raise ValueError(
                f"site_filters.{field} 必须是单个预设字符串: {', '.join(sorted(allowed))}；不限时省略字段"
            )
        site_filters[field] = value.strip()

    if "gender" in site_filters:
        gender_value = site_filters["gender"]
        if gender_value is None or (
            isinstance(gender_value, str) and not gender_value.strip()
        ):
            site_filters.pop("gender")
        else:
            if not isinstance(gender_value, str) or gender_value.strip() not in GENDER_CHOICES:
                raise ValueError(
                    "site_filters.gender 必须是单个值: male, female, 男, 女；不限时省略字段"
                )
            site_filters["gender"] = gender_value.strip()

    if "age_range" in site_filters:
        site_filters["age_range"] = normalize_range(
            site_filters["age_range"],
            "site_filters.age_range",
            minimum_allowed=AGE_MIN,
            maximum_allowed=AGE_MAX,
        )

    for field in ("current_cities", "expected_cities"):
        if field in site_filters:
            site_filters[field] = normalize_string_list(
                site_filters[field], f"site_filters.{field}", maximum=9
            )
        if field in hard_filters:
            hard_filters[field] = normalize_string_list(
                hard_filters[field], f"hard_filters.{field}", maximum=20
            )

    if "education" in site_filters:
        site_filters["education"] = normalize_education_list(
            site_filters["education"], "site_filters.education", maximum=1
        )
    if "education" in hard_filters:
        hard_filters["education"] = normalize_education_list(
            hard_filters["education"], "hard_filters.education", maximum=10
        )
    if "school_requirements" in site_filters:
        site_filters["school_requirements"] = normalize_string_list(
            site_filters["school_requirements"],
            "site_filters.school_requirements",
            maximum=1,
            allowed=SCHOOL_REQUIREMENTS,
        )
    if "school_requirements" in hard_filters:
        hard_filters["school_requirements"] = normalize_string_list(
            hard_filters["school_requirements"],
            "hard_filters.school_requirements",
            maximum=4,
            allowed=SCHOOL_REQUIREMENTS,
        )

    if "experience_years" in hard_filters:
        hard_filters["experience_years"] = normalize_range(
            hard_filters["experience_years"],
            "hard_filters.experience_years",
            minimum_allowed=0,
            maximum_allowed=50,
        )
    if "experience_years" in site_filters:
        site_filters["experience_years"] = normalize_range(
            site_filters["experience_years"],
            "site_filters.experience_years",
            minimum_allowed=0,
            maximum_allowed=50,
        )
    for field in ("company", "work_content"):
        if field in hard_filters:
            hard_filters[field] = normalize_string_list(
                hard_filters[field], f"hard_filters.{field}", maximum=10
            )

    site_experience = site_filters.get("experience_years")
    if site_experience and (
        site_experience["min"],
        site_experience["max"],
    ) not in SITE_EXPERIENCE_PRESETS:
        if hard_filters.get("experience_years") != site_experience:
            raise ValueError(
                "site_filters.experience_years 不是猎聘支持的预设，且未在 hard_filters 中保留相同条件"
            )
        site_filters.pop("experience_years")
        warnings.append(
            {
                "field": "site_filters.experience_years",
                "code": "SITE_FILTER_PRESET_UNSUPPORTED",
                "message": "渠道不支持该工作年限组合，已仅保留本地硬筛条件",
            }
        )

    required_keywords = hard_filters.get("required_keywords")
    if required_keywords is not None:
        if not isinstance(required_keywords, dict):
            raise ValueError("hard_filters.required_keywords 必须是对象")
        unknown_required = sorted(set(required_keywords) - {"all", "any"})
        if unknown_required:
            raise ValueError(
                "hard_filters.required_keywords 包含未知字段: "
                + ", ".join(unknown_required)
            )
        hard_filters["required_keywords"] = {
            key: normalize_string_list(
                value, f"hard_filters.required_keywords.{key}", maximum=20
            )
            for key, value in required_keywords.items()
        }

    required_groups = hard_filters.get("required_keyword_groups")
    if required_groups is not None:
        if not isinstance(required_groups, list) or len(required_groups) > 10:
            raise ValueError("hard_filters.required_keyword_groups 必须是最多 10 组的数组")
        if any(not isinstance(group, list) for group in required_groups):
            raise ValueError("hard_filters.required_keyword_groups 的每一组都必须是字符串数组")
        hard_filters["required_keyword_groups"] = [
            normalize_string_list(
                group,
                f"hard_filters.required_keyword_groups.{index}",
                maximum=10,
            )
            for index, group in enumerate(required_groups)
        ]
        if not hard_filters["required_keyword_groups"] or any(
            not group for group in hard_filters["required_keyword_groups"]
        ):
            raise ValueError("hard_filters.required_keyword_groups 至少包含一组，且每组不能为空")

    if "allow_partial_filters" in normalized and not isinstance(
        normalized["allow_partial_filters"], bool
    ):
        raise ValueError("allow_partial_filters 必须是 boolean")
    if "allow_partial_filters" in normalized:
        warnings.append(
            {
                "field": "allow_partial_filters",
                "code": "ALLOW_PARTIAL_FILTERS_DEPRECATED",
                "message": "已忽略全局容错开关；所有站内筛选失败都会记录后继续执行",
            }
        )
    normalized["site_filters"] = site_filters
    normalized["hard_filters"] = hard_filters
    return normalized, warnings


def normalize_query(value: Any, field: str) -> str:
    keyword = str(value or "").strip()
    if not keyword or len(keyword) > 50:
        raise ValueError(f"{field} 必须是 1-50 字符的非空字符串")
    if re.search(r"(?:^|\s)(?:OR|AND|NOT)(?:\s|$)", keyword, re.IGNORECASE):
        raise ValueError(f"{field} 不支持 OR/AND/NOT，请使用空格分隔的自然语言词")
    return keyword


def normalize_semantic_criteria(value: Any) -> dict[str, list[str]]:
    if value in (None, {}):
        return {"must_have": [], "nice_to_have": [], "exclude_signals": []}
    if not isinstance(value, dict):
        raise ValueError("semantic_criteria 必须是对象")
    unknown = sorted(set(value) - ALLOWED_SEMANTIC_KEYS)
    if unknown:
        raise ValueError(f"semantic_criteria 包含未知字段: {', '.join(unknown)}")
    return {
        key: normalize_string_list(value.get(key), f"semantic_criteria.{key}", maximum=20)
        for key in ("must_have", "nice_to_have", "exclude_signals")
    }


def normalize_search_limits(value: Any, *, has_secondary: bool) -> dict[str, int]:
    limits = value or {}
    if not isinstance(limits, dict):
        raise ValueError("limits 必须是对象")
    unknown = sorted(
        set(limits)
        - {
            "max_cards_per_path",
            "primary_max_details",
            "secondary_max_details",
            "max_pages",
            "max_candidates",
            "max_details",
        }
    )
    if unknown:
        raise ValueError(f"limits 包含未知字段: {', '.join(unknown)}")
    max_cards = bounded_integer(
        limits.get("max_cards_per_path", limits.get("max_candidates")),
        MAX_CARDS_PER_PATH,
        1,
        MAX_CARDS_PER_PATH,
    )
    primary_details = bounded_integer(
        limits.get("primary_max_details", limits.get("max_details")),
        PRIMARY_DETAIL_BUDGET,
        0,
        PRIMARY_DETAIL_BUDGET,
    )
    secondary_details = 0
    if has_secondary:
        secondary_details = bounded_integer(
            limits.get("secondary_max_details"),
            SECONDARY_DETAIL_BUDGET,
            0,
            SECONDARY_DETAIL_BUDGET,
        )
    return {
        "max_cards_per_path": max_cards,
        "primary_max_details": primary_details,
        "secondary_max_details": secondary_details,
        "max_pages": 1,
    }


def read_plan(plan_path: str) -> tuple[dict[str, Any], list[dict[str, str]]]:
    target = Path(plan_path).expanduser().resolve()
    if not target.is_file():
        raise ValueError(f"搜索计划文件不存在: {target}")
    if target.stat().st_size > 64 * 1024:
        raise ValueError("搜索计划文件不能超过 64 KiB")
    try:
        plan = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"搜索计划不是有效 JSON: {error}") from error
    if not isinstance(plan, dict):
        raise ValueError("搜索计划必须是 JSON 对象")
    unknown_keys = sorted(set(plan) - ALLOWED_PLAN_KEYS)
    if unknown_keys:
        raise ValueError(f"搜索计划包含未知字段: {', '.join(unknown_keys)}")
    basis = plan.get("decision_basis")
    version = plan.get("requirement_version", basis.get("requirement_version", "v1") if isinstance(basis, dict) else "v1")
    if not isinstance(version, str) or not version.strip() or len(version) > 80:
        raise ValueError("requirement_version 必须是 1-80 字符的已确认需求版本")
    plan["requirement_version"] = version.strip()
    if "keyword_text" in plan and "primary_query" in plan:
        if str(plan["keyword_text"]).strip() != str(plan["primary_query"]).strip():
            raise ValueError("keyword_text 与 primary_query 不一致；请只使用 primary_query")
    primary = plan.get("primary_query", plan.get("keyword_text"))
    plan["primary_query"] = normalize_query(primary, "primary_query")
    plan.pop("keyword_text", None)
    secondary = plan.get("secondary_query")
    if secondary in (None, ""):
        plan.pop("secondary_query", None)
    else:
        plan["secondary_query"] = normalize_query(secondary, "secondary_query")
        if plan["secondary_query"] == plan["primary_query"]:
            raise ValueError("secondary_query 不能与 primary_query 相同")
    plan["semantic_criteria"] = normalize_semantic_criteria(plan.get("semantic_criteria"))
    plan["limits"] = normalize_search_limits(
        plan.get("limits"), has_secondary="secondary_query" in plan
    )
    for field in ("site_filters", "hard_filters"):
        if not isinstance(plan.get(field, {}), dict):
            raise ValueError(f"{field} 必须是对象")
    return normalize_plan(plan)


def map_filter_value(field: str, value: Any, channel: dict[str, Any]) -> Any:
    mappings = channel.get("canonical_values", {})
    if field in ("current_cities", "expected_cities"):
        city_mapping = mappings.get("cities", {})
        return [city_mapping.get(item, item) for item in value]
    if field == "experience_years":
        for preset in channel.get("experience_presets", []):
            if preset.get("min") == value.get("min") and preset.get("max") == value.get("max"):
                return preset["label"]
        raise ValueError("渠道工作年限预设缺失")
    if field in ("education", "school_requirements"):
        mapping = mappings.get(field, {})
        return [mapping.get(item, item) for item in value]
    if field in ("activity_recency", "job_hop_frequency", "gender"):
        mapping = mappings.get(field, {})
        return mapping.get(value, value)
    return copy.deepcopy(value)


def locator_within(locator: dict[str, Any], within: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(locator)
    result["within"] = copy.deepcopy(within)
    result.setdefault("visible", True)
    result.setdefault("enabled", True)
    return result


def require_unique_filter_targets(
    step_id: str, targets: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    # Compiled page programs otherwise use the first match. Reject ambiguous
    # rows/options before a click rather than depending on DOM order.
    return [
        {
            "id": f"count-{step_id}",
            "op": "page.extract",
            "schema": {"fields": {
                name: {"source": "count", "locator": target}
                for name, target in targets.items()
            }},
            "save_as": "filter_matches",
        },
        {
            "id": f"require-unique-{step_id}",
            "op": "page.wait",
            "until": {"all": [
                {"type": "variable", "path": f"filter_matches.{name}", "value": 1}
                for name in targets
            ]},
            "timeout_ms": 100,
        },
    ]


def compile_company_filter_program(
    value: str, config: dict[str, Any], channel: dict[str, Any], action_delay_ms: int
) -> list[dict[str, Any]]:
    control_timeout = channel["timing"]["control_timeout_ms"]
    row = config["row"]
    company_input = locator_within(config["input"], row)
    option = {
        **locator_within(config["option"], config["dropdown"]),
        "text": {"equals": value},
    }
    confirm = locator_within(config["confirm"], row)
    selected = {
        "any": [
            {
                "type": "exists",
                "target": {
                    **locator_within(config["selected"], row),
                    "text": {"equals": value},
                },
            },
            {
                "all": [
                    {"type": "value", "target": company_input, "value": value},
                    {
                        "type": "attribute",
                        "target": company_input,
                        "attribute": "aria-expanded",
                        "value": "false",
                    },
                ]
            },
        ]
    }

    def wait(step_id: str, condition: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": f"wait-company-{step_id}",
            "op": "page.wait",
            "until": condition,
            "timeout_ms": control_timeout,
        }

    return [
        wait("input", {"type": "exists", "target": company_input}),
        *require_unique_filter_targets("company-control", {"row": row, "input": company_input}),
        {
            "id": "focus-company-input",
            "op": "page.click",
            "target": company_input,
            "after_ms": action_delay_ms,
        },
        {
            "id": "fill-company-input",
            "op": "page.fill",
            "target": company_input,
            "value": value,
            "events": ["input", "change"],
            "after_ms": action_delay_ms,
        },
        {
            "id": "read-company-list-id",
            "op": "page.extract",
            "schema": {"fields": {"list_id": {
                "source": "attribute",
                "locator": company_input,
                "attribute": "aria-controls",
                "strategies": [{"attribute": "aria-owns"}],
                "transforms": [{"type": "regex_capture", "pattern": "^([A-Za-z0-9_-]+)$"}],
                "required": True,
            }}},
            "save_as": "company_control",
        },
        wait("suggestion", {"type": "exists", "target": option}),
        *require_unique_filter_targets("company-suggestion", {"option": option}),
        {
            "id": "select-company-suggestion",
            "op": "page.click",
            "target": option,
            "after_ms": action_delay_ms,
        },
        wait("selected", selected),
        {
            "id": "activate-company-confirm",
            "op": "page.click",
            "target": company_input,
            "after_ms": action_delay_ms,
        },
        wait("confirm", {"type": "exists", "target": confirm}),
        *require_unique_filter_targets("company-confirm", {"button": confirm}),
        {
            "id": "confirm-filter-company",
            "op": "page.click",
            "target": confirm,
            "after_ms": action_delay_ms,
        },
        {
            **wait("applied", {"all": [
                selected,
                {
                    "type": "exists",
                    "target": {
                        "any_css": channel["selectors"]["submitted_filter_chips"],
                        "text": {"equals": value},
                        "visible": True,
                    },
                },
                {"url_contains": ["#session"]},
                {"none_visible": channel["selectors"]["loading"]},
                {"any": [
                    {"any_visible": channel["selectors"]["candidate_rows"]},
                    {"any_visible": channel["selectors"]["empty_results"]},
                    {"text_any": channel["text_markers"]["no_results"]},
                ]},
            ]}),
            "timeout_ms": channel["timing"]["search_timeout_ms"],
        },
    ]


def compile_site_filter_program(
    plan: dict[str, Any], channel: dict[str, Any], action_delay_ms: int
) -> list[dict[str, Any]]:
    site_filters = plan.get("site_filters") or {}
    hard_filter_fields = {
        field
        for field, value in (plan.get("hard_filters") or {}).items()
        if value not in (None, [], "", {})
    }
    program: list[dict[str, Any]] = []
    selectors = channel["selectors"]

    def wrap_filter(operations: list[dict[str, Any]], field: str) -> dict[str, Any]:
        return {
            "id": f"apply-filter-{field}",
            "op": "flow.foreach",
            "items": [field],
            "max_iterations": 1,
            "program": operations,
            "on_error": "continue",
            "record_error_as": "search.unsupported_filters[]",
            "error_context": {
                "field": field,
                "requested": site_filters[field],
                "policy": "continue_on_error",
                "hard_filter_fallback": field in hard_filter_fields,
            },
        }

    def stable_waits(field: str) -> list[dict[str, Any]]:
        return [
            {
                "id": f"wait-filter-{field}",
                "op": "page.wait",
                "until": {"none_visible": selectors["loading"]},
                "timeout_ms": channel["timing"]["search_timeout_ms"],
            },
            {
                "id": f"stabilize-filter-{field}",
                "op": "page.wait",
                "until": {
                    "type": "dom_stable",
                    "target": {"any_css": selectors["result_roots"]},
                    "stable_ms": channel["timing"]["stable_window_ms"],
                },
                "timeout_ms": channel["timing"]["search_timeout_ms"],
            },
        ]

    for field in channel["filter_order"]:
        raw_value = site_filters.get(field)
        if raw_value in (None, [], ""):
            continue
        config = channel["filters"][field]
        value = map_filter_value(field, raw_value, channel)
        interaction = config["interaction"]
        operations: list[dict[str, Any]] = []

        if interaction == "city_modal":
            operations.append(
                {
                    "id": f"open-filter-{field}",
                    "op": "page.click",
                    "target": locator_within(config["trigger"], config["row"]),
                    "after_ms": action_delay_ms,
                }
            )
            operations.append(
                {
                    "id": f"wait-filter-{field}-modal",
                    "op": "page.wait",
                    "until": {"any_visible": selectors["city_modal"]},
                    "timeout_ms": channel["timing"]["control_timeout_ms"],
                }
            )
            operations.append(
                {
                    "id": f"choose-filter-{field}-values",
                    "op": "flow.foreach",
                    "items": value,
                    "item_as": "filter_value",
                    "program": [
                        {
                            "id": f"fill-filter-{field}-city",
                            "op": "page.fill",
                            "target": {
                                "any_css": selectors["city_search_inputs"],
                                "within": {"any_css": selectors["city_modal"], "visible": True},
                                "visible": True,
                                "enabled": True,
                            },
                            "value": {"$ref": "filter_value"},
                            "events": ["input", "change"],
                            "after_ms": action_delay_ms,
                        },
                        {
                            "id": f"click-filter-{field}-city",
                            "op": "page.click",
                            "target": {
                                "any_css": selectors["city_suggestions"],
                                "within": {"any_css": selectors["city_modal"], "visible": True},
                                "text": {"contains": {"$ref": "filter_value"}},
                                "visible": True,
                                "enabled": True,
                            },
                            "after_ms": action_delay_ms,
                        },
                    ],
                }
            )
            operations.extend(
                [
                    {
                        "id": f"confirm-filter-{field}",
                        "op": "page.click",
                        "target": {
                            "any_css": selectors["city_confirm"],
                            "within": {"any_css": selectors["city_modal"], "visible": True},
                            "visible": True,
                            "enabled": True,
                        },
                        "after_ms": action_delay_ms,
                    },
                    *stable_waits(field),
                ]
            )
        elif interaction == "company_autocomplete":
            operations.extend(
                compile_company_filter_program(value[0], config, channel, action_delay_ms)
            )
            operations.extend(stable_waits(field))
        elif interaction == "inline_option":
            label = value[0] if isinstance(value, list) else value
            operations.extend(
                [
                    {
                        "id": f"select-filter-{field}",
                        "op": "page.click",
                        "target": {
                            **locator_within(config["option"], config["row"]),
                            "text": {"equals": label},
                        },
                        "after_ms": action_delay_ms,
                    },
                    *stable_waits(field),
                ]
            )
        elif interaction == "select_dropdown":
            row = {**config["row"], "visible": True}
            trigger = locator_within(config["trigger"], row)
            dropdown = {
                "any_css": selectors["select_dropdowns"],
                "text": {"contains": value},
                "visible": True,
            }
            option = {
                "any_css": selectors["select_options"],
                "within": dropdown,
                "text": {"equals": value},
                "visible": True,
                "enabled": True,
            }
            operations.extend(
                [
                    {
                        "id": f"wait-filter-{field}-trigger",
                        "op": "page.wait",
                        "until": {"type": "exists", "target": trigger},
                        "timeout_ms": channel["timing"]["control_timeout_ms"],
                    },
                    *require_unique_filter_targets(
                        f"{field}-control", {"row": row, "trigger": trigger}
                    ),
                    {
                        "id": f"open-filter-{field}",
                        "op": "page.click",
                        "target": trigger,
                        "after_ms": action_delay_ms,
                    },
                    {
                        "id": f"wait-filter-{field}-options",
                        "op": "page.wait",
                        "until": {"type": "exists", "target": option},
                        "timeout_ms": channel["timing"]["control_timeout_ms"],
                    },
                    *require_unique_filter_targets(
                        f"{field}-option", {"dropdown": dropdown, "option": option}
                    ),
                    {
                        "id": f"select-filter-{field}",
                        "op": "page.click",
                        "target": option,
                        "after_ms": action_delay_ms,
                    },
                    {
                        "id": f"verify-filter-{field}-applied",
                        "op": "page.wait",
                        "until": {"all": [
                            {"not": {"type": "exists", "target": dropdown}},
                            {
                                "type": "exists",
                                "target": {**trigger, "text": {"equals": value}},
                            },
                            {
                                "type": "exists",
                                "target": {
                                    "any_css": selectors["submitted_filter_chips"],
                                    "text": {"equals": value},
                                    "visible": True,
                                },
                            },
                            {"none_visible": selectors["loading"]},
                            {"any": [
                                {"any_visible": selectors["candidate_rows"]},
                                {"any_visible": selectors["empty_results"]},
                                {"text_any": channel["text_markers"]["no_results"]},
                            ]},
                        ]},
                        "timeout_ms": channel["timing"]["search_timeout_ms"],
                    },
                    *stable_waits(field),
                ]
            )
        elif interaction == "range_inputs":
            for boundary, selector_key in (("min", "age_low"), ("max", "age_high")):
                if value.get(boundary) is not None:
                    operations.append(
                        {
                            "id": f"fill-filter-{field}-{boundary}",
                            "op": "page.fill",
                            "target": {
                                "any_css": selectors[selector_key],
                                "within": config["row"],
                                "visible": True,
                                "enabled": True,
                            },
                            "value": str(value[boundary]),
                            "events": ["input", "change"],
                        }
                    )
            operations.extend(
                [
                    {
                        "id": f"submit-filter-{field}",
                        "op": "page.click",
                        "target": {
                            "any_css": selectors["age_submit"],
                            "within": config["row"],
                            "visible": True,
                            "enabled": True,
                        },
                        "after_ms": action_delay_ms,
                    },
                    *stable_waits(field),
                ]
            )
        else:
            raise ValueError(f"Skill 渠道资产包含未知筛选交互: {interaction}")
        program.append(wrap_filter(operations, field))
    return program


def text_actual(paths: list[str]) -> dict[str, Any]:
    return {"paths": paths, "join": " ", "normalize": ["trim", "lowercase"]}


def compile_predicates(filters: dict[str, Any], phase: str) -> list[dict[str, Any]]:
    predicates: list[dict[str, Any]] = []
    for filter_field, actual_field in (
        ("expected_cities", "expected_city"),
        ("current_cities", "city"),
        ("education", "education"),
    ):
        expected = filters.get(filter_field) or []
        if expected:
            predicates.append(
                {
                    "id": actual_field,
                    "actual": {"path": actual_field},
                    "operator": "text.includes_any",
                    "expected": expected,
                    "on_missing": "unknown",
                    "on_mismatch": "reject",
                }
            )

    experience = filters.get("experience_years")
    if experience:
        predicates.append(
            {
                "id": "work_years",
                "actual": {"path": "work_years"},
                "operator": "number.in_range",
                "expected": experience,
                "on_missing": "unknown",
                "on_mismatch": "reject",
            }
        )

    school_requirements = filters.get("school_requirements") or []
    if school_requirements:
        if phase == "card":
            predicates.append(
                {
                    "id": "school_requirements",
                    "actual": {"path": "school_tags"},
                    "operator": "set.intersects",
                    "expected": school_requirements,
                    "on_missing": "unknown",
                    "on_mismatch": "unknown",
                }
            )
        else:
            predicates.append(
                {
                    "id": "school_requirements",
                    "actual": {"path": "school_tags"},
                    "known_when": {"path": "education_summary", "operator": "not_empty"},
                    "operator": "set.intersects",
                    "expected": school_requirements,
                    "on_missing": "unknown",
                    "on_mismatch": "reject",
                }
            )

    keyword_paths = (
        ["current_work_text", "expected_title", "skills", "highlights", "card_text"]
        if phase == "card"
        else [
            "current_work_text",
            "expected_title",
            "skills",
            "self_summary",
            "work_experience_summary",
            "project_experience_summary",
            "education_summary",
            "job_intention_summary",
        ]
    )
    keyword_mismatch = "unknown" if phase == "card" else "reject"
    required = filters.get("required_keywords") or {}
    for key, operator in (("all", "text.includes_all"), ("any", "text.includes_any")):
        expected = required.get(key) or []
        if expected:
            predicates.append(
                {
                    "id": f"required_keywords.{key}",
                    "actual": text_actual(keyword_paths),
                    "operator": operator,
                    "expected": expected,
                    "on_missing": "unknown",
                    "on_mismatch": keyword_mismatch,
                }
            )
    groups = filters.get("required_keyword_groups") or []
    if groups:
        predicates.append(
            {
                "id": "required_keyword_groups",
                "actual": text_actual(keyword_paths),
                "operator": "text.includes_groups",
                "expected": groups,
                "on_missing": "unknown",
                "on_mismatch": keyword_mismatch,
            }
        )
    company_paths = (
        ["current_work_text", "card_text"]
        if phase == "card"
        else ["current_work_text", "work_experience_summary", "project_experience_summary"]
    )
    work_content_paths = (
        ["highlights", "card_text", "current_work_text"]
        if phase == "card"
        else [
            "highlights",
            "work_experience_summary",
            "project_experience_summary",
            "self_summary",
        ]
    )
    for field, paths in (("company", company_paths), ("work_content", work_content_paths)):
        expected = filters.get(field) or []
        if expected:
            predicates.append(
                {
                    "id": field,
                    "actual": text_actual(paths),
                    "operator": "text.includes_any",
                    "expected": expected,
                    "on_missing": "unknown",
                    "on_mismatch": "unknown" if phase == "card" else "reject",
                }
            )
    return predicates


def resolve_template(
    value: Any,
    *,
    channel: dict[str, Any],
    plan: dict[str, Any],
    generated: dict[str, Any],
    schemas: dict[str, Any],
    workflows: dict[str, Any],
) -> Any:
    sources = {
        "$channel": (channel, "channel"),
        "$plan": (plan, "plan"),
        "$generated": (generated, "generated"),
        "$schema": (schemas, "schema"),
        "$workflow": (workflows, "workflow"),
    }
    if isinstance(value, dict):
        if len(value) == 1:
            key, path = next(iter(value.items()))
            if key in sources and isinstance(path, str):
                source, source_name = sources[key]
                resolved = lookup(source, path, source_name)
                return resolve_template(
                    resolved,
                    channel=channel,
                    plan=plan,
                    generated=generated,
                    schemas=schemas,
                    workflows=workflows,
                )
        return {
            key: resolve_template(
                item,
                channel=channel,
                plan=plan,
                generated=generated,
                schemas=schemas,
                workflows=workflows,
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        result: list[Any] = []
        for item in value:
            resolved = resolve_template(
                item,
                channel=channel,
                plan=plan,
                generated=generated,
                schemas=schemas,
                workflows=workflows,
            )
            should_expand = (
                isinstance(item, dict)
                and len(item) == 1
                and next(iter(item)) in {"$generated", "$workflow"}
                and isinstance(resolved, list)
            )
            if should_expand:
                result.extend(resolved)
            else:
                result.append(resolved)
        return result
    return copy.deepcopy(value)


def validate_program(program: Any) -> None:
    if not isinstance(program, list):
        raise ValueError("page.run.program 必须是数组")
    for operation in program:
        if not isinstance(operation, dict) or operation.get("op") not in PAGE_OPS:
            raise ValueError(f"工作流包含不支持的页面 op: {operation!r}")
        for nested_key in ("program", "then", "else"):
            if nested_key in operation:
                validate_program(operation[nested_key])


def validate_workflow(workflow: dict[str, Any]) -> None:
    if workflow.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Workflow schema_version 无效")
    if workflow.get("workflow_schema") != WORKFLOW_SCHEMA:
        raise ValueError("Workflow workflow_schema 无效")
    steps = workflow.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("Workflow steps 不能为空")
    for step in steps:
        if not isinstance(step, dict) or step.get("action") not in HOST_ACTIONS:
            raise ValueError(f"工作流包含不支持的 Host action: {step!r}")
        if step["action"] == "page.run":
            validate_program(step.get("program"))
        if step["action"] == "tabs.foreach":
            pre_program = step.get("open", {}).get("pre_program", [])
            validate_program(pre_program)
            for nested_step in step.get("steps", []):
                if nested_step.get("action") != "page.run":
                    raise ValueError("tabs.foreach 首期只允许嵌套 page.run")
                validate_program(nested_step.get("program"))
    encoded = json.dumps(workflow, ensure_ascii=False)
    forbidden = ("adapter.invoke", "liepin.validate_session", "liepin.search_candidates", "liepin.fetch_details")
    if any(value in encoded for value in forbidden):
        raise ValueError("通用 Workflow 中不得包含旧渠道 capability")


def expected_search_plan_path(task_work_dir: Path, iteration: int) -> Path:
    if not 1 <= iteration <= MAX_SEARCH_ITERATION:
        raise ValueError(
            f"搜索计划轮次仅支持 1-{MAX_SEARCH_ITERATION}，首轮必须使用 iteration-1.json"
        )
    return (
        task_work_dir / SKILL_NAME / "search-plans" / f"iteration-{iteration}.json"
    ).resolve()


def prefix_step_ids(value: Any, prefix: str) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key == "id" and isinstance(item, str):
                result[key] = f"{prefix}-{item}"
            else:
                result[key] = prefix_step_ids(item, prefix)
        return result
    if isinstance(value, list):
        return [prefix_step_ids(item, prefix) for item in value]
    return value


def schemas_for_path(assets: dict[str, Any], path_name: str) -> dict[str, Any]:
    schemas = copy.deepcopy(assets["schemas"])
    schemas["card"].setdefault("computed", {})["search_path"] = {"constant": path_name}
    return schemas


def compile_path_steps(
    *,
    path_name: str,
    query: str,
    max_cards: int,
    max_details: int,
    action_delay_ms: int,
    site_filter_program: list[dict[str, Any]],
    card_predicates: list[dict[str, Any]],
    detail_predicates: list[dict[str, Any]],
    assets: dict[str, Any],
    plan: dict[str, Any],
    channel: dict[str, Any],
    interaction_mode: str = "direct",
) -> list[dict[str, Any]]:
    generated = {
        "keyword_text": query,
        "site_filter_program": site_filter_program,
        "card_predicates": card_predicates,
        "detail_predicates": detail_predicates,
        "max_pages": 1,
        "max_candidates": max_cards,
        "max_details": max_details,
        "action_delay_ms": action_delay_ms,
        "search_output_key": f"search_{path_name}",
        "cards_context": f"search_{path_name}.cards",
        "card_filter_key": f"card_filter_{path_name}",
        "details_key": f"details_{path_name}",
        "detail_filter_key": f"detail_filter_{path_name}",
        "failures_key": f"failures_{path_name}",
        "detail_browse_program": ([
            {"id": "browse-detail", "op": "page.scroll", "direction": "down", "distance": 600},
            {"id": "detect-after-detail-scroll", "op": "page.detect", "rules": channel["page_detection"]},
        ] if interaction_mode == "human" else []),
    }
    steps = resolve_template(
        assets["workflows"]["search"]["path_steps"],
        channel=channel,
        plan=plan,
        generated=generated,
        schemas=schemas_for_path(assets, path_name),
        workflows=assets["workflows"],
    )
    if max_details == 0:
        steps = [
            step
            for step in steps
            if step["id"] not in {"collect-candidate-details", "detail-hard-filter"}
        ]
    return prefix_step_ids(steps, path_name)


def build_emit_step(paths: list[dict[str, Any]]) -> dict[str, Any]:
    summary_paths: dict[str, Any] = {}
    search: dict[str, Any] = {}
    candidates: dict[str, Any] = {}
    details: dict[str, Any] = {}
    failures: dict[str, Any] = {}
    for path in paths:
        name = path["name"]
        summary_paths[name] = {
            "query": path["query"],
            "pages_visited": {"$context": f"search_{name}.pages.length"},
            "unsupported_filter_count": {
                "$context": f"search_{name}.unsupported_filters.length"
            },
            "card_filter": {"$context": f"_runtime.reports.{name}-card-hard-filter"},
            "detail_filter": (
                {"$context": f"_runtime.reports.{name}-detail-hard-filter"}
                if path["max_details"]
                else {"evaluated": 0, "matched": 0, "rejected": 0, "unknown": 0}
            ),
        }
        search[name] = {
            "query": path["query"],
            "unsupported_filters": {"$context": f"search_{name}.unsupported_filters"},
            "pages": {"$context": f"search_{name}.pages"},
        }
        candidates[name] = {"$context": f"card_filter_{name}"}
        details[name] = (
            {"$context": f"detail_filter_{name}"} if path["max_details"] else []
        )
        failures[name] = {"$context": f"failures_{name}"} if path["max_details"] else []
    return {
        "id": "emit-search-result",
        "action": "result.emit",
        "value": {
            "summary": {
                "workflow": "candidate_search",
                "channel": "liepin",
                "paths": summary_paths,
            },
            "search": search,
            "candidates": candidates,
            "details": details,
            "failures": failures,
        },
    }


def base_workflow(args: argparse.Namespace, template: dict[str, Any], channel: dict[str, Any]) -> dict[str, Any]:
    created_at = datetime.now(timezone.utc)
    interaction_mode = getattr(args, "interaction_mode", None) or channel.get("interaction_mode", "direct")
    if interaction_mode not in {"direct", "human"}:
        raise ValueError("interaction_mode 仅支持 direct 或 human")
    return {
        "schema_version": SCHEMA_VERSION,
        "workflow_schema": WORKFLOW_SCHEMA,
        "workflow_id": str(uuid.uuid4()),
        "workflow_type": template["workflow_type"],
        "task_id": args.task_id,
        "iteration": args.iteration,
        "interaction_mode": interaction_mode,
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
        "expires_at": (created_at + timedelta(minutes=args.deadline_minutes))
        .isoformat()
        .replace("+00:00", "Z"),
        "skill": {"name": SKILL_NAME, "version": SKILL_VERSION},
        "channel": {
            "id": channel["channel_id"],
            "display_name": channel["display_name"],
            "rule_version": channel["rule_version"],
        },
        "allowed_domains": channel["allowed_domains"],
        "required_capabilities": [*template["required_capabilities"], *(["interaction.human.v1"] if interaction_mode == "human" else [])],
    }


def build_preflight(args: argparse.Namespace, assets: dict[str, Any]) -> dict[str, Any]:
    channel = assets["channel"]
    template = assets["workflows"]["preflight"]
    workflow = base_workflow(args, template, channel)
    workflow["limits"] = {
        "max_step_executions": 20,
        "max_loop_iterations": 1,
        "max_extract_items": 1,
        "max_field_length": 5000,
        "default_timeout_ms": channel["timing"]["search_timeout_ms"],
        "poll_interval_ms": channel["timing"]["poll_interval_ms"],
        "max_result_bytes": 64 * 1024,
    }
    workflow["steps"] = resolve_template(
        template["steps"],
        channel=channel,
        plan={},
        generated={},
        schemas=assets["schemas"],
        workflows=assets["workflows"],
    )
    validate_workflow(workflow)
    return workflow


def build_search(args: argparse.Namespace, assets: dict[str, Any]) -> dict[str, Any]:
    plan, warnings = read_plan(args.plan_file)
    previous_plan = executed_plan(args, args.iteration - 1) if args.iteration > 1 else None
    if previous_plan and not plan.get("decision_basis"):
        raise ValueError("第 2 轮起必须填写 decision_basis，不能删除它来跳过条件与历史评分校验")
    args.decision_receipt = decision_receipt(
        plan, iteration=args.iteration, task_id=args.task_id,
        store_root=Path(args.store_root).expanduser().resolve(), previous_plan=previous_plan,
    )
    if args.iteration == 1 and plan.get("secondary_query"):
        raise ValueError("第 1 轮不能设置 secondary_query")
    channel = assets["channel"]
    template = assets["workflows"]["search"]
    workflow = base_workflow(args, template, channel)
    limits = plan["limits"]
    action_delay_ms = bounded_integer(
        plan.get("action_delay_ms"),
        1200,
        channel["timing"]["minimum_action_delay_ms"],
        5000,
    )
    hard_filters = plan.get("hard_filters") or {}
    site_filters = plan.get("site_filters") or {}
    site_filter_fields = {
        field for field, value in site_filters.items() if value not in (None, [], "")
    }
    hard_site_filter_fields = sorted(site_filter_fields & set(hard_filters))
    site_filter_program = compile_site_filter_program(plan, channel, action_delay_ms)
    card_predicates = compile_predicates(hard_filters, "card")
    detail_predicates = compile_predicates(hard_filters, "detail")
    paths = [
        {
            "name": "primary",
            "query": plan["primary_query"],
            "max_cards": limits["max_cards_per_path"],
            "max_details": limits["primary_max_details"],
        }
    ]
    if plan.get("secondary_query"):
        paths.append(
            {
                "name": "secondary",
                "query": plan["secondary_query"],
                "max_cards": limits["max_cards_per_path"],
                "max_details": limits["secondary_max_details"],
            }
        )
    steps: list[dict[str, Any]] = []
    for path in paths:
        steps.extend(
            compile_path_steps(
                path_name=path["name"],
                query=path["query"],
                max_cards=path["max_cards"],
                max_details=path["max_details"],
                action_delay_ms=action_delay_ms,
                site_filter_program=site_filter_program,
                card_predicates=card_predicates,
                detail_predicates=detail_predicates,
                assets=assets,
                plan=plan,
                channel=channel,
                interaction_mode=workflow["interaction_mode"],
            )
        )
    steps.append(build_emit_step(paths))
    total_details = sum(path["max_details"] for path in paths)
    total_cards = limits["max_cards_per_path"] * len(paths)
    workflow["limits"] = {
        "max_pages": 1,
        "max_candidates": total_cards,
        "max_tabs": total_details,
        "max_result_bytes": channel["limits"]["max_result_bytes"],
        "action_delay_ms": action_delay_ms,
        "max_step_executions": 5000,
        "max_loop_iterations": 20,
        "max_extract_items": total_cards,
        "max_field_length": channel["limits"]["max_section_length"],
        "default_timeout_ms": channel["timing"]["search_timeout_ms"],
        "poll_interval_ms": channel["timing"]["poll_interval_ms"],
    }
    workflow["input_summary"] = {
        "requirement_version": plan["requirement_version"],
        "primary_query": plan["primary_query"],
        "secondary_query": plan.get("secondary_query"),
        "site_filter_fields": sorted(site_filter_fields),
        "hard_filter_fields": sorted(hard_filters.keys()),
        "semantic_criteria": plan["semantic_criteria"],
        "limits": limits,
        "site_filter_failure_policy": {
            "continue_and_report": sorted(site_filter_fields),
            "hard_filter_fallback": hard_site_filter_fields,
        },
        "warnings": warnings,
    }
    # Covered by the workflow digest; later rounds compare against what ran,
    # not an editable iteration-N.json. The host never executes this metadata.
    workflow["input_plan"] = copy.deepcopy(plan)
    workflow["steps"] = steps
    validate_workflow(workflow)
    return workflow


def executed_plan(args: argparse.Namespace, iteration: int) -> dict[str, Any]:
    """Recover the most recently completed plan for a round from immutable stores."""
    root = Path(args.store_root).expanduser().resolve()
    workflows = {}
    for path in (root / "workflow-store" / args.task_id).glob("*.json"):
        if not path.resolve().is_relative_to(root) or path.stat().st_size > 256 * 1024:
            raise ValueError("历史工作流越界或超过大小限制")
        workflow = load_json(path)
        if (workflow.get("task_id") != args.task_id or workflow.get("iteration") != iteration
                or (workflow.get("skill") or {}).get("name") != SKILL_NAME):
            continue
        integrity = workflow.pop("integrity", {})
        digest = hashlib.sha256(canonical_bytes(workflow)).hexdigest()
        if digest != path.stem or integrity.get("digest") != digest:
            raise ValueError("历史工作流摘要不匹配，不能依据已变化的计划继续")
        if isinstance(workflow.get("input_plan"), dict):
            workflows[workflow["workflow_id"]] = workflow["input_plan"]
    if not workflows:
        # Compatibility for workflows compiled before input_plan was recorded.
        return read_plan(str(expected_search_plan_path(Path(args.task_work_dir), iteration)))[0]
    completed = []
    for path in (root / "result-store" / args.task_id).glob("*.json"):
        if not path.resolve().is_relative_to(root) or path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError("历史结果越界或超过大小限制")
        raw = path.read_bytes()
        result = json.loads(raw)
        metadata = result.get("workflow") or {}
        workflow_id = metadata.get("workflow_id")
        if workflow_id not in workflows or result.get("status") not in {"success", "partial"}:
            continue
        if metadata.get("task_id") != args.task_id or hashlib.sha256(raw).hexdigest() != path.stem:
            raise ValueError("历史结果任务或摘要不匹配，不能复用执行计划")
        completed.append((metadata.get("finished_at") or "", workflow_id))
    if not completed:
        raise ValueError(f"第 {iteration} 轮没有已完成结果；先读取执行状态对账，不能跳过该轮或原样重跑")
    return workflows[max(completed)[1]]


def save_workflow(workflow: dict[str, Any], store_root: Path) -> dict[str, Any]:
    digest = hashlib.sha256(canonical_bytes(workflow)).hexdigest()
    workflow["integrity"] = {"algorithm": "sha256", "digest": digest}
    encoded = canonical_bytes(workflow)
    if len(encoded) > 256 * 1024:
        raise ValueError("生成的 workflow 超过 256 KiB")

    target = store_root / "workflow-store" / workflow["task_id"] / f"{digest}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() != encoded:
            raise ValueError("摘要相同但 Workflow Store 内容冲突")
    else:
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        try:
            temporary.write_bytes(encoded)
            os.chmod(temporary, 0o600)
            temporary.replace(target)
        finally:
            if temporary.exists():
                temporary.unlink()

    return {
        "status": "success",
        "workflow_ref": f"wf://{workflow['task_id']}/{digest}",
        "digest": digest,
        "summary": {
            "workflow_schema": workflow["workflow_schema"],
            "workflow_type": workflow["workflow_type"],
            "channel": workflow["channel"],
            "iteration": workflow["iteration"],
            "interaction_mode": workflow.get("interaction_mode", "direct"),
            "step_count": len(workflow["steps"]),
            "input": workflow.get("input_summary"),
            "expires_at": workflow["expires_at"],
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="WTS：preflight 登录前置；search 编译搜索；settle 结算最后已完成的轮次（不新增搜索）",
        epilog="仅支持 preflight/search/settle，没有 reflect 子命令。settle --iteration N 使用最后已完成轮次 N（1-5），不是 N+1。",
    )
    parser.add_argument("workflow_type", choices=["preflight", "search", "settle"])
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--iteration", type=int, default=0)
    parser.add_argument("--plan-file", help="默认读取任务目录 wts/search-plans/iteration-N.json")
    parser.add_argument("--decision-file", help="settle 默认读取任务目录 wts/final-decision.json")
    parser.add_argument("--task-work-dir", default=os.environ.get("DEEPAGENT_TASK_WORK_DIR", ""))
    parser.add_argument("--store-root", default=os.environ.get("DEEPAGENT_WORKFLOW_STORE_DIR", ""))
    parser.add_argument("--deadline-minutes", type=int, default=20)
    parser.add_argument("--interaction-mode", choices=["direct", "human"], help="交互模式；省略时使用渠道资产的默认值")
    args = parser.parse_args()
    if not TASK_ID_PATTERN.fullmatch(args.task_id):
        parser.error("--task-id 仅支持 1-100 位字母、数字、点、下划线和短横线")
    if not 0 <= args.iteration <= 100:
        parser.error("--iteration 必须在 0-100 之间")
    if args.workflow_type == "preflight" and args.iteration != 0:
        parser.error("preflight 的 --iteration 必须为 0")
    if args.workflow_type in {"search", "settle"} and not 1 <= args.iteration <= MAX_SEARCH_ITERATION:
        parser.error(
            f"{args.workflow_type} 的 --iteration 仅支持 1-{MAX_SEARCH_ITERATION}；settle 填最后已完成的轮次，不是下一轮"
        )
    if not args.task_work_dir:
        parser.error("缺少 DEEPAGENT_TASK_WORK_DIR 或 --task-work-dir")
    if not args.store_root:
        parser.error("缺少 DEEPAGENT_WORKFLOW_STORE_DIR 或 --store-root")

    task_work_dir = Path(args.task_work_dir).expanduser().resolve()
    store_root = Path(args.store_root).expanduser().resolve()
    configured_task_work_dir = os.environ.get("DEEPAGENT_TASK_WORK_DIR", "").strip()
    configured_store_root = os.environ.get("DEEPAGENT_WORKFLOW_STORE_DIR", "").strip()
    if configured_task_work_dir and task_work_dir != Path(configured_task_work_dir).expanduser().resolve():
        parser.error("--task-work-dir 必须等于当前运行时注入的任务工作目录")
    if configured_store_root and store_root != Path(configured_store_root).expanduser().resolve():
        parser.error("--store-root 必须等于当前会话的 Workflow Store 目录")

    args.task_work_dir = str(task_work_dir)
    args.store_root = str(store_root)
    if args.workflow_type in {"search", "settle"}:
        expected_plan = expected_search_plan_path(task_work_dir, args.iteration)
        plan_path = Path(args.plan_file).expanduser().resolve() if args.plan_file else expected_plan
        if plan_path != expected_plan:
            parser.error(f"--plan-file 路径无效；当前轮次只能使用 {expected_plan}")
        args.plan_file = str(plan_path)
    if args.workflow_type == "settle":
        expected_decision = (task_work_dir / SKILL_NAME / "final-decision.json").resolve()
        if args.decision_file and Path(args.decision_file).expanduser().resolve() != expected_decision:
            parser.error(f"settle 的 --decision-file 必须为 {expected_decision}")
        args.decision_file = str(expected_decision)
    args.deadline_minutes = bounded_integer(args.deadline_minutes, 20, 5, 30)
    return args


def main() -> None:
    args = parse_args()
    if args.workflow_type == "settle":
        plan = executed_plan(args, args.iteration)
        decision_path = Path(args.decision_file)
        if not decision_path.is_file():
            raise ValueError(f"先用 write_file 创建最终 decision_basis：{decision_path}；completed_iteration={args.iteration}，next_action.action=report")
        if decision_path.stat().st_size > 64 * 1024:
            raise ValueError("最终评分快照不能超过 64 KiB")
        report_data = {}
        receipt = decision_receipt(
            {**plan, "decision_basis": load_json(decision_path)},
            iteration=args.iteration + 1, task_id=args.task_id,
            store_root=Path(args.store_root), previous_plan=plan, settle=True, report_data=report_data,
        )
        report_path = Path(args.task_work_dir) / SKILL_NAME / "final-report-data.json"
        temporary = report_path.with_name(f".{report_path.name}.{os.getpid()}.tmp")
        try:
            temporary.write_text(json.dumps(report_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.chmod(temporary, 0o600)
            temporary.replace(report_path)
        finally:
            if temporary.exists():
                temporary.unlink()
        print(json.dumps({"status": "success", "decision_receipt": receipt,
                          "report_data_file": str(report_path),
                          "next_action": {"action": "report", "instruction": "读取 report_data_file，使用其中已核验的姓名、detail_url、分数、证据和 unknown 交付报告；null 明确写缺失。无需扫描结果目录或重评。"}},
                         ensure_ascii=False, separators=(",", ":")))
        return
    assets = load_assets()
    workflow = build_preflight(args, assets) if args.workflow_type == "preflight" else build_search(args, assets)
    output = save_workflow(workflow, Path(args.store_root).expanduser().resolve())
    if getattr(args, "decision_receipt", None) is not None:
        output["decision_receipt"] = args.decision_receipt
    output["next_action"] = {
        "tool": "browser_run_workflow", "task_id": args.task_id,
        "workflow_ref": output["workflow_ref"],
        "instruction": "编译成功。使用此引用执行既定工作流；不要重新评分或重新选择关键词。",
    }
    print(json.dumps(output, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        print(json.dumps({"status": "error", "error": str(error),
                          "instruction": "按具体错误修正当前输入；已有文件用 edit_file，不回改已执行计划，不猜测额外子命令。"}, ensure_ascii=False))
        sys.exit(2)

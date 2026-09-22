"""Compile bounded jitter into the existing page DSL; no runtime or network code."""
from __future__ import annotations

import random
from typing import Any

# Page detection and load polling deliberately remain immediate.
ATOMIC_OPS = {"page.click", "page.fill", "page.press", "page.extract", "page.extract_list"}
DETAIL_BUDGET_MS = 15000
INDEX_PATH = "_wts_pacing_index"


def split_budget(count: int, rng: random.Random) -> list[int]:
    """Balance small variations so one detail still adds exactly 15 seconds."""
    base = DETAIL_BUDGET_MS / count
    offsets = [rng.uniform(-0.1, 0.1) for _ in range(count)]
    mean = sum(offsets) / count
    values = [round(base * (1 + offset - mean)) for offset in offsets]
    values[-1] += DETAIL_BUDGET_MS - sum(values)
    return values


def wait_step(step_id: str, milliseconds: int) -> dict[str, Any]:
    return {"id": step_id, "op": "page.wait", "until": {"type": "delay", "ms": milliseconds}}


def indexed_wait(step_id: str, durations: list[int]) -> dict[str, Any]:
    # Each candidate gets its own precompiled values. No unsupported runtime RNG
    # or dynamic array indexing is required. The host supplies the foreach index.
    result = wait_step(f"{step_id}-{len(durations) - 1}", durations[-1])
    for index in reversed(range(len(durations) - 1)):
        result = {
            "id": f"{step_id}-choose-{index}", "op": "flow.if",
            "condition": {"type": "variable", "path": INDEX_PATH,
                          "operator": "equals", "value": index},
            "then": [wait_step(f"{step_id}-{index}", durations[index])],
            "else": [result],
        }
    return result


def pace_program(program, base, rng, detail_delays=None):
    result = []
    for step in program:
        for key in ("program", "then", "else"):
            if key in step:
                step[key] = pace_program(step[key], base, rng, detail_delays)
        if step.get("op") in ATOMIC_OPS:
            # Replace the old click tail delay, rather than stacking two policies.
            milliseconds = step.pop("after_ms", step.pop("delay_after_ms", base))
            wait_id = "pacing-before-" + step["id"]
            if detail_delays is not None and step["id"] in detail_delays:
                result.append(indexed_wait(wait_id, detail_delays[step["id"]]))
            else:
                result.append(wait_step(wait_id, rng.randint(round(milliseconds * .8), round(milliseconds * 1.2))))
        result.append(step)
    return result


def pace_navigation(program, navigation_id, base, rng):
    # The first page can be about:blank (no page adapter yet). Pace immediately
    # AFTER navigation and its safety detection, before any ordinary operation.
    if not program or program[0].get("op") != "page.detect":
        raise ValueError("Navigation pacing requires an immediate safety detector")
    program.insert(1, wait_step("pacing-after-" + navigation_id,
                               rng.randint(round(base * .8), round(base * 1.2))))


def initialize_index(program, step_id):
    program.insert(0, {"id": "pacing-index-" + step_id, "op": "data.set",
                       "path": INDEX_PATH, "value": {"$index": True}})


def maximum_delay(program):
    """Bound injected waits, following the most expensive conditional branch."""
    total = 0
    for step in program:
        if step.get("op") == "page.wait" and step.get("until", {}).get("type") == "delay":
            total += step["until"]["ms"]
        if step.get("op") == "flow.if":
            total += max(maximum_delay(step.get("then", [])), maximum_delay(step.get("else", [])))
    return total


def pace_details(step, base, channel, rng):
    opening = step["open"]
    opening["program"] = [{"id": step["id"] + "-open", "op": "page.click", "target": opening["target"]}]
    programs = [opening["pre_program"], opening["program"], *[s["program"] for s in step["steps"]]]
    # Normal path: read list position -> open detail -> extract detail.
    # Conditional page restoration receives the smaller ordinary action delay.
    operations = [s for program in programs for s in program if s.get("op") in ATOMIC_OPS]
    if len(operations) != 3:
        raise ValueError("Detail pacing budget must be reviewed when its atomic sequence changes")
    allocations = [split_budget(len(operations), rng) for _ in range(step["max_items"])]
    delays = {op["id"]: [row[index] for row in allocations] for index, op in enumerate(operations)}
    opening["pre_program"] = pace_program(opening["pre_program"], base, rng, delays)
    opening["program"] = pace_program(opening["program"], base, rng, delays)
    initialize_index(opening["pre_program"], step["id"])
    for nested in step["steps"]:
        nested["program"] = pace_program(nested["program"], base, rng, delays)
        initialize_index(nested["program"], nested["id"])
    # Capture begins before pre_program. Include both injected waits and the
    # restoration click/wait, final target lookup, and original popup window.
    opening["timeout_ms"] = (maximum_delay(opening["pre_program"]) + maximum_delay(opening["program"])
                             + 3 * channel["timing"]["search_timeout_ms"]
                             + channel["timing"]["detail_timeout_ms"])
    if opening["timeout_ms"] > 120000:
        raise ValueError("Paced popup capture exceeds the supported runtime budget")


def pace_search_path(steps, *, action_delay_ms, channel, rng=None):
    rng = rng or random.SystemRandom()
    navigation_id = None
    for step in steps:
        if step["action"] == "page.navigate":
            navigation_id = step["id"]
        elif step["action"] == "page.run":
            step["program"] = pace_program(step["program"], action_delay_ms, rng)
            if navigation_id:
                pace_navigation(step["program"], navigation_id, action_delay_ms, rng)
                navigation_id = None
        elif step["action"] == "tabs.foreach":
            pace_details(step, action_delay_ms, channel, rng)
    if navigation_id:
        raise ValueError("Navigation has no following page program for pacing")
    return steps


def pace_preflight(steps, *, channel):
    pace_search_path(steps, action_delay_ms=1200, channel=channel)

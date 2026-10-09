"""Reconcile immutable session evidence before compiling another browser action."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

REF = re.compile(r'result://([A-Za-z0-9._-]{1,100})/([a-f0-9]{64})')


def read_result(root, ref):
    match = REF.fullmatch(str(ref))
    if not match:
        raise ValueError('result_ref 格式无效')
    root = Path(root).resolve()
    path = root / 'result-store' / match[1] / (match[2] + '.json')
    if not path.resolve().is_relative_to(root) or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('结果不在当前会话 Store 中或过大')
    raw = path.read_bytes()
    result = json.loads(raw)
    if hashlib.sha256(raw).hexdigest() != match[2] or result.get('workflow', {}).get('task_id') != match[1]:
        raise ValueError('结果归属或摘要不匹配')
    return result


def session_history(root):
    """The runtime supplies a session-scoped store; never search outside that root."""
    root = Path(root).resolve()
    workflows = {}
    for path in sorted((root / 'workflow-store').glob('*/*.json')):
        if not path.resolve().is_relative_to(root) or path.stat().st_size > 256 * 1024:
            raise ValueError('历史工作流越界或过大')
        w = json.loads(path.read_bytes())
        integrity = w.pop('integrity', {})
        digest = hashlib.sha256(json.dumps(w, ensure_ascii=False, sort_keys=True,
                                          separators=(',', ':')).encode()).hexdigest()
        if digest != path.stem or integrity.get('digest') != digest or w.get('task_id') != path.parent.name:
            raise ValueError('历史工作流归属或摘要不匹配')
        if w.get('skill', {}).get('name') == 'wts':
            workflows[(w['task_id'], w['workflow_id'])] = w
    results = {}
    for path in sorted((root / 'result-store').glob('*/*.json')):
        ref = f'result://{path.parent.name}/{path.stem}'
        r = read_result(root, ref)
        key = (r['workflow']['task_id'], r['workflow'].get('workflow_id'))
        if key in workflows:
            results.setdefault(key, []).append((ref, r))
    return workflows, results


def source_workflow(root, ref):
    result = read_result(root, ref)
    workflows, _ = session_history(root)
    meta = result['workflow']
    source = workflows.get((meta['task_id'], meta.get('workflow_id')))
    if not source:
        raise ValueError('结果缺少同会话内可核验的原工作流')
    return source, result


def selection(workflow):
    summary = workflow.get('input_summary', {})
    if workflow.get('expansion'):
        return {'expand': summary.get('include_candidate_refs', [])}
    return summary.get('selection') or {}


def scope(workflow):
    return workflow.get('input_summary', {}).get('recovery_scope') or f"{workflow['task_id']}:{workflow['iteration']}"


def not_started(workflow, result, path):
    """Only explicit pre-collection evidence establishes that no card was opened."""
    data = result.get('data') or {}
    check = ((data.get('search') or {}).get(path) or {}).get('collection_check') or {}
    if check.get('status') == 'needs_restore':
        return True
    steps = workflow.get('steps', [])
    failed = data.get('failed_step_id')
    failed_at = next((i for i, s in enumerate(steps) if s['id'] == failed), None)
    tabs_at = next((i for i, s in enumerate(steps) if s['id'] == path + '-collect-candidate-details'), None)
    return failed_at is not None and tabs_at is not None and failed_at < tabs_at


def reconcile(root, requested, recovery_scope, plan, seen=(), retry=()):
    workflows, results = session_history(root)
    completed, failed, uncertain, occupied, attempts, scored = {}, {}, set(seen), {}, [], set()
    page_checks = []
    criteria = {k: plan.get(k) for k in ('requirement_version', 'hard_filters', 'semantic_criteria')}
    for key, w in workflows.items():
        old_plan = w.get('input_plan', {})
        if {k: old_plan.get(k) for k in criteria} == criteria:
            for score in old_plan.get('decision_basis', {}).get('candidate_scores', []):
                # Actual score validation happens again in decision_receipt.
                scored.add(score['candidate_ref'])
        selected = selection(w)
        if not selected:
            continue
        runs = results.get(key, [])
        same_scope = scope(w) == recovery_scope
        for path, refs in selected.items():
            budget = ('expand:' + str(w['expansion'])) if path == 'expand' else path
            for ref in refs:
                if not runs:
                    uncertain.add(ref)
                    attempts.append({'candidate_ref': ref, 'result_ref': None, 'workflow_id': w['workflow_id'],
                                     'state': 'uncertain', 'scope': scope(w), 'path': budget})
                    if same_scope:
                        occupied.setdefault(budget, set()).add(ref)
            for result_ref, r in runs:
                data = r.get('data') or {}
                check = (data.get('search', {}).get(path) or {}).get('collection_check')
                if same_scope and check and check.get('status') == 'needs_restore':
                    page_checks.append({'result_ref': result_ref, 'path': path, **check})
                rows = {row['candidate_ref']: row for row in (data.get('details', {}).get(path) or [])}
                errors = {row['candidate_ref']: row for row in (data.get('failures', {}).get(path) or [])}
                for ref in refs:
                    if ref in rows:
                        completed.setdefault(ref, {'candidate_ref': ref, 'detail_ref': result_ref,
                            'detail_section': 'details.' + path,
                            'finished_at': r.get('workflow', {}).get('finished_at')})
                        state = 'collected'
                    elif ref in errors:
                        error = errors[ref]
                        nested = error.get('error') if isinstance(error.get('error'), dict) else {}
                        failed[ref] = {'candidate_ref': ref, 'result_ref': result_ref,
                                       'section': 'failures.' + path,
                                       'error_code': error.get('error_code') or nested.get('code'),
                                       'step_id': error.get('step_id') or nested.get('step_id')}
                        state = 'failed'
                    elif not_started(w, r, path):
                        continue
                    else:
                        uncertain.add(ref)
                        state = 'uncertain'
                    attempts.append({'candidate_ref': ref, 'result_ref': result_ref,
                                     'state': state, 'scope': scope(w), 'path': budget})
                    if same_scope:
                        occupied.setdefault(budget, set()).add(ref)
    uncertain -= completed.keys()
    # An explicit failure is retryable only if no other invocation has unknown effects.
    retry = set(retry)
    if retry - (failed.keys() - uncertain - completed.keys()):
        raise ValueError('retry-candidate 只能引用明确失败且没有成功或效果不明记录的人')
    checkpoints = score_checkpoints(root, criteria)
    for packet, _ in checkpoints:
        scored.update(row['candidate_ref'] for row in packet['output']['candidate_scores'])
    wanted = set(ref for refs in requested.values() for ref in refs)
    remaining = {path: [ref for ref in refs if ref not in completed and ref not in uncertain
                       and (ref not in failed or ref in retry)] for path, refs in requested.items()}
    return {'completed': [v for k, v in completed.items() if k in wanted],
            'failed': [v for k, v in failed.items() if k in wanted and k not in completed],
            'uncertain': sorted(uncertain & wanted), 'remaining': remaining,
            'already_scored': sorted(scored & wanted & completed.keys()),
            'score_files': [str(path) for packet, path in checkpoints if any(
                row['candidate_ref'] in wanted for row in packet['output']['candidate_scores'])],
            'occupied': {k: sorted(v) for k, v in occupied.items()},
            'page_checks': page_checks,
            'attempts': [a for a in attempts if a['scope'] == recovery_scope],
            'next_action': 'collect' if any(remaining.values()) else
                           ('score' if (wanted & completed.keys()) - scored else 'continue')}


def round_receipt(root, task_id, iteration, source_task_id=None):
    recovery_scope = f'{source_task_id or task_id}:{iteration}'
    workflows, _ = session_history(root)
    members = [w for w in workflows.values() if scope(w) == recovery_scope]
    if not members:
        raise ValueError('当前会话没有该任务/轮次的已校验工作流')
    requested = {}
    for w in members:
        chosen = w.get('input_summary', {}).get('requested_selection') or selection(w)
        for name, refs in chosen.items():
            requested.setdefault(name, [])
            requested[name] = list(dict.fromkeys(requested[name] + refs))
    plans = [w for w in members if w.get('input_plan') and not w.get('expansion') and not w.get('refill')]
    if not plans:
        raise ValueError('找不到原轮次计划')
    latest = max(plans, key=lambda w: w.get('created_at', ''))
    receipt = reconcile(root, requested, recovery_scope, latest['input_plan'])
    receipt['recovery_scope'] = recovery_scope
    receipt['detail_result_refs'] = list(dict.fromkeys(e['detail_ref'] for e in receipt['completed']))
    receipt['result_refs'] = list(dict.fromkeys(receipt['detail_result_refs'] +
        [e['result_ref'] for e in receipt['failed']]))
    return receipt


def score_checkpoints(root, criteria):
    root = Path(root).resolve()
    found = []
    for path in (root / 'wts-score-store').glob('*/*.json'):
        if not path.resolve().is_relative_to(root) or path.stat().st_size > 1024 * 1024:
            raise ValueError('评分记录越界或过大')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != path.stem:
            raise ValueError('评分记录摘要不匹配')
        packet = json.loads(raw)
        if packet.get('task_id') != path.parent.name:
            raise ValueError('评分记录任务归属不一致')
        if packet['criteria'] == criteria:
            found.append((packet, path))
    return sorted(found, key=lambda pair: pair[0]['created_at'])


def save_scores(root, task_id, iteration, plan, output):
    from datetime import datetime, timezone
    from decision_basis import decision_receipt
    criteria = {k: plan.get(k) for k in ('requirement_version', 'hard_filters', 'semantic_criteria')}
    scores = output.get('candidate_scores')
    previous = {row['candidate_ref']: row for packet, _ in score_checkpoints(root, criteria)
                for row in packet['output']['candidate_scores']}
    if not isinstance(scores, list):
        raise ValueError('评分结果缺少 candidate_scores')
    for row in scores:
        old = previous.get(row['candidate_ref'])
        if old and row != old and not row.get('correction_reason'):
            raise ValueError('同版本已评分者改变分数需要 correction_reason')
        if old and row.get('scored_iteration') != old.get('scored_iteration'):
            raise ValueError('保留首次评分轮次')
    validation = {**plan, 'decision_basis': {'requirement_version': criteria['requirement_version'],
        'completed_iteration': iteration, 'candidate_scores': scores,
        'prf_decision': {'status': 'none', 'reason': '仅保存评分结果'},
        'next_action': {'action': 'report', 'reason': '仅校验评分，不执行报告或搜索'}}}
    decision_receipt(validation, iteration=iteration + 1, task_id=task_id,
                     store_root=Path(root), settle=True)
    packet = {'task_id': task_id, 'iteration': iteration, 'criteria': criteria,
              'created_at': datetime.now(timezone.utc).isoformat(), 'output': output}
    raw = json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    if len(raw) > 1024 * 1024:
        raise ValueError('评分结果超过 1 MiB')
    path = Path(root) / 'wts-score-store' / task_id / (hashlib.sha256(raw).hexdigest() + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('评分保存路径越界')
    with path.open('xb') as f:
        f.write(raw)
    return str(path)


def main():
    import argparse
    import os
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task-id', required=True)
    parser.add_argument('--iteration', type=int, required=True)
    parser.add_argument('--plan-file', help='需求版本变化后提供当前搜索计划，用其条件校验评分')
    parser.add_argument('--record-scores', help='保存评分子 Agent 的 JSON 返回，复用时不重新评分')
    parser.add_argument('--source-task-id', help='同会话旧任务；仅核验和复用已有结果')
    parser.add_argument('--store-root', default=os.environ.get('DEEPAGENT_WORKFLOW_STORE_DIR', ''))
    args = parser.parse_args()
    if not args.store_root:
        parser.error('缺少当前会话 Workflow Store')
    configured = os.environ.get('DEEPAGENT_WORKFLOW_STORE_DIR', '').strip()
    if configured and Path(configured).resolve() != Path(args.store_root).resolve():
        parser.error('store-root 必须等于当前会话 Store')
    if not re.fullmatch(r'[A-Za-z0-9._-]{1,100}', args.task_id) or not 1 <= args.iteration <= 3:
        parser.error('任务编号或轮次无效')
    if args.record_scores:
        path = Path(args.record_scores).resolve()
        configured_dir = os.environ.get('DEEPAGENT_TASK_WORK_DIR', '').strip()
        if configured_dir and not path.is_relative_to(Path(configured_dir).resolve()):
            parser.error('评分输入必须位于当前任务目录')
        if path.stat().st_size > 1024 * 1024:
            parser.error('评分输入过大')
        histories, _ = session_history(args.store_root)
        candidates = [w for w in histories.values() if scope(w) == f'{args.source_task_id or args.task_id}:{args.iteration}'
                      and w.get('input_plan') and not w.get('expansion') and not w.get('refill')]
        if not candidates:
            parser.error('找不到本轮原计划')
        plan = max(candidates, key=lambda w: w.get('created_at', ''))['input_plan']
        if args.plan_file:
            plan_path = Path(args.plan_file).resolve()
            if configured_dir and not plan_path.is_relative_to(Path(configured_dir).resolve()):
                parser.error('计划必须位于当前任务目录')
            from build_workflow import read_plan
            plan, _ = read_plan(str(plan_path))
        saved = save_scores(args.store_root, args.task_id, args.iteration, plan, json.loads(path.read_bytes()))
        print(json.dumps({'score_file': saved}, ensure_ascii=False))
    else:
        print(json.dumps(round_receipt(args.store_root, args.task_id, args.iteration, args.source_task_id), ensure_ascii=False))


if __name__ == '__main__':
    main()

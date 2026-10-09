#!/usr/bin/env python3
"""Materialize isolated scoring inputs; stdout contains an index, never resumes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re


def export_inputs(task_id, result_ref, task_dir, store_root):
    match = re.fullmatch(r'result://([A-Za-z0-9._-]{1,100})/([a-f0-9]{64})', result_ref)
    if not match:
        raise ValueError('result_ref 格式无效')
    root = (Path(store_root) / 'result-store').resolve()
    source = (root / match[1] / (match[2] + '.json')).resolve()
    if not source.is_relative_to(root) or not source.is_file() or source.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('结果不存在、越界或超过 16 MiB')
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != match[2]:
        raise ValueError('结果摘要不匹配')
    result = json.loads(raw)
    if result.get('workflow', {}).get('task_id') != match[1] or (result.get('status') not in {'success', 'partial'} and not any(isinstance(result.get('data', {}).get(key), dict) for key in ('details', 'failures'))):
        raise ValueError('只能读取归属正确且已有详情或失败分区的结果')
    if match[1] != task_id:
        from recovery import source_workflow
        source_workflow(store_root, result_ref)
    base = Path(task_dir).resolve()
    folder = (base / 'wts/scoring-inputs' / match[2]).resolve()
    if not folder.is_relative_to(base):
        raise ValueError('评分目录越界')
    entries, packets = [], []
    data = result.get('data', {})
    for group in ('details', 'failures'):
        for section in ('primary', 'secondary', 'expand'):
            rows = data.get(group, {}).get(section, [])
            if not isinstance(rows, list):
                raise ValueError('详情和失败分区必须是数组')
            refs = set()
            for row in rows:
                ref = row.get('candidate_ref')
                if not isinstance(ref, str) or not ref or ref in refs:
                    raise ValueError('分区内 candidate_ref 必须非空且唯一')
                refs.add(ref)
                status = row.get('detail_hard_filter_status', 'collected') if group == 'details' else 'failed'
                entry = {'candidate_ref': ref, 'detail_ref': result_ref,
                         'detail_section': 'details.' + section, 'detail_status': status}
                if group == 'details':
                    path = folder / f'{section}-{len(entries)}.json'
                    entry['profile_path'] = str(path)
                    packets.append((path, {**entry, 'profile': row}))
                entries.append(entry)
    folder.mkdir(parents=True, exist_ok=True)
    for path, packet in packets:
        if path.is_symlink():
            raise ValueError('评分文件不能是符号链接')
        path.write_text(json.dumps(packet, ensure_ascii=False), encoding='utf-8')
    return {'result_ref': result_ref, 'finished_at': result.get('workflow', {}).get('finished_at'),
            'entries': entries}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task-id', required=True)
    parser.add_argument('--result-ref', action='append', required=True)
    parser.add_argument('--task-work-dir', default=os.environ.get('DEEPAGENT_TASK_WORK_DIR', ''))
    parser.add_argument('--store-root', default=os.environ.get('DEEPAGENT_WORKFLOW_STORE_DIR', ''))
    args = parser.parse_args()
    for value, env in ((args.task_work_dir, 'DEEPAGENT_TASK_WORK_DIR'),
                       (args.store_root, 'DEEPAGENT_WORKFLOW_STORE_DIR')):
        if not value:
            parser.error('缺少 ' + env)
        configured = os.environ.get(env, '').strip()
        if configured and Path(value).expanduser().resolve() != Path(configured).expanduser().resolve():
            parser.error('路径必须等于运行时注入的 ' + env)
    try:
        outputs = [export_inputs(args.task_id, ref, Path(args.task_work_dir).expanduser(),
                                 Path(args.store_root).expanduser()) for ref in dict.fromkeys(args.result_ref)]
        entries = {}
        for out in outputs:
            for entry in out['entries']:
                entry['opened_at'] = out['finished_at']
                old = entries.get(entry['candidate_ref'])
                if old is None or ('profile_path' not in old and 'profile_path' in entry):
                    entries[entry['candidate_ref']] = entry
        output = {**outputs[0], 'result_refs': list(dict.fromkeys(args.result_ref)), 'entries': list(entries.values())}
    except (ValueError, OSError, TypeError, AttributeError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

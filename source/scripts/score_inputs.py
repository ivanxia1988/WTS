#!/usr/bin/env python3
"""Materialize isolated scoring inputs; stdout contains an index, never resumes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re


def write_private_json(path, value):
    if path.is_symlink():
        raise ValueError('评分文件不能是符号链接')
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    descriptor = -1
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            descriptor = -1
            json.dump(value, handle, ensure_ascii=False)
        temporary.replace(path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary.exists():
            temporary.unlink()


def export_inputs(task_id, result_ref, task_dir, store_root):
    match = re.fullmatch(r'result://([A-Za-z0-9._-]{1,100})/([a-f0-9]{64})', result_ref)
    if not match or match[1] != task_id:
        raise ValueError('result_ref 必须来自当前任务')
    root = (Path(store_root) / 'result-store').resolve()
    source = (root / task_id / (match[2] + '.json')).resolve()
    if not source.is_relative_to(root) or not source.is_file() or source.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('结果不存在、越界或超过 16 MiB')
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != match[2]:
        raise ValueError('结果摘要不匹配')
    result = json.loads(raw)
    if result.get('status') not in {'success', 'partial'} or result.get('workflow', {}).get('task_id') != task_id:
        raise ValueError('只能读取当前任务已完成的结果')
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
                status = row.get('detail_hard_filter_status') if group == 'details' else 'failed'
                entry = {'candidate_ref': ref, 'detail_ref': result_ref,
                         'detail_section': 'details.' + section, 'detail_status': status}
                if group == 'details':
                    path = folder / f'{section}-{len(entries)}.json'
                    entry['profile_path'] = str(path)
                    packets.append((path, {**entry, 'profile': row}))
                entries.append(entry)
    private_root = folder.parent
    private_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(private_root, 0o700)
    folder.mkdir(exist_ok=True, mode=0o700)
    os.chmod(folder, 0o700)
    for path, packet in packets:
        write_private_json(path, packet)
    return {'result_ref': result_ref, 'finished_at': result.get('workflow', {}).get('finished_at'),
            'entries': entries}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task-id', required=True)
    parser.add_argument('--result-ref', required=True)
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
        output = export_inputs(args.task_id, args.result_ref, Path(args.task_work_dir).expanduser(),
                               Path(args.store_root).expanduser())
    except (ValueError, OSError, TypeError, AttributeError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

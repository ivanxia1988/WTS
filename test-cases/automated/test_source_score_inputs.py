"""Single-person scoring packets retain source references without stdout resumes."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / 'source/scripts/score_inputs.py'
spec = importlib.util.spec_from_file_location('score_inputs', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ScoreInputsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.result = {'status': 'partial', 'workflow': {'task_id': 't', 'finished_at': 'now'},
                       'data': {'details': {
                           'primary': [{'candidate_ref': 'a', 'detail_hard_filter_status': 'matched', 'full_text': 'RESUME_A'}],
                           'secondary': [{'candidate_ref': 'b', 'detail_hard_filter_status': 'rejected', 'full_text': 'RESUME_B'}],
                           'expand': [{'candidate_ref': 'c', 'detail_hard_filter_status': 'unknown', 'full_text': 'RESUME_C'}]},
                           'failures': {'primary': [{'candidate_ref': 'd', 'error': 'timeout'}]}}}

    def save(self):
        raw = json.dumps(self.result).encode()
        digest = hashlib.sha256(raw).hexdigest()
        self.path = self.root / 'result-store/t' / (digest + '.json')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(raw)
        return 'result://t/' + digest

    def test_isolation_and_complete_index(self):
        ref = self.save()
        out = module.export_inputs('t', ref, self.root, self.root)
        self.assertNotIn('RESUME_', json.dumps(out))
        self.assertEqual(len(out['entries']), 4)
        self.assertEqual(out['finished_at'], 'now')
        for row in out['entries'][:3]:
            packet = json.loads(Path(row['profile_path']).read_text())
            self.assertEqual(packet['detail_ref'], ref)
            self.assertEqual(packet['profile']['candidate_ref'], row['candidate_ref'])
            self.assertEqual(json.dumps(packet).count('RESUME_'), 1)
        self.assertEqual(out['entries'][2]['detail_section'], 'details.expand')
        self.assertEqual(out['entries'][3]['detail_status'], 'failed')
        self.assertNotIn('profile_path', out['entries'][3])

    def test_scoring_packets_are_written_with_private_permissions(self):
        out = module.export_inputs('t', self.save(), self.root, self.root)
        profile_paths = [Path(row['profile_path']) for row in out['entries'] if 'profile_path' in row]

        self.assertEqual(profile_paths[0].parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(profile_paths[0].parent.parent.stat().st_mode & 0o777, 0o700)
        for path in profile_paths:
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_wrong_task_and_tampered_source_rejected(self):
        ref = self.save()
        with self.assertRaises(ValueError):
            module.export_inputs('other', ref, self.root, self.root)
        self.path.write_text('{}')
        with self.assertRaisesRegex(ValueError, '摘要'):
            module.export_inputs('t', ref, self.root, self.root)

    def test_empty_result_and_invalid_partitions(self):
        self.result['data'] = {}
        self.assertEqual(module.export_inputs('t', self.save(), self.root, self.root)['entries'], [])
        self.result['data'] = {'details': {'primary': {}}}
        with self.assertRaises(ValueError):
            module.export_inputs('t', self.save(), self.root, self.root)

    def test_duplicate_profiles_rejected(self):
        self.result['data']['details']['primary'] *= 2
        with self.assertRaisesRegex(ValueError, '唯一'):
            module.export_inputs('t', self.save(), self.root, self.root)

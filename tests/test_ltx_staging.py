import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from scripts import stage_ltx
from scripts.stage_ltx import check_range, load_manifest, verify


class LtxStagingTests(unittest.TestCase):
    def test_candidate_is_pinned_and_cannot_publish(self):
        data = load_manifest()
        self.assertEqual(len(data['files']), 5)
        self.assertFalse(data['publication_enabled'])

    def test_rejects_paths_mutable_revisions_and_publication(self):
        base = load_manifest()
        for field, value in [('path', '../escape.safetensors'), ('path', 'C:/escape.safetensors'),
                             ('revision', 'main'), ('sha256', 'unknown')]:
            data = copy.deepcopy(base)
            data['files'][0][field] = value
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'manifest.json'
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    load_manifest(path)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'manifest.json'
            base['publication_enabled'] = True
            path.write_text(json.dumps(base))
            with self.assertRaises(ValueError):
                load_manifest(path)

    def test_corrupt_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'model.safetensors'
            path.write_bytes(b'test')
            entry = {'bytes': 4, 'sha256': hashlib.sha256(b'test').hexdigest()}
            verify(path, entry)
            path.write_bytes(b'fail')
            with self.assertRaises(ValueError):
                verify(path, entry)

    def test_range_response_must_match_exact_offset_and_length(self):
        response = SimpleNamespace(status_code=206, headers={'content-range': 'bytes 4-7/12'}, content=b'abcd')
        self.assertEqual(check_range(response, 4, 7, 12), b'abcd')
        for field, value in [('status_code', 200), ('content', b'abc'),
                             ('headers', {'content-range': 'bytes 0-3/12'})]:
            bad = SimpleNamespace(**vars(response))
            setattr(bad, field, value)
            with self.assertRaises(ValueError):
                check_range(bad, 4, 7, 12)

    def test_checkpoint_resume_verifies_complete_file_before_rename(self):
        data = b'abcdefghij'
        entry = {'repo': 'Lightricks/LTX-2.5', 'path': 'model.safetensors',
                 'revision': 'a' * 40, 'bytes': len(data),
                 'sha256': hashlib.sha256(data).hexdigest()}
        hub, locks, http = mock.MagicMock(), mock.MagicMock(), mock.MagicMock()
        hub.get_hf_file_metadata.return_value = SimpleNamespace(
            size=len(data), etag=entry['sha256'], location='https://example.invalid/model')
        response = SimpleNamespace(status_code=206, headers={'content-range': 'bytes 4-9/10'}, content=data[4:])
        client = http.Client.return_value.__enter__.return_value
        client.get.return_value = response
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / entry['path']
            partial = target.with_suffix('.' + entry['sha256'] + '.partial')
            partial.write_bytes(data[:4])
            with mock.patch.object(stage_ltx, 'DESTINATION', root), mock.patch.dict(
                    'sys.modules', {'httpx': http, 'filelock': locks, 'huggingface_hub': hub}):
                self.assertEqual(stage_ltx.download_chunks(entry, target, 'test-only'), target)
            self.assertEqual(target.read_bytes(), data)
            self.assertFalse(partial.exists())
            self.assertEqual(client.get.call_args.kwargs['headers']['Range'], 'bytes=4-9')

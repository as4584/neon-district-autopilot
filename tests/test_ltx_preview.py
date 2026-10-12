import unittest
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from scripts import preview_ltx


class LtxPreviewTests(unittest.TestCase):
    def test_environment_does_not_pass_credentials(self):
        with mock.patch.dict('os.environ', {'HF_TOKEN': 'secret', 'DOPPLER_TOKEN': 'secret',
                                           'AWS_SECRET_ACCESS_KEY': 'secret'}, clear=True):
            env = preview_ltx.worker_environment()
        self.assertNotIn('secret', env.values())
        self.assertEqual(env['HF_HUB_OFFLINE'], '1')
        self.assertEqual(env['TRANSFORMERS_OFFLINE'], '1')

    def test_graph_is_bounded_distilled_local_workflow(self):
        graph = preview_ltx.workflow()
        self.assertEqual(graph['12']['inputs']['length'], 49)
        self.assertEqual(len(preview_ltx.SIGMAS.split(',')), 9)
        self.assertEqual(graph['20']['inputs']['video_cfg'], 1)
        self.assertEqual(graph['13']['inputs']['image'], graph['14']['inputs']['image'])
        self.assertEqual(graph['26']['class_type'], 'SaveVideo')
        for node in graph.values():
            for value in node['inputs'].values():
                if isinstance(value, list):
                    self.assertIn(value[0], graph)

    def test_bad_dimensions_rejected(self):
        for args in ({'width': 513}, {'height': 289}, {'frames': 48}):
            with self.assertRaises(ValueError):
                preview_ltx.workflow(**args)

    def test_cleanup_only_owned_tree(self):
        process = mock.Mock(pid=42)
        process.poll.return_value = None
        child = mock.Mock()
        psutil = mock.Mock()
        psutil.Process.return_value.children.return_value = [child]
        psutil.wait_procs.return_value = ([], [])
        with mock.patch.dict('sys.modules', {'psutil': psutil}):
            preview_ltx.stop_owned(process)
        psutil.Process.assert_called_once_with(42)
        child.terminate.assert_called_once()
        process.terminate.assert_called_once()

    def test_startup_failure_stops_owned_runtime_and_records_failure(self):
        args = SimpleNamespace(id='SMOKE', smoke_only=True, source=None, seed=1, timeout=60)
        process = mock.Mock()
        process.poll.return_value = None
        with tempfile.TemporaryDirectory() as temp:
            candidate = Path(temp) / 'candidate'
            with mock.patch.object(preview_ltx.review, 'folder', return_value=candidate), \
                    mock.patch.object(preview_ltx.subprocess, 'check_output', side_effect=[preview_ltx.REVISION, '']), \
                    mock.patch.object(preview_ltx.subprocess, 'Popen', return_value=process), \
                    mock.patch.object(preview_ltx, 'request', side_effect=RuntimeError('startup failed')), \
                    mock.patch.object(preview_ltx, 'stop_owned') as stop:
                with self.assertRaises(RuntimeError):
                    preview_ltx.run(args)
                stop.assert_called_once_with(process)
            evidence = json.loads((candidate / 'execution.json').read_text())
            self.assertEqual(evidence['status'], 'failed')
            self.assertTrue(evidence['owned_runtime_stopped'])
            self.assertFalse(evidence['publication_enabled'])


if __name__ == '__main__':
    unittest.main()

"""Offline argument gates; never load model weights or upload."""

import subprocess
import sys
import unittest
from pathlib import Path


class LocalVideoWorkerTests(unittest.TestCase):
    def test_invalid_frame_counts_fail_before_model_loading(self):
        worker = Path(__file__).resolve().parents[1] / 'scripts' / 'generate_local_video.py'
        for count in (1, 48, 125):
            result = subprocess.run([sys.executable, str(worker), '--image', 'unused.jpg',
                                     '--output', 'unused.mp4', '--frames', str(count)],
                                    capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'Frames must be 4n+1', result.stderr)

    def test_invalid_step_count_fails_before_model_loading(self):
        worker = Path(__file__).resolve().parents[1] / 'scripts' / 'generate_local_video.py'
        result = subprocess.run([sys.executable, str(worker), '--image', 'unused.jpg',
                                 '--output', 'unused.mp4', '--steps', '51'],
                                capture_output=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'Steps outside audition budget', result.stderr)

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yt_audio_qa


class AudioQATests(unittest.TestCase):
    def check(self, mean, peak, duration='30', channels=2):
        probe = mock.Mock(returncode=0, stdout=json.dumps({
            'streams': [{'codec_type': 'audio', 'channels': channels, 'sample_rate': '48000'}],
            'format': {'duration': duration}}))
        meter = mock.Mock(returncode=0, stderr=f'mean_volume: {mean} dB\nmax_volume: {peak} dB')
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / 'sample.flac'
            audio.write_bytes(b'fixture')
            with mock.patch.object(yt_audio_qa.subprocess, 'run', side_effect=[probe, meter]):
                return yt_audio_qa.inspect(audio)

    def test_valid_stereo_audio(self):
        self.assertEqual(self.check(-17, -1)['channels'], 2)

    def test_silent_clipped_and_excessively_loud_audio_blocked(self):
        for mean, peak in (('-inf', '-inf'), (-17, 0), (-5, -1), (-60, -40)):
            with self.assertRaises(RuntimeError):
                self.check(mean, peak)

    def test_invalid_duration_or_channel_count_blocked(self):
        for duration, channels in (('nan', 2), ('1', 2), ('30', 6)):
            with self.assertRaises(RuntimeError):
                self.check(-17, -1, duration, channels)


if __name__ == '__main__':
    unittest.main()

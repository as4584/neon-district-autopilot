import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

import yt_motion
import yt_thumbnail
import yt_visual_qa
import requests


class ImageryMotionTests(unittest.TestCase):
    def test_cover_has_no_text_crop_or_brand_bars(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            covers = root / 'covers'
            covers.mkdir()
            with mock.patch.object(yt_thumbnail, 'BASE_DIR', root), \
                 mock.patch.object(yt_thumbnail, 'COVERS_DIR', covers), \
                 mock.patch.object(yt_thumbnail, 'generate_base_image', return_value=Image.new('RGB', (1280, 720), (60, 100, 150))) as generate, \
                 mock.patch.object(yt_thumbnail, 'composite_text') as text, \
                 mock.patch.object(yt_thumbnail, 'crop_watermark_if_present') as crop:
                path = yt_thumbnail.generate({'id': 'TEST', 'title': 'Do Not Draw Me'})
                text.assert_not_called()
                crop.assert_not_called()
                with Image.open(path) as image:
                    self.assertTrue(all(high - low <= 1 for low, high in image.getextrema()))
                self.assertTrue(yt_thumbnail.is_imagery_only('TEST'))
                yt_thumbnail.generate({'id': 'TEST', 'title': 'Do Not Draw Me'})
                self.assertEqual(generate.call_count, 1)

    def test_legacy_cover_is_not_reused_without_new_layout_marker(self):
        with tempfile.TemporaryDirectory() as folder:
            with mock.patch.object(yt_thumbnail, 'COVERS_DIR', Path(folder)):
                Image.new('RGB', (1280, 720)).save(Path(folder) / 'TEST.jpg')
                self.assertFalse(yt_thumbnail.is_imagery_only('TEST'))
                (Path(folder) / 'TEST.json').write_text(json.dumps({'layout_version': 'old-text-v1'}))
                self.assertFalse(yt_thumbnail.is_imagery_only('TEST'))

    def test_still_fallback_never_moves_camera_lights_or_draws_labels(self):
        filter_graph = yt_motion.motion_filter()
        self.assertNotIn('zoompan', filter_graph)
        self.assertNotIn('brightness=', filter_graph)
        self.assertNotIn('drawtext', filter_graph)
        self.assertNotIn('overlay', filter_graph)

    def test_long_session_duration_is_bounded(self):
        with mock.patch.object(yt_motion.subprocess, 'run') as run:
            for seconds in (True, 0, 43201):
                with self.assertRaises(ValueError):
                    yt_motion.render_session('scene', 'audio', 'out', seconds)
        run.assert_not_called()

    def test_session_copy_is_capped_to_exact_frame_count(self):
        with mock.patch.object(yt_motion.subprocess, 'run', return_value=mock.Mock(returncode=0)) as run:
            yt_motion.render_session('scene', 'audio', 'out', 30)
        command = run.call_args.args[0]
        self.assertEqual(command[command.index('-frames:v') + 1], '900')
        self.assertEqual(command[command.index('-c:v') + 1], 'copy')

    def test_visual_qa_gpu_server_failure_retries_on_cpu(self):
        failure = mock.Mock(status_code=500)
        failure.raise_for_status.side_effect = requests.HTTPError('local runner failed')
        success = mock.Mock()
        success.json.return_value = {'message': {'content': json.dumps({
            'content_match_score': 9, 'neon_theme_score': 9,
            'visual_quality_score': 9, 'mismatches': [],
        })}}
        with mock.patch.object(yt_visual_qa, 'resolve_model', return_value='local-vision'), \
             mock.patch.object(yt_visual_qa, '_source_bytes', return_value=b'image'), \
             mock.patch.object(yt_visual_qa.requests, 'post', side_effect=[failure, success]) as post:
            result = yt_visual_qa.inspect_visual('local.jpg', {'title': 'Quiet Rain'})
        self.assertTrue(result.passed)
        self.assertEqual(post.call_args.kwargs['json']['options']['num_gpu'], 0)
        self.assertIn('no title overlays', post.call_args.kwargs['json']['messages'][0]['content'])

    def test_high_scores_do_not_override_visible_text_mismatch(self):
        response = mock.Mock()
        response.json.return_value = {'message': {'content': json.dumps({
            'content_match_score': 10, 'neon_theme_score': 10,
            'visual_quality_score': 10, 'mismatches': ['Title overlay is present'],
        })}}
        with mock.patch.object(yt_visual_qa, 'resolve_model', return_value='local-vision'), \
             mock.patch.object(yt_visual_qa, '_source_bytes', return_value=b'image'), \
             mock.patch.object(yt_visual_qa.requests, 'post', return_value=response):
            result = yt_visual_qa.inspect_visual('local.jpg', {'title': 'Quiet Rain'})
        self.assertFalse(result.passed)


if __name__ == '__main__':
    unittest.main()

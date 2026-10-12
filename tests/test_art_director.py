import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests
import yt_art_director as director
import yt_visual_qa as qa


class ArtDirectorTests(unittest.TestCase):
    def test_nature_sleep_uses_natural_scene_but_explicit_room_is_preserved(self):
        forest = director.direct({'title': 'Forest Sleep', 'visual_scene': 'forest stream'}, use_agent=False)
        self.assertTrue(forest['nature'])
        self.assertIn('stream', forest['prompt'])
        self.assertNotIn('neon', forest['prompt'])
        room = director.brief({'title': 'Bedroom overlooking a forest'})
        self.assertFalse(room['nature'])
        self.assertIn('bedroom', room['scene'])

    def test_retries_change_seed_and_composition_reproducibly(self):
        item = {'id': 'T1', 'title': 'Quiet mountain lake'}
        a, b = director.brief(item), director.brief(item, 1)
        self.assertEqual(a, director.brief(item))
        self.assertNotEqual(a['seed'], b['seed'])
        self.assertNotEqual(a['composition'], b['composition'])

    def test_reference_selection_never_crosses_models_or_uses_unapproved_images(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            image = root / 'image.png'
            image.write_bytes(b'fixture')
            base = {'id': 'approved', 'model': director.DEFAULT_MODEL, 'kind': 'local_output',
                    'status': 'approved', 'subjects': ['nature'], 'image_path': 'image.png',
                    'sha256': hashlib.sha256(b'fixture').hexdigest()}
            library = root / 'library.json'
            library.write_text(json.dumps({'version': 'test', 'references': [base,
                dict(base, id='pending', status='pending'),
                dict(base, id='other-model', model='Tongyi-MAI/Z-Image'),
                dict(base, id='changed', sha256='incorrect')]}))
            with mock.patch.object(director, 'ROOT', root):
                _, refs = director.references_for(director.DEFAULT_MODEL, True, library)
            self.assertEqual([r['id'] for r in refs], ['approved'])

    def test_local_agent_receives_feedback_and_unloads_cpu_model(self):
        response = mock.Mock()
        detail = ('Small irregular ripples gather along the shaded shore. Weathered stones '
                  'break the foreground gently, while distant trees soften in the moist air. '
                  'The water keeps a subdued reflection of the ridge beneath an open sky.')
        response.json.return_value = {'message': {'content': json.dumps({'detail': detail})}}
        session = mock.Mock()
        session.post.return_value = response
        with mock.patch.object(director.requests, 'Session', return_value=session):
            result = director.direct({'title': 'Lake'}, feedback='Reflections were implausible')
        body = session.post.call_args.kwargs['json']
        self.assertEqual(body['keep_alive'], 0)
        self.assertEqual(body['options']['num_gpu'], 0)
        self.assertFalse(session.trust_env)
        self.assertIn('Reflections were implausible', body['messages'][1]['content'])
        self.assertEqual(result['method'], 'local_agent')
        session.close.assert_called_once()

    def test_reviewed_preview_can_teach_same_model_and_rejection_deletes_only_preview(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            library = root / 'library.json'
            library.write_text(json.dumps({'version': 'test', 'references': []}))
            for name in ('keep', 'reject'):
                directory = root / 'test_outputs' / 'art_direction' / name
                directory.mkdir(parents=True)
                (directory / 'preview.png').write_bytes(b'image')
                (directory / 'direction.json').write_text(json.dumps({
                    'image_model': director.DEFAULT_MODEL, 'nature': True, 'seed': 12,
                    'prompt': 'A forest stream', 'image_sha256': hashlib.sha256(b'image').hexdigest()}))
            lesson = 'Quiet open water balances the irregular stones and trees.'
            with mock.patch.object(director, 'ROOT', root):
                director.review_preview('keep', 'approved', lesson)
                director.review_preview('reject', 'rejected')
                _, refs = director.references_for(director.DEFAULT_MODEL, True, library)
            self.assertEqual([r['id'] for r in refs], ['keep'])
            self.assertEqual(refs[0]['prompt'], 'A forest stream')
            self.assertFalse((directory / 'preview.png').exists())
            self.assertTrue((directory / 'direction.json').exists())
            self.assertTrue((directory / 'review.json').exists())

    def test_agent_failure_keeps_auditable_brief_without_cloud_fallback(self):
        session = mock.Mock()
        session.post.side_effect = requests.Timeout()
        with mock.patch.object(director.requests, 'Session', return_value=session):
            result = director.direct({'title': 'Forest'})
        self.assertEqual(result['method'], 'structured_brief')
        self.assertEqual(result['fallback_reason'], 'Timeout')
        self.assertIn('forest', result['prompt'])
        self.assertEqual(session.post.call_count, 1)

    def test_qa_passes_visible_defects_to_retry(self):
        failed = qa.VisualQAResult(False, 9, 9, 4, 'lake', ['warped shore'], 'bad geometry', 'local', 'image')
        passed = qa.VisualQAResult(True, 9, 9, 9, 'lake', [], 'clear', 'local', 'replacement')
        retry = mock.Mock(return_value='replacement')
        legacy = mock.Mock()
        with mock.patch.object(qa, 'inspect_visual', side_effect=[failed, passed]), \
             mock.patch.object(qa, 'save_report'):
            path, _ = qa.approve_cover({'id': 'T1'}, 'image', legacy, regenerate_with_feedback=retry)
        self.assertEqual(path, 'replacement')
        retry.assert_called_once_with(failed, 1)
        legacy.assert_not_called()

    def test_natural_artwork_is_not_required_to_have_neon_by_qa(self):
        response = mock.Mock()
        response.json.return_value = {'message': {'content': json.dumps({
            'content_match_score': 9, 'neon_theme_score': 9, 'visual_quality_score': 9, 'mismatches': []})}}
        with mock.patch.object(qa, 'resolve_model', return_value='local'), \
             mock.patch.object(qa, '_source_bytes', return_value=b'image'), \
             mock.patch.object(qa.requests, 'post', return_value=response) as post:
            self.assertTrue(qa.inspect_visual('forest.png', {'title': 'Forest'}).passed)
        prompt = post.call_args.kwargs['json']['messages'][0]['content']
        self.assertIn('neon is not required', prompt)
        self.assertIn('plastic-looking', prompt)


if __name__ == '__main__':
    unittest.main()

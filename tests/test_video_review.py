import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yt_video_review as review


class VideoReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        root_patch = mock.patch.object(review, 'ROOT', self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        self.patch = mock.patch.object(review, 'CANDIDATES', self.root / 'candidates')
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.source = self.root / 'original.jpg'
        self.source.write_bytes(b'original image')
        self.directory = review.folder('TEST')
        self.directory.mkdir(parents=True)
        self.preview = self.directory / 'preview.mp4'
        self.preview.write_bytes(b'generated clip')
        review.register('TEST', self.source, self.preview)

    def test_pending_is_never_approved(self):
        self.assertFalse(review.is_approved('TEST'))

    def test_ltx_model_provenance_is_recorded(self):
        other = review.folder('LTX')
        other.mkdir()
        preview = other / 'preview.mp4'
        preview.write_bytes(b'ltx candidate')
        payload = review.register('LTX', self.source, preview, model='Lightricks/LTX-2.5')
        self.assertEqual(payload['model'], 'Lightricks/LTX-2.5')
        self.assertFalse(review.is_approved('LTX'))

    def test_rejection_deletes_only_registered_preview(self):
        neighbor = self.directory / 'unrelated.txt'
        neighbor.write_text('keep')
        review.decide('TEST', 'rejected')
        self.assertFalse(self.preview.exists())
        self.assertTrue(self.source.exists())
        self.assertTrue(neighbor.exists())
        self.assertFalse(review.is_approved('TEST'))

    def test_explicit_approval_is_hash_bound(self):
        review.decide('TEST', 'approved')
        self.assertTrue(review.is_approved('TEST'))
        self.preview.write_bytes(b'changed clip')
        self.assertFalse(review.is_approved('TEST'))

    def test_changed_preview_is_not_deleted(self):
        self.preview.write_bytes(b'user replacement')
        with self.assertRaises(ValueError):
            review.decide('TEST', 'rejected')
        self.assertTrue(self.preview.exists())

    def test_traversal_cannot_delete_source(self):
        manifest = self.directory / 'review.json'
        payload = json.loads(manifest.read_text())
        payload['assets'][0]['name'] = '../../original.jpg'
        manifest.write_text(json.dumps(payload))
        with self.assertRaises(ValueError):
            review.decide('TEST', 'rejected')
        self.assertTrue(self.source.exists())

    def test_candidate_path_traversal_is_rejected(self):
        for candidate in ('..', '../outside', 'C:\\outside', 'folder/test'):
            with self.assertRaises(ValueError):
                review.folder(candidate)

    def test_duplicate_id_preserves_existing_review(self):
        with self.assertRaises(ValueError):
            review.register('TEST', self.source, self.preview)
        self.assertTrue(self.preview.exists())

    def test_rejected_cleanup_can_be_retried(self):
        review.decide('TEST', 'rejected')
        result = review.decide('TEST', 'rejected')
        self.assertEqual(result['status'], 'rejected')
        self.assertTrue(self.source.exists())

    def test_review_directory_outside_workspace_is_blocked(self):
        with mock.patch.object(review, 'CANDIDATES', self.root.parent / 'outside'):
            with self.assertRaises(ValueError):
                review.folder('TEST')

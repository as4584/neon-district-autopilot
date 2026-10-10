import unittest
from unittest import mock

import yt_autopost
import yt_upload


class ReadbackTests(unittest.TestCase):
    def video(self, processing='succeeded', privacy='public', duration='PT1H1S'):
        response = mock.Mock(status_code=200)
        response.json.return_value = {'items': [{'snippet': {'channelId': 'UCWO8s_ObXOM5f_9YocsTvuQ'},
                                                'status': {'privacyStatus': privacy, 'uploadStatus': 'uploaded'},
                                                'processingDetails': {'processingStatus': processing},
                                                'contentDetails': {'duration': duration}}]}
        return response

    def verify(self, response, timeout=3600):
        with mock.patch.object(yt_upload, 'get_access_token', return_value='fixture-token'), \
             mock.patch.object(yt_upload.requests, 'get', return_value=response):
            return yt_upload.verify_uploaded_video('fixture-video', 'public', 3600, timeout=timeout)

    def test_success_checks_cloud_duration(self):
        self.assertEqual(self.verify(self.video())['duration_seconds'], 3601)

    def test_processing_failure_visibility_and_duration_mismatch_block(self):
        for response in (self.video(processing='failed'), self.video(privacy='private'),
                         self.video(duration='PT0S'), self.video(duration='PT13H')):
            with self.assertRaises(RuntimeError):
                self.verify(response)

    def test_pending_processing_is_not_success(self):
        with self.assertRaisesRegex(RuntimeError, 'still pending'):
            self.verify(self.video(processing='processing'), timeout=0)

    def test_accepted_queue_item_is_never_picked_again(self):
        queue = {'queue': [{'id': '001', 'status': 'pending', 'youtube_id': 'accepted-id'}]}
        self.assertIsNone(yt_autopost.pick_next(queue))
        self.assertIsNone(yt_autopost.pick_next(queue, '001'))


if __name__ == '__main__':
    unittest.main()

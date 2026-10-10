import importlib
import unittest
from datetime import datetime, timezone
from unittest import mock

import yt_experiments
import yt_local_image


class ExperimentTests(unittest.TestCase):
    def test_no_partial_age_windows(self):
        published = "2026-09-01T12:00:00Z"
        self.assertIsNone(yt_experiments.comparison_window(
            published, 14, datetime(2026, 9, 15, tzinfo=timezone.utc)))
        start, end = yt_experiments.comparison_window(
            published, 14, datetime(2026, 9, 17, tzinfo=timezone.utc))
        self.assertEqual((end - start).days, 13)

    def test_low_views_and_missing_metrics_are_inconclusive(self):
        policy = yt_experiments.registry()["policy"]
        record = {"model": "test", "series": "sleep", "duration_hours": 6,
                  "period_views": 2, "watch_minutes": 20}
        result = yt_experiments.summarize([record], policy)
        self.assertEqual(result[0]["evidence"], "inconclusive")
        record["watch_minutes"] = None
        self.assertEqual(yt_experiments.summarize([record], policy), [])

    def test_durations_and_series_never_pooled(self):
        records = [{"model": "test", "series": series, "duration_hours": hours,
                    "period_views": 10, "watch_minutes": 100}
                   for series, hours in (("sleep", 1), ("sleep", 6), ("jazz", 1))]
        self.assertEqual(len(yt_experiments.summarize(records, yt_experiments.registry()["policy"])), 3)

    def test_gated_models_never_start_download(self):
        with mock.patch.object(yt_experiments.subprocess, "run") as run:
            result = yt_experiments.stage_model({"id": "gated", "state": "license-blocked"}, {})
        self.assertEqual(result["state"], "license-blocked")
        run.assert_not_called()

    def test_generation_worker_has_no_credentials_and_is_offline(self):
        with mock.patch.dict("os.environ", {"DOPPLER_TOKEN": "do-not-forward",
                                           "YOUTUBE_REFRESH_TOKEN": "do-not-forward",
                                           "PATH": "keep", "LOCAL_IMAGE_MODEL": "keep"}, clear=True):
            env = yt_local_image.worker_environment()
        self.assertNotIn("DOPPLER_TOKEN", env)
        self.assertNotIn("YOUTUBE_REFRESH_TOKEN", env)
        self.assertEqual(env["PATH"], "keep")
        self.assertEqual(env["HF_HUB_OFFLINE"], "1")

    def test_doppler_error_never_contains_response_body(self):
        import io
        import urllib.error
        module = importlib.import_module("scripts.doppler_env")
        error = urllib.error.HTTPError("https://api.doppler.com", 403, "Denied", {},
                                       io.BytesIO(b"private-response-secret"))
        with mock.patch.dict("os.environ", {"DOPPLER_TOKEN": "test"}), \
             mock.patch.object(module.urllib.request, "urlopen", side_effect=error), \
             self.assertRaisesRegex(RuntimeError, "^Doppler read failed: HTTP 403$"):
            module.fetch_secrets("test", "test")

    def test_public_report_discards_free_text_and_unknown_fields(self):
        module = importlib.import_module('scripts.publish_findings')
        payload = {'schema_version': 1, 'window_days': 14, 'checked_at': '2026-10-10T01:00:00+00:00',
                   'private': 'do-not-publish', 'models': [{'id': 'ace-step', 'state': 'baseline',
                                                         'blocker': 'private-free-text'}], 'cohorts': []}
        result = module.sanitize(payload)
        self.assertNotIn('private', result)
        self.assertNotIn('blocker', result['models'][0])
        payload['models'][0]['id'] = 'unreviewed-model'
        with self.assertRaises(ValueError):
            module.sanitize(payload)


if __name__ == "__main__":
    unittest.main()

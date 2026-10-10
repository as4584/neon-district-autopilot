import copy
import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_json(name):
    return {"_meta": {"privacy": "unlisted", "loop_to_seconds": 3600,
                      "default_duration_seconds": 60, "require_visual_approval": True},
            "queue": [{"id": "FIXTURE01", "status": "pending", "title": "Neon Rain",
                       "prompt": "quiet instrumental rain music", "tags": [],
                       "created": None, "youtube_id": None}]}


def write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class PipelineRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PIL import Image
        cls.fixture_folder = tempfile.TemporaryDirectory()
        cls.cover_image = str(Path(cls.fixture_folder.name) / "cover.jpg")
        Image.effect_noise((1280, 720), 80).convert("RGB").save(cls.cover_image, quality=95)

    @classmethod
    def tearDownClass(cls):
        cls.fixture_folder.cleanup()

    def test_longform_dry_run_does_not_mark_pending_item_uploaded(self):
        yt_autopost = importlib.import_module("yt_autopost")
        queue = load_json("yt_queue.json")
        pending_before = next(item for item in queue["queue"] if item["status"] == "pending")

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            queue_file = tmp / "yt_queue.json"
            log_file = tmp / "autopost.log"
            write_json(queue_file, queue)

            with mock.patch.object(yt_autopost, "QUEUE_FILE", queue_file), \
                 mock.patch.object(yt_autopost, "LOG_FILE", log_file), \
                 mock.patch.object(sys, "argv", ["yt_autopost.py", "--dry-run"]):
                yt_autopost.main()

            after = json.loads(queue_file.read_text(encoding="utf-8"))
            same_item = next(item for item in after["queue"] if item["id"] == pending_before["id"])
            self.assertEqual(same_item["status"], "pending")
            self.assertIsNone(same_item.get("youtube_id"))

    def test_shorts_dry_run_does_not_mutate_queue(self):
        yt_shorts = importlib.import_module("yt_shorts")
        queue = load_json("shorts_queue.json")
        queue["queue"][0]["status"] = "pending"
        queue["queue"][0]["youtube_id"] = None
        queue["queue"][0]["created"] = None
        before = copy.deepcopy(queue)

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            queue_file = tmp / "shorts_queue.json"
            log_file = tmp / "shorts.log"
            write_json(queue_file, queue)

            with mock.patch.object(yt_shorts, "QUEUE_FILE", queue_file), \
                 mock.patch.object(yt_shorts, "LOG_FILE", log_file), \
                 mock.patch.object(sys, "argv", ["yt_shorts.py", "--dry-run"]):
                yt_shorts.main()

            after = json.loads(queue_file.read_text(encoding="utf-8"))
            self.assertEqual(after, before)

    def test_shorts_render_filter_keeps_shorts_format_static(self):
        yt_shorts = importlib.import_module("yt_shorts")

        filter_graph = yt_shorts.short_video_filter()

        self.assertIn("scale=1080:1920", filter_graph)
        self.assertIn("crop=1080:1920", filter_graph)
        self.assertNotIn("sin(t", filter_graph)
        self.assertIn("force_original_aspect_ratio=increase", filter_graph)
        self.assertTrue(filter_graph.endswith("[v]"))

    def test_shorts_cover_is_vertical_and_item_specific(self):
        yt_shorts = importlib.import_module("yt_shorts")
        from PIL import Image

        item = {"title": "Dark Electronica Coding Pulse #Shorts"}
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "short-cover.jpg"
            cover = yt_shorts.build_short_cover(item, self.cover_image, str(out))

            with Image.open(cover) as img:
                self.assertEqual(img.size, (yt_shorts.SHORT_WIDTH, yt_shorts.SHORT_HEIGHT))
            self.assertGreater(Path(cover).stat().st_size, 50_000)

    def test_shorts_qa_rejects_non_vertical_video_before_upload(self):
        yt_shorts = importlib.import_module("yt_shorts")

        with tempfile.TemporaryDirectory() as td:
            video = Path(td) / "bad-short.mp4"
            video.write_bytes(b"not enough video data")

            with self.assertRaisesRegex(RuntimeError, "video file too small"):
                yt_shorts.qa_short_video(str(video), 60)

    def test_shorts_qa_rejects_regular_landscape_video(self):
        yt_shorts = importlib.import_module("yt_shorts")

        with tempfile.TemporaryDirectory() as td:
            video = Path(td) / "regular-video.mp4"
            video.write_bytes(b"0" * yt_shorts.SHORT_MIN_BYTES)
            metadata = {
                "streams": [
                    {
                        "codec_type": "video",
                        "width": 1920,
                        "height": 1080,
                        "duration": "60.0",
                    },
                    {"codec_type": "audio", "duration": "60.0"},
                ],
                "format": {"duration": "60.0"},
            }

            with mock.patch.object(yt_shorts, "_ffprobe_json", return_value=metadata), \
                 self.assertRaisesRegex(RuntimeError, "expected 1080x1920"):
                yt_shorts.qa_short_video(str(video), 60)

    def test_shorts_qa_rejects_extra_video_streams(self):
        yt_shorts = importlib.import_module("yt_shorts")

        with tempfile.TemporaryDirectory() as td:
            video = Path(td) / "multi-stream.mp4"
            video.write_bytes(b"0" * yt_shorts.SHORT_MIN_BYTES)
            metadata = {
                "streams": [
                    {"codec_type": "video", "width": 1080, "height": 1920},
                    {"codec_type": "video", "width": 1280, "height": 720},
                    {"codec_type": "audio", "duration": "60.0"},
                ],
                "format": {"duration": "60.0"},
            }

            with mock.patch.object(yt_shorts, "_ffprobe_json", return_value=metadata), \
                 self.assertRaisesRegex(RuntimeError, "expected 1 video stream"):
                yt_shorts.qa_short_video(str(video), 60)

    def test_shorts_upload_is_blocked_when_qa_fails(self):
        yt_shorts = importlib.import_module("yt_shorts")
        item = {
            "id": "SHQA",
            "title": "QA Test #Shorts",
            "duration_seconds": 60,
            "cover_image": self.cover_image,
            "prompt": "test prompt",
            "tags": ["shorts"],
        }
        meta = {"category_id": "10", "privacy": "public"}

        with tempfile.TemporaryDirectory() as td:
            log_file = Path(td) / "shorts.log"
            with mock.patch.object(yt_shorts, "LOG_FILE", log_file), \
                 mock.patch.object(yt_shorts.yt_generate, "generate", return_value="audio.flac"), \
                 mock.patch.object(yt_shorts, "build_short_cover", return_value=self.cover_image), \
                 mock.patch.object(yt_shorts, "render_vertical_short", side_effect=RuntimeError("Shorts QA failed: expected 1080x1920")), \
                 mock.patch.object(yt_shorts.yt_upload, "upload_video") as upload:
                result = yt_shorts.run_item(item, meta, dry_run=False)

        self.assertFalse(result["success"])
        upload.assert_not_called()

    def test_shorts_preview_only_does_not_upload(self):
        yt_shorts = importlib.import_module("yt_shorts")
        item = {
            "id": "SHPREV",
            "title": "Preview Only #Shorts",
            "duration_seconds": 60,
            "cover_image": self.cover_image,
            "prompt": "test prompt",
            "tags": ["shorts"],
        }
        meta = {"category_id": "10", "privacy": "public"}

        with tempfile.TemporaryDirectory() as td:
            preview_video = str(Path(td) / "preview.mp4")
            preview_cover = str(Path(td) / "preview.jpg")
            Path(preview_video).write_bytes(b"0" * 1_000_000)
            with mock.patch.object(yt_shorts, "LOG_FILE", Path(td) / "shorts.log"), \
                 mock.patch.object(yt_shorts.yt_generate, "generate", return_value="audio.flac"), \
                 mock.patch.object(yt_shorts, "build_short_cover", return_value=preview_cover), \
                 mock.patch.object(yt_shorts, "render_vertical_short", return_value=preview_video), \
                 mock.patch.object(yt_shorts.yt_upload, "upload_video") as upload:
                result = yt_shorts.run_item(item, meta, preview_only=True)

        self.assertTrue(result["success"])
        self.assertFalse(result["uploaded"])
        self.assertEqual(result["video_path"], preview_video)
        upload.assert_not_called()

    def test_shorts_live_upload_requires_visual_approval(self):
        yt_shorts = importlib.import_module("yt_shorts")
        queue = {
            "_meta": {"default_duration_seconds": 60, "require_visual_approval": True},
            "queue": [
                {
                    "id": "SHAPP",
                    "status": "pending",
                    "title": "Needs Approval #Shorts",
                    "youtube_id": None,
                }
            ],
        }

        with tempfile.TemporaryDirectory() as td:
            queue_file = Path(td) / "shorts_queue.json"
            log_file = Path(td) / "shorts.log"
            write_json(queue_file, queue)

            with mock.patch.object(yt_shorts, "QUEUE_FILE", queue_file), \
                 mock.patch.object(yt_shorts, "LOG_FILE", log_file), \
                 mock.patch.object(sys, "argv", ["yt_shorts.py"]):
                with self.assertRaisesRegex(SystemExit, "not visually approved"):
                    yt_shorts.main()

    def test_shorts_approve_preview_sets_visual_approval(self):
        yt_shorts = importlib.import_module("yt_shorts")
        queue = {
            "_meta": {"default_duration_seconds": 60, "require_visual_approval": True},
            "queue": [
                {
                    "id": "SHAPP",
                    "status": "pending",
                    "title": "Needs Approval #Shorts",
                    "preview_video": "preview.mp4",
                    "visual_approved": False,
                }
            ],
        }

        with tempfile.TemporaryDirectory() as td:
            queue_file = Path(td) / "shorts_queue.json"
            write_json(queue_file, queue)

            with mock.patch.object(yt_shorts, "QUEUE_FILE", queue_file), \
                 mock.patch.object(yt_shorts, "qa_short_video"):
                current = json.loads(queue_file.read_text(encoding="utf-8"))
                item = current["queue"][0]
                yt_shorts.approve_preview(current, item)

            after = json.loads(queue_file.read_text(encoding="utf-8"))
            self.assertTrue(after["queue"][0]["visual_approved"])
            self.assertIn("visual_approved_at", after["queue"][0])

    def test_visual_qa_uses_strict_score_thresholds(self):
        yt_visual_qa = importlib.import_module("yt_visual_qa")

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "message": {
                        "content": json.dumps({
                            "content_match_score": 6,
                            "neon_theme_score": 10,
                            "visual_quality_score": 9,
                            "observed_scene": "A generic neon desk",
                            "mismatches": ["No rain or sleep scene"],
                            "reason": "Brand fit is strong but the scene is unrelated.",
                        })
                    }
                }

        with tempfile.TemporaryDirectory() as td:
            image = Path(td) / "candidate.jpg"
            image.write_bytes(b"fake-image")
            with mock.patch.object(yt_visual_qa, "resolve_model", return_value="qwen3-vl:latest"), \
                 mock.patch.object(yt_visual_qa.requests, "post", return_value=FakeResponse()):
                result = yt_visual_qa.inspect_visual(
                    str(image),
                    {"title": "Deep Sleep Rain", "prompt": "rainy neon bedroom", "tags": []},
                )

        self.assertFalse(result.passed)
        self.assertEqual(result.content_match_score, 6)

    def test_visual_qa_retries_one_empty_ollama_response(self):
        yt_visual_qa = importlib.import_module("yt_visual_qa")

        class FakeResponse:
            def __init__(self, content):
                self.content = content

            def raise_for_status(self):
                return None

            def json(self):
                return {"message": {"content": self.content}}

        valid = json.dumps({
            "content_match_score": 9,
            "neon_theme_score": 9,
            "visual_quality_score": 9,
            "observed_scene": "A neon jazz lounge",
            "mismatches": [],
            "reason": "Matches the target.",
        })

        with tempfile.TemporaryDirectory() as td:
            image = Path(td) / "candidate.jpg"
            image.write_bytes(b"fake-image")
            post = mock.Mock(side_effect=[FakeResponse(""), FakeResponse(valid)])
            with mock.patch.object(yt_visual_qa, "resolve_model", return_value="qwen3-vl:latest"), \
                 mock.patch.object(yt_visual_qa.requests, "post", post):
                result = yt_visual_qa.inspect_visual(
                    str(image),
                    {"title": "Late Night Jazz", "prompt": "neon jazz lounge", "tags": []},
                )

        self.assertTrue(result.passed)
        self.assertEqual(post.call_count, 2)

    def test_sleep_thumbnail_prompt_prioritizes_bedroom_over_city(self):
        yt_thumbnail = importlib.import_module("yt_thumbnail")
        item = {
            "title": "1 Hour Deep Sleep Music | Neon Night Rain Ambience",
            "prompt": "deep sleep music, steady rainfall, gentle neon bedroom atmosphere",
            "tags": ["sleep music", "night rain", "ambient music"],
        }

        prompt, genre = yt_thumbnail.build_prompt(item)

        self.assertEqual(genre, "sleep")
        self.assertIn("bedroom must dominate", prompt)
        self.assertNotIn("Scene: nighttime cityscape", prompt)

    def test_jazz_thumbnail_ignores_sleep_discovery_tag(self):
        yt_thumbnail = importlib.import_module("yt_thumbnail")
        item = {
            "title": "1 Hour Late Night Jazz Piano | Background Music for Reading",
            "prompt": (
                "late night jazz piano, soft brushed drums, upright bass, mellow saxophone, "
                "candlelit lounge, relaxed reading music, neon city outside"
            ),
            "tags": ["jazz", "reading music", "sleep music"],
        }

        prompt, genre = yt_thumbnail.build_prompt(item)

        self.assertEqual(genre, "jazz")
        self.assertIn("candlelit jazz lounge", prompt)
        self.assertIn("neon city", prompt)
        self.assertNotIn("bedroom", prompt)

    def test_visual_qa_regenerates_locally_and_rechecks(self):
        yt_visual_qa = importlib.import_module("yt_visual_qa")
        failed = yt_visual_qa.VisualQAResult(
            False, 3, 8, 8, "generic desk", ["no rain"], "wrong scene", "qwen3-vl", "old.jpg"
        )
        passed = yt_visual_qa.VisualQAResult(
            True, 9, 9, 9, "neon rain bedroom", [], "matches", "qwen3-vl", "new.jpg"
        )
        regenerate = mock.Mock(return_value="new.jpg")

        with mock.patch.object(yt_visual_qa, "inspect_visual", side_effect=[failed, passed]), \
             mock.patch.object(yt_visual_qa, "save_report"):
            path, result = yt_visual_qa.approve_cover(
                {"id": "QA01", "title": "Neon Rain"},
                "old.jpg",
                regenerate,
                max_regenerations=1,
            )

        self.assertEqual(path, "new.jpg")
        self.assertTrue(result.passed)
        regenerate.assert_called_once_with()

    def test_visual_qa_blocks_when_local_regeneration_fails(self):
        yt_visual_qa = importlib.import_module("yt_visual_qa")
        failed = yt_visual_qa.VisualQAResult(
            False, 2, 2, 8, "unrelated scene", ["not neon"], "rejected", "qwen3-vl", "old.jpg"
        )

        with mock.patch.object(yt_visual_qa, "inspect_visual", return_value=failed), \
             mock.patch.object(yt_visual_qa, "save_report"), \
             self.assertRaisesRegex(yt_visual_qa.VisualQAFailed, "image regeneration failed"):
            yt_visual_qa.approve_cover(
                {"id": "QA02", "title": "Neon Rain"},
                "old.jpg",
                mock.Mock(side_effect=RuntimeError("missing API client")),
                max_regenerations=1,
            )

    def test_longform_upload_is_blocked_when_visual_qa_fails(self):
        yt_autopost = importlib.import_module("yt_autopost")
        item = {
            "id": "QA03",
            "title": "1 Hour Deep Sleep Music | Neon Rain",
            "prompt": "sleep music, neon bedroom, steady rain",
            "tags": ["sleep music", "rain music"],
        }
        meta = {
            "cover_image": self.cover_image,
            "default_duration_seconds": 1,
            "loop_to_seconds": 1,
            "privacy": "unlisted",
            "category_id": "10",
        }

        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(yt_autopost, "LOG_FILE", Path(td) / "autopost.log"), \
                 mock.patch.object(yt_autopost.yt_generate, "generate", return_value=str(Path(td) / "audio.flac")), \
                 mock.patch.object(yt_autopost, "stop_ace_step_api"), \
                 mock.patch.object(
                     yt_autopost.yt_visual_qa,
                     "approve_cover",
                     side_effect=yt_autopost.yt_visual_qa.VisualQAFailed("wrong scene"),
                 ), \
                 mock.patch.object(yt_autopost.yt_upload, "upload_video") as upload:
                result = yt_autopost.run_item(item, meta)

        self.assertFalse(result)
        upload.assert_not_called()

    def test_analytics_api_uses_auth_header_and_400_is_nonfatal(self):
        yt_analytics = importlib.import_module("yt_analytics")
        captured = {}

        class FakeResponse:
            status_code = 400

            def raise_for_status(self):
                raise AssertionError("raise_for_status should not be called for handled 400")

        def fake_get(url, **kwargs):
            captured["url"] = url
            captured["kwargs"] = kwargs
            return FakeResponse()

        with mock.patch.object(yt_analytics.requests, "get", side_effect=fake_get):
            result = yt_analytics.get_video_analytics("secret-access-token", "channel123", "video123")

        self.assertEqual(result["analytics_error"], "Analytics API not available (400)")
        params = captured["kwargs"]["params"]
        headers = captured["kwargs"]["headers"]
        self.assertNotIn("access_token", params)
        self.assertEqual(headers["Authorization"], "Bearer secret-access-token")
        self.assertNotIn("secret-access-token", str(params))
        self.assertNotIn("secret-access-token", captured["url"])

    def test_analytics_query_uses_supported_playback_metrics(self):
        analytics = importlib.import_module("yt_analytics")
        response = mock.Mock(status_code=200)
        response.json.return_value = {
            "columnHeaders": [{"name": "views"}, {"name": "averageViewDuration"}],
            "rows": [[12, 696]],
        }
        with mock.patch.object(analytics.requests, "get", return_value=response) as get:
            result = analytics.get_video_analytics("token", "channel", "video")
        self.assertEqual(result["averageViewDuration"], 696)
        self.assertEqual(get.call_args.kwargs["params"]["metrics"],
                         "views,estimatedMinutesWatched,averageViewDuration")

    def test_analytics_visibility_comes_from_video_status(self):
        analytics = importlib.import_module("yt_analytics")
        response = mock.Mock()
        response.json.return_value = {"items": [{
            "snippet": {"title": "Test", "publishedAt": "2026-01-01", "liveBroadcastContent": "none"},
            "status": {"privacyStatus": "unlisted"},
            "contentDetails": {"duration": "PT1H"}, "statistics": {"viewCount": "12"},
        }]}
        with mock.patch.object(analytics.requests, "get", return_value=response) as get:
            stats = analytics.get_video_stats("token", "video")
        self.assertEqual(stats["privacy"], "unlisted")
        self.assertIn("status", get.call_args.kwargs["params"]["part"])

    def test_unavailable_metrics_are_not_reported_as_zero_or_failing_grade(self):
        analytics = importlib.import_module("yt_analytics")
        performance = analytics.score_video({"views": 12}, {"analytics_error": "403"})
        self.assertIsNone(performance["ctr_pct"])
        self.assertIsNone(performance["avg_duration_min"])
        self.assertEqual(performance["grade"], "PARTIAL")
        viral = importlib.import_module("yt_viral_score").score_item({"analytics": {
            "views": 12, "likes": 1, "ctr_pct": None, "avg_duration_min": None,
        }})
        self.assertIsNone(viral["ctr_pct"])
        self.assertIsNone(viral["avg_watch_min"])
        self.assertEqual(viral["grade"], "PARTIAL")

    def test_real_zero_watch_time_is_preserved(self):
        analytics = importlib.import_module("yt_analytics")
        result = analytics.score_video({"views": 0}, {"averageViewDuration": 0})
        self.assertEqual(result["avg_duration_min"], "0.0m")
        self.assertIsNone(result["ctr_pct"])

    def test_installed_vision_replacement_is_capability_checked(self):
        qa = importlib.import_module("yt_visual_qa")
        tags = mock.Mock()
        tags.json.return_value = {"models": [{"name": "qwen3.6:27b"}]}
        show = mock.Mock()
        show.json.return_value = {"capabilities": ["completion", "vision"]}
        with mock.patch.dict("os.environ", {}, clear=True), \
             mock.patch.object(qa.requests, "get", return_value=tags), \
             mock.patch.object(qa.requests, "post", return_value=show):
            self.assertEqual(qa.resolve_model(), "qwen3.6:27b")
            show.json.return_value = {"capabilities": ["completion"]}
            with self.assertRaises(qa.VisualQAFailed):
                qa.resolve_model()

    def test_explicit_vision_model_is_never_silently_replaced(self):
        qa = importlib.import_module("yt_visual_qa")
        tags = mock.Mock()
        tags.json.return_value = {"models": [{"name": "qwen3.6:27b"}]}
        with mock.patch.dict("os.environ", {"VISUAL_QA_MODEL": "missing:latest"}), \
             mock.patch.object(qa.requests, "get", return_value=tags), \
             self.assertRaisesRegex(qa.VisualQAFailed, "missing:latest"):
            qa.resolve_model()

    def test_thumbnail_generation_uses_local_model(self):
        thumbnail = importlib.import_module("yt_thumbnail")
        from PIL import Image
        with mock.patch.object(thumbnail.yt_local_image, "generate",
                               return_value=Image.new("RGB", (1280, 720), "blue")) as generate:
            image = thumbnail.generate_base_image("rainy jazz lounge")
        self.assertEqual(image.size, (1280, 720))
        generate.assert_called_once_with("rainy jazz lounge")

    def test_missing_local_image_environment_blocks_without_cloud_fallback(self):
        thumbnail = importlib.import_module("yt_thumbnail")
        with mock.patch.dict("os.environ", {"LOCAL_IMAGE_PYTHON": "C:/missing-neon-env/python.exe"}), \
             self.assertRaisesRegex(RuntimeError, "not installed"):
            thumbnail.generate_base_image("rain")

    def test_channel_duration_variants_and_platform_limit(self):
        autopost = importlib.import_module("yt_autopost")
        for hours in (1, 6, 12):
            expected = hours * 3600 - (1 if hours == 12 else 0)
            self.assertEqual(autopost.target_duration({"duration_hours": hours}, {}), expected)
        for hours in (True, 0, 13, "6"):
            with self.assertRaises(ValueError):
                autopost.target_duration({"duration_hours": hours}, {})
        with self.assertRaises(ValueError):
            autopost.target_duration({}, {"loop_to_seconds": 43201})

    def test_seo_preserves_title_and_avoids_unverified_promises(self):
        seo = importlib.import_module("yt_seo")
        title = "1 Hour Cyberpunk Ambient | Late Night Coding Marathon"
        result = seo.optimize(title, ["cyberpunk", "coding music"])
        self.assertEqual(result.title, title)
        self.assertNotIn("No ads", result.description)
        self.assertNotIn("No copyright claims", result.description)
        self.assertNotIn("Safe for streaming", result.description)
        self.assertNotIn("no ads", result.tags)

    def test_long_duration_metadata_does_not_advertise_one_hour(self):
        seo = importlib.import_module("yt_seo")
        result = seo.optimize("12 Hours Neon Night Rain | Music for Rest", [])
        self.assertIn("12 hour music", result.tags)
        self.assertNotIn("1 hour music", result.tags)

    def test_actual_duration_must_fit_target_and_platform_limit(self):
        autopost = importlib.import_module("yt_autopost")
        for duration in (43200.01, 300, float("nan")):
            with mock.patch.object(autopost.yt_render, "get_audio_duration", return_value=duration), \
                 self.assertRaises(autopost.yt_visual_qa.VisualQAFailed):
                autopost.validate_rendered_duration("test.mp4", 43199)
        with mock.patch.object(autopost.yt_render, "get_audio_duration", return_value=43199.5):
            autopost.validate_rendered_duration("test.mp4", 43199)

    def test_viral_score_marks_unscored_items_as_needing_analytics(self):
        yt_viral_score = importlib.import_module("yt_viral_score")
        item = {
            "id": "T001",
            "title": "1 Hour Piano Ambient | Gentle Focus Music for Work",
            "prompt": "solo piano, ambient, gentle focus",
            "tags": ["piano", "focus music"],
            "status": "uploaded",
            "youtube_id": "abc123",
        }

        score = yt_viral_score.score_item(item)

        self.assertIsNone(score["score"])
        self.assertEqual(score["grade"], "UNSCORED")
        self.assertEqual(score["reason"], "needs analytics")

    def test_viral_score_scores_items_with_basic_data_api_stats(self):
        yt_viral_score = importlib.import_module("yt_viral_score")
        item = {
            "id": "T002",
            "title": "1 Hour Night Study Music | Dark Ambient",
            "prompt": "dark ambient, focus, study",
            "tags": ["dark ambient", "study music"],
            "analytics": {
                "views": 171,
                "likes": 4,
                "ctr_pct": "0.0%",
                "avg_duration_min": "0.0m",
            },
        }

        score = yt_viral_score.score_item(item)

        self.assertIsInstance(score["score"], int)
        self.assertGreater(score["score"], 0)
        self.assertIn("dark_ambient", score["features"]["genres"])

    def test_viral_score_pending_metadata_does_not_treat_neon_as_synthwave(self):
        yt_viral_score = importlib.import_module("yt_viral_score")
        item = {
            "id": "T003",
            "status": "pending",
            "title": "1 Hour Rain Sounds and Soft Piano | Study Background Music",
            "prompt": "gentle piano, light rainfall, neon desk lamp ambience",
            "tags": ["rain music", "piano music", "study music"],
            "bpm": 62,
        }

        features = yt_viral_score.detect_features(item)
        recommendations = yt_viral_score.recommend_pending(
            {"queue": [item]},
            [
                {"feature": "genre:synthwave", "avg_score": 90},
                {"feature": "genre:jazz", "avg_score": 80},
                {"feature": "genre:rain_ambient", "avg_score": 70},
                {"feature": "genre:piano", "avg_score": 60},
            ],
        )

        self.assertEqual(features["genres"], ["rain_ambient", "piano"])
        self.assertEqual(
            recommendations[0]["matched_features"],
            ["genre:rain_ambient", "genre:piano"],
        )
        self.assertEqual(recommendations[0]["detected_features"], features)

        jazz = yt_viral_score.detect_features({
            "title": "Late Night Jazz Piano",
            "prompt": "mellow saxophone and upright bass in a neon lounge",
            "tags": ["jazz", "piano"],
        })
        self.assertIn("jazz", jazz["genres"])
        self.assertNotIn("synthwave", jazz["genres"])

    def test_youtube_watch_urls_are_not_mangled(self):
        yt_upload = (ROOT / "yt_upload.py").read_text(encoding="utf-8")
        yt_autopost = (ROOT / "yt_autopost.py").read_text(encoding="utf-8")
        self.assertNotIn("watchWARNINGv", yt_upload)
        self.assertNotIn("watchWARNINGv", yt_autopost)
        self.assertIn("watch?v=", yt_upload)
        self.assertIn("watch?v=", yt_autopost)

    def test_completed_shorts_queue_downgrades_stale_log_to_warning(self):
        health_check = (ROOT / "scripts" / "Health-Check.ps1").read_text(encoding="utf-8")

        self.assertIn("[switch]$StaleAsWarning", health_check)
        self.assertIn("$shortsQueueComplete", health_check)
        self.assertIn("-StaleAsWarning:$shortsQueueComplete", health_check)

    def test_forced_uploaded_item_cannot_be_uploaded_twice(self):
        autopost = importlib.import_module('yt_autopost')
        self.assertIsNone(autopost.pick_next({'queue': [
            {'id': '001', 'status': 'uploaded'}]}, '001'))

    def test_daily_rotation_is_bounded_and_idempotent(self):
        daily = importlib.import_module('yt_daily')
        queue = {'_meta': {}, 'queue': []}
        daily.refill(queue)
        before = copy.deepcopy(queue)
        daily.refill(queue)
        self.assertEqual(queue, before)
        self.assertEqual(len(queue['queue']), 7)
        self.assertEqual({item['duration_hours'] for item in queue['queue']}, {1, 6, 12})
        self.assertEqual(len({item['id'] for item in queue['queue']}), 7)

    def test_daily_receipt_prevents_same_day_duplicate(self):
        from datetime import datetime, timezone
        daily = importlib.import_module('yt_daily')
        now = datetime(2026, 10, 10, 10, tzinfo=timezone.utc)
        queue = {'queue': []}
        receipt = {'youtube_id': 'accepted-id', 'created': now.isoformat()}
        self.assertTrue(daily.uploaded_today(queue, [receipt], now))
        self.assertFalse(daily.uploaded_today(queue, [], now))

    def test_unexpected_failure_marks_queue_failed_not_stuck(self):
        autopost = importlib.import_module('yt_autopost')
        queue = {'_meta': {}, 'queue': [{'id': '001', 'status': 'pending'}]}
        with mock.patch.object(autopost, 'load_queue', return_value=queue), \
             mock.patch.object(autopost, 'save_queue'), \
             mock.patch.object(autopost, 'log'), \
             mock.patch.object(autopost, 'run_item', side_effect=ValueError('invalid duration')), \
             mock.patch.object(sys, 'argv', ['yt_autopost.py']), \
             self.assertRaises(SystemExit):
            autopost.main()
        self.assertEqual(queue['queue'][0]['status'], 'failed')


if __name__ == "__main__":
    unittest.main()

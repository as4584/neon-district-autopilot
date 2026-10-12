"""
yt_autopost.py — Full automation: generate → render → upload → mark done.

Reads yt_queue.json, picks the next pending item, runs the full pipeline,
then marks it uploaded. Designed to be called by the Claude Code scheduler.

Usage:
    # Single run (called by cron):
    doppler run --project agentop --config prd -- python3 yt_autopost.py

    # Force a specific queue item by ID:
    doppler run --project agentop --config prd -- python3 yt_autopost.py --id 003

    # Dry run (show what would be processed, don't actually run):
    python3 yt_autopost.py --dry-run

    # Show queue status:
    python3 yt_autopost.py --status
"""

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR   = Path(__file__).parent
QUEUE_FILE = BASE_DIR / "yt_queue.json"
LOG_FILE   = BASE_DIR / "test_outputs" / "autopost.log"

# Import pipeline modules
sys.path.insert(0, str(BASE_DIR))
import yt_generate
import yt_render
import yt_upload
import yt_stitch
import yt_seo
import yt_visual_qa
import yt_series
import yt_audio_qa
import yt_motion
try:
    import yt_thumbnail
except Exception as e:
    yt_thumbnail = None
    THUMBNAIL_IMPORT_ERROR = e
else:
    THUMBNAIL_IMPORT_ERROR = None


def stop_ace_step_api():
    """Stop ACE-Step after generation so render/upload can use the GPU freely."""
    import subprocess as _sp

    if os.name == "nt":
        script = BASE_DIR / "scripts" / "Stop-AceStep.ps1"
        if script.exists():
            _sp.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                ],
                capture_output=True,
                text=True,
            )
        return

    _sp.run(["pkill", "-f", "acestep-api"], capture_output=True)


# ── Queue management ──────────────────────────────────────────────────────────

def load_queue() -> dict:
    with open(QUEUE_FILE) as f:
        return json.load(f)


def save_queue(q: dict):
    temporary = QUEUE_FILE.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(q, indent=2), encoding="utf-8")
    temporary.replace(QUEUE_FILE)


def pick_next(q: dict, force_id: str = None) -> dict | None:
    """Return next pending queue item (or specific ID if forced)."""
    for item in q["queue"]:
        if force_id:
            if item["id"] == force_id and item["status"] == "pending" and not item.get("youtube_id"):
                return item
        elif item["status"] == "pending" and not item.get("youtube_id"):
            return item
    return None


def mark_status(q: dict, item_id: str, status: str, **kwargs):
    """Update a queue item's status and optional fields."""
    for item in q["queue"]:
        if item["id"] == item_id:
            item["status"] = status
            for k, v in kwargs.items():
                item[k] = v
            break
    save_queue(q)


# ── Logging ───────────────────────────────────────────────────────────────────

def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG_FILE.parent.mkdir(exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ── Main pipeline ─────────────────────────────────────────────────────────────

def target_duration(item: dict, meta: dict) -> int:
    hours = item.get("duration_hours")
    if hours is not None:
        if isinstance(hours, bool) or hours not in (1, 6, 12):
            raise ValueError("duration_hours must be 1, 6, or 12")
        # Leave one second for encoder/container rounding at YouTube's limit.
        return int(hours * 3600) - (1 if hours == 12 else 0)
    seconds = item.get("loop_to_seconds", meta.get("loop_to_seconds", 3600))
    if isinstance(seconds, bool) or not isinstance(seconds, int) or not 0 < seconds <= 43200:
        raise ValueError("Target duration must be between 1 second and 12 hours")
    return seconds


def validate_rendered_duration(video_path: str, target: int) -> None:
    try:
        duration = yt_render.get_audio_duration(video_path)
    except Exception as exc:
        raise yt_visual_qa.VisualQAFailed(
            f"Could not measure rendered duration ({type(exc).__name__})"
        ) from None
    if not math.isfinite(duration) or duration > 43200 or abs(duration - target) > 2:
        raise yt_visual_qa.VisualQAFailed(
            f"Rendered duration is invalid: {duration:.2f}s (target {target}s)"
        )


def run_item(item: dict, meta: dict, dry_run: bool = False) -> bool:
    """
    Full pipeline for one queue item. Two modes:

    mode=generate (default):
      ACE-Step generate → render (video loop) → upload

    mode=stitch:
      Stitch pre-existing FLACs with crossfades → render (video loop) → upload
      Requires item["stitch_sources"] = ["/path/to/a.flac", ...]

    Returns True on success, False on failure.
    """
    item_id   = item["id"]
    title     = item["title"]
    tags      = item.get("tags", [])
    mode      = item.get("mode", "generate")
    if mode == "generate" and item.get("audio_model", "ace-step") != "ace-step":
        raise ValueError("Audio backend has not passed production acceptance; upload blocked")

    loop_to     = target_duration(item, meta)
    privacy     = meta.get("privacy", "unlisted")
    category_id = meta.get("category_id", "10")
    cover_video = meta.get("cover_video")
    cover_image = meta.get("cover_image")

    log(f"Starting item {item_id}: {title}")
    log(f"  Mode: {mode}")
    log(f"  Target duration: {loop_to}s")

    if dry_run:
        log("  [DRY RUN] Would process, render, upload. Skipping.")
        return True

    ts = time.strftime("%Y%m%d_%H%M%S")
    audio_path = None
    stitch_cleanup = False  # only clean up audio for stitch (generated paths handled separately)

    if mode == "reuse":
        audio_path = item.get("audio_source")
        if not audio_path or not Path(audio_path).is_file():
            log("  ERROR: Preserved audio source is missing.")
            return False
        log(f"  Reusing preserved audio: {Path(audio_path).name}")
    elif mode == "stitch":
        # ── Step 1: Stitch pre-existing FLACs ────────────────────────────────
        sources      = item.get("stitch_sources", [])
        crossfade    = item.get("crossfade_seconds", 4)
        audio_out    = str(BASE_DIR / "test_outputs" / f"stitch_{item_id}_{ts}.mp3")
        stitch_cleanup = True

        try:
            log(f"  [1/3] Stitching {len(sources)} sources with {crossfade}s crossfades...")
            audio_path = yt_stitch.stitch(
                inputs=sources,
                output=audio_out,
                crossfade_sec=crossfade,
            )
            log(f"  Audio: {audio_path}")
        except Exception as e:
            log(f"  ERROR during stitch: {e}")
            return False

    else:
        # ── Step 1: Generate audio via ACE-Step ───────────────────────────────
        prompt       = item.get("prompt", "")
        bpm          = item.get("bpm", 80)
        gen_duration = meta.get("default_duration_seconds", 300)
        audio_out    = str(BASE_DIR / "test_outputs" / f"track_{item_id}_{ts}.flac")

        log(f"  Prompt: {prompt[:80]}")
        try:
            track_count = item.get("track_count", 1)
            if isinstance(track_count, bool) or not isinstance(track_count, int) or not 1 <= track_count <= 6:
                raise ValueError("track_count must be between 1 and 6")
            masters = []
            for index in range(track_count):
                output = audio_out if track_count == 1 else str(
                    BASE_DIR / "test_outputs" / f"track_{item_id}_{ts}_{index+1:02d}.flac")
                log(f"  [1/3] Generating track {index+1}/{track_count}: {gen_duration}s via ACE-Step...")
                masters.append(yt_generate.generate({
                    "prompt": prompt, "bpm": bpm, "duration": gen_duration,
                    "format": "flac", "output": output,
                }))
            audio_path = masters[0]
            if track_count > 1:
                audio_path = yt_stitch.stitch(masters, str(
                    BASE_DIR / "test_outputs" / f"stitch_{item_id}_{ts}.mp3"), crossfade_sec=4)
                stitch_cleanup = True
            log(f"  Audio: {audio_path}")
        except Exception as e:
            log(f"  ERROR during generation: {e}")
            stop_ace_step_api()
            log("  ACE-Step engine stopped (freeing VRAM)")
            return False

        # Shut down ACE-Step immediately — render/upload don't need it
        stop_ace_step_api()
        log("  ACE-Step engine stopped (freeing VRAM for render)")

    try:
        audio_qa = yt_audio_qa.inspect(audio_path)
        log(f"  Audio technical QA passed: mean={audio_qa['mean_volume']}dB, peak={audio_qa['max_volume']}dB")
    except Exception as exc:
        log(f"  ERROR: Audio technical QA blocked upload ({type(exc).__name__}): {exc}")
        return False

    # ── Step 2: Render to 1-hour MP4 ─────────────────────────────────────────
    video_out = str(BASE_DIR / "test_outputs" / f"video_{item_id}_{ts}.mp4")

    # Resolve cover — priority:
    #   1. Per-item AI-generated image (yt_thumbnail.py, idempotent)
    #   2. Per-item override in queue item["cover"]
    #   3. Looping .mov from _meta
    #   4. Static default image from _meta
    cover_path = None
    use_video_loop = False

    # Reuse an existing item-specific image first. Local generation runs after
    # Ollama rejects the current candidate.
    try:
        existing_ai_cover = BASE_DIR / "covers" / f"{item_id}.jpg"
        if not existing_ai_cover.exists() or yt_thumbnail is None or not yt_thumbnail.is_imagery_only(item_id):
            if yt_thumbnail is None:
                raise RuntimeError('Local artwork module unavailable')
            existing_ai_cover = Path(yt_thumbnail.generate(item))
        log("  Reusing existing item-specific cover for visual QA...")
        cover_path = str(existing_ai_cover)
        log(f"  Cover: {Path(cover_path).name}")
        use_video_loop = False
    except Exception as thumb_err:
        log(f"  ERROR: Imagery-only artwork unavailable ({type(thumb_err).__name__}); legacy text covers are not a fallback.")
        return False

    def regenerate_cover_locally() -> str:
        if yt_thumbnail is None:
            raise RuntimeError(f"thumbnail module unavailable: {THUMBNAIL_IMPORT_ERROR}")
        log("  Visual QA mismatch: regenerating cover with the local image model...")
        return yt_thumbnail.generate(item, force=True)

    def regenerate_cover_with_feedback(result, attempt) -> str:
        feedback = '; '.join([result.reason, *result.mismatches])
        return yt_thumbnail.generate(item, force=True, feedback=feedback, attempt=attempt)

    try:
        log("  Visual QA: checking cover against description and art direction...")
        approved_cover, cover_qa = yt_visual_qa.approve_cover(
            item,
            cover_path,
            regenerate_cover_locally,
            regenerate_with_feedback=regenerate_cover_with_feedback,
        )
        if Path(approved_cover).resolve() != Path(cover_path).resolve():
            cover_path = approved_cover
            use_video_loop = False
            log(f"  Visual QA: local replacement approved ({Path(cover_path).name})")
        log(
            "  Visual QA passed: "
            f"content={cover_qa.content_match_score}/10, "
            f"neon={cover_qa.neon_theme_score}/10, "
            f"quality={cover_qa.visual_quality_score}/10"
        )
    except yt_visual_qa.VisualQAFailed as qa_error:
        log(f"  ERROR: Upload blocked by visual QA: {qa_error}")
        return False

    try:
        log(f"  [2/3] Rendering to {loop_to//3600}hr MP4...")
        if use_video_loop:
            # Loop both video and audio to reach target duration
            import subprocess
            vf = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black"
            cmd = [
                "ffmpeg", "-y",
                "-stream_loop", "-1", "-i", cover_path,
                "-stream_loop", "-1", "-i", audio_path,
                "-t", str(loop_to),
                "-map", "0:v:0", "-map", "1:a:0",
                "-vf", vf,
                "-c:v", "h264_nvenc", "-preset", "fast", "-b:v", "4M",
                "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                video_out,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                # Fallback to CPU encode if NVENC fails
                cmd[cmd.index("h264_nvenc")] = "libx264"
                cmd[cmd.index("fast")] = "ultrafast"
                result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"ffmpeg failed: {result.stderr[-500:]}")
        else:
            log('  Rendering imagery-only still scene; real image-to-video acceptance pending...')
            scene = yt_motion.render_scene(cover_path)
            yt_motion.render_session(scene, audio_path, video_out, loop_to)
        log(f"  Video: {video_out} ({Path(video_out).stat().st_size / 1_048_576:.0f} MB)")
    except Exception as e:
        log(f"  ERROR during render: {e}")
        return False
    finally:
        # Clean up stitched audio to save disk space
        # (stitch output is intermediate; generated FLACs are cleaned here too)
        # Note: stitch sources (pre-existing FLACs) are NOT deleted
        if audio_path and stitch_cleanup:
            try:
                os.remove(audio_path)
                log(f"  Cleaned up stitched audio: {Path(audio_path).name}")
            except Exception:
                pass
        # Preserve original masters for retries and future long listening mixes.

    try:
        validate_rendered_duration(video_out, loop_to)
        log("  Visual QA: checking the rendered video frame before upload...")
        rendered_qa = yt_visual_qa.approve_rendered_video(item, video_out)
        log(
            "  Rendered video QA passed: "
            f"content={rendered_qa.content_match_score}/10, "
            f"neon={rendered_qa.neon_theme_score}/10, "
            f"quality={rendered_qa.visual_quality_score}/10"
        )
    except yt_visual_qa.VisualQAFailed as qa_error:
        log(f"  ERROR: Upload blocked by rendered video QA: {qa_error}")
        log(f"  Video preserved for diagnosis: {video_out}")
        return False

    # ── Step 3: SEO optimize ──────────────────────────────────────────────────
    genre = item.get("genre", "")
    stitch_track_names = None
    if mode == "stitch":
        # Build human-readable track names from source filenames for description
        sources = item.get("stitch_sources", [])
        stitch_track_names = [Path(s).stem[:40] for s in sources]

    seo = yt_seo.optimize(
        title=title,
        tags=tags,
        mode=mode,
        genre=genre,
        stitch_tracks=stitch_track_names,
    )
    if seo.warnings:
        for w in seo.warnings:
            log(f"  SEO: {w}")
    seo.description += "\n\nThis instrumental session repeats a locally generated music mix for continuous listening."
    log(f"  SEO score: {seo.seo_score}/100 — title: {seo.title}")

    # ── Step 3b: Thumbnail generation ────────────────────────────────────────
    thumbnail_path = cover_path if Path(cover_path).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} else None
    if thumbnail_path:
        log(f"  Thumbnail: using QA-approved cover {Path(thumbnail_path).name}")

    # ── Step 4: Upload ────────────────────────────────────────────────────────
    try:
        log(f"  [3/3] Uploading to YouTube as '{seo.title}'...")
        video = yt_upload.upload_video(
            video_path=video_out,
            title=seo.title,
            description=seo.description,
            tags=seo.tags,
            category_id=category_id,
            privacy=privacy,
        )
        video_id = video.get("id")
        if not video_id:
            raise RuntimeError("YouTube did not return a video ID")
        item['youtube_id'] = video_id
        receipt = BASE_DIR / "test_outputs" / f"upload_receipt_{item_id}.json"
        receipt.write_text(json.dumps({
            "id": item_id, "youtube_id": video_id, "privacy": privacy,
            "created": datetime.now(timezone.utc).isoformat(),
        }, indent=2), encoding="utf-8")
        url = f"https://www.youtube.com/watch?v={video_id}"
        log(f"  Uploaded: {url}")

        # Set custom thumbnail (non-fatal if it fails)
        if thumbnail_path and video_id:
            try:
                ok = yt_upload.set_thumbnail(video_id, thumbnail_path)
                if ok:
                    log(f"  Thumbnail uploaded to YouTube")
            except Exception as te:
                log(f"  WARNING: Thumbnail set failed (video still uploaded): {te}")
        try:
            yt_series.organize_video(item, video_id)
            log("  Video organized into its listening series.")
        except Exception as exc:
            log(f"  WARNING: Playlist organization needs retry ({type(exc).__name__})")
        log('  Waiting for YouTube processing and visibility read-back...')
        verified = yt_upload.verify_uploaded_video(video_id, privacy, loop_to)
        (BASE_DIR / 'test_outputs' / f'upload_verification_{item_id}.json').write_text(
            json.dumps(verified, indent=2), encoding='utf-8')
        log('  YouTube processing, channel identity, visibility, and duration verified.')
    except Exception as e:
        log(f"  ERROR during upload: {e}")
        log(f"  Video preserved for retry: {video_out}")
        return False
    else:
        # Only clean up video on success — keep it if upload failed for retry
        try:
            os.remove(video_out)
            log(f"  Cleaned up video: {Path(video_out).name}")
        except Exception:
            pass

    return True, video_id


def build_description(title: str, tags: list) -> str:
    tag_line = " ".join(f"#{t.replace(' ', '').replace('-', '')}" for t in tags[:10])
    return (
        f"{title}\n\n"
        f"Background music for deep focus, work, studying, and relaxation.\n"
        f"Instrumental atmosphere for long listening sessions.\n\n"
        f"Original AI-generated music by Neon District Archive.\n"
        f"For reuse or licensing enquiries, contact Neon District Archive.\n\n"
        f"{tag_line}\n\n"
        f"— Neon District Archive\n"
        f"Subscribe for weekly ambient & lo-fi uploads."
    )


# ── Status display ────────────────────────────────────────────────────────────

def show_status(q: dict):
    items = q["queue"]
    counts = {"pending": 0, "generating": 0, "uploaded": 0, "failed": 0}
    for item in items:
        s = item.get("status", "pending")
        counts[s] = counts.get(s, 0) + 1

    print(f"\n=== Queue Status ({len(items)} total) ===")
    print(f"  Pending:    {counts['pending']}")
    print(f"  Uploaded:   {counts['uploaded']}")
    print(f"  Failed:     {counts['failed']}")
    print()
    for item in items:
        status = item.get("status", "pending")
        icon = {
            "pending": "PENDING",
            "uploaded": "UPLOADED",
            "failed": "FAILED",
            "generating": "GENERATING",
        }.get(status, "UNKNOWN")
        yt_id = item.get("youtube_id", "")
        yt_str = f" -> https://youtu.be/{yt_id}" if yt_id else ""
        print(f"  {icon} [{item['id']}] {item['title'][:60]}{yt_str}")
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Neon District Archive — automated YouTube publisher")
    parser.add_argument("--id",       default=None, help="Force specific queue item by ID")
    parser.add_argument("--dry-run",  action="store_true", help="Show what would run without doing it")
    parser.add_argument("--status",   action="store_true", help="Print queue status and exit")
    args = parser.parse_args()

    q = load_queue()

    if args.status:
        show_status(q)
        return

    item = pick_next(q, force_id=args.id)
    if not item:
        if args.id:
            sys.exit(f"Item {args.id} not found or not pending.")
        log("Queue empty — all items processed.")
        return

    meta = q["_meta"]

    log(f"=== yt_autopost run — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} ===")
    if args.dry_run:
        run_item(item, meta, dry_run=True)
        log(f"=== Dry run complete: item {item['id']} left unchanged ===\n")
        return

    mark_status(q, item["id"], "generating")

    try:
        result = run_item(item, meta, dry_run=False)
    except Exception as exc:
        log(f"  ERROR: Unexpected pipeline failure ({type(exc).__name__})")
        result = False

    if isinstance(result, tuple):
        success, video_id = result
    else:
        success, video_id = result, None

    if success:
        mark_status(q, item["id"], "uploaded",
                    youtube_id=video_id,
                    created=datetime.now(timezone.utc).isoformat())
        log(f"=== Done: item {item['id']} uploaded ===\n")
    else:
        mark_status(q, item["id"], "failed")
        log(f"=== FAILED: item {item['id']} marked failed ===\n")
        sys.exit(1)


if __name__ == "__main__":
    main()

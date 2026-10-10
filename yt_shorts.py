"""Generate and upload YouTube Shorts for Neon District Archive."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from textwrap import wrap

BASE_DIR = Path(__file__).parent
QUEUE_FILE = BASE_DIR / "shorts_queue.json"
LOG_FILE = BASE_DIR / "test_outputs" / "shorts.log"

sys.path.insert(0, str(BASE_DIR))
import yt_generate
import yt_upload

SHORT_WIDTH = 1080
SHORT_HEIGHT = 1920
SHORT_MAX_SECONDS = 60.5
SHORT_MIN_BYTES = 1_000_000
CHANNEL_NAME = "Neon District Archive"


def log(message: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    line = f"[{ts}] {message}"
    print(line, flush=True)
    LOG_FILE.parent.mkdir(exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_queue() -> dict:
    return json.loads(QUEUE_FILE.read_text(encoding="utf-8"))


def save_queue(queue: dict) -> None:
    QUEUE_FILE.write_text(json.dumps(queue, indent=2), encoding="utf-8")


def pick_next(queue: dict, force_id: str | None = None) -> dict | None:
    for item in queue["queue"]:
        if force_id:
            if item["id"] == force_id:
                return item
        elif item.get("status") == "pending":
            return item
    return None


def mark_status(queue: dict, item_id: str, status: str, **kwargs) -> None:
    for item in queue["queue"]:
        if item["id"] == item_id:
            item["status"] = status
            item.update(kwargs)
            break
    save_queue(queue)


def show_status(queue: dict) -> None:
    counts = {}
    for item in queue["queue"]:
        counts[item.get("status", "pending")] = counts.get(item.get("status", "pending"), 0) + 1
    print(f"\n=== Shorts Queue ({len(queue['queue'])} total) ===")
    print(f"  Pending:  {counts.get('pending', 0)}")
    print(f"  Uploaded: {counts.get('uploaded', 0)}")
    print(f"  Failed:   {counts.get('failed', 0)}")
    print()
    for item in queue["queue"]:
        yt = f" -> https://youtu.be/{item['youtube_id']}" if item.get("youtube_id") else ""
        print(f"  {item.get('status', 'pending').upper()} [{item['id']}] {item['title']}{yt}")
    print()


def _load_font(size: int, bold: bool = False):
    from PIL import ImageFont

    names = [
        "arialbd.ttf" if bold else "arial.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
    ]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def build_short_cover(item: dict, source_cover: str, output_path: str) -> str:
    from PIL import Image, ImageDraw, ImageFilter

    source = Image.open(source_cover).convert("RGB")
    bg = source.copy()
    bg_ratio = SHORT_WIDTH / SHORT_HEIGHT
    src_ratio = bg.width / bg.height
    if src_ratio > bg_ratio:
        new_height = SHORT_HEIGHT
        new_width = int(new_height * src_ratio)
    else:
        new_width = SHORT_WIDTH
        new_height = int(new_width / src_ratio)
    bg = bg.resize((new_width, new_height), Image.LANCZOS)
    left = (bg.width - SHORT_WIDTH) // 2
    top = (bg.height - SHORT_HEIGHT) // 2
    bg = bg.crop((left, top, left + SHORT_WIDTH, top + SHORT_HEIGHT))
    bg = bg.filter(ImageFilter.GaussianBlur(34))
    overlay = Image.new("RGB", (SHORT_WIDTH, SHORT_HEIGHT), "#13051f")
    canvas = Image.blend(bg, overlay, 0.62)
    draw = ImageDraw.Draw(canvas)

    title = item.get("title", "Neon District Archive #Shorts")
    title = title.replace("#Shorts", "").strip()
    lines = wrap(title, width=18)
    if not lines:
        lines = [title]
    lines = lines[:4]

    title_font = _load_font(86, bold=True)
    tag_font = _load_font(44, bold=True)
    channel_font = _load_font(34, bold=False)

    cyan = (0, 245, 230)
    pink = (255, 68, 210)
    purple = (104, 80, 255)
    yellow = (255, 235, 110)
    panel = (33, 14, 54)

    for x, y, r, color in [
        (130, 220, 115, cyan),
        (940, 260, 135, pink),
        (165, 1650, 150, purple),
        (895, 1560, 120, cyan),
    ]:
        glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        glow_draw.ellipse((x - r, y - r, x + r, y + r), fill=(*color, 72))
        glow = glow.filter(ImageFilter.GaussianBlur(32))
        canvas = Image.alpha_composite(canvas.convert("RGBA"), glow).convert("RGB")
        draw = ImageDraw.Draw(canvas)

    for x, y, color in [
        (88, 480, yellow),
        (960, 540, cyan),
        (142, 1240, pink),
        (920, 1190, yellow),
        (805, 170, yellow),
        (310, 1740, pink),
    ]:
        draw.polygon(
            [(x, y - 24), (x + 9, y - 8), (x + 28, y), (x + 9, y + 8), (x, y + 24), (x - 9, y + 8), (x - 28, y), (x - 9, y - 8)],
            fill=color,
        )

    draw.text((56, 64), CHANNEL_NAME, font=channel_font, fill=cyan)
    draw.rounded_rectangle((56, 238, SHORT_WIDTH - 56, 1450), radius=54, fill=panel, outline=pink, width=5)
    draw.rounded_rectangle((92, 274, SHORT_WIDTH - 92, 1414), radius=42, outline=cyan, width=3)

    icon_x, icon_y = 352, 930
    draw.rounded_rectangle((icon_x, icon_y, icon_x + 376, icon_y + 230), radius=44, fill=(20, 10, 36), outline=cyan, width=6)
    draw.ellipse((icon_x + 86, icon_y + 70, icon_x + 136, icon_y + 120), fill=cyan)
    draw.ellipse((icon_x + 240, icon_y + 70, icon_x + 290, icon_y + 120), fill=pink)
    draw.arc((icon_x + 132, icon_y + 98, icon_x + 244, icon_y + 174), 15, 165, fill=yellow, width=8)
    draw.rounded_rectangle((icon_x + 116, icon_y - 38, icon_x + 260, icon_y + 8), radius=22, fill=purple, outline=yellow, width=4)
    draw.line((icon_x + 188, icon_y - 38, icon_x + 188, icon_y - 92), fill=yellow, width=5)
    draw.ellipse((icon_x + 170, icon_y - 122, icon_x + 206, icon_y - 86), fill=yellow)

    y = 382
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        x = (SHORT_WIDTH - (bbox[2] - bbox[0])) // 2
        draw.text((x + 6, y + 6), line, font=title_font, fill=pink)
        draw.text((x - 4, y - 4), line, font=title_font, fill=cyan)
        draw.text((x, y), line, font=title_font, fill=(255, 255, 255))
        y += 104

    tag_text = "#Shorts"
    tag_bbox = draw.textbbox((0, 0), tag_text, font=tag_font)
    tag_x = (SHORT_WIDTH - (tag_bbox[2] - tag_bbox[0])) // 2
    draw.rounded_rectangle((tag_x - 34, 1246, tag_x + (tag_bbox[2] - tag_bbox[0]) + 34, 1316), radius=28, fill=(18, 8, 32), outline=yellow, width=3)
    draw.text((tag_x, 1258), tag_text, font=tag_font, fill=cyan)
    draw.rectangle((56, 1430, SHORT_WIDTH - 56, 1440), fill=cyan)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, "JPEG", quality=94)
    return str(output.resolve())


def short_video_filter() -> str:
    """Build a 9:16 layout without destructively cropping the source art."""
    return (
        f"scale={SHORT_WIDTH}:{SHORT_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={SHORT_WIDTH}:{SHORT_HEIGHT},"
        "format=yuv420p[v]"
    )


def _ffprobe_json(video_path: str) -> dict:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=index,codec_type,width,height,duration:format=duration",
            "-of",
            "json",
            video_path,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr[-800:]}")
    return json.loads(result.stdout)


def qa_short_video(video_path: str, expected_duration: int) -> None:
    path = Path(video_path)
    if not path.exists():
        raise RuntimeError(f"Shorts QA failed: video missing: {video_path}")
    if path.stat().st_size < SHORT_MIN_BYTES:
        raise RuntimeError(
            f"Shorts QA failed: video file too small ({path.stat().st_size} bytes)"
        )

    metadata = _ffprobe_json(str(path))
    streams = metadata.get("streams", [])
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    video_stream = video_streams[0] if video_streams else None
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not video_stream:
        raise RuntimeError("Shorts QA failed: no video stream")
    if len(video_streams) != 1:
        raise RuntimeError(f"Shorts QA failed: expected 1 video stream, got {len(video_streams)}")
    if not audio_stream:
        raise RuntimeError("Shorts QA failed: no audio stream")

    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    if width != SHORT_WIDTH or height != SHORT_HEIGHT:
        raise RuntimeError(f"Shorts QA failed: expected 1080x1920, got {width}x{height}")
    if height <= width:
        raise RuntimeError(f"Shorts QA failed: video is not vertical ({width}x{height})")

    duration = float(metadata.get("format", {}).get("duration") or 0)
    if duration <= 0:
        duration = float(video_stream.get("duration") or 0)
    if duration <= 0:
        raise RuntimeError("Shorts QA failed: duration unavailable")
    if duration > SHORT_MAX_SECONDS:
        raise RuntimeError(f"Shorts QA failed: duration {duration:.2f}s exceeds Shorts limit")
    if abs(duration - expected_duration) > 1.5:
        raise RuntimeError(
            f"Shorts QA failed: duration {duration:.2f}s does not match expected {expected_duration}s"
        )


def render_vertical_short(audio_path: str, cover_path: str, output_path: str, duration: int) -> str:
    output = str(Path(output_path).resolve())
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-framerate",
        "30",
        "-i",
        cover_path,
        "-stream_loop",
        "-1",
        "-i",
        audio_path,
        "-t",
        str(duration),
        "-map",
        "[v]",
        "-map",
        "1:a:0",
        "-filter_complex",
        short_video_filter(),
        "-c:v",
        "h264_nvenc",
        "-preset",
        "fast",
        "-b:v",
        "4M",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        output,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        cmd[cmd.index("h264_nvenc")] = "libx264"
        cmd[cmd.index("fast")] = "ultrafast"
        result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg vertical render failed: {result.stderr[-800:]}")
    qa_short_video(output, duration)
    return output


def shorts_description(item: dict) -> str:
    tags = item.get("tags", [])
    tag_line = " ".join(f"#{tag.replace(' ', '').replace('-', '')}" for tag in tags[:8])
    if "#Shorts" not in tag_line and "#shorts" not in tag_line:
        tag_line = "#Shorts " + tag_line
    return (
        f"{item['title']}\n\n"
        "Short-form AI-generated focus music from Neon District Archive.\n"
        "Follow for ambient, lo-fi, jazz, synthwave, and deep work music.\n\n"
        f"{tag_line}"
    )


def approve_preview(queue: dict, item: dict) -> None:
    preview_video = item.get("preview_video")
    if not preview_video:
        raise RuntimeError(f"No preview_video recorded for {item['id']}; run --preview-only first.")
    qa_short_video(preview_video, int(item.get("duration_seconds") or queue["_meta"].get("default_duration_seconds", 60)))
    item["visual_approved"] = True
    item["visual_approved_at"] = datetime.now(timezone.utc).isoformat()
    save_queue(queue)


def run_item(item: dict, meta: dict, dry_run: bool = False, preview_only: bool = False) -> dict:
    item_id = item["id"]
    duration = int(item.get("duration_seconds") or meta.get("default_duration_seconds", 60))
    cover = item.get("cover_image") or meta.get("cover_image")
    title = item["title"]
    tags = list(dict.fromkeys([*item.get("tags", []), "Shorts", "shorts music"]))

    log(f"Starting short {item_id}: {title}")
    log(f"  Duration: {duration}s")
    if dry_run:
        log("  [DRY RUN] Would generate, render vertical video, and upload.")
        return {"success": True, "uploaded": False}

    if not cover or not Path(cover).exists():
        raise FileNotFoundError(f"Cover image not found: {cover}")

    ts = time.strftime("%Y%m%d_%H%M%S")
    audio_path = str(BASE_DIR / "test_outputs" / f"short_audio_{item_id}_{ts}.flac")
    video_path = str(BASE_DIR / "test_outputs" / f"short_video_{item_id}_{ts}.mp4")
    short_cover_path = str(BASE_DIR / "test_outputs" / f"short_cover_{item_id}_{ts}.jpg")

    try:
        log("  [1/4] Generating short audio via ACE-Step...")
        audio_path = yt_generate.generate(
            {
                "prompt": item.get("prompt", ""),
                "bpm": item.get("bpm", 85),
                "duration": duration,
                "format": "flac",
                "output": audio_path,
            }
        )
        log(f"  Audio: {audio_path}")

        log("  [2/4] Building Shorts-specific visual cover...")
        short_cover_path = build_short_cover(item, cover, short_cover_path)
        log(f"  Cover: {short_cover_path}")

        log("  [3/4] Rendering 9:16 YouTube Short...")
        video_path = render_vertical_short(audio_path, short_cover_path, video_path, duration)
        log(f"  Video: {video_path} ({Path(video_path).stat().st_size / 1_048_576:.0f} MB)")
        log("  [QA] Shorts container and media checks passed.")

        if preview_only:
            log("  [PREVIEW] Upload skipped. Review the preview and approve before live upload.")
            return {
                "success": True,
                "uploaded": False,
                "video_path": video_path,
                "cover_path": short_cover_path,
            }

        log("  [4/4] Uploading YouTube Short...")
        video = yt_upload.upload_video(
            video_path=video_path,
            title=title,
            description=shorts_description(item),
            tags=tags,
            category_id=meta.get("category_id", "10"),
            privacy=meta.get("privacy", "public"),
        )
        video_id = video.get("id")
        log(f"  Uploaded: https://www.youtube.com/watch?v={video_id}")
        return {"success": True, "uploaded": True, "video_id": video_id}
    except Exception as exc:
        log(f"  ERROR: {exc}")
        return {"success": False, "uploaded": False, "error": str(exc)}
    finally:
        for path in [audio_path]:
            try:
                if path and Path(path).exists():
                    os.remove(path)
            except Exception:
                pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and upload YouTube Shorts.")
    parser.add_argument("--id", default=None, help="Force a specific Shorts queue ID.")
    parser.add_argument("--status", action="store_true", help="Show Shorts queue status.")
    parser.add_argument("--dry-run", action="store_true", help="Do not mutate queue or upload.")
    parser.add_argument("--preview-only", action="store_true", help="Generate and QA a local preview, but do not upload.")
    parser.add_argument("--approve-preview", action="store_true", help="Approve the latest preview for a queue item.")
    args = parser.parse_args()

    queue = load_queue()
    if args.status:
        show_status(queue)
        return

    item = pick_next(queue, args.id)
    if not item:
        raise SystemExit("No matching Shorts queue item found.")

    if args.approve_preview:
        approve_preview(queue, item)
        print(f"Approved preview for {item['id']}: {item.get('preview_video')}")
        return

    meta = queue["_meta"]
    log(f"=== yt_shorts run - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} ===")
    if args.dry_run:
        run_item(item, meta, dry_run=True)
        log(f"=== Dry run complete: short {item['id']} left unchanged ===\n")
        return

    if args.preview_only:
        result = run_item(item, meta, dry_run=False, preview_only=True)
        if result.get("success"):
            item["preview_video"] = result.get("video_path")
            item["preview_cover"] = result.get("cover_path")
            item["preview_created"] = datetime.now(timezone.utc).isoformat()
            item["visual_approved"] = False
            item.pop("visual_approved_at", None)
            save_queue(queue)
            log(f"=== Preview ready: short {item['id']} left pending ===\n")
            return
        item["preview_error"] = result.get("error")
        save_queue(queue)
        log(f"=== PREVIEW FAILED: short {item['id']} left pending ===\n")
        raise SystemExit(1)

    if meta.get("require_visual_approval", True) and not item.get("visual_approved"):
        raise SystemExit(
            f"Short {item['id']} is not visually approved. Run --preview-only, review the video, "
            "then run --approve-preview before uploading."
        )

    mark_status(queue, item["id"], "generating")
    result = run_item(item, meta, dry_run=False)
    success = bool(result.get("success"))
    video_id = result.get("video_id")

    if success:
        mark_status(
            queue,
            item["id"],
            "uploaded",
            youtube_id=video_id,
            created=datetime.now(timezone.utc).isoformat(),
            visual_approved=False,
        )
        log(f"=== Done: short {item['id']} uploaded ===\n")
    else:
        mark_status(queue, item["id"], "failed")
        log(f"=== FAILED: short {item['id']} marked failed ===\n")
        raise SystemExit(1)


if __name__ == "__main__":
    main()

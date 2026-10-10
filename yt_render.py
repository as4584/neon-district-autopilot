"""
yt_render.py — Render audio + cover image → MP4 for YouTube upload.

Uses ffmpeg to combine:
  - An audio file (mp3/wav/flac) — any length
  - A static JPEG/PNG cover image
→ Output: MP4 at 1920x1080, suitable for YouTube long-form video

Usage:
    python3 yt_render.py --audio path/to/track.mp3 --image path/to/cover.jpg
    python3 yt_render.py --audio track.mp3 --image cover.jpg --output video.mp4

If --output is omitted, writes to test_outputs/video_<timestamp>.mp4
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

TEST_OUTPUTS = Path(__file__).parent / "test_outputs"
TEST_OUTPUTS.mkdir(exist_ok=True)

# YouTube recommended: 1920x1080, H.264, AAC 192kbps, 30fps still frame
VIDEO_W   = 1920
VIDEO_H   = 1080
VIDEO_FPS = 1        # 1 fps for static image — minimal file size, YouTube fine with this
VIDEO_CRF = 23       # H.264 quality (18=near-lossless, 28=low quality, 23=default good)
AUDIO_BR  = "192k"  # AAC bitrate


def get_audio_duration(audio_path: str) -> float:
    """Return audio duration in seconds using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            audio_path,
        ],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    import json
    info = json.loads(result.stdout)
    duration = float(info["format"]["duration"])
    return duration


def render(audio_path: str, image_path: str, output_path: str) -> str:
    """
    Combine static image + audio into MP4.

    ffmpeg strategy:
    - Loop the static image as video input
    - Encode audio as AAC
    - Shortest stream determines duration (= audio length)
    - Scale+pad image to 1920x1080 with black bars if needed
    """
    print(f"  Audio:  {audio_path}")
    print(f"  Image:  {image_path}")
    print(f"  Output: {output_path}")

    duration = get_audio_duration(audio_path)
    h = int(duration // 3600)
    m = int((duration % 3600) // 60)
    s = int(duration % 60)
    print(f"  Duration: {h:02d}:{m:02d}:{s:02d} ({duration:.1f}s)")

    # Scale image to 1920x1080, pad with black if aspect ratio differs
    vf = f"scale={VIDEO_W}:{VIDEO_H}:force_original_aspect_ratio=decrease,pad={VIDEO_W}:{VIDEO_H}:(ow-iw)/2:(oh-ih)/2:black"

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",                          # loop image
        "-framerate", str(VIDEO_FPS),
        "-i", image_path,                       # video input: static image
        "-i", audio_path,                       # audio input
        "-vf", vf,
        "-c:v", "libx264",
        "-crf", str(VIDEO_CRF),
        "-preset", "ultrafast",                 # fast encode; quality controlled by CRF
        "-tune", "stillimage",                  # optimize for static image
        "-c:a", "aac",
        "-b:a", AUDIO_BR,
        "-ar", "44100",
        "-ac", "2",                             # stereo
        "-pix_fmt", "yuv420p",                  # YouTube compatible
        "-shortest",                            # stop when audio ends
        "-movflags", "+faststart",              # web optimized (moov atom at front)
        output_path,
    ]

    print("\n  Encoding (this may take a while for long audio)...")
    t0 = time.time()

    proc = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.time() - t0

    if proc.returncode != 0:
        print("ffmpeg stderr:")
        print(proc.stderr[-2000:])  # last 2000 chars
        raise RuntimeError("ffmpeg failed — see stderr above")

    size_mb = os.path.getsize(output_path) / 1_048_576
    print(f"  ✅ Rendered in {elapsed:.1f}s → {size_mb:.1f} MB")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Render audio + image → MP4 for YouTube")
    parser.add_argument("--audio",  required=True, help="Path to audio file (mp3/wav/flac)")
    parser.add_argument("--image",  required=True, help="Path to cover image (jpg/png)")
    parser.add_argument("--output", default=None,  help="Output MP4 path (default: test_outputs/video_<ts>.mp4)")
    args = parser.parse_args()

    if not os.path.exists(args.audio):
        sys.exit(f"Audio file not found: {args.audio}")
    if not os.path.exists(args.image):
        sys.exit(f"Image file not found: {args.image}")

    if args.output:
        out = args.output
    else:
        ts = time.strftime("%Y%m%d_%H%M%S")
        out = str(TEST_OUTPUTS / f"video_{ts}.mp4")

    print("=== yt_render ===")
    render(args.audio, args.image, out)
    print(f"\nOutput: {out}")


if __name__ == "__main__":
    main()

"""
yt_stitch.py — Stitch multiple audio files into a single long-form MP3.

Used for the 021-040 queue: pre-generated 10-min FLAC masters stitched
6 at a time with crossfades instead of looping a single track.

Usage:
    python3 yt_stitch.py \
        --inputs a.flac b.flac c.flac d.flac e.flac f.flac \
        --output test_outputs/stitched.mp3 \
        --crossfade 4

    # Or call from Python:
    from yt_stitch import stitch
    output = stitch(
        inputs=["/path/to/a.flac", ...],
        output="/path/to/out.mp3",
        crossfade_sec=4,
    )
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def stitch(
    inputs: list[str],
    output: str,
    crossfade_sec: int = 4,
    bitrate: str = "192k",
) -> str:
    """
    Stitch N audio files with acrossfade transitions.

    Args:
        inputs: List of input audio file paths (FLAC, WAV, MP3, etc.)
        output: Output MP3 path
        crossfade_sec: Duration of crossfade between tracks in seconds
        bitrate: MP3 output bitrate

    Returns:
        Absolute path to output file.

    Raises:
        ValueError: If fewer than 2 inputs provided
        FileNotFoundError: If any input file is missing
        RuntimeError: If ffmpeg fails
    """
    if len(inputs) < 2:
        raise ValueError(f"Need at least 2 inputs, got {len(inputs)}")

    for f in inputs:
        if not os.path.exists(f):
            raise FileNotFoundError(f"Input not found: {f}")

    output = str(Path(output).resolve())
    Path(output).parent.mkdir(parents=True, exist_ok=True)

    n = len(inputs)
    print(f"  Stitching {n} tracks with {crossfade_sec}s crossfades...", flush=True)
    for i, f in enumerate(inputs, 1):
        print(f"  [{i}/{n}] {Path(f).name}", flush=True)

    # Build ffmpeg filter_complex for N-1 acrossfade operations
    # [0:a][1:a]acrossfade=d=4[a01]; [a01][2:a]acrossfade=d=4[a02]; ...
    filter_parts = []
    prev_label = "[0:a]"
    for i in range(1, n):
        label = f"[a{i:02d}]"
        filter_parts.append(f"{prev_label}[{i}:a]acrossfade=d={crossfade_sec}{label}")
        prev_label = label

    filter_complex = "; ".join(filter_parts)
    final_label = prev_label  # e.g. [a05] for 6 inputs

    cmd = ["ffmpeg", "-y"]
    for f in inputs:
        cmd += ["-i", f]
    cmd += [
        "-filter_complex", filter_complex,
        "-map", final_label,
        "-c:a", "libmp3lame",
        "-b:a", bitrate,
        "-ar", "44100",
        "-ac", "2",
        output,
    ]

    print(f"  Running ffmpeg...", flush=True)
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg stitch failed:\n{result.stderr[-1000:]}")

    size_mb = os.path.getsize(output) / 1_048_576
    print(f"  ✅ Stitched: {output} ({size_mb:.1f} MB)", flush=True)
    return output


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Stitch audio files with crossfades")
    parser.add_argument("--inputs",    nargs="+", required=True, help="Input audio files in order")
    parser.add_argument("--output",    required=True, help="Output MP3 path")
    parser.add_argument("--crossfade", type=int, default=4, help="Crossfade duration in seconds (default: 4)")
    parser.add_argument("--bitrate",   default="192k", help="MP3 bitrate (default: 192k)")
    args = parser.parse_args()

    print("=== yt_stitch ===")
    out = stitch(
        inputs=args.inputs,
        output=args.output,
        crossfade_sec=args.crossfade,
        bitrate=args.bitrate,
    )
    print(f"\nOutput: {out}")


if __name__ == "__main__":
    main()

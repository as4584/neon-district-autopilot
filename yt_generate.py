"""
yt_generate.py — Generate music via ACE-Step API and save to test_outputs/.

Calls the local ACE-Step engine at http://localhost:8001:
  1. POST /release_task  — submit generation job
  2. POST /query_result  — poll until done
  3. GET  /v1/audio      — download audio file

Usage:
    python3 yt_generate.py \
        --prompt "dark ambient, minimal, cinematic, atmospheric pads" \
        --bpm 75 \
        --duration 300 \
        --format flac \
        --output test_outputs/my_track.flac

    # Or generate from a queue item dict (used by yt_autopost.py):
    python3 -c "import yt_generate; yt_generate.generate({'prompt':..., 'bpm':75, 'duration':300})"
"""

import argparse
import os
import sys
import time
from pathlib import Path

import requests

ACESTEP_URL = "http://localhost:8001"
TEST_OUTPUTS = Path(__file__).parent / "test_outputs"
TEST_OUTPUTS.mkdir(exist_ok=True)

POLL_INTERVAL = 5    # seconds between status checks
MAX_WAIT = 3600      # 60 min max wait for generation
SUBMIT_TIMEOUT = int(os.environ.get("ACESTEP_SUBMIT_TIMEOUT", "900"))


# ── Status codes ──────────────────────────────────────────────────────────────
STATUS_RUNNING  = 0
STATUS_DONE     = 1
STATUS_ERROR    = 2


def check_engine():
    """Verify ACE-Step engine is up. Raises RuntimeError if not."""
    try:
        r = requests.get(f"{ACESTEP_URL}/docs", timeout=5)
        if r.status_code != 200:
            raise RuntimeError(f"ACE-Step engine returned {r.status_code}")
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            "ACE-Step engine not reachable at localhost:8001.\n"
            "Start it first:\n"
            "  cd ~/lab/audio-experiments/ace-step-ui\n"
            "  nohup bash -c \"cd ../ACE-Step-1.5 && uv run acestep-api --port 8001\" "
            "> logs/api.log 2>&1 &"
        )


def submit_job(prompt: str, bpm: int, duration: int, audio_format: str = "flac") -> str:
    """Submit a music generation job. Returns task_id."""
    payload = {
        "prompt":         prompt,
        "lyrics":         "",               # instrumental
        "bpm":            bpm,
        "audio_duration": float(duration),
        "audio_format":   audio_format,
        "task_type":      "text2music",
        "inference_steps": 4,
        "use_random_seed": True,
        "thinking":        False,
    }

    resp = requests.post(f"{ACESTEP_URL}/release_task", json=payload, timeout=SUBMIT_TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(f"Submit failed: {resp.status_code} {resp.text[:300]}")

    data = resp.json()
    task_id = data.get("data", {}).get("task_id") or data.get("task_id")
    if not task_id:
        raise RuntimeError(f"No task_id in response: {data}")

    return task_id


def poll_until_done(task_id: str, timeout: int = MAX_WAIT) -> dict:
    """
    Poll /query_result until status=done. Returns the result item dict.
    Status codes: 0=running, 1=done, 2=error
    """
    start = time.time()
    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            raise TimeoutError(f"Generation timed out after {timeout}s")

        try:
            resp = requests.post(
                f"{ACESTEP_URL}/query_result",
                json={"task_id_list": [task_id]},
                timeout=60,  # GPU may be busy; give it up to 60s to respond
            )
        except requests.exceptions.Timeout:
            print(f"  [poll] query_result timed out — GPU busy, retrying...", flush=True)
            time.sleep(POLL_INTERVAL)
            continue
        if resp.status_code != 200:
            print(f"  [poll] HTTP {resp.status_code} — retrying...", flush=True)
            time.sleep(POLL_INTERVAL)
            continue

        data = resp.json()
        items = data.get("data", [])
        if not items:
            time.sleep(POLL_INTERVAL)
            continue

        item = items[0]
        status = item.get("status", STATUS_RUNNING)
        progress = item.get("progress_text", "")

        if status == STATUS_DONE:
            import json
            result_raw = item.get("result", "[]")
            try:
                result_list = json.loads(result_raw)
                return result_list[0] if result_list else {}
            except Exception:
                return {}

        if status == STATUS_ERROR:
            raise RuntimeError(f"Generation failed: {item}")

        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        print(f"  [{mins:02d}:{secs:02d}] Generating... {progress}", end="\r", flush=True)
        time.sleep(POLL_INTERVAL)


def _decode_file_field(file_field: str) -> str:
    """
    ACE-Step returns file as a URL-encoded reference:
      /v1/audio?path=%2Froot%2Flab%2F...flac
    Decode it to get the actual local filesystem path.
    """
    from urllib.parse import unquote
    if "?path=" in file_field:
        return unquote(file_field.split("?path=", 1)[1])
    return file_field


def download_audio(file_path: str, output_path: str) -> str:
    """
    Retrieve generated audio from ACE-Step.
    file_path is the raw 'file' field from the result — may be a URL-encoded
    reference like /v1/audio?path=%2Froot%2F...
    Decodes it, then copies directly (fast local path) or falls back to HTTP.
    """
    import shutil

    actual_path = _decode_file_field(file_path)

    # Direct copy — fastest, works since engine is local
    if os.path.exists(actual_path):
        shutil.copy2(actual_path, output_path)
        size_mb = os.path.getsize(output_path) / 1_048_576
        print(f"  Audio saved: {output_path} ({size_mb:.1f} MB)")
        return output_path

    # HTTP fallback — use the decoded path so the server can find it
    resp = requests.get(
        f"{ACESTEP_URL}/v1/audio",
        params={"path": actual_path},
        timeout=120,
        stream=True,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Download failed: {resp.status_code} {resp.text[:300]}")

    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)

    size_mb = os.path.getsize(output_path) / 1_048_576
    print(f"  Audio saved: {output_path} ({size_mb:.1f} MB)")
    return output_path


def generate(spec: dict) -> str:
    """
    Full flow: submit → poll → download. Returns local audio file path.

    spec keys:
        prompt    (str)  — text description of desired music
        bpm       (int)  — beats per minute
        duration  (int)  — audio duration in seconds (e.g. 300 = 5 min)
        format    (str)  — "flac" | "mp3" | "wav" (default: flac)
        output    (str)  — output path (auto-generated if omitted)
    """
    prompt   = spec["prompt"]
    bpm      = int(spec.get("bpm", 80))
    duration = int(spec.get("duration", 300))
    fmt      = spec.get("format", "flac")
    output   = spec.get("output")

    if not output:
        ts = time.strftime("%Y%m%d_%H%M%S")
        output = str(TEST_OUTPUTS / f"track_{ts}.{fmt}")

    print(f"  Prompt:   {prompt[:70]}{'...' if len(prompt) > 70 else ''}", flush=True)
    print(f"  BPM:      {bpm}   Duration: {duration}s ({duration//60}m{duration%60}s)", flush=True)
    print(f"  Format:   {fmt}", flush=True)

    check_engine()

    print("  Submitting job to ACE-Step...", flush=True)
    task_id = submit_job(prompt, bpm, duration, fmt)
    print(f"  Task ID:  {task_id}", flush=True)

    print("  Waiting for generation...", flush=True)
    t0 = time.time()
    result = poll_until_done(task_id)
    elapsed = time.time() - t0
    print(f"\n  Done in {elapsed:.0f}s", flush=True)

    file_path = result.get("file", "")
    if not file_path:
        raise RuntimeError(f"No file path in result: {result}")

    print("  Downloading audio...", flush=True)
    download_audio(file_path, output)
    return output


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate music via ACE-Step")
    parser.add_argument("--prompt",   required=True)
    parser.add_argument("--bpm",      type=int, default=80)
    parser.add_argument("--duration", type=int, default=300, help="Seconds (default 300 = 5 min)")
    parser.add_argument("--format",   default="flac", choices=["flac", "mp3", "wav"])
    parser.add_argument("--output",   default=None)
    args = parser.parse_args()

    print("=== yt_generate ===")
    out = generate({
        "prompt":   args.prompt,
        "bpm":      args.bpm,
        "duration": args.duration,
        "format":   args.format,
        "output":   args.output,
    })
    print(f"\nOutput: {out}")


if __name__ == "__main__":
    main()

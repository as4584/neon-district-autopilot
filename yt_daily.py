"""Windows daily dispatch: local queue rotation, locking, and duplicate protection."""

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path

import yt_autopost

ROOT = Path(__file__).resolve().parent
TEMPLATES = [
    ("Chill Jazz / Rainy Nights", "Rainy Window Jazz", "jazz", 74,
     "mellow Rhodes piano, soft upright bass, brushed drums, muted saxophone, gentle rainfall, warm candlelit neon jazz lounge, instrumental, relaxed, no sudden changes"),
    ("Rest / Sleep", "Quiet Rain Sleep", "sleep", 48,
     "steady soft rainfall, deep warm pads, gentle piano fragments, peaceful neon bedroom window at night, no drums, no vocals, no sharp sounds, slow evolving ambient"),
    ("Chill Jazz / Rainy Nights", "Midnight Piano Lounge", "jazz", 70,
     "warm jazz piano, soft bass, gentle brushes, candlelit neon lounge, rainy windows, mellow late night atmosphere, instrumental, smooth dynamics"),
    ("Rest / Sleep", "Moonlit Rest", "sleep", 50,
     "soft rain on glass, low warm drones, quiet sustained piano, restful neon bedroom, moonlit window, no percussion, no vocals, no dramatic builds"),
]


def uploaded_today(queue, receipts=(), now=None):
    now = now or datetime.now().astimezone()
    for item in list(queue["queue"]) + list(receipts):
        if not item.get("youtube_id"):
            continue
        try:
            stamp = datetime.fromisoformat(item["created"]).astimezone(now.tzinfo)
        except (KeyError, TypeError, ValueError):
            continue
        if stamp.date() == now.date():
            return True
    return False


def refill(queue, minimum=7):
    count = sum(item.get("status") == "pending" for item in queue["queue"])
    sequence = queue["_meta"].get("daily_sequence", 0)
    ids = {item["id"] for item in queue["queue"]}
    while count < minimum:
        series, name, genre, bpm, prompt = TEMPLATES[sequence % len(TEMPLATES)]
        hours = (1, 6, 1, 12, 6, 1, 12)[sequence % 7]
        sequence += 1
        item_id = f"D{sequence:04d}"
        if item_id in ids:
            continue
        queue["queue"].append({
            "id": item_id, "status": "pending", "series": series, "genre": genre,
            "duration_hours": hours,
            "track_count": 4,
            "audio_model": "ace-step",
            "title": f"{hours} Hour{'s' if hours != 1 else ''} {name} | Music to Unwind - Session {sequence:03d}",
            "prompt": prompt, "bpm": bpm,
            "tags": [f"{hours} hour music", "relaxing music", "background music",
                     "rain music", "sleep music" if genre == "sleep" else "smooth jazz"],
            "created": None, "youtube_id": None,
        })
        ids.add(item_id)
        count += 1
    queue["_meta"]["daily_sequence"] = sequence
    return queue


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    outputs = ROOT / "test_outputs"
    outputs.mkdir(exist_ok=True)
    import msvcrt
    with (outputs / "daily.lock").open("a+b") as lock:
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            print("Daily uploader already running; no duplicate dispatch.")
            return 0
        try:
            queue = yt_autopost.load_queue()
            if any(item.get("status") == "generating" for item in queue["queue"]):
                print("An unfinished queue item needs reconciliation; upload blocked.")
                return 1
            receipts = [json.loads(path.read_text(encoding="utf-8"))
                        for path in outputs.glob("upload_receipt_*.json")]
            if not args.prepare_only and uploaded_today(queue, receipts):
                print("A video was already uploaded today; skipping duplicate.")
                return 0
            refill(queue)
            for item in queue["queue"]:
                if item.get("status") == "pending" and item.get("mode", "generate") == "generate":
                    item.setdefault("audio_model", "ace-step")
            yt_autopost.save_queue(queue)
            if args.prepare_only:
                print("Prepared seven pending chill/rest sessions; no upload.")
                return 0
            result = subprocess.run([
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(ROOT / "scripts" / "Run-Autopost.ps1"),
            ], cwd=ROOT)
            return result.returncode
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


if __name__ == "__main__":
    raise SystemExit(main())

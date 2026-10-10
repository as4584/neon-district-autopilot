"""Curated, bounded model staging and equal-age experiment reporting. No uploads."""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
REGISTRY = ROOT / "config" / "music_models.json"


def registry():
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def comparison_window(published_at, days=14, now=None):
    start = datetime.fromisoformat(published_at.replace("Z", "+00:00")).date()
    end = start + timedelta(days=days - 1)
    today = (now or datetime.now(timezone.utc)).date()
    # Leave three days for Analytics ingestion, and never compare partial windows.
    return (start, end) if today >= end + timedelta(days=3) else None


def summarize(records, policy):
    groups = {}
    for record in records:
        if record.get("period_views") is None or record.get("watch_minutes") is None:
            continue
        key = (record["model"], record["series"], record["duration_hours"])
        group = groups.setdefault(key, {"videos": 0, "views": 0, "watch_minutes": 0.0})
        group["videos"] += 1
        group["views"] += record["period_views"]
        group["watch_minutes"] += record["watch_minutes"]
    result = []
    for (model, series, hours), group in sorted(groups.items()):
        enough = (group["videos"] >= policy["minimum_videos_per_arm"] and
                  group["views"] >= policy["minimum_views_per_arm"])
        result.append({"model": model, "series": series, "duration_hours": hours,
                       **group, "minutes_per_view": round(group["watch_minutes"] / group["views"], 3)
                       if group["views"] else None,
                       "evidence": "eligible-for-review" if enough else "inconclusive"})
    return result


def stage_model(model, policy):
    """Download only pinned data files. Never execute code from a model repository."""
    if model["state"] != "staging":
        return {"model": model["id"], "state": model["state"]}
    python = ROOT / ".venv-images" / "Scripts" / "python.exe"
    if not python.is_file():
        raise RuntimeError("Model download environment unavailable")
    plans = []
    total = 0
    for spec in model["downloads"]:
        if not re.fullmatch(r"[a-f0-9]{40}", spec["revision"]):
            raise ValueError("Model revisions must be immutable commit hashes")
        response = requests.get(
            f"https://huggingface.co/api/models/{spec['repo']}/revision/{spec['revision']}",
            params={"blobs": "true"}, timeout=30)
        if response.status_code != 200:
            raise RuntimeError(f"Model metadata unavailable (HTTP {response.status_code})")
        metadata = response.json()
        if metadata.get("gated"):
            raise RuntimeError("Gated download requires separate human acceptance")
        files = [entry for entry in metadata["siblings"]
                 if Path(entry["rfilename"]).suffix in {".json", ".safetensors"}]
        if any(Path(entry["rfilename"]).is_absolute() or ".." in Path(entry["rfilename"]).parts
               for entry in files):
            raise ValueError("Unsafe model path")
        total += sum(entry["size"] for entry in files)
        plans.append((spec, files))
    if total > policy["max_download_gib"] * 2**30:
        raise RuntimeError("Model exceeds the configured download budget")
    if shutil.disk_usage(ROOT).free < total + policy["min_free_disk_gib"] * 2**30:
        raise RuntimeError("Insufficient reserved free disk space")
    from yt_local_image import worker_environment
    env = worker_environment()
    env.pop("HF_HUB_OFFLINE", None)
    env.pop("TRANSFORMERS_OFFLINE", None)
    destination = ROOT / "models" / model["id"]
    for spec, files in plans:
        target = destination / spec["folder"]
        command = [str(python), "-m", "huggingface_hub.cli.hf", "download", spec["repo"],
                   *[entry["rfilename"] for entry in files], "--revision", spec["revision"],
                   "--local-dir", str(target)]
        completed = subprocess.run(command, env=env, capture_output=True, timeout=10800)
        if completed.returncode:
            raise RuntimeError("Pinned model download failed; resume next maintenance run")
        for entry in files:
            path = target / entry["rfilename"]
            if not path.is_file() or path.stat().st_size != entry["size"]:
                raise RuntimeError("Downloaded file size validation failed")
            expected = entry.get("lfs", {}).get("sha256")
            if expected:
                with path.open("rb") as handle:
                    actual = hashlib.file_digest(handle, "sha256").hexdigest()
                if actual != expected:
                    raise RuntimeError("Downloaded weights failed SHA256 validation")
    result = {"model": model["id"], "state": "downloaded-awaiting-runtime-review",
              "bytes": total, "revisions": [spec["revision"] for spec, _ in plans]}
    (destination / "installation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def report(refresh=False):
    config = registry()
    states = {}
    for model in config["models"]:
        marker = ROOT / "models" / model["id"] / "installation.json"
        state = model["state"]
        if marker.is_file() and state == "staging":
            installed = json.loads(marker.read_text(encoding="utf-8"))
            if installed.get("state") == "downloaded-awaiting-runtime-review":
                state = installed["state"]
        states[model["id"]] = state
    queue = json.loads((ROOT / "yt_queue.json").read_text(encoding="utf-8"))
    records = []
    if refresh:
        import yt_analytics
        token = yt_analytics.get_access_token()
        channel = yt_analytics.get_channel_id(token)
        if channel != "UCWO8s_ObXOM5f_9YocsTvuQ":
            raise RuntimeError("Analytics channel does not match the configured channel")
        for item in queue["queue"]:
            if item.get("status") != "uploaded" or not item.get("audio_model"):
                continue
            stats = yt_analytics.get_video_stats(token, item["youtube_id"])
            if not stats or stats["privacy"] != "public":
                continue
            window = comparison_window(stats["published_at"], config["policy"]["comparison_days"])
            if not window:
                continue
            metrics = yt_analytics.get_video_analytics(token, channel, item["youtube_id"],
                                                       start_date=window[0], end_date=window[1])
            records.append({"model": item["audio_model"], "series": item.get("series", "legacy"),
                            "duration_hours": item.get("duration_hours", 1),
                            "period_views": metrics.get("views"),
                            "watch_minutes": metrics.get("estimatedMinutesWatched")})
    payload = {"schema_version": 1, "checked_at": datetime.now(timezone.utc).isoformat(),
               "window_days": config["policy"]["comparison_days"],
               "models": [{"id": model["id"], "state": states[model["id"]],
                            "blocker": model.get("blocker")} for model in config["models"]],
               "cohorts": summarize(records, config["policy"]),
               "decision": "No automatic promotion; insufficient evidence unless noted per cohort."}
    folder = ROOT / "reports" / "public"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "experiments.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("Sanitized experiment report saved; no uploads or production queue changes.")
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    failures = 0
    if args.stage:
        config = registry()
        for model in config["models"]:
            try:
                result = stage_model(model, config["policy"])
                print(f"{model['id']}: {result['state']}")
            except Exception as exc:
                failures += 1
                print(f"{model['id']}: staging blocked ({type(exc).__name__}); baseline unchanged")
    report(args.refresh)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

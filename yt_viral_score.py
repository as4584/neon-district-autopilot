"""Compute viral scores for Neon District Archive uploads.

The score is intentionally simple and explainable. It reads metrics already
stored in yt_queue.json by yt_analytics.py, writes a per-item viral_score block,
and reports which styles should be repeated.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).parent
QUEUE_FILE = BASE_DIR / "yt_queue.json"
REPORT_FILE = BASE_DIR / "test_outputs" / "viral_score_report.json"


GENRE_KEYWORDS = {
    "dark_ambient": ["dark ambient", "drone", "cinematic", "atmospheric tension"],
    "lofi": ["lofi", "lo-fi", "vinyl", "hip hop", "study beats"],
    # "neon" is the channel's visual identity, not evidence of synthwave.
    "synthwave": ["synthwave", "chillwave", "retrowave", "retro", "night drive"],
    # Piano is its own feature; it should not make rain/piano tracks jazz.
    "jazz": ["jazz", "saxophone", "double bass", "upright bass", "noir"],
    "meditation": ["meditation", "healing", "mindfulness", "singing bowls"],
    "rain_ambient": ["rain", "rainfall", "rain sounds", "thunder"],
    "electronic": ["electronic", "techno", "electronica", "glitch", "modular"],
    "piano": ["piano", "rhodes"],
    "space": ["space", "interstellar", "cosmic", "nebula"],
}


def load_queue() -> dict:
    return json.loads(QUEUE_FILE.read_text(encoding="utf-8"))


def save_queue(queue: dict) -> None:
    QUEUE_FILE.write_text(json.dumps(queue, indent=2), encoding="utf-8")


def parse_percent(value, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value) / 100 if value > 1 else float(value)
    if isinstance(value, str):
        value = value.strip().replace("%", "")
        try:
            return float(value) / 100
        except ValueError:
            return default
    return default


def parse_minutes(value, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        value = value.strip().lower().replace("m", "")
        try:
            return float(value)
        except ValueError:
            return default
    return default


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def contains_keyword(text: str, keyword: str) -> bool:
    """Match a metadata term without accidental substring matches."""
    return re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text) is not None


def detect_features(item: dict) -> dict:
    text = " ".join(
        [
            item.get("title", ""),
            item.get("prompt", ""),
            " ".join(item.get("tags", [])),
        ]
    ).lower()
    genres = []
    for genre, keywords in GENRE_KEYWORDS.items():
        if any(contains_keyword(text, keyword) for keyword in keywords):
            genres.append(genre)
    if not genres:
        genres.append("uncategorized")

    bpm = item.get("bpm")
    if bpm is None:
        bpm_bucket = "unknown_bpm"
    elif bpm < 75:
        bpm_bucket = "slow"
    elif bpm <= 95:
        bpm_bucket = "mid"
    else:
        bpm_bucket = "fast"

    title = item.get("title", "").lower()
    use_cases = []
    for use_case in ["study", "work", "focus", "sleep", "coding", "relax"]:
        if use_case in title or use_case in text:
            use_cases.append(use_case)

    return {
        "genres": genres,
        "bpm_bucket": bpm_bucket,
        "use_cases": use_cases or ["general"],
        "has_1_hour_title": "1 hour" in title,
    }


def score_item(item: dict) -> dict:
    analytics = item.get("analytics", {})
    if not analytics:
        return {
            "score": None,
            "grade": "UNSCORED",
            "reason": "needs analytics",
            "features": detect_features(item),
            "scored_at": datetime.now(timezone.utc).isoformat(),
        }

    views = int(analytics.get("views", 0) or 0)
    likes = int(analytics.get("likes", 0) or 0)
    ctr = parse_percent(analytics.get("ctr_pct", 0))
    avg_watch_min = parse_minutes(analytics.get("avg_duration_min", 0))

    # The weights favor early signal, not vanity totals alone.
    views_component = clamp(math.log10(max(views, 1)) / 4.0) * 25
    ctr_component = clamp(ctr / 0.08) * 30
    retention_component = clamp(avg_watch_min / 20.0) * 30
    engagement_component = clamp((likes / max(views, 1)) / 0.05) * 15

    score = round(
        views_component + ctr_component + retention_component + engagement_component
    )
    grade = "S" if score >= 90 else "A" if score >= 75 else "B" if score >= 60 else "C" if score >= 40 else "D"
    missing = [key for key in ("ctr_pct", "avg_duration_min") if analytics.get(key) is None]
    if missing:
        grade = "PARTIAL"

    return {
        "score": int(score),
        "grade": grade,
        "views": views,
        "ctr_pct": round(ctr * 100, 2) if "ctr_pct" not in missing else None,
        "avg_watch_min": round(avg_watch_min, 2) if "avg_duration_min" not in missing else None,
        "missing_metrics": missing,
        "reason": "incomplete metrics; score is a lower bound" if missing else None,
        "like_rate_pct": round((likes / max(views, 1)) * 100, 2),
        "features": detect_features(item),
        "scored_at": datetime.now(timezone.utc).isoformat(),
    }


def uploaded_items(queue: dict) -> list[dict]:
    return [
        item
        for item in queue.get("queue", [])
        if item.get("status") == "uploaded" and item.get("youtube_id")
    ]


def summarize(items: list[dict]) -> dict:
    by_feature = defaultdict(list)
    for item in items:
        viral = item.get("viral_score", {})
        score = viral.get("score")
        if score is None:
            continue
        features = viral.get("features", {})
        for genre in features.get("genres", ["uncategorized"]):
            by_feature[f"genre:{genre}"].append(score)
        by_feature[f"bpm:{features.get('bpm_bucket', 'unknown')}"].append(score)
        for use_case in features.get("use_cases", ["general"]):
            by_feature[f"use:{use_case}"].append(score)

    ranked = []
    for name, scores in by_feature.items():
        ranked.append(
            {
                "feature": name,
                "avg_score": round(sum(scores) / len(scores), 1),
                "samples": len(scores),
            }
        )
    ranked.sort(key=lambda row: (row["avg_score"], row["samples"]), reverse=True)
    return {"feature_rankings": ranked}


def recommend_pending(queue: dict, feature_rankings: list[dict]) -> list[dict]:
    weights = {row["feature"]: row["avg_score"] for row in feature_rankings}
    recs = []
    for item in queue.get("queue", []):
        if item.get("status") != "pending":
            continue
        features = detect_features(item)
        keys = [f"genre:{g}" for g in features["genres"]]
        keys.append(f"bpm:{features['bpm_bucket']}")
        keys.extend(f"use:{u}" for u in features["use_cases"])
        known_scores = [weights[k] for k in keys if k in weights]
        predicted = round(sum(known_scores) / len(known_scores), 1) if known_scores else 50.0
        recs.append(
            {
                "id": item["id"],
                "title": item["title"],
                "predicted_viral_score": predicted,
                "detected_features": features,
                "matched_features": [k for k in keys if k in weights],
            }
        )
    recs.sort(key=lambda row: row["predicted_viral_score"], reverse=True)
    return recs


def run(update: bool = True, write_report: bool = True) -> dict:
    queue = load_queue()
    items = uploaded_items(queue)
    for item in items:
        item["viral_score"] = score_item(item)

    summary = summarize(items)
    recommendations = recommend_pending(queue, summary["feature_rankings"])
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "uploaded_scored": len(items),
        "top_uploaded": sorted(
            [
                {
                    "id": item["id"],
                    "title": item["title"],
                    "youtube_id": item.get("youtube_id"),
                    **item.get("viral_score", {}),
                }
                for item in items
            ],
            key=lambda row: row.get("score") or -1,
            reverse=True,
        ),
        **summary,
        "recommended_pending": recommendations[:10],
    }

    if update:
        save_queue(queue)
    if write_report:
        REPORT_FILE.parent.mkdir(exist_ok=True)
        REPORT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def print_report(report: dict) -> None:
    print("=== Neon District Viral Score ===")
    print(f"Uploaded videos scored: {report['uploaded_scored']}")
    print()
    print("Top uploaded:")
    for row in report["top_uploaded"][:8]:
        score = row.get("score")
        if score is None:
            print(f"  UNSCORED [{row['id']}] {row['title'][:64]} - needs analytics")
        else:
            print(f"  {row['grade']} {score:>3}/100 [{row['id']}] {row['title'][:64]}")
    print()
    print("Winning features:")
    if report["feature_rankings"]:
        for row in report["feature_rankings"][:8]:
            print(f"  {row['avg_score']:>5} avg ({row['samples']}x) {row['feature']}")
    else:
        print("  No scored analytics yet. Run analytics after videos have data.")
    print()
    print("Recommended pending:")
    for row in report["recommended_pending"][:8]:
        print(
            f"  {row['predicted_viral_score']:>5} predicted [{row['id']}] {row['title'][:64]}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute Neon District viral scores.")
    parser.add_argument("--no-update", action="store_true", help="Do not write scores to queue.")
    parser.add_argument("--no-report", action="store_true", help="Do not write JSON report.")
    parser.add_argument("--json", action="store_true", help="Print full report JSON.")
    args = parser.parse_args()

    report = run(update=not args.no_update, write_report=not args.no_report)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)


if __name__ == "__main__":
    main()

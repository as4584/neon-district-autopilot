"""
yt_analytics.py — Pull YouTube Analytics for uploaded Neon District Archive videos.

Uses YouTube Analytics API v2 to fetch:
  - Views, watch time, impressions, CTR, average view duration
  - Traffic sources breakdown
  - Performance score per video

Reads from yt_queue.json to find uploaded videos, writes analytics back.

Usage:
    doppler run --project agentop --config prd -- python3 yt_analytics.py
    doppler run --project agentop --config prd -- python3 yt_analytics.py --video VIDEO_ID
    doppler run --project agentop --config prd -- python3 yt_analytics.py --report
"""

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

BASE_DIR    = Path(__file__).parent
QUEUE_FILE  = BASE_DIR / "yt_queue.json"
TOKEN_URL   = "https://oauth2.googleapis.com/token"
YT_API_URL  = "https://www.googleapis.com/youtube/v3"
ANALYTICS_URL = "https://youtubeanalytics.googleapis.com/v2/reports"


# ── Credentials ───────────────────────────────────────────────────────────────

def _creds():
    return (
        os.environ["YOUTUBE_CLIENT_ID"],
        os.environ["YOUTUBE_CLIENT_SECRET"],
        os.environ["YOUTUBE_REFRESH_TOKEN"],
    )


def get_access_token() -> str:
    client_id, client_secret, refresh_token = _creds()
    resp = requests.post(TOKEN_URL, data={
        "client_id":     client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type":    "refresh_token",
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]


# ── Queue helpers ─────────────────────────────────────────────────────────────

def load_queue() -> dict:
    with open(QUEUE_FILE) as f:
        return json.load(f)


def save_queue(q: dict):
    with open(QUEUE_FILE, "w") as f:
        json.dump(q, f, indent=2)


def get_uploaded_videos(q: dict) -> list[dict]:
    return [item for item in q["queue"] if item.get("status") == "uploaded" and item.get("youtube_id")]


# ── YouTube Data API — video stats ────────────────────────────────────────────

def get_video_stats(access_token: str, video_id: str) -> dict:
    """Pull title, view count, like count, comment count from Data API."""
    resp = requests.get(
        f"{YT_API_URL}/videos",
        params={
            "part":        "snippet,statistics,contentDetails,status",
            "id":          video_id,
        },
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    resp.raise_for_status()
    items = resp.json().get("items", [])
    if not items:
        return {}
    item = items[0]
    stats = item.get("statistics", {})
    return {
        "title":          item["snippet"]["title"],
        "published_at":   item["snippet"]["publishedAt"],
        "privacy":        item.get("status", {}).get("privacyStatus", "unknown"),
        "duration":       item["contentDetails"]["duration"],
        "views":          int(stats.get("viewCount", 0)),
        "likes":          int(stats.get("likeCount", 0)),
        "comments":       int(stats.get("commentCount", 0)),
    }


# ── YouTube Analytics API ─────────────────────────────────────────────────────

def get_channel_id(access_token: str) -> str:
    resp = requests.get(
        f"{YT_API_URL}/channels",
        params={"part": "id", "mine": "true"},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    resp.raise_for_status()
    items = resp.json().get("items", [])
    if not items:
        raise RuntimeError("No channel found for this account")
    return items[0]["id"]


def get_video_analytics(access_token: str, channel_id: str, video_id: str, days: int = 28,
                        start_date=None, end_date=None) -> dict:
    """
    Pull Analytics API metrics for a specific video over the last N days.
    Returns views, estimatedMinutesWatched, averageViewDuration, impressions, CTR.
    """
    end = end_date or datetime.now(timezone.utc).date()
    start = start_date or end - timedelta(days=days)
    if start > end:
        raise ValueError("Analytics start date must not follow end date")

    resp = requests.get(
        ANALYTICS_URL,
        params={
            "ids":         f"channel=={channel_id}",
            "startDate":   start.isoformat(),
            "endDate":     end.isoformat(),
            "metrics":     "views,estimatedMinutesWatched,averageViewDuration",
            "filters":     f"video=={video_id}",
        },
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )

    if resp.status_code in (400, 403):
        # Keep Data API stats usable if Analytics API rejects this query.
        return {"analytics_error": f"Analytics API not available ({resp.status_code})"}

    resp.raise_for_status()
    data = resp.json()
    rows = data.get("rows", [])
    if not rows:
        return {"analytics_note": "No data yet (video too new or no views)"}

    row = rows[0]
    headers = [h["name"] for h in data["columnHeaders"]]
    return dict(zip(headers, row))


# ── Performance score ─────────────────────────────────────────────────────────

def score_video(stats: dict, analytics: dict) -> dict:
    """
    Simple performance score 0-100 based on CTR and watch time.
    Grade: A (80+), B (60+), C (40+), D (<40)
    """
    score = 0
    details = {}

    views = stats.get("views", 0)
    ctr   = analytics.get("impressionClickThroughRate")
    avg_duration = analytics.get("averageViewDuration")

    # Views (30 pts)
    if views >= 1000:  score += 30
    elif views >= 500: score += 20
    elif views >= 100: score += 10
    elif views >= 10:  score += 5
    details["views"] = views

    # CTR (40 pts) — good CTR for music is 3-7%
    if ctr is None:   pass
    elif ctr >= 0.07: score += 40
    elif ctr >= 0.05: score += 30
    elif ctr >= 0.03: score += 20
    elif ctr >= 0.01: score += 10
    details["ctr_pct"] = f"{ctr*100:.1f}%" if ctr is not None else None

    # Avg view duration (30 pts) — for 1hr music, even 10min is good
    if avg_duration is None:   pass
    elif avg_duration >= 1800: score += 30   # 30+ min
    elif avg_duration >= 600:  score += 20   # 10+ min
    elif avg_duration >= 120:  score += 10   # 2+ min
    details["avg_duration_min"] = f"{avg_duration/60:.1f}m" if avg_duration is not None else None

    grade = "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D"
    if ctr is None or avg_duration is None:
        grade = "PARTIAL"
    return {"score": score, "grade": grade, **details}


# ── Main analytics run ────────────────────────────────────────────────────────

def run_analytics(video_id: str = None, report: bool = False, days: int = 28):
    print("=== Neon District Archive — Analytics ===\n")

    access_token = get_access_token()
    print(f"  Token obtained.")

    channel_id = get_channel_id(access_token)
    print(f"  Channel ID: {channel_id}\n")

    q = load_queue()
    uploaded = get_uploaded_videos(q)

    if video_id:
        uploaded = [v for v in uploaded if v["youtube_id"] == video_id]
        if not uploaded:
            print(f"  Video {video_id} not found in queue (or not yet uploaded).")
            return

    if not uploaded:
        print("  No uploaded videos found in queue.")
        return

    results = []
    for item in uploaded:
        vid = item["youtube_id"]
        print(f"  Checking {item['id']}: {item['title'][:50]}...")
        print(f"    https://youtu.be/{vid}")

        try:
            stats     = get_video_stats(access_token, vid)
            if not stats:
                print("    Video unavailable; existing analytics left unchanged.")
                continue
            analytics = get_video_analytics(access_token, channel_id, vid, days=days)
            perf      = score_video(stats, analytics)

            print(f"    Views: {stats.get('views', 'WARNING:')}  |  "
                  f"CTR: {perf.get('ctr_pct') or 'unavailable'}  |  "
                  f"Avg watch: {perf.get('avg_duration_min') or 'unavailable'}  |  "
                  f"Score: {perf['score']}/100 ({perf['grade']})")

            # Write analytics back to queue item
            item["analytics"] = {
                "last_checked": datetime.now(timezone.utc).isoformat(),
                "views":        stats.get("views", 0),
                "likes":        stats.get("likes", 0),
                "privacy":      stats["privacy"],
                "ctr_pct":      perf["ctr_pct"],
                "avg_duration_min": perf["avg_duration_min"],
                "analytics_error": analytics.get("analytics_error"),
                "analytics_note": analytics.get("analytics_note"),
                "period_days": days,
                "period_views": analytics.get("views"),
                "estimated_minutes_watched": analytics.get("estimatedMinutesWatched"),
                "score":        perf["score"],
                "grade":        perf["grade"],
            }
            results.append({"id": item["id"], "vid": vid, **perf, "views": stats.get("views", 0)})

        except requests.RequestException as e:
            status = e.response.status_code if e.response is not None else "network"
            print(f"    ERROR: YouTube request failed ({status}); existing analytics left unchanged.")

        print()

    save_queue(q)
    print("  Analytics saved to yt_queue.json.")

    if report and results:
        print("\n=== Performance Report ===")
        results.sort(key=lambda x: x["views"], reverse=True)
        for r in results:
            print(f"  [{r['grade']}] {r['id']} ({r['vid']}) — "
                  f"{r['views']} views, score {r['score']}/100")
        top = results[0]
        print(f"\n  Most lifetime views: {top['id']}. This is not an equal-age comparison.")
        print("  PARTIAL scores are incomplete; missing metrics are not zero.")
        print("  Thumbnail impressions and CTR must be reviewed in YouTube Studio.")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YouTube Analytics for Neon District Archive")
    parser.add_argument("--video",  default=None, help="Check a specific video ID")
    parser.add_argument("--report", action="store_true", help="Print summary performance report")
    parser.add_argument("--days", type=int, default=28, help="Analytics window in days (default: 28)")
    args = parser.parse_args()
    if args.days < 1:
        parser.error("--days must be positive")
    run_analytics(video_id=args.video, report=args.report, days=args.days)

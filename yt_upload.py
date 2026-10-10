"""
yt_upload.py — Upload an MP4 to YouTube using OAuth 2.0 (refresh token flow).

Uses the stored YOUTUBE_REFRESH_TOKEN from Doppler — no browser needed after yt_auth.py runs.

Usage:
    doppler run --project agentop -- python3 yt_upload.py \
        --video path/to/video.mp4 \
        --title "Relaxing Jazz — 3 Hours" \
        --description "Background music for work and study." \
        --tags "jazz,lofi,relaxing,background music" \
        --category 10 \
        --privacy unlisted

YouTube category IDs (common):
    10 = Music
    22 = People & Blogs
    27 = Education
    28 = Science & Technology

Privacy: public | private | unlisted
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
import isodate
sys.path.insert(0, str(Path(__file__).parent / "scripts"))
try:
    import doppler_env
except Exception:
    doppler_env = None

# ── Credentials (loaded lazily so --status/--dry-run don't need doppler) ─────

TOKEN_URL  = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"


def verify_uploaded_video(video_id, privacy, target_seconds, timeout=3600):
    """Wait for processing and validate read-back; never retry uploads here."""
    token = get_access_token()
    deadline = time.monotonic() + timeout
    while True:
        try:
            response = requests.get('https://www.googleapis.com/youtube/v3/videos',
                                    params={'part': 'snippet,status,contentDetails,processingDetails', 'id': video_id},
                                    headers={'Authorization': f'Bearer {token}'}, timeout=30)
        except requests.RequestException:
            raise RuntimeError('Processing read-back network failure; reconcile the accepted upload') from None
        if response.status_code != 200:
            raise RuntimeError(f'Processing read-back failed (HTTP {response.status_code}); upload already accepted')
        videos = response.json().get('items', [])
        if videos:
            video = videos[0]
            if video['snippet']['channelId'] != 'UCWO8s_ObXOM5f_9YocsTvuQ':
                raise RuntimeError('Uploaded video channel mismatch')
            status = video['status']
            if status.get('privacyStatus') != privacy:
                raise RuntimeError('Uploaded video visibility does not match requested privacy')
            processing = video.get('processingDetails', {}).get('processingStatus')
            if processing in ('failed', 'terminated') or status.get('uploadStatus') in ('failed', 'rejected', 'deleted'):
                raise RuntimeError('YouTube processing failed or rejected the accepted upload; do not reupload blindly')
            if processing == 'succeeded' or status.get('uploadStatus') == 'processed':
                try:
                    seconds = isodate.parse_duration(video['contentDetails']['duration']).total_seconds()
                except Exception:
                    raise RuntimeError('Processed video duration could not be validated') from None
                if not 0 < seconds <= 43200 or abs(seconds - target_seconds) > 2:
                    raise RuntimeError('Processed video duration does not match the accepted render')
                return {'youtube_id': video_id, 'privacy': privacy, 'duration_seconds': seconds,
                        'processing': 'succeeded', 'channel_verified': True}
        if time.monotonic() >= deadline:
            raise RuntimeError('YouTube processing is still pending; reconcile the accepted upload, do not reupload')
        time.sleep(30)

def _creds():
    return (
        os.environ["YOUTUBE_CLIENT_ID"],
        os.environ["YOUTUBE_CLIENT_SECRET"],
        os.environ["YOUTUBE_REFRESH_TOKEN"],
    )

# ── Resumable upload chunk size ───────────────────────────────────────────────
# Google recommends multiples of 256KB; 8MB is a good balance
CHUNK_SIZE = 8 * 1024 * 1024   # 8 MB


# ── Token management ──────────────────────────────────────────────────────────

def get_access_token() -> str:
    """
    Exchange refresh token for a fresh access token.
    If Google rotates the refresh token (returns a new one), save it back to
    Doppler immediately so the next run still works.
    """
    CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN = _creds()
    resp = requests.post(TOKEN_URL, data={
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "grant_type":    "refresh_token",
    }, timeout=15)

    if resp.status_code != 200:
        raise RuntimeError(f"Token refresh failed (HTTP {resp.status_code})")

    data = resp.json()
    access_token = data.get("access_token")
    if not access_token:
        raise RuntimeError("Token response did not contain an access token")

    expires_in = data.get("expires_in", "WARNING")
    print(f"  Access token obtained (expires in {expires_in}s)")

    # If Google rotated the refresh token, save the new one to Doppler
    new_refresh = data.get("refresh_token")
    if new_refresh and new_refresh != REFRESH_TOKEN:
        print("  Refresh token rotated - saving new token to Doppler...")
        try:
            if doppler_env is None:
                raise RuntimeError("doppler_env helper is unavailable")
            doppler_env.set_secret("YOUTUBE_REFRESH_TOKEN", new_refresh)
            print("  New refresh token saved to Doppler.")
            os.environ["YOUTUBE_REFRESH_TOKEN"] = new_refresh
        except Exception as e:
            print(f"  WARNING: Could not save new refresh token ({type(e).__name__})")

    return access_token


# ── Resumable upload ──────────────────────────────────────────────────────────

def initiate_resumable_upload(access_token: str, metadata: dict, file_size: int) -> str:
    """
    Step 1 of resumable upload: POST metadata, get upload URI.
    Returns the session upload URI.
    """
    resp = requests.post(
        UPLOAD_URL,
        params={"uploadType": "resumable", "part": "snippet,status"},
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(file_size),
        },
        data=json.dumps(metadata),
        timeout=30,
    )

    if resp.status_code != 200:
        raise RuntimeError(f"Initiate upload failed (HTTP {resp.status_code})")

    upload_uri = resp.headers.get("Location")
    if not upload_uri:
        raise RuntimeError("No Location header in initiate response")

    return upload_uri


def query_upload_offset(upload_uri: str, file_size: int) -> int:
    """
    Ask YouTube how many bytes it has received so far.
    Used to resume after a timeout. Returns the byte offset to resume from.
    """
    resp = requests.put(
        upload_uri,
        headers={
            "Content-Range": f"bytes */{file_size}",
            "Content-Type": "video/mp4",
            "Content-Length": "0",
        },
        data=b"",
        timeout=30,
    )
    if resp.status_code == 308:
        # Range header like "bytes=0-12582911" tells us what was received
        range_hdr = resp.headers.get("Range", "")
        if range_hdr:
            return int(range_hdr.split("-")[1]) + 1
        return 0  # Nothing received yet
    if resp.status_code in (200, 201):
        return file_size  # Already complete
    raise RuntimeError(f"Resume query failed (HTTP {resp.status_code})")


def upload_file(upload_uri: str, video_path: str) -> dict:
    """
    Step 2 of resumable upload: PUT file in chunks with chunk-level retry.
    On timeout, queries server for actual offset and resumes from there.
    Returns the video resource dict on completion.
    """
    file_size = os.path.getsize(video_path)
    uploaded = 0
    t0 = time.time()
    MAX_CHUNK_RETRIES = 5

    with open(video_path, "rb") as f:
        while uploaded < file_size:
            f.seek(uploaded)
            chunk = f.read(CHUNK_SIZE)
            chunk_end = uploaded + len(chunk) - 1

            # Attempt chunk with retries on timeout/connection error
            resp = None
            for attempt in range(MAX_CHUNK_RETRIES):
                try:
                    resp = requests.put(
                        upload_uri,
                        headers={
                            "Content-Range": f"bytes {uploaded}-{chunk_end}/{file_size}",
                            "Content-Type": "video/mp4",
                        },
                        data=chunk,
                        timeout=(30, 900),  # 30s connect, 15min read (slow connections)
                    )
                    break  # success
                except (requests.exceptions.Timeout,
                        requests.exceptions.ConnectionError) as e:
                    wait = 15 * (attempt + 1)
                    print(f"\n  [retry {attempt+1}/{MAX_CHUNK_RETRIES}] chunk at {uploaded/1_048_576:.0f}MB timed out ({e.__class__.__name__}), querying server offset in {wait}s...", flush=True)
                    time.sleep(wait)
                    try:
                        # Ask YouTube what it actually received
                        server_offset = query_upload_offset(upload_uri, file_size)
                        if server_offset > uploaded:
                            print(f"  Server has {server_offset/1_048_576:.0f}MB - resuming from there", flush=True)
                            uploaded = server_offset
                            f.seek(uploaded)
                            chunk = f.read(CHUNK_SIZE)
                            chunk_end = uploaded + len(chunk) - 1
                    except Exception as qe:
                        print(f"  [resume query failed: {type(qe).__name__}] retrying chunk from {uploaded/1_048_576:.0f}MB", flush=True)
                    if attempt == MAX_CHUNK_RETRIES - 1:
                        raise RuntimeError(f"Chunk failed after {MAX_CHUNK_RETRIES} attempts at offset {uploaded}")

            if resp is None:
                raise RuntimeError("No response after retries")

            # 308 = Resume Incomplete (more chunks needed)
            # 200/201 = Done
            if resp.status_code in (200, 201):
                elapsed = time.time() - t0
                print(f"\n  Upload complete in {elapsed:.1f}s")
                return resp.json()
            elif resp.status_code == 308:
                uploaded = chunk_end + 1
                elapsed = time.time() - t0
                pct = uploaded / file_size * 100
                speed_mbps = (uploaded / elapsed) / 1_048_576 if elapsed > 0 else 0
                print(f"  Uploaded {uploaded / 1_048_576:.1f} MB / {file_size / 1_048_576:.1f} MB ({pct:.1f}%) @ {speed_mbps:.1f} MB/s", end="\r")
            else:
                raise RuntimeError(f"Upload chunk failed (HTTP {resp.status_code})")

    raise RuntimeError("Upload loop ended without completion response")


def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: list,
    category_id: str = "10",
    privacy: str = "unlisted",
) -> dict:
    """Full upload flow: refresh token → initiate → upload → return video resource."""

    video_path = str(Path(video_path).resolve())
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    file_size = os.path.getsize(video_path)
    print(f"  File: {video_path}")
    print(f"  Size: {file_size / 1_048_576:.1f} MB")

    # Step 1: Get fresh access token
    print("  Refreshing access token...")
    access_token = get_access_token()
    channel_response = requests.get(
        'https://www.googleapis.com/youtube/v3/channels',
        params={'part': 'id', 'mine': 'true'},
        headers={'Authorization': f'Bearer {access_token}'}, timeout=30,
    )
    if not channel_response.ok:
        raise RuntimeError(f'Channel verification failed (HTTP {channel_response.status_code})')
    channels = channel_response.json().get('items', [])
    if len(channels) != 1 or channels[0]['id'] != 'UCWO8s_ObXOM5f_9YocsTvuQ':
        raise RuntimeError('Channel identity mismatch; upload blocked')

    # Step 2: Build video metadata
    metadata = {
        "snippet": {
            "title":       title,
            "description": description,
            "tags":        tags,
            "categoryId":  category_id,
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,
        }
    }

    # Step 3: Initiate resumable upload session
    print("  Initiating upload session...")
    upload_uri = initiate_resumable_upload(access_token, metadata, file_size)
    print(f"  Upload URI obtained")

    # Step 4: Upload file
    print("  Uploading...")
    video = upload_file(upload_uri, video_path)

    video_id = video.get("id")
    print(f"  Video ID: {video_id}")
    print(f"  URL: https://www.youtube.com/watch?v={video_id}")
    print(f"  Status: {video.get('status', {}).get('uploadStatus')}")

    return video


def set_thumbnail(video_id: str, thumbnail_path: str) -> bool:
    """
    Upload a custom thumbnail for a video.
    YouTube requires a separate POST to thumbnails.set after the video upload.

    Args:
        video_id: The YouTube video ID returned by upload_video()
        thumbnail_path: Absolute path to a JPEG or PNG image (1280×720 recommended)

    Returns:
        True on success, False on failure (logs error, does not raise).
    """
    if not thumbnail_path or not os.path.exists(thumbnail_path):
        print(f"  WARNING: Thumbnail not found: {thumbnail_path}")
        return False

    print(f"  Setting thumbnail: {os.path.basename(thumbnail_path)}")
    access_token = get_access_token()

    thumbnail_url = f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
    file_size = os.path.getsize(thumbnail_path)

    with open(thumbnail_path, "rb") as f:
        thumb_data = f.read()

    # Determine content type
    ext = Path(thumbnail_path).suffix.lower()
    content_type = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"

    resp = requests.post(
        thumbnail_url,
        params={"videoId": video_id},
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": content_type,
            "Content-Length": str(file_size),
        },
        data=thumb_data,
        timeout=60,
    )

    if resp.status_code in (200, 201):
        print(f"  Thumbnail set for video {video_id}")
        return True
    else:
        print(f"  WARNING: Thumbnail upload failed (HTTP {resp.status_code})")
        return False


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Upload MP4 to YouTube")
    parser.add_argument("--video",       required=True)
    parser.add_argument("--title",       required=True)
    parser.add_argument("--description", default="")
    parser.add_argument("--tags",        default="ambient,relaxing,background music",
                        help="Comma-separated tags")
    parser.add_argument("--category",    default="10",
                        help="YouTube category ID (10=Music, default)")
    parser.add_argument("--privacy",     default="unlisted",
                        choices=["public", "private", "unlisted"])
    args = parser.parse_args()

    tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    print("=== yt_upload ===")
    video = upload_video(
        video_path=args.video,
        title=args.title,
        description=args.description,
        tags=tags,
        category_id=args.category,
        privacy=args.privacy,
    )

    print(f"\nDone. Video live at: https://www.youtube.com/watch?v={video['id']}")
    print(f"Privacy: {args.privacy} - change to public in YouTube Studio when ready.")


if __name__ == "__main__":
    main()

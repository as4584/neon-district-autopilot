"""Fail-closed visual QA for Neon District long-form videos.

The local Ollama vision model judges whether the actual cover/frame matches the
queue item and the Neon District visual identity. A mismatch can be repaired by
the caller's local regeneration callback, but no upload is allowed until the
replacement also passes.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import requests


BASE_DIR = Path(__file__).parent
REPORT_DIR = BASE_DIR / "test_outputs"
DEFAULT_MODEL = "qwen3-vl:latest"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


class VisualQAFailed(RuntimeError):
    """Raised when imagery cannot be approved before upload."""


@dataclass(frozen=True)
class VisualQAResult:
    passed: bool
    content_match_score: float
    neon_theme_score: float
    visual_quality_score: float
    observed_scene: str
    mismatches: list[str]
    reason: str
    model: str
    source_path: str


def _ollama_url() -> str:
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    if not host.startswith(("http://", "https://")):
        host = f"http://{host}"
    return f"{host}/api/chat"


def resolve_model() -> str:
    """Use the preferred model, or a verified installed vision replacement."""
    configured = os.environ.get("VISUAL_QA_MODEL")
    base = _ollama_url().rsplit("/", 1)[0]
    try:
        response = requests.get(f"{base}/tags", timeout=10)
        response.raise_for_status()
        installed = {entry["name"] for entry in response.json().get("models", [])}
        candidates = [configured] if configured else [DEFAULT_MODEL, "qwen3.6:27b"]
        for model in candidates:
            if model not in installed:
                continue
            response = requests.post(f"{base}/show", json={"model": model}, timeout=10)
            response.raise_for_status()
            if "vision" in response.json().get("capabilities", []):
                return model
    except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
        raise VisualQAFailed("Ollama vision model discovery failed") from exc
    raise VisualQAFailed(f"No installed vision model available: {', '.join(candidates)}")


def _extract_review_frame(video_path: Path) -> bytes:
    with tempfile.TemporaryDirectory(prefix="neon-visual-qa-") as td:
        frame = Path(td) / "frame.jpg"
        command = [
            "ffmpeg",
            "-y",
            "-ss",
            "5",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(frame),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        if result.returncode != 0 or not frame.exists():
            raise VisualQAFailed(
                f"Visual QA could not extract a video frame: {result.stderr[-300:]}"
            )
        return frame.read_bytes()


def _source_bytes(source_path: str) -> bytes:
    path = Path(source_path)
    if not path.exists():
        raise VisualQAFailed(f"Visual QA source is missing: {path}")
    suffix = path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return path.read_bytes()
    if suffix in VIDEO_SUFFIXES:
        return _extract_review_frame(path)
    raise VisualQAFailed(f"Unsupported visual QA source type: {path.suffix}")


def _numeric(payload: dict, key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise VisualQAFailed(f"Ollama visual QA returned invalid {key}")
    return max(0.0, min(10.0, float(value)))


def inspect_visual(source_path: str, item: dict) -> VisualQAResult:
    """Score one image or representative video frame with local Ollama vision."""
    model = resolve_model()
    image_b64 = base64.b64encode(_source_bytes(source_path)).decode("ascii")
    title = item.get("title", "")
    music_prompt = item.get("prompt", "")
    tags = ", ".join(item.get("tags", []))
    prompt = f"""
You are the strict pre-publish visual QA reviewer for Neon District Archive.
Judge the VISIBLE SCENE in the attached image, not title text overlaid on it.

Target video title: {title}
Target description and mood: {music_prompt}
Target tags: {tags}

The image must:
1. Visibly represent the concrete scene, mood, and use case in the target.
2. Maintain a dark, cinematic neon identity with intentional neon light or glow.
3. Be professional 16:9 music-video artwork without obvious corruption, random UI,
   unrelated subject matter, third-party watermarks, or illegible AI text.

The pipeline intentionally adds the video title and "Neon District Archive" as
small branding overlays. Those two overlays are allowed and are not watermarks.

Do not give content-match credit merely because overlay text repeats the title.
Return only JSON with this exact shape:
{{
  "content_match_score": 0-10,
  "neon_theme_score": 0-10,
  "visual_quality_score": 0-10,
  "observed_scene": "brief factual description",
  "mismatches": ["specific visible mismatch"],
  "reason": "one-sentence verdict"
}}
""".strip()
    body = {
        "model": model,
        "stream": False,
        "think": False,
        "keep_alive": 0,
        "format": "json",
        "options": {"temperature": 0},
        "messages": [
            {"role": "user", "content": prompt, "images": [image_b64]},
        ],
    }
    timeout = int(os.environ.get("VISUAL_QA_TIMEOUT_SECONDS", "240"))
    request_attempts = max(1, int(os.environ.get("VISUAL_QA_REQUEST_ATTEMPTS", "2")))
    payload = None
    last_error = None
    for _ in range(request_attempts):
        try:
            response = requests.post(_ollama_url(), json=body, timeout=timeout)
            response.raise_for_status()
            content = response.json()["message"]["content"]
            payload = json.loads(content)
            break
        except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
            last_error = exc

    if payload is None:
        raise VisualQAFailed(
            f"Ollama visual QA unavailable or invalid after {request_attempts} attempts: {last_error}"
        ) from last_error

    content_score = _numeric(payload, "content_match_score")
    neon_score = _numeric(payload, "neon_theme_score")
    quality_score = _numeric(payload, "visual_quality_score")
    content_min = float(os.environ.get("VISUAL_QA_CONTENT_MIN", "7"))
    neon_min = float(os.environ.get("VISUAL_QA_NEON_MIN", "7"))
    quality_min = float(os.environ.get("VISUAL_QA_QUALITY_MIN", "7"))
    passed = (
        content_score >= content_min
        and neon_score >= neon_min
        and quality_score >= quality_min
    )
    mismatches = payload.get("mismatches", [])
    if not isinstance(mismatches, list):
        mismatches = [str(mismatches)]
    return VisualQAResult(
        passed=passed,
        content_match_score=content_score,
        neon_theme_score=neon_score,
        visual_quality_score=quality_score,
        observed_scene=str(payload.get("observed_scene", "")),
        mismatches=[str(value) for value in mismatches],
        reason=str(payload.get("reason", "")),
        model=model,
        source_path=str(Path(source_path).resolve()),
    )


def save_report(item_id: str, stage: str, result: VisualQAResult) -> Path:
    REPORT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = REPORT_DIR / f"visual_qa_{item_id}_{stage}_{stamp}.json"
    report_path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    return report_path


def approve_cover(
    item: dict,
    cover_path: str,
    regenerate: Callable[[], str],
    *,
    max_regenerations: int | None = None,
) -> tuple[str, VisualQAResult]:
    """Approve a cover or regenerate it locally until it passes."""
    if max_regenerations is None:
        max_regenerations = int(os.environ.get("VISUAL_QA_REGEN_ATTEMPTS", "2"))

    candidate = cover_path
    last_result: VisualQAResult | None = None
    for attempt in range(max_regenerations + 1):
        result = inspect_visual(candidate, item)
        last_result = result
        save_report(item["id"], f"cover_attempt_{attempt + 1}", result)
        if result.passed:
            return candidate, result
        if attempt < max_regenerations:
            try:
                candidate = regenerate()
            except Exception as exc:
                raise VisualQAFailed(
                    f"Visual QA rejected the cover and image regeneration failed: {exc}"
                ) from exc

    assert last_result is not None
    scores = (
        f"content={last_result.content_match_score}/10, "
        f"neon={last_result.neon_theme_score}/10, "
        f"quality={last_result.visual_quality_score}/10"
    )
    raise VisualQAFailed(
        f"Visual QA rejected all cover attempts ({scores}): {last_result.reason}"
    )


def approve_rendered_video(item: dict, video_path: str) -> VisualQAResult:
    """Re-check the actual rendered video frame immediately before upload."""
    result = inspect_visual(video_path, item)
    save_report(item["id"], "rendered_video", result)
    if not result.passed:
        scores = (
            f"content={result.content_match_score}/10, "
            f"neon={result.neon_theme_score}/10, "
            f"quality={result.visual_quality_score}/10"
        )
        raise VisualQAFailed(
            f"Rendered video visual QA failed ({scores}): {result.reason}"
        )
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Inspect local visual-QA model availability")
    parser.add_argument("--check-model", action="store_true")
    args = parser.parse_args()
    if args.check_model:
        try:
            print(resolve_model())
        except VisualQAFailed as exc:
            print(str(exc))
            raise SystemExit(1)
    else:
        parser.print_help()

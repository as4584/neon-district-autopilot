"""
yt_seo.py — SEO optimization for Neon District Archive YouTube uploads.

Improves titles, generates structured descriptions, and scores/prioritizes tags
before every upload. Ported and adapted from darkzOGx/youtube-automation-agent
seo-optimizer-agent.js for ambient/lofi/focus music content.

Usage:
    from yt_seo import optimize

    result = optimize(
        title="1 Hour Dark Ambient Mix | Deep Focus Music",
        tags=["dark ambient", "focus music"],
        mode="generate",      # or "stitch"
        genre="dark ambient", # optional hint
    )
    # result.title, result.description, result.tags
"""

import re
from dataclasses import dataclass, field
from datetime import datetime


# ── Power words that boost CTR for music/focus content ───────────────────────

POWER_WORDS = [
    "Deep", "Pure", "Uninterrupted", "Ultimate", "Best",
    "Relaxing", "Immersive", "Calm", "Intense", "Smooth",
]

# Music channel niche: genre → tag clusters
NICHE_TAGS: dict[str, list[str]] = {
    "dark ambient":    ["dark ambient", "ambient music", "atmospheric music", "drone music", "background music"],
    "lofi":            ["lofi music", "lo-fi beats", "lofi hip hop", "chill beats", "lofi study"],
    "synthwave":       ["synthwave", "retrowave", "chillwave", "80s music", "neon music"],
    "meditation":      ["meditation music", "relaxing music", "calm music", "healing music", "zen music"],
    "jazz":            ["jazz music", "smooth jazz", "jazz cafe", "piano jazz", "late night jazz"],
    "piano":           ["piano music", "ambient piano", "instrumental piano", "solo piano", "peaceful piano"],
    "space ambient":   ["space music", "cosmic ambient", "space ambient", "interstellar music", "sci-fi ambient"],
    "focus":           ["focus music", "study music", "concentration music", "deep work music", "productivity music"],
    "sleep":           ["sleep music", "sleep sounds", "relaxing sleep", "calm sleep music", "night music"],
    "binaural":        ["binaural beats", "alpha waves", "theta waves", "brain waves", "focus frequency"],
    "electronic":      ["electronic music", "ambient electronic", "minimal electronic", "downtempo", "chillout"],
    "nature":          ["nature sounds", "rain sounds", "forest sounds", "ambient nature", "white noise"],
    "classical":       ["classical music", "neoclassical", "piano classical", "orchestral", "instrumental classical"],
    "default":         ["background music", "1 hour music", "instrumental music", "work music"],
}

# Use-case tags that pair well with almost any genre
USE_CASE_TAGS = [
    "study music", "work music", "focus music", "background music",
    "1 hour music", "instrumental", "concentration", "productivity",
]


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class SEOResult:
    title: str
    description: str
    tags: list[str]
    seo_score: int       # 0-100
    warnings: list[str] = field(default_factory=list)


# ── Core optimizer ────────────────────────────────────────────────────────────

def optimize(
    title: str,
    tags: list[str],
    mode: str = "generate",
    genre: str = "",
    stitch_tracks: list[str] | None = None,
) -> SEOResult:
    """
    Full SEO pass: optimize title → build description → expand tags → score.

    Args:
        title:         Original title from queue
        tags:          Original tag list from queue
        mode:          "generate" (single looped track) or "stitch" (multi-track)
        genre:         Optional genre hint for niche tag injection
        stitch_tracks: List of track names for stitch descriptions (e.g. ["Rain + Piano", ...])

    Returns:
        SEOResult with optimized title, description, tags, score, and warnings.
    """
    year = datetime.now().year
    warnings = []

    opt_title = _optimize_title(title, warnings)
    opt_tags  = _optimize_tags(tags, genre, opt_title, warnings)
    opt_desc  = _build_description(opt_title, opt_tags, mode, stitch_tracks)
    score     = _seo_score(opt_title, opt_desc, opt_tags)

    return SEOResult(
        title=opt_title,
        description=opt_desc,
        tags=opt_tags,
        seo_score=score,
        warnings=warnings,
    )


# ── Title optimization ────────────────────────────────────────────────────────

def _optimize_title(title: str, warnings: list[str]) -> str:
    """
    - Ensure title starts with a duration marker (1 Hour, 2 Hour, etc.)
    - Preserve the intended wording instead of injecting generic power words
    - Enforce 100-char YouTube limit (truncate at word boundary)
    - Strip double spaces / weird punctuation
    """
    t = title.strip()

    # Check for duration marker — add if missing
    has_duration = bool(re.search(r'\d+\s*hour', t, re.IGNORECASE))
    if not has_duration:
        t = "1 Hour " + t
        warnings.append("Added '1 Hour' duration marker — was missing.")

    # Enforce 100-char limit at word boundary
    if len(t) > 100:
        truncated = t[:97].rsplit(" ", 1)[0]
        warnings.append(f"Title truncated from {len(t)} → {len(truncated)} chars.")
        t = truncated.rstrip(" |—-").strip()

    # Clean up
    t = re.sub(r"  +", " ", t)
    t = re.sub(r"\s+([|—])\s+", r" \1 ", t)

    return t


# ── Tag optimization ──────────────────────────────────────────────────────────

def _optimize_tags(
    original_tags: list[str],
    genre: str,
    title: str,
    warnings: list[str],
) -> list[str]:
    """
    Merge original tags + niche cluster + use-case tags.
    Deduplicate, lowercase, respect 500-char YouTube limit.
    Return max 15 most relevant tags.
    """
    seen = set()
    result = []
    duration = re.search(r"\b(\d+)\s*hours?\b", title, re.IGNORECASE)

    def add(tag: str):
        t = tag.strip().lower()
        if t == "1 hour music" and duration:
            t = f"{duration.group(1)} hour music"
        if t and t not in seen:
            seen.add(t)
            result.append(t)

    # 1. Original tags first (highest relevance signal)
    for t in original_tags:
        add(t)

    # 2. Niche cluster from genre hint
    if genre:
        cluster_key = next(
            (k for k in NICHE_TAGS if k in genre.lower()),
            None
        )
        if cluster_key:
            for t in NICHE_TAGS[cluster_key]:
                add(t)

    # 3. Auto-detect genre from title
    title_lower = title.lower()
    for niche_key, niche_tags in NICHE_TAGS.items():
        if niche_key in title_lower:
            for t in niche_tags:
                add(t)

    # 4. Use-case fillers
    for t in USE_CASE_TAGS:
        add(t)

    # 5. Default niche
    for t in NICHE_TAGS["default"]:
        add(t)

    # Respect YouTube 500-char tag limit
    final = []
    char_count = 0
    for tag in result[:15]:  # YouTube best practice: ≤15 tags
        cost = len(tag) + (1 if final else 0)  # comma separator
        if char_count + cost <= 500:
            final.append(tag)
            char_count += cost

    if len(final) < len(original_tags):
        warnings.append(f"Tags trimmed to {len(final)} to respect 500-char limit.")

    return final


# ── Description builder ───────────────────────────────────────────────────────

def _build_description(
    title: str,
    tags: list[str],
    mode: str,
    stitch_tracks: list[str] | None,
) -> str:
    """
    Structured description optimized for YouTube:
    - First 125 chars are the hook (shown before "Show more")
    - Timestamps / track listing for stitch mode
    - Keyword-rich body
    - Hashtags (≤15, YouTube recommendation)
    """
    lines = []

    # Hook — first 125 chars matter most
    lines.append(f"{title}")
    lines.append("")
    lines.append(
        "Background music for deep focus, work, studying, and relaxation. "
        "Instrumental atmosphere for long listening sessions."
    )
    lines.append("")

    # Track listing for stitch mode
    if mode == "stitch" and stitch_tracks:
        lines.append("─── TRACKS IN THIS MIX ───")
        # Approximate timestamps (each track ~10 min, 4s crossfades)
        seconds = 0
        for i, track in enumerate(stitch_tracks):
            h = seconds // 3600
            m = (seconds % 3600) // 60
            s = seconds % 60
            ts = f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
            lines.append(f"  {ts}  {track}")
            seconds += 596  # 600s track - 4s crossfade
        lines.append("")

    # Body
    lines.append("─── ABOUT THIS MUSIC ───")
    lines.append(
        "Original AI-generated music by Neon District Archive. "
        "Crafted for long sessions — designed to blend into the background "
        "and keep you in flow state without demanding attention."
    )
    lines.append("")
    lines.append("For reuse or licensing enquiries, contact Neon District Archive.")
    lines.append("")

    # Subscribe CTA
    lines.append("─── NEON DISTRICT ARCHIVE ───")
    lines.append("🔔 Subscribe for weekly ambient & lo-fi uploads.")
    lines.append("New mixes every week — dark ambient, lofi, synthwave, meditation, and more.")
    lines.append("")

    # Hashtags (max 15, no spaces in tags)
    hashtags = [
        "#" + t.replace(" ", "").replace("-", "")
        for t in tags[:10]
        if len(t) < 25
    ]
    lines.append(" ".join(hashtags))
    lines.append("")
    lines.append("— Neon District Archive")

    return "\n".join(lines)


# ── SEO scoring ───────────────────────────────────────────────────────────────

def _seo_score(title: str, description: str, tags: list[str]) -> int:
    """Score 0-100 based on YouTube SEO best practices."""
    score = 0

    # Title (40 pts)
    tlen = len(title)
    if 40 <= tlen <= 70:
        score += 20
    elif tlen <= 100:
        score += 12
    if re.search(r'\d+\s*hour', title, re.IGNORECASE):
        score += 10   # duration in title = strong click signal for music
    if any(pw.lower() in title.lower() for pw in POWER_WORDS):
        score += 10

    # Description (30 pts)
    if len(description) >= 200:
        score += 10
    if "subscribe" in description.lower():
        score += 5
    if "#" in description:
        score += 5
    if "00:" in description or "0:00" in description:
        score += 10   # timestamps / chapters

    # Tags (30 pts)
    if len(tags) >= 8:
        score += 15
    elif len(tags) >= 5:
        score += 8
    total_tag_chars = sum(len(t) for t in tags)
    if 200 <= total_tag_chars <= 450:
        score += 10
    if any("study" in t or "focus" in t or "work" in t for t in tags):
        score += 5   # use-case tags present

    return min(score, 100)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    result = optimize(
        title="1 Hour Dark Ambient Mix | Deep Focus Music for Work & Study",
        tags=["dark ambient", "ambient", "focus music", "work music", "study music"],
        mode="generate",
        genre="dark ambient",
    )
    print(f"Title:     {result.title}")
    print(f"SEO Score: {result.seo_score}/100")
    print(f"Tags ({len(result.tags)}): {', '.join(result.tags)}")
    if result.warnings:
        print(f"Warnings:  {result.warnings}")
    print("\n--- Description ---")
    print(result.description)

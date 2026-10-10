"""
yt_thumbnail.py — Generate YouTube thumbnails using local Hugging Face models.

Generates a 1280x720 JPEG thumbnail for each queue item. Uses genre-specific
neon aesthetics for the Neon District Archive brand. Future covers preserve the
imagery without titles, branding bars, or logo overlays.

Image generation uses an isolated local worker, with no cloud fallback.

Usage:
    # Generate thumbnail for a specific item ID:
    doppler run --project agentop --config prd -- python3 yt_thumbnail.py --id 001

    # Generate thumbnails for ALL pending items missing covers:
    doppler run --project agentop --config prd -- python3 yt_thumbnail.py --all

    # Dry run (show prompt, don't call API):
    doppler run --project agentop --config prd -- python3 yt_thumbnail.py --id 001 --dry-run

Called automatically by yt_autopost.py before upload step.
Idempotent: skips generation if covers/{item_id}.jpg already exists.
"""

import argparse
import json
import os
import sys
import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import yt_local_image

# ── Paths ─────────────────────────────────────────────────────────────────────

BASE_DIR    = Path(__file__).parent
QUEUE_FILE  = BASE_DIR / "yt_queue.json"
COVERS_DIR  = BASE_DIR / "covers"
COVERS_DIR.mkdir(exist_ok=True)
LAYOUT_VERSION = 'imagery-only-v1'


def is_imagery_only(item_id):
    path = COVERS_DIR / f'{item_id}.jpg'
    marker = path.with_suffix('.json')
    try:
        metadata = json.loads(marker.read_text(encoding='utf-8'))
        return (metadata.get('layout_version') == LAYOUT_VERSION and
                metadata.get('sha256') == hashlib.sha256(path.read_bytes()).hexdigest())
    except (OSError, ValueError):
        return False

# ── Genre → neon accent mapping ───────────────────────────────────────────────

GENRE_ACCENTS = {
    "ambient":     {"color": "cyan and purple",      "hex": (0, 255, 240)},
    "dark ambient":{"color": "deep purple and teal", "hex": (120, 0, 200)},
    "lofi":        {"color": "warm orange and gold",  "hex": (255, 140, 0)},
    "lo-fi":       {"color": "warm orange and gold",  "hex": (255, 140, 0)},
    "synthwave":   {"color": "hot pink and electric blue", "hex": (255, 20, 147)},
    "jazz":        {"color": "gold and smoke",        "hex": (212, 175, 55)},
    "piano":       {"color": "silver and soft blue",  "hex": (176, 196, 222)},
    "meditation":  {"color": "soft purple and white", "hex": (180, 100, 255)},
    "sleep":       {"color": "deep indigo and silver","hex": (75, 0, 130)},
    "focus":       {"color": "electric blue and white","hex": (30, 144, 255)},
    "nature":      {"color": "forest green and gold", "hex": (34, 139, 34)},
    "classical":   {"color": "gold and burgundy",     "hex": (180, 30, 50)},
    "space":       {"color": "deep space blue and nebula purple","hex": (25, 25, 112)},
    "electronic":  {"color": "electric green and cyan","hex": (0, 255, 100)},
    "binaural":    {"color": "soft teal and silver",  "hex": (0, 200, 200)},
    "default":     {"color": "cyan and purple",       "hex": (0, 200, 255)},
}

CHANNEL_NAME = "Neon District Archive"

# ── API setup ─────────────────────────────────────────────────────────────────

# ── Prompt builder ────────────────────────────────────────────────────────────

def _resolve_genre(item: dict) -> str:
    """Resolve genre, preferring descriptive content over discovery tags."""
    genre = item.get("genre", "").lower().strip()
    if genre:
        return genre

    # SEO/discovery tags can intentionally span adjacent listening use cases
    # (for example, a jazz track tagged "sleep music"). They must not override
    # the scene and genre explicitly described by the title and music prompt.
    descriptive_source = " ".join([
        item.get("title", ""),
        item.get("prompt", ""),
    ]).lower()
    tag_source = " ".join(item.get("tags", [])).lower()
    priority = [
        "sleep", "meditation", "jazz", "piano", "lo-fi", "lofi",
        "classical", "nature", "space", "dark ambient", "ambient",
        "synthwave", "electronic", "focus", "binaural",
    ]
    for source in (descriptive_source, tag_source):
        for g in priority:
            if g in source:
                return g
    return "default"


def build_prompt(item: dict) -> tuple[str, str]:
    """
    Returns (prompt, genre) for this queue item.
    Genre is used for accent color selection.
    """
    genre = _resolve_genre(item)
    accent = GENRE_ACCENTS.get(genre, GENRE_ACCENTS["default"])["color"]

    title = item.get("title", "1 Hour Ambient Music")

    # Build one coherent physical scene. Specific use cases override broad
    # nighttime/city cues so a sleep track cannot become generic cyberpunk art.
    descriptive_source = " ".join([
        title,
        item.get("prompt", ""),
    ]).lower()
    tag_source = " ".join(item.get("tags", [])).lower()
    source = descriptive_source or tag_source
    has_rain = "rain" in source or "rainy" in source
    if "sleep" in source or "bedroom" in source or "deep rest" in source:
        rain_detail = "rain streaking the bedroom window" if has_rain else "a quiet moonlit window"
        scene = (
            "interior of a serene dark bedroom prepared for sleep, an inviting bed, "
            f"{rain_detail}, soft cyan and violet neon reflected inside the room; "
            "the bedroom must dominate the composition, not an exterior city skyline"
        )
    elif "meditation" in source or "zen" in source or "mindfulness" in source:
        scene = "peaceful night meditation garden with water, stones, lotus forms, and subtle neon glow"
    elif "lounge" in source or "jazz" in source:
        scene = (
            "candlelit jazz lounge interior with a grand piano, upright bass, and saxophone, "
            "warm intimate tables, and a neon city visible through tall windows"
        )
    elif "cafe" in source or "coffee" in source:
        scene = "cozy neon-lit cafe interior with warm tables and rain visible through the windows"
    elif "study" in source or "focus" in source or "work" in source or "reading" in source:
        scene = "dark minimalist study or reading desk with a soft neon lamp and calm window reflections"
    elif "forest" in source or "nature" in source:
        scene = "dark forest with bioluminescent plants and restrained neon light"
    elif "space" in source or "cosmic" in source:
        scene = "cosmic nebula with distant stars and cyan-violet glow"
    elif "night" in source or "midnight" in source:
        scene = "quiet nighttime lounge interior with neon light and atmospheric depth"
    elif has_rain:
        scene = "rain-streaked window viewed from a calm interior with neon reflections"
    else:
        scene = "abstract atmospheric landscape with a clear calm focal point"

    prompt = (
        f"Cinematic atmospheric {genre} music thumbnail, 16:9 composition. "
        f"Ultra-dark background (#0a0a0a), {accent} neon light accents. "
        f"Scene: {scene}. "
        f"Photorealistic, high contrast, moody depth, volumetric lighting. "
        f"No text, no people, no faces, no watermarks, no logos, no UI elements. "
        f"Professional music video aesthetic, immersive and atmospheric."
    )
    return prompt, genre


# ── Image generation ──────────────────────────────────────────────────────────

def generate_base_image(prompt: str) -> Image.Image:
    """
    Call the configured local image model and return a PIL Image.
    Returns 1280×720 (native 16:9 output).
    """
    img = yt_local_image.generate(prompt)

    # Ensure 1280×720
    if img.size != (1280, 720):
        img = img.resize((1280, 720), Image.LANCZOS)

    return img


def crop_watermark_if_present(img: Image.Image) -> Image.Image:
    """
    Precautionary: crop bottom 40px and right 40px where AI logos sometimes appear.
    Then resize back to 1280×720.
    Only applied if CROP_WATERMARK=1 env var is set, or as a safety default.
    """
    if os.environ.get("THUMBNAIL_SKIP_CROP"):
        return img
    # Crop bottom-right corner region (conservative 30px strip)
    w, h = img.size
    cropped = img.crop((0, 0, w, h - 30))  # remove bottom 30px
    return cropped.resize((1280, 720), Image.LANCZOS)


# ── Text overlay (Pillow) ─────────────────────────────────────────────────────

def _get_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Try to load a system font; fall back to default."""
    candidates = [
        str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" /
            ("segoeuib.ttf" if bold else "segoeui.ttf")),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf" if bold else
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def composite_text(img: Image.Image, title: str, genre: str) -> Image.Image:
    """
    Add text overlays:
    - Title: bottom-third, large, white with shadow
    - Channel name: top-right corner, small, semi-transparent
    - Genre accent bar: thin neon line at bottom
    """
    draw = ImageDraw.Draw(img)
    w, h = img.size
    accent_rgb = GENRE_ACCENTS.get(genre, GENRE_ACCENTS["default"])["hex"]

    # ── Bottom accent bar ───────────────────────────────────────────────────
    draw.rectangle([(0, h - 4), (w, h)], fill=accent_rgb)

    # ── Channel name (top-right) ────────────────────────────────────────────
    ch_font = _get_font(22, bold=False)
    ch_text = CHANNEL_NAME
    # Calculate text width for right-align
    try:
        bbox = draw.textbbox((0, 0), ch_text, font=ch_font)
        ch_w = bbox[2] - bbox[0]
    except Exception:
        ch_w = len(ch_text) * 13  # fallback estimate
    ch_x = w - ch_w - 20
    ch_y = 18
    # Shadow
    draw.text((ch_x + 1, ch_y + 1), ch_text, font=ch_font, fill=(0, 0, 0, 160))
    # Text
    draw.text((ch_x, ch_y), ch_text, font=ch_font,
              fill=(*accent_rgb, 220))  # accent color, slight transparency

    # ── Title (bottom third) ────────────────────────────────────────────────
    # Clean up title: remove "1 Hour " prefix if too long for display
    display_title = title
    if len(display_title) > 55:
        # Try to shorten: keep the mood/genre keywords
        parts = display_title.split("|")
        display_title = parts[0].strip() if parts else display_title[:55]

    title_font = _get_font(42, bold=True)
    # Word-wrap manually for long titles
    words = display_title.split()
    lines = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        try:
            bbox = draw.textbbox((0, 0), test, font=title_font)
            test_w = bbox[2] - bbox[0]
        except Exception:
            test_w = len(test) * 25
        if test_w > w - 80:
            if current:
                lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)

    # Draw lines from bottom up
    line_h = 52
    y_start = h - 30 - (len(lines) * line_h) - 30
    for i, line in enumerate(lines):
        y = y_start + i * line_h
        try:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            lw = bbox[2] - bbox[0]
        except Exception:
            lw = len(line) * 25
        x = (w - lw) // 2  # centered

        # Dark semi-transparent background bar for readability
        draw.rectangle(
            [(x - 10, y - 5), (x + lw + 10, y + line_h - 10)],
            fill=(0, 0, 0, 140)
        )
        # Shadow
        draw.text((x + 2, y + 2), line, font=title_font, fill=(0, 0, 0, 200))
        # Main text (white)
        draw.text((x, y), line, font=title_font, fill=(255, 255, 255, 255))

    return img


# ── Main generate function ────────────────────────────────────────────────────

def generate(item: dict, force: bool = False) -> str:
    """
    Generate thumbnail for a queue item.
    Returns path to the saved JPEG.
    Skips if covers/{item_id}.jpg already exists (idempotent).

    Args:
        item: Queue item dict with at least "id", "title"
        force: If True, regenerate even if file exists

    Returns:
        Absolute path string to the generated/existing cover JPEG.
    """
    item_id = item["id"]
    out_path = COVERS_DIR / f"{item_id}.jpg"

    if out_path.exists() and not force and is_imagery_only(item_id):
        print(f"  Thumbnail exists, skipping: {out_path.name}")
        return str(out_path)

    print(f"  Generating thumbnail for [{item_id}]: {item.get('title', '')[:60]}")

    prompt, genre = build_prompt(item)
    print(f"  Genre: {genre} | Prompt: {prompt[:80]}...")

    # Generate base image
    img = generate_base_image(prompt)
    print(f"  Image generated: {img.size}")

    # Preserve the entire model-generated scene. No titles, logo, bars, or labels.
    img = img.convert('RGB').resize((1280, 720), Image.Resampling.LANCZOS)
    if out_path.exists():
        digest = hashlib.sha256(out_path.read_bytes()).hexdigest()[:12]
        backup = BASE_DIR / 'backups' / 'imagery-migration'
        backup.mkdir(parents=True, exist_ok=True)
        shutil.copy2(out_path, backup / f'{item_id}-{digest}.jpg')

    # Save
    img.save(str(out_path), "JPEG", quality=95)
    out_path.with_suffix('.json').write_text(json.dumps({
        'layout_version': LAYOUT_VERSION,
        'sha256': hashlib.sha256(out_path.read_bytes()).hexdigest(),
        'created': datetime.now(timezone.utc).isoformat(),
    }, indent=2), encoding='utf-8')
    print(f"  Saved: {out_path} ({out_path.stat().st_size // 1024} KB)")

    return str(out_path)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate YouTube thumbnails with local HF models")
    parser.add_argument("--id",      default=None, help="Queue item ID (e.g. 001, S001)")
    parser.add_argument("--all",     action="store_true", help="Generate for all pending items missing thumbnails")
    parser.add_argument("--force",   action="store_true", help="Regenerate even if thumbnail exists")
    parser.add_argument("--dry-run", action="store_true", help="Print prompt without generation")
    args = parser.parse_args()

    with open(QUEUE_FILE) as f:
        q = json.load(f)

    if args.id:
        items = [i for i in q["queue"] if i["id"] == args.id]
        if not items:
            sys.exit(f"Item {args.id} not found in queue.")
    elif args.all:
        items = [
            i for i in q["queue"]
            if i.get("status") == "pending" and not is_imagery_only(i['id'])
        ]
        print(f"Found {len(items)} items missing thumbnails.")
    else:
        parser.print_help()
        return

    failures = 0
    for item in items:
        if args.dry_run:
            prompt, genre = build_prompt(item)
            print(f"\n[{item['id']}] {item.get('title', '')}")
            print(f"  Genre: {genre}")
            print(f"  Prompt: {prompt}")
        else:
            try:
                path = generate(item, force=args.force)
                print(f"  OK: {path}")
            except Exception as e:
                print(f"  FAILED for {item['id']}: {e}")
                failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

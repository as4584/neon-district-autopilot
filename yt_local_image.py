"""Generate artwork in an isolated local image environment, with no cloud fallback."""

import os
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent


def worker_environment():
    env = {key: value for key, value in os.environ.items()
           if not any(word in key.upper() for word in
                      ("TOKEN", "SECRET", "API_KEY", "DOPPLER", "YOUTUBE", "GEMINI"))}
    env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
    return env


def generate(prompt: str, seed: int = 42) -> Image.Image:
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**32:
        raise ValueError('Invalid image seed')
    python = Path(os.environ.get("LOCAL_IMAGE_PYTHON", str(ROOT / ".venv-images" / "Scripts" / "python.exe")))
    if not python.is_file():
        raise RuntimeError("Local image environment is not installed; see LOCAL_IMAGE_MIGRATION.md")
    model = os.environ.get("LOCAL_IMAGE_MODEL", "black-forest-labs/FLUX.2-klein-4B")
    with tempfile.TemporaryDirectory(prefix="neon-local-image-") as folder:
        prompt_path = Path(folder) / "prompt.txt"
        output_path = Path(folder) / "image.png"
        prompt_path.write_text(prompt, encoding="utf-8")
        result = subprocess.run([
            str(python), str(ROOT / "scripts" / "generate_local_image.py"),
            "--model", model, "--prompt-file", str(prompt_path), "--output", str(output_path),
            "--seed", str(seed),
        ], capture_output=True, text=True, timeout=900, env=worker_environment())
        if result.returncode or not output_path.is_file():
            # Do not forward dependency tracebacks or inherited credential data.
            raise RuntimeError(f"Local image generation failed (exit={result.returncode}); check model cache and free VRAM")
        with Image.open(output_path) as image:
            return image.convert("RGB").resize((1280, 720), Image.Resampling.LANCZOS)

# Local Image Migration

Prepared for the RTX 5070 Ti (16 GB VRAM) and 32 GB system RAM.
The isolated CUDA image runtime is installed and passed a real CUDA computation.
FLUX weights are installed and SHA256-verified. Three local scenes passed actual
image inspection and visual QA; a mismatched jazz/sleep cover was rejected.
Existing covers are backed up; incomplete model installations block live dispatch.

## Model Selection

| Model | Role | Published hardware guidance | Tradeoff |
| --- | --- | --- | --- |
| [FLUX.2 klein 4B](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B) | First choice | About 13 GB VRAM; Apache-2.0 | Supports generation and reference editing; needs dedicated GPU time |
| [Z-Image-Turbo](https://huggingface.co/Tongyi-MAI/Z-Image-Turbo) | Alternative | Model card targets 16 GB consumer GPUs; Apache-2.0 | Strong photorealism; distilled model has lower diversity |
| [Qwen-Image-2512](https://huggingface.co/Qwen/Qwen-Image-2512) | Later evaluation | No measured fit on this machine | Detailed scenery; larger model is not the first deployment target |

The FLUX repository is ungated. Its safetensor files total about 22.09 GiB at
revision `e7b7dc27f91deacad38e78976d1f2b499d76a294`. That is disk download size,
not its VRAM requirement. Allow extra disk space for CUDA wheels and caches.
Published speed claims are not a benchmark of this PC.

Odysseus hardware scoring was unavailable because ODYSSEUS_URL and
ODYSSEUS_API_TOKEN were not configured. Hardware was measured with nvidia-smi;
model fit estimates come from the official model cards.

## Prepared Integration

- `yt_art_director.py` adds a local CPU prompt agent, model-specific reference
  lessons, per-item seeds and visual-QA feedback. See `ART_DIRECTION.md`.
- Natural scenery no longer requires neon. Publisher guidance is distinguished
  from explicitly approved local image examples; alternative models remain untested.
- `yt_thumbnail.py` now calls `yt_local_image.py`, with no Gemini generation fallback.
- The worker in `scripts/generate_local_image.py` uses Diffusers and CPU offload.
- Default model: `black-forest-labs/FLUX.2-klein-4B`.
- Alternative: set `LOCAL_IMAGE_MODEL=Tongyi-MAI/Z-Image-Turbo` after installation.
- Runtime: `.venv-images/Scripts/python.exe`, configurable with LOCAL_IMAGE_PYTHON.
- Inference uses `local_files_only=True`; it never downloads weights implicitly.
- The worker exits after generation, releasing its GPU allocation before visual QA.
- Vision QA selects a capability-checked installed model and unloads its own inference
  model after the request. Existing score thresholds and rendered-frame checks remain.

## Approved Setup

Use an isolated environment; do not alter ACE-Step's environment. The following
commands create the isolated runtime:

```powershell
python -m venv .venv-images
.\.venv-images\Scripts\python.exe -m pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cu128
.\.venv-images\Scripts\python.exe -m pip install -r requirements-images.txt
.\.venv-images\Scripts\hf.exe download black-forest-labs/FLUX.2-klein-4B --exclude flux-2-klein-4b.safetensors
```

The installed runtime imports Flux2KleinPipeline and performs CUDA tensor math.
Diffusers requires huggingface-hub below 2; the tested combination uses 1.33.0.
The standard CLI transfer provided insufficient progress visibility on this host. The explicit fallback,
`scripts\download_flux_weights.py`, retrieves public revision-pinned Diffusers
files in resumable HTTPS ranges and verifies each weight's published SHA256.
It excludes the unused duplicate root checkpoint (saving about 7.2 GiB), installing
14.88 GiB to `models\flux2-klein-4b`. A completed installation marker is required.
Before downloading weights, verify imports for Flux2KleinPipeline and
ZImagePipeline, CUDA availability, and an actual CUDA tensor operation on the 5070 Ti.
Never execute repository remote code. Keep tokens in the environment.

## Acceptance

1. Check model cache and free VRAM; do not run ACE-Step, Ollama, and image inference concurrently.
2. Generate three local-only scenes: rainy jazz lounge, quiet neon bedroom, cozy rain window.
3. Inspect the actual images for artifacts, scene accuracy, and restrained lighting.
4. Run positive and deliberately mismatched visual-QA checks with saved reports.
5. Render a short local audio/video preview; verify audio loops and container duration.
6. Run `test.cmd` and `health-check.cmd`. A stale posting log remains an honest failure
   until a separately approved posting run succeeds.
7. Only then consider resetting specifically diagnosed failed items or live uploads.

FLUX local image acceptance passed: jazz lounge scores 8/9/9, sleep bedroom
10/10/10, and cozy rain window 10/10/10. All three actual images were inspected;
the wrong jazz cover was rejected for the sleep target. Saved evidence is
`test_outputs/local_flux_acceptance.json` and visual QA reports. Each composite
cover plus QA took about 43 seconds on this machine. `test.cmd` passes 61 tests.
The recovery upload passed YouTube read-back: public, processed, and correct channel.

Future artwork uses `imagery-only-v1` covers with content hashes, without title,
logo, or branding bars. Existing public uploads stay unchanged. Camera and light
animation were rejected by Alex and are disabled. `yt_motion.py` currently uses
still imagery while a genuine local image-to-video worker is acceptance-tested.

Wan 2.2 TI2V 5B is an ungated Apache-2.0 I2V candidate. Its pinned Diffusers
weights require 31.85 GiB of disk. `scripts/download_wan_weights.py` verifies
published SHA256 hashes and never enables publishing. `scripts/generate_local_video.py`
uses offline inference, CPU offload, a bounded 640x352 audition, and a locked-camera
prompt for actual rain flow on glass. This is experimental on the 16 GiB GPU;
official standard-resolution guidance calls for at least 24 GiB. Downloading
weights is not proof of runtime suitability or accepted scene motion.

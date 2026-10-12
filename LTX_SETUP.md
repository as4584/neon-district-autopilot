# LTX-2.5 Local Setup Status

Status (2026-10-12): all five pinned model files downloaded and SHA256 verified.
The isolated Windows CUDA 13 runtime passed startup, required-node checks, and
actual local image-to-video inference. Visual and loop acceptance remain pending.
No daily-publishing integration is enabled.

## One-time Owner Action

Review the access terms for both repositories in your own Hugging Face account:

- https://huggingface.co/Lightricks/LTX-2.5
- https://huggingface.co/Lightricks/LTX-2.5-22b-LoRA-Cinemagraph

Authenticate locally in PowerShell, without putting the token in chat or command
arguments. Use a read token authorized for these gated repositories:

```powershell
.\.venv-images\Scripts\hf.exe auth login
```

Do not add the token to Git credentials. Access terms must be reviewed by the
owner; the staging tool never accepts terms or searches other applications for
credentials.

## Preflight and Explicit Staging

```powershell
.\.venv-images\Scripts\python.exe scripts\stage_ltx.py
.\.venv-images\Scripts\python.exe scripts\stage_ltx.py --download
.\.venv-images\Scripts\python.exe scripts\stage_ltx.py --download --http-chunks --workers 16
```

The first command checks access only. The second checks every pinned file before
downloading and verifies size and SHA256 afterward. Network retries can resume
within a running HTTP transfer. This installed Hub client uses unique partial
files, so an interrupted process restarts its unfinished file on the next run.
The optional chunked mode retains a SHA-named partial file, validates each HTTP
range, and verifies the complete SHA256 before atomic rename. A file lock
prevents concurrent chunked writers. Up to sixteen 16 MiB requests are in flight;
each file has a one-hour bound per invocation, after which it can be resumed.
Errors expose only exception types, never signed URLs or credential values.

`config/ltx_candidate.json` pins official NVFP4 distilled transformer, ComfyUI
INT8 text encoder, convolutional video VAE, audio VAE and Cinemagraph adapter:
33.63 GiB total, plus 40 GiB free-space reserve. These are candidate components,
not a proven compatible workflow or a complete two-stage upscaling installation.
The default two-stage workflow needs additional components. No prompt enhancer
is included; use the existing local prompt service or an explicit motion prompt.

## Remaining Acceptance

1. Owner completes access and local authentication. Done: all five access checks pass.
2. Stage and verify the pinned weights. Done: all five SHA256 checks pass.
3. Install an isolated, pinned Windows-native ComfyUI runtime; do not upgrade
   the working FLUX or ACE-Step environments. Validate NVFP4, INT8 text encoder,
   convolutional VAE and adapter compatibility before inference. Done: the
   complete graph rendered a 49-frame H.264 preview with Cinemagraph loaded.
4. Exercise a bounded city-water audition with CPU offload and tiled decoding.
   Record seeds, versions, wall time, peak VRAM and system RAM. Distilled versus
   full-model sampler settings must match the selected workflow; do not copy
   the adapter card's full-model settings blindly.
5. Verify actual water motion, stable buildings/exposure, temporal quality and
   loop joins. Candidate outputs remain pending human review.
6. Exit the owned worker/runtime and verify GPU memory release, including on
   failure. No persistent idle GPU service is required.

Keep daily videos still-image based until explicit visual acceptance and a
tested integration. Downloaded weights alone never enable an engine.

## Isolated Preview Runner

`scripts/preview_ltx.py` targets ComfyUI revision
`e8665ca8e4089ab917567cdb491308e1397663d4` in `.runtimes/ComfyUI-LTX`, with
Python 3.12 and CUDA PyTorch 2.11.0 in `.venv-ltx`. CUDA 13 is required by the
pinned ComfyUI optimized kernels; the initial CUDA 12.8 startup test passed but
disabled that backend and is not inference acceptance. The base music and FLUX
environments are not upgraded. Optional workflow-gallery media is not needed.

```powershell
.\.venv-ltx\Scripts\python.exe scripts\preview_ltx.py --id LTX-SMOKE-001 --smoke-only
.\.venv-ltx\Scripts\python.exe scripts\preview_ltx.py --id LTX-CITY-001 --source test_outputs\art_direction\city-blue-hour-v1\preview.png
.\preview-ltx.cmd --id LTX-CITY-002 --quality preview --source test_outputs\art_direction\city-blue-hour-v1\preview.png
```

Each ID must be new. The runner checks pinned weight hashes before inference,
binds a disposable server to localhost, disables partner and custom nodes,
strips inherited credentials, and runs with offline Hugging Face settings.
It terminates its owned process tree after success, errors, or the 30-minute
default timeout. It does not attach to or stop existing user services.

The experimental graph adapts the official ComfyUI LTX-2.5 first/last-frame
template: 512x288, 49 frames, 24 fps, eight distilled steps, CFG 1, the same
city image at both ends, Cinemagraph strength 1, and tiled convolutional VAE
decoding. Generated audio is discarded. No spatial upscaler or prompt enhancer
is downloaded. Matching endpoints are only a loop experiment, not a seamless
loop guarantee. A successful MP4 is registered as pending, never approved.

Reference: https://github.com/Comfy-Org/workflow_templates/blob/main/templates/video_ltx2_5_flf2v.json

`--quality preview` raises the bounded audition to 1024x576, 97 frames and
image-guide strength 1.0. It still registers pending, never approved. The smoke
preset is an execution test, not a production-quality output.

## Audition Findings (2026-10-12)

- 512x288, 49-frame smoke clip rendered in a 56.05-second owned-runtime run.
  Architectural detail was too soft for publication; this is not an accepted asset.
- 1024x576, 97-frame preview rendered in a 64.66-second owned-runtime run.
  Device-wide sampled peak was 13,906 MiB, with at least 7.41 GiB system RAM
  available at sampled points. These are sampled device/system observations,
  not exact per-model memory peaks. Runtime timings exclude preflight hashing.
- Both workers exited and device memory returned to about 1.3 GiB desktop usage.
- Visual review found subtle water motion and architectural detail drift.
  A diagnostic water-region adjacent-frame difference was 0.267/255 versus
  0.673/255 for a building region. Pixel differences alone do not prove physically
  convincing motion. Whole-frame endpoint difference was 3.877/255 versus
  0.492/255 average adjacent-frame difference, so a seamless loop is not accepted.
- The higher-resolution clip remains pending human review. No clip is connected
  to daily publishing. Next quality work is stronger localized water motion and
  preservation of static architecture, followed by temporal and loop review.

`requirements-ltx.lock.txt` records the installed runtime packages. Install the
three pinned CUDA 13 PyTorch packages from the official CUDA 13 index first,
then install the lock file into `.venv-ltx`; never apply it to music/image venvs.
`scripts/stage_ltx_runtime.py` can checkpoint the large official Windows wheel
and verify its published SHA256 before a separate pip install. Optional ComfyUI
gallery media and embedded docs are omitted, so their startup warnings are
expected; they do not prevent the local API or video generation.

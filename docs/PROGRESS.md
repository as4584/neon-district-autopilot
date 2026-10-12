# Progress Ledger

## 2026-10-12: LTX Local Inference Verified, Quality Gate Remains

All five pinned official files completed SHA256 verification. An isolated Python
3.12 / PyTorch 2.11.0 CUDA 13 environment now runs the pinned ComfyUI workflow
with its optimized CUDA backend enabled. The installed package snapshot is
recorded in `requirements-ltx.lock.txt`; no music or image environment was upgraded.

The smoke render produced 49 frames at 512x288. A stronger-guidance audition
produced 97 frames at 1024x576 / 24 fps, taking 64.66 seconds inside the owned
runtime (preflight hashing excluded). Sampled device-wide GPU memory peaked at
13,906 MiB; sampled available system memory stayed above 7.41 GiB. Both runtime
process trees stopped after rendering, with device memory back near desktop
baseline. The regression suite passes 93 tests, including failed-startup cleanup.

This is execution acceptance, not visual acceptance. The low-resolution smoke
clip was rejected and its media removed, preserving its source and audit record.
The higher-resolution clip remains pending: water motion is too subtle, building
details drift, and the endpoint difference is larger than ordinary frame changes.
It is not approved as a seamless loop or connected to daily publishing. Local
preview media stays private; only sanitized findings and reviewed source are public.

## 2026-10-11: LTX-2.5 Integration in Progress

Owner-authorized access checks passed for five pinned official model files
(33.63 GiB). NVFP4 distilled transformer, INT8 text encoder, convolutional video
VAE, audio VAE and Cinemagraph adapter are staged only after full hash checks.
Large-file network stalls led to an explicit chunked downloader with checked
byte ranges, checkpointed partial files, a writer lock and final SHA256 checks.

An isolated Windows ComfyUI startup test found all required preview nodes and
exited its owned process tree cleanly. Device memory returned to desktop baseline.
The initial CUDA 12.8 build disabled optimized quantization kernels; CUDA 13
installation and weight transfer remain in progress. No LTX inference or quality
acceptance is claimed. The local regression suite passes 92 tests.

The experimental audition graph uses a locked city-water scene, identical
first/last image guides, eight distilled steps and tiled decoding. It has no
upload capability and records any generated clip as pending human review.
Daily publishing remains on still imagery, and existing uploads are untouched.

## 2026-10-11: Elevated City Artwork and Video Research

The owner approved both nature previews; their private, hash-bound review
records now make them eligible as same-model nature references. City exteriors
have their own subject routing, lighting and elevated compositions. An interior
with a city outside its window remains an interior; a city waterfront is not
misclassified as a forest stream.

Two actual local FLUX.2 Klein 4B previews completed using the local prompt agent:
a blue-hour waterfront overlook and a sunlit neighborhood panorama. The latter
did not deliver the requested tall-tower emphasis. Both were visually inspected
and remain pending owner review; neither has automated visual-QA acceptance or
upload approval. No new video was generated and no new model was downloaded.
After completion Ollama listed no loaded models and total GPU use was 1123 MiB.

The expanded suite passes 82 tests in both local and sanitized checkouts.
See the [video shortlist](../VIDEO_MODEL_SHORTLIST.md) for publisher examples,
exact candidate variants, hardware caveats and the no-download decision gate.
Only reduced-resolution Wan is locally exercised; Hunyuan and LTX compatibility
remain unverified on this machine. Publisher demos do not establish loop quality.

## 2026-10-11: Local Artwork Prompt Curator

Future cover generation now uses a local CPU prompt agent with exact-model
reference selection, recorded briefs and reproducible per-item seeds. Natural
scenes use natural light; neon is optional when the subject does not call for it.
Visual QA judges composition and material plausibility, requires quality 8/10
by default, and sends visible defects back into a bounded retry with a new seed.

The initial reference library contains labeled publisher guidance, not purported
user-approved outputs. Explicitly approved local examples retain image hashes,
prompts, seeds and aesthetic lessons. Changed, missing, rejected and cross-model
examples cannot become active references. Rejected isolated previews can be
deleted while retaining the small review record.

Two actual local FLUX previews completed through the prompt agent: a woodland
stream and a mountain lake at dawn. Both remain pending human review. The stream
passed the new automated visual review at content 10, direction 10, quality 9;
the lake was visually inspected but has not run the automated review. No preview
was uploaded. After generation Ollama had no loaded model and total GPU use
returned to 833 MiB. Z-Image profiles are prepared, not locally benchmarked.

All 80 regression tests passed in the Windows source and sanitized checkout.
The operational health check passed with historical failure warnings preserved.
See [artwork direction](../ART_DIRECTION.md) for the workflow and review commands.

## 2026-10-10: Recovery and Public Showcase

### Motion Requirement Correction

The initial camera/light animation was a misunderstanding of the requested motion.
Those effects are now disabled. Future clips should contain real image-to-video
environmental motion with a locked camera and stable lighting. Daily uploads keep
clean still imagery until this new stage passes acceptance; existing public videos
and thumbnails remain untouched.

Wan 2.2 TI2V 5B is the first local audition candidate, pinned to
`b8fff7315c768468a5333511427288870b2e9635`. Its ungated Apache-2.0 weights require
31.85 GiB. The worker uses CPU offload and a bounded low-resolution rain-flow
test because the host has 16 GiB VRAM, below the official standard-resolution
24 GiB recommendation. Weight download and runtime acceptance are distinct gates.

The resumable public range download has now completed with SHA256 verification.
Offline generation ran on the 16 GiB GPU after separating text encoding from
video inference and moving cached prompt tensors onto the GPU. The image worker
environment also requires `ftfy` for Wan prompt cleaning.

Two genuine I2V auditions used an existing imagery-only bedroom cover at 640x352,
24 fps. The 49-frame / 20-step audition remains pending human review. The
121-frame / 30-step audition showed edge blocks and warped window details; it
was rejected and its video deleted. Neither clip is approved or connected to
daily publishing. Convincing object motion, temporal QA and loop preparation
remain acceptance gates. A still render is not represented as AI video.

Local candidate reviews bind source and preview hashes. Rejection deletes only
owned, unchanged media and preserves source images and a small audit record.
Eight earlier rejected camera/light preview artifacts were removed; historical
upload retry files and existing public videos remain untouched. The expanded
Windows-native regression suite passes 72 tests.

### Verified

- Windows-native regression tests pass without production queues or artwork.
- ACE-Step produced valid 30-second 48 kHz stereo audio.
- 1080p NVENC/AAC rendering produced a valid 30-second preview.
- Local visual QA accepted a relevant cover and rejected an unrelated sleep cover.
- Existing channel videos were organized into two public playlists.
- Unsupported promises about ads, interruptions, and copyright were removed from tracked video descriptions.
- Curated model revisions, download budgets, hashes, and licensing blockers are recorded.
- The initial 50 tests passed on a clean GitHub Actions Windows runner; the expanded 61-test suite passes in both local checkouts.
- Weekly native model staging and sanitized findings tasks are enabled; a live report publication was verified.
- FLUX weights completed SHA256 verification; jazz, sleep bedroom, and cozy rain window generation passed actual inspection and visual QA.
- A deliberately incorrect local jazz cover was rejected for the sleep target.
- Preserved recovery audio passed technical QA: 300 seconds, 48 kHz stereo, -17 dB average and -1 dB peak.
- [Recovery video](https://www.youtube.com/watch?v=glUxXuiUxps) is public, processed successfully, and has a verified 3,601-second duration on the expected channel.
- Future covers are imagery-only; legacy title/logo overlays are not reused. Existing public videos and thumbnails are left untouched.
- Local FFmpeg renders a reusable 30-second camera/light loop, then stream-copies it into long sessions. A real 1080p/30fps preview passed nonblank, motion, duration, and loop-continuity pixel checks.
- A two-loop mux test contains exactly 60 seconds of video and audio and 1,800 video frames.
- Local visual QA retries GPU server failures on the CPU without bypassing its acceptance scores.
- Animated bedroom-frame visual QA passed 10/10/10 using the local CPU fallback after a GPU initialization failure.
- Daily Windows dispatch is enabled at 09:00 local; invoking the dispatcher confirmed it skips an already-published day without another upload.
- The Windows health check passed: seven pending long-form sessions, no generating items, and completed Shorts queue. Eight historical failures remain preserved, not blindly reset.

Tracking: [daily publishing acceptance](https://github.com/as4584/neon-district-autopilot/issues/1), [HeartMuLa auditions](https://github.com/as4584/neon-district-autopilot/issues/2), [Stable Audio gate](https://github.com/as4584/neon-district-autopilot/issues/3).

### Pending Acceptance

- Install and verify isolated alternative music runtimes; audition for vocal leakage and harsh transitions.
- Run balanced challenger trials by series and duration.
- Gather enough equal-age watch-time evidence to retain or replace engines.

### Evidence Rules

No upload is claimed successful merely because a process started. No music-engine winner is declared from lifetime view totals or absent metrics. Public findings expose only aggregates, never credentials, private account data, machine paths, or production logs.

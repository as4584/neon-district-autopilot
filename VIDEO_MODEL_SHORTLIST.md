# City Image-to-Video Shortlist

Research date: 2026-10-11. No new model downloads or video generation authorized
for this research pass. Existing published videos remain untouched.

## Target and Acceptance

Windows-native RTX 5070 Ti, 16 GB VRAM, 32 GB system RAM. First produce beautiful
elevated city stills using installed FLUX.2 Klein 4B. Keep clips local and pending
until explicitly reviewed. Real environmental motion means water, foliage,
clouds or restrained distant traffic, not a zoom or animated lighting filter.

A long listening session should reuse reviewed short loops, not recursively
extend a clip for hours. Reject warped buildings, flickering windows, changing
reflections, camera drift and visible loop seams. Crossfades are not evidence of
a seamless loop: inspect the join for ghosting. Do not reverse traffic footage.
Keep generation workers one-shot and verify their exit and released GPU memory.

## Candidates

### Wan2.2 TI2V-5B: installed baseline

Already installed and previously exercised locally at 640x352. That proves the
reduced-resolution runtime, not acceptable city animation: the prior longer
audition was rejected for artifacts. The publisher's standard 720p command asks
for at least 24 GB VRAM, so do not promise that configuration on this machine.
No additional download is needed for another low-resolution audition after
approval. Apache-2.0 model.

- [Official implementation and family video demo](https://github.com/Wan-Video/Wan2.2#video-demos)
- [Exact 5B checkpoint](https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B)
- [Publisher 5B demo Space](https://huggingface.co/spaces/Wan-AI/Wan-2.2-5B)

The family montage is not a 5B benchmark. The Space returned an access error
during this research pass; do not present it as a verified playable result.

### HunyuanVideo-1.5 480P I2V step-distill: next audition candidate

8.3B model. Publisher documents 14 GB minimum with offloading and an 8/12-step
480p I2V checkpoint. Their reference runtime explicitly targets Linux; ComfyUI
integration offers a Windows-native route to investigate. Its standard 720p
tutorial targets 24 GB, not proof of the 14 GB configuration on Windows.
CPU offload, lower resolution, and possibly quantized weights need acceptance
testing against both VRAM and 32 GB RAM. Do not claim it is already compatible,
faster on our hardware, or free of architectural artifacts.

- [Exact model family and requirements](https://huggingface.co/tencent/HunyuanVideo-1.5)
- [Watch original versus step-distilled I2V](https://github.com/Tencent-Hunyuan/HunyuanVideo-1.5/blob/main/assets/step_distillation_comparison.md)
- [Official ComfyUI integration](https://github.com/Tencent-Hunyuan/HunyuanVideo-1.5/blob/main/ComfyUI/README.md)
- [ComfyUI workflow documentation](https://docs.comfy.org/tutorials/video/hunyuan/hunyuan-video-1-5)
- [Custom Tencent license, review before commercial deployment](https://github.com/Tencent-Hunyuan/HunyuanVideo-1.5/blob/main/LICENSE)

### LTX-2.5 distilled NVFP4: newer, experimental on this hardware

Official candidate is `Lightricks/LTX-2.5`, file
`diffusion_models/ltx-2.5-22b-distilled-transformer-nvfp4.safetensors`.
The publisher lists ComfyUI and Blackwell NVFP4 support. Also requires a text
encoder, VAEs and workflow-specific components; the 4-bit transformer alone
does not establish total memory requirements. The lighter convolutional video
VAE is an option to evaluate. No confirmed 16 GB Windows acceptance result here.
Model access is gated; do not accept terms or share account details automatically.

- [Official examples](https://ltx.io/model/ltx-2-5)
- [Exact checkpoints and component list](https://huggingface.co/Lightricks/LTX-2.5)
- [Earlier LTX-2.3 image-to-video examples](https://ltx.io/model/ltx-2-3)
- [Official LTX-2.3 NVFP4 alternative](https://huggingface.co/Lightricks/LTX-2.3-nvfp4)

LTX-2.3 remains an alternative, not the newest release. Its NVFP4 model card
lists the dev checkpoint and labels distilled NVFP4 coming soon. Publisher
galleries are selected examples, not evidence of quantized quality or local
performance. LTX embeds failed playback in the in-app browser; original page
links are retained for viewing in a regular browser. LTX uses a custom community
license, not an unconditional commercial-use grant.

## Decision

Review examples before approving downloads. First compare an approved city still
with the existing Wan baseline; consider Hunyuan's 480p I2V checkpoint as a new
challenger. LTX is a higher-complexity experiment, not a production dependency.
Any future download needs an exact revision, complete component/storage budget,
license review and an isolated Windows runtime. No model is promoted on the
basis of publisher demos alone. Keep original music; generated video audio is
not needed. No cloud or Gemini dependency is required by this proposed design.

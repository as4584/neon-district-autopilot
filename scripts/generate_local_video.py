"""Offline Wan image-to-video audition. Never uploads or enables an engine."""

import argparse
import json
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frames', type=int, default=49)
    parser.add_argument('--steps', type=int, default=20)
    args = parser.parse_args()
    if args.frames < 17 or args.frames > 121 or (args.frames - 1) % 4:
        raise ValueError('Frames must be 4n+1 within the bounded audition budget')
    if not 12 <= args.steps <= 50:
        raise ValueError('Steps outside audition budget')
    root = Path(__file__).resolve().parents[1]
    cache = root / 'models' / 'wan2.2-ti2v-5b'
    marker = json.loads((cache / 'installation.json').read_text(encoding='utf-8'))
    if marker.get('revision') != 'b8fff7315c768468a5333511427288870b2e9635' or not marker.get('sha256_verified'):
        raise RuntimeError('Verified pinned Wan installation required')
    import torch
    from PIL import Image
    from diffusers import AutoencoderKLWan, WanImageToVideoPipeline
    import numpy as np

    if not torch.cuda.is_available() or torch.cuda.mem_get_info()[0] < 13 * 1024**3:
        raise RuntimeError('At least 13 GiB free CUDA memory required for this audition')
    print('Loading pinned offline Wan with CPU offload; no network inference.', flush=True)
    vae = AutoencoderKLWan.from_pretrained(cache, subfolder='vae', torch_dtype=torch.float32,
                                         local_files_only=True)
    pipeline = WanImageToVideoPipeline.from_pretrained(
        cache, vae=vae, torch_dtype=torch.bfloat16, local_files_only=True,
        image_encoder=None, image_processor=None, expand_timesteps=True)
    pipeline.vae.enable_tiling()
    pipeline.enable_model_cpu_offload()
    with Image.open(args.image) as source:
        image = source.convert('RGB').resize((640, 352), Image.Resampling.LANCZOS)
    prompt = (
        'A locked-off tripod shot of this exact quiet bedroom and rain-streaked window. '
        'Raindrops slide slowly down the glass, merge and trickle in thin flowing streams. '
        'Rain continues outside. The bed, walls, window frame and furniture stay perfectly still. '
        'Subtle natural water motion only. Stable exposure and unchanged lighting. '
        'No camera movement, no zoom, no pan, no people, no text. Calm photorealistic footage.')
    negative = 'camera movement, zoom, pan, flashing lights, exposure change, flicker, warped furniture, moving bed, people, text, logo, morphing, scene cut'
    print(f'Generating {args.frames} genuine video frames, {args.steps} diffusion steps.', flush=True)
    frames = pipeline(image=image, prompt=prompt, negative_prompt=negative,
                      width=640, height=352, num_frames=args.frames,
                      num_inference_steps=args.steps, guidance_scale=5.0,
                      generator=torch.Generator(device='cpu').manual_seed(20261010),
                      max_sequence_length=256, output_type='np').frames[0]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pixels = np.rint(np.clip(np.asarray(frames), 0, 1) * 255).astype('uint8')
    result = subprocess.run([
        'ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'rawvideo',
        '-pix_fmt', 'rgb24', '-s', '640x352', '-r', '24', '-i', 'pipe:0',
        '-an', '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p',
        '-movflags', '+faststart', str(args.output)],
        input=pixels.tobytes(), capture_output=True, timeout=300)
    if result.returncode:
        raise RuntimeError('Local video export failed; audition not accepted')
    print(f'Local I2V audition saved: {args.output.name}; not approved for publishing.', flush=True)


if __name__ == '__main__':
    main()

"""Offline Wan image-to-video audition. Never uploads or enables an engine."""

import argparse
import gc
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frames', type=int, default=49)
    parser.add_argument('--steps', type=int, default=20)
    parser.add_argument('--seed', type=int, default=20261010)
    parser.add_argument('--review-id')
    args = parser.parse_args()
    if args.frames < 17 or args.frames > 121 or (args.frames - 1) % 4:
        raise ValueError('Frames must be 4n+1 within the bounded audition budget')
    if not 12 <= args.steps <= 50:
        raise ValueError('Steps outside audition budget')
    root = Path(__file__).resolve().parents[1]
    if not 0 <= args.seed < 2**32:
        raise ValueError('Seed outside the reproducible range')
    sys.path.insert(0, str(root))
    if args.review_id:
        import yt_video_review
        directory = yt_video_review.folder(args.review_id)
        if args.output.resolve() != (directory / 'preview.mp4').resolve():
            raise ValueError('Review preview must be in its candidate directory')
        if args.output.exists() or (directory / 'review.json').exists():
            raise ValueError('Candidate ID already used; never overwrite a review')
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
    with Image.open(args.image) as source:
        image = source.convert('RGB').resize((640, 352), Image.Resampling.LANCZOS)
    prompt = (
        'A locked-off tripod shot of this exact quiet bedroom and rain-streaked window. '
        'Raindrops slide slowly down the glass, merge and trickle in thin flowing streams. '
        'Rain continues outside. The bed, walls, window frame and furniture stay perfectly still. '
        'Subtle natural water motion only. Stable exposure and unchanged lighting. '
        'No camera movement, no zoom, no pan, no people, no text. Calm photorealistic footage.')
    negative = 'camera movement, zoom, pan, flashing lights, exposure change, flicker, warped furniture, moving bed, people, text, logo, morphing, scene cut'
    from safetensors.torch import load_file, save_file
    from transformers import AutoTokenizer, UMT5EncoderModel

    prompt_key = hashlib.sha256((marker['revision'] + prompt + negative + ':256').encode()).hexdigest()[:20]
    prompt_cache = root / 'test_outputs' / 'video_prompt_cache' / f'{prompt_key}.safetensors'
    if not prompt_cache.exists():
        print('Encoding motion prompts separately to keep RAM within budget.', flush=True)
        tokenizer = AutoTokenizer.from_pretrained(cache / 'tokenizer', local_files_only=True)
        encoder = UMT5EncoderModel.from_pretrained(cache / 'text_encoder',
                                                  torch_dtype=torch.bfloat16, local_files_only=True).to('cuda')
        text_pipeline = WanImageToVideoPipeline(tokenizer=tokenizer, text_encoder=encoder,
                                                vae=None, scheduler=None, expand_timesteps=True)
        with torch.inference_mode():
            positive, negative_embeds = text_pipeline.encode_prompt(
                prompt=prompt, negative_prompt=negative, max_sequence_length=256,
                device=torch.device('cuda'), dtype=torch.bfloat16)
        embeddings = {'prompt_embeds': positive.cpu().contiguous(),
                      'negative_prompt_embeds': negative_embeds.cpu().contiguous()}
        prompt_cache.parent.mkdir(parents=True, exist_ok=True)
        save_file(embeddings, str(prompt_cache))
        del text_pipeline, encoder, tokenizer, positive, negative_embeds
        gc.collect()
        torch.cuda.empty_cache()
    else:
        embeddings = load_file(str(prompt_cache))
    print('Loading offline Wan video models with CPU offload; text model released.', flush=True)
    vae = AutoencoderKLWan.from_pretrained(cache, subfolder='vae', torch_dtype=torch.float32,
                                         local_files_only=True)
    pipeline = WanImageToVideoPipeline.from_pretrained(
        cache, vae=vae, torch_dtype=torch.bfloat16, local_files_only=True,
        text_encoder=None, tokenizer=None, image_encoder=None, image_processor=None, expand_timesteps=True)
    pipeline.vae.enable_tiling()
    pipeline.enable_model_cpu_offload()
    embeddings = {name: value.to(device='cuda', dtype=torch.bfloat16)
                  for name, value in embeddings.items()}
    print(f'Generating {args.frames} genuine video frames, {args.steps} diffusion steps.', flush=True)
    frames = pipeline(image=image, **embeddings,
                      width=640, height=352, num_frames=args.frames,
                      num_inference_steps=args.steps, guidance_scale=5.0,
                      generator=torch.Generator(device='cpu').manual_seed(args.seed),
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
    if args.review_id:
        yt_video_review.register(args.review_id, args.image, args.output)
    print(f'Local I2V audition saved: {args.output.name}; not approved for publishing.', flush=True)


if __name__ == '__main__':
    main()

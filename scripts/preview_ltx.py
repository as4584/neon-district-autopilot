"""One local LTX audition with a bounded, disposable ComfyUI process tree."""

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import yt_video_review as review
from scripts.stage_ltx import DESTINATION, load_manifest, verify

COMFY = ROOT / '.runtimes' / 'ComfyUI-LTX'
REVISION = 'e8665ca8e4089ab917567cdb491308e1397663d4'
SIGMAS = '1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0'
PROMPT = (
    'CINEMAGRAPH_MOTION, a locked-off tripod view of this exact harbor city. '
    'Only the open water develops small slow wind-driven ripples and gentle '
    'physically coherent reflections. Buildings, rooftops, roads, windows, sky '
    'and horizon remain fixed. Stable exposure and lighting. Quiet natural water '
    'motion throughout. No camera movement, no cuts, no text.'
)


def worker_environment():
    allowed = {'SYSTEMROOT', 'WINDIR', 'PATH', 'PATHEXT', 'TEMP', 'TMP',
               'USERPROFILE', 'USERNAME', 'APPDATA', 'LOCALAPPDATA', 'PROGRAMDATA',
               'PROGRAMFILES', 'PROGRAMFILES(X86)', 'SYSTEMDRIVE', 'COMSPEC'}
    env = {k: v for k, v in os.environ.items() if k.upper() in allowed}
    env.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
               HF_HUB_DISABLE_IMPLICIT_TOKEN='1', HF_HUB_DISABLE_TELEMETRY='1',
               HF_HOME=str(COMFY / '.hf-offline'), PYTHONUNBUFFERED='1')
    return env


def workflow(seed=12345, width=512, height=288, frames=49, guide_strength=0.7):
    if width % 32 or height % 32 or frames % 8 != 1:
        raise ValueError('LTX geometry must be 32-aligned and frames 8n+1')
    graph = {}

    def node(key, kind, **inputs):
        graph[str(key)] = {'class_type': kind, 'inputs': inputs}

    node(1, 'UNETLoader', unet_name='ltx-2.5-22b-distilled-transformer-nvfp4.safetensors', weight_dtype='default')
    node(2, 'LoraLoaderModelOnly', model=['1', 0], lora_name='ltx-2.5-22b-lora-cinemagraph-0.9.safetensors', strength_model=1.0)
    node(3, 'CLIPLoader', clip_name='gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors', type='ltxv', device='default')
    node(4, 'VAELoader', vae_name='ltx-2.5-video-vae-conv-bf16.safetensors')
    node(5, 'VAELoader', vae_name='ltx-2.5-audio-vae-bf16.safetensors')
    node(6, 'LoadImage', image='source.png')
    node(7, 'ImageScale', image=['6', 0], upscale_method='lanczos', width=width, height=height, crop='center')
    node(8, 'LTXVPreprocess', image=['7', 0], img_compression=18)
    node(9, 'CLIPTextEncode', clip=['3', 0], text=PROMPT)
    node(10, 'CLIPTextEncode', clip=['3', 0], text='')
    node(11, 'LTXVConditioning', positive=['9', 0], negative=['10', 0], frame_rate=24.0)
    node(12, 'EmptyLTXVLatentVideo', width=width, height=height, length=frames, batch_size=1)
    # Same first/last guide encourages a loop; it does not prove a seamless join.
    node(13, 'LTXVAddGuide', positive=['11', 0], negative=['11', 1], vae=['4', 0], latent=['12', 0], image=['8', 0], frame_idx=-1, strength=guide_strength)
    node(14, 'LTXVAddGuide', positive=['13', 0], negative=['13', 1], vae=['4', 0], latent=['13', 2], image=['8', 0], frame_idx=0, strength=guide_strength)
    node(15, 'LTXVEmptyLatentAudio', audio_vae=['5', 0], frames_number=frames, frame_rate=24, batch_size=1)
    node(16, 'LTXVConcatAVLatent', video_latent=['14', 2], audio_latent=['15', 0])
    node(17, 'RandomNoise', noise_seed=seed)
    node(18, 'SamplerEulerAncestral', eta=0.0, s_noise=1.0)
    node(19, 'ManualSigmas', sigmas=SIGMAS)
    node(20, 'LTXVDualCFGGuider', model=['2', 0], positive=['14', 0], negative=['14', 1], video_cfg=1.0, audio_cfg=1.0)
    node(21, 'SamplerCustomAdvanced', noise=['17', 0], guider=['20', 0], sampler=['18', 0], sigmas=['19', 0], latent_image=['16', 0])
    node(22, 'LTXVSeparateAVLatent', av_latent=['21', 0])
    node(23, 'LTXVCropGuides', positive=['14', 0], negative=['14', 1], latent=['22', 0])
    node(24, 'VAEDecodeTiled', samples=['23', 2], vae=['4', 0], tile_size=256, overlap=64, temporal_size=64, temporal_overlap=16)
    node(25, 'CreateVideo', images=['24', 0], fps=24.0)
    node(26, 'SaveVideo', video=['25', 0], filename_prefix='preview', format='mp4', **{'format.codec': 'h264'})
    return graph


def request(port, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(f'http://127.0.0.1:{port}{path}', data=data,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


def sample_resources(evidence):
    import psutil
    evidence['min_system_available_gib'] = min(
        evidence.get('min_system_available_gib', float('inf')),
        round(psutil.virtual_memory().available / 1024**3, 2))
    try:
        result = subprocess.check_output(
            ['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'],
            text=True, timeout=5, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        evidence['sampled_peak_device_memory_mib'] = max(
            evidence.get('sampled_peak_device_memory_mib', 0), int(result.splitlines()[0]))
    except (OSError, ValueError, subprocess.SubprocessError):
        pass


def stop_owned(process):
    import psutil
    try:
        children = psutil.Process(process.pid).children(recursive=True)
    except psutil.NoSuchProcess:
        children = []
    for child in reversed(children):
        try:
            child.terminate()
        except psutil.NoSuchProcess:
            pass
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
    _, alive = psutil.wait_procs(children, timeout=10)
    for child in alive:
        child.kill()
    _, alive = psutil.wait_procs(alive, timeout=10)
    if alive:
        raise RuntimeError('Owned runtime process survived cleanup')


def run(args):
    revision = subprocess.check_output(['git', '-C', str(COMFY), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != REVISION:
        raise ValueError('ComfyUI revision changed; revalidation required')
    if subprocess.check_output(['git', '-C', str(COMFY), 'diff', '--name-only', 'HEAD'], text=True).strip():
        raise ValueError('Tracked ComfyUI source changed; revalidation required')
    data = load_manifest()
    if not args.smoke_only:
        if not args.source or not Path(args.source).is_file():
            raise ValueError('An existing source image is required')
        for entry in data['files']:
            verify(DESTINATION / entry['path'], entry)
    directory = review.folder(args.id)
    directory.mkdir(parents=True, exist_ok=False)
    inputs = directory / 'input'
    inputs.mkdir()
    if args.source:
        from PIL import Image
        with Image.open(args.source) as source:
            source.convert('RGB').save(inputs / 'source.png')
    config = directory / 'model-paths.json'
    config.write_text(json.dumps({'neon_ltx': {
        'base_path': str(DESTINATION), 'diffusion_models': 'diffusion_models',
        'text_encoders': 'text_encoders', 'vae': 'vae', 'loras': '.'}}), encoding='utf-8')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    command = [sys.executable, str(COMFY / 'main.py'), '--listen', '127.0.0.1',
               '--port', str(port), '--extra-model-paths-config', str(config),
               '--input-directory', str(inputs), '--output-directory', str(directory),
               '--disable-auto-launch', '--disable-all-custom-nodes', '--offline',
               '--disable-assets', '--reserve-vram', '2', '--vram-headroom', '2',
               '--disable-pinned-memory', '--cache-none']
    started = time.monotonic()
    evidence = {'runtime_revision': revision, 'publication_enabled': False,
                'smoke_only': args.smoke_only, 'status': 'starting'}
    with (directory / 'runtime.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen(command, cwd=COMFY, env=worker_environment(),
                                   stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            while True:
                if process.poll() is not None:
                    raise RuntimeError('ComfyUI exited during startup')
                try:
                    request(port, '/system_stats')
                    break
                except (OSError, urllib.error.URLError):
                    if time.monotonic() - started > 180:
                        raise TimeoutError('ComfyUI startup timed out')
                    time.sleep(2)
            settings = ({'width': 1024, 'height': 576, 'frames': 97, 'guide_strength': 1.0}
                        if args.quality == 'preview' else {})
            graph = workflow(seed=args.seed, **settings)
            info = request(port, '/object_info')
            missing = sorted({n['class_type'] for n in graph.values()} - info.keys())
            if missing:
                raise RuntimeError('Required nodes missing: ' + ', '.join(missing))
            evidence['required_nodes_present'] = True
            review.save(directory / 'node-schemas.json', {
                kind: info[kind] for kind in sorted({n['class_type'] for n in graph.values()})})
            if args.smoke_only:
                evidence['status'] = 'runtime_smoke_passed_no_inference'
                return
            review.save(directory / 'workflow.json', graph)
            try:
                submitted = request(port, '/prompt', {'prompt': graph})
            except urllib.error.HTTPError as exc:
                review.save(directory / 'validation-error.json', json.loads(exc.read()))
                raise
            prompt_id = submitted['prompt_id']
            print('LTX preview queued locally; runtime exits on completion or timeout.', flush=True)
            while time.monotonic() - started < args.timeout:
                sample_resources(evidence)
                if process.poll() is not None:
                    raise RuntimeError('ComfyUI exited during inference')
                result = request(port, '/history/' + prompt_id).get(prompt_id)
                if result:
                    review.save(directory / 'history.json', result)
                    if result['status']['status_str'] != 'success':
                        raise RuntimeError('Inference failed; inspect local runtime log')
                    previews = list(directory.glob('preview*.mp4'))
                    if len(previews) != 1:
                        raise RuntimeError('Expected exactly one preview')
                    review.register(args.id, args.source, previews[0], model='Lightricks/LTX-2.5+Cinemagraph-0.9')
                    evidence['status'] = 'pending_visual_review'
                    print(f'Preview pending review: {previews[0]}', flush=True)
                    return
                time.sleep(5)
            raise TimeoutError('Bounded LTX audition timed out')
        except BaseException as exc:
            evidence['status'] = 'failed'
            evidence['error_type'] = type(exc).__name__
            raise
        finally:
            stop_owned(process)
            evidence['owned_runtime_stopped'] = True
            evidence['elapsed_seconds'] = round(time.monotonic() - started, 2)
            review.save(directory / 'execution.json', evidence)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--id', required=True)
    parser.add_argument('--source')
    parser.add_argument('--seed', type=int, default=12345)
    parser.add_argument('--quality', choices=('smoke', 'preview'), default='smoke')
    parser.add_argument('--timeout', type=int, default=1800, choices=range(60, 3601))
    parser.add_argument('--smoke-only', action='store_true')
    run(parser.parse_args())


if __name__ == '__main__':
    main()

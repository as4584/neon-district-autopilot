"""Long-session muxing; still fallback until real image-to-video is accepted."""

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FPS = 30
LOOP_SECONDS = 30
VERSION = 'still-imagery-v1'


def motion_filter():
    return 'scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,format=yuv420p'


def render_scene(image_path):
    image_path = Path(image_path)
    digest = hashlib.sha256(image_path.read_bytes() + VERSION.encode()).hexdigest()[:20]
    folder = ROOT / 'test_outputs' / 'motion'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f'{digest}.mp4'
    if target.is_file():
        return str(target)
    temporary = target.with_suffix('.tmp.mp4')
    command = ['ffmpeg', '-nostdin', '-y', '-loop', '1', '-framerate', str(FPS),
               '-i', str(image_path), '-vf', motion_filter(), '-t', str(LOOP_SECONDS),
               '-an', '-c:v', 'h264_nvenc', '-preset', 'p5', '-cq', '20',
               '-b:v', '3000k', '-maxrate', '5000k', '-bufsize', '10000k',
               '-g', str(FPS * 2), '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(temporary)]
    result = subprocess.run(command, capture_output=True, timeout=600)
    if result.returncode:
        # CPU fallback affects only the short scene, never hours of animation.
        command[command.index('h264_nvenc')] = 'libx264'
        command[command.index('p5')] = 'veryfast'
        index = command.index('-cq')
        command[index:index + 2] = ['-crf', '23']
        result = subprocess.run(command, capture_output=True, timeout=900)
    if result.returncode or not temporary.is_file():
        raise RuntimeError('Local ambient scene rendering failed')
    temporary.replace(target)
    return str(target)


def render_session(scene_path, audio_path, output_path, seconds):
    if isinstance(seconds, bool) or not isinstance(seconds, int) or not 0 < seconds <= 43200:
        raise ValueError('Session duration must be within the platform limit')
    command = ['ffmpeg', '-nostdin', '-y', '-stream_loop', '-1', '-i', str(scene_path),
               '-stream_loop', '-1', '-i', str(audio_path), '-t', str(seconds),
               '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy',
               '-frames:v', str(seconds * FPS),
               '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '2',
               '-movflags', '+faststart', str(output_path)]
    result = subprocess.run(command, capture_output=True, timeout=7200)
    if result.returncode:
        raise RuntimeError('Animated session muxing failed; no upload')
    return str(output_path)

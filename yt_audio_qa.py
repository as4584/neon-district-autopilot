"""Technical audio checks only; these do not prove musical taste or absence of vocals."""

import json
import math
import re
import subprocess
from pathlib import Path


def inspect(path):
    if not Path(path).is_file():
        raise RuntimeError('Audio source is missing')
    probe = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                            '-of', 'json', str(path)], capture_output=True, text=True, timeout=30)
    if probe.returncode:
        raise RuntimeError('Audio container probe failed')
    metadata = json.loads(probe.stdout)
    streams = [stream for stream in metadata.get('streams', []) if stream.get('codec_type') == 'audio']
    duration = float(metadata.get('format', {}).get('duration', 'nan'))
    if len(streams) != 1 or not math.isfinite(duration) or duration < 10:
        raise RuntimeError('Audio must have one stream and at least ten finite seconds')
    stream = streams[0]
    if stream.get('channels') not in (1, 2) or int(stream.get('sample_rate', 0)) < 22050:
        raise RuntimeError('Audio channel count or sample rate is invalid')
    meter = subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-i', str(path),
                            '-af', 'volumedetect', '-f', 'null', '-'],
                           capture_output=True, text=True, timeout=300)
    if meter.returncode:
        raise RuntimeError('Audio decode or volume analysis failed')
    values = {}
    for field in ('mean_volume', 'max_volume'):
        match = re.search(rf'{field}:\s*(-?\d+(?:\.\d+)?|-?inf)\s*dB', meter.stderr)
        if not match:
            raise RuntimeError('Audio volume measurement unavailable')
        values[field] = float(match.group(1))
    if not all(math.isfinite(value) for value in values.values()):
        raise RuntimeError('Audio is silent or has invalid volume measurements')
    if values['mean_volume'] < -55 or values['mean_volume'] > -8:
        raise RuntimeError('Audio average volume is outside the quiet-listening safety range')
    if values['max_volume'] >= -0.1:
        raise RuntimeError('Audio has no peak headroom; clipping risk blocks upload')
    return {'duration_seconds': duration, 'sample_rate': int(stream['sample_rate']),
            'channels': stream['channels'], **values}

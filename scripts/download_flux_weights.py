"""Explicit public, resumable HTTPS fallback for the approved FLUX installation."""

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
REPO = 'black-forest-labs/FLUX.2-klein-4B'
DESTINATION = ROOT / 'models' / 'flux2-klein-4b'
CHUNK = 32 * 1024 * 1024


def fetch_range(url, start, end, expected):
    for attempt in range(4):
        try:
            with requests.get(url, headers={'Range': f'bytes={start}-{end}'},
                              timeout=(30, 90), stream=True) as response:
                if response.status_code not in (200, 206):
                    raise RuntimeError(f'Weight request HTTP {response.status_code}')
                if response.status_code == 200 and expected > CHUNK:
                    raise RuntimeError('Server did not honor range request')
                if response.status_code == 206 and response.headers.get('Content-Range') != f'bytes {start}-{end}/{expected}':
                    raise RuntimeError('Server returned an incorrect range')
                payload = bytearray()
                for block in response.iter_content(1024 * 1024):
                    payload.extend(block)
                    if len(payload) > end - start + 1:
                        raise RuntimeError('Response exceeded requested range')
            if len(payload) != end - start + 1:
                raise RuntimeError('Unexpected download range length')
            return payload
        except (requests.RequestException, RuntimeError):
            if attempt == 3:
                raise RuntimeError('Public weight range transfer failed') from None
            time.sleep(2 ** attempt)


def download(entry, revision, repo=REPO, destination=DESTINATION, chunk_size=CHUNK):
    relative = Path(entry['rfilename'])
    if relative.is_absolute() or '..' in relative.parts:
        raise RuntimeError('Unsafe repository filename')
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    expected = entry.get('size')
    checksum = entry.get('lfs', {}).get('sha256')
    if target.is_file() and target.stat().st_size == expected:
        with target.open('rb') as source:
            valid = not checksum or hashlib.file_digest(source, 'sha256').hexdigest() == checksum
        if valid:
            print(f'Cached: {relative}', flush=True)
            return
    partial = target.with_suffix(target.suffix + '.part')
    offset = partial.stat().st_size if partial.exists() else 0
    url = f'https://huggingface.co/{repo}/resolve/{revision}/{relative.as_posix()}'
    with partial.open('ab') as output, ThreadPoolExecutor(max_workers=4) as ranges:
        while offset < expected:
            # Bound concurrent transfers and RAM while preserving a resumable prefix.
            starts = list(range(offset, min(offset + 4 * chunk_size, expected), chunk_size))
            for payload in ranges.map(lambda start: fetch_range(
                    url, start, min(start + chunk_size, expected) - 1, expected), starts):
                output.write(payload)
                output.flush()
                offset += len(payload)
            if offset == expected or offset % (128 * 1024**2) < 4 * chunk_size:
                print(f'{relative}: {offset / 1024**3:.2f}/{expected / 1024**3:.2f} GiB', flush=True)
    if checksum:
        with partial.open('rb') as source:
            if hashlib.file_digest(source, 'sha256').hexdigest() != checksum:
                raise RuntimeError(f'Weight SHA256 mismatch: {relative}')
    partial.replace(target)
    print(f'Verified: {relative}', flush=True)


def main():
    response = requests.get(f'https://huggingface.co/api/models/{REPO}?blobs=true', timeout=30)
    response.raise_for_status()
    metadata = response.json()
    revision = metadata['sha']
    files = [entry for entry in metadata['siblings'] if entry['rfilename'] == 'model_index.json'
             or entry['rfilename'].startswith(('scheduler/', 'tokenizer/', 'text_encoder/', 'transformer/', 'vae/'))]
    DESTINATION.mkdir(parents=True, exist_ok=True)
    print(f'Downloading Diffusers-only weights: {sum(item["size"] for item in files)/1024**3:.2f} GiB', flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda entry: download(entry, revision), files))
    (DESTINATION / 'installation.json').write_text(json.dumps({'repo': REPO, 'revision': revision,
                                                            'sha256_verified': True}, indent=2))
    print('FLUX local installation verified; no cloud image generation.', flush=True)


if __name__ == '__main__':
    main()

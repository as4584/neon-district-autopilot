"""Explicit staging only: no inference, license acceptance or production changes."""

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'config' / 'ltx_candidate.json'
DESTINATION = ROOT / 'models' / 'ltx-2.5-candidate'


def load_manifest(path=MANIFEST):
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('publication_enabled') is not False or not data.get('files'):
        raise ValueError('Staging must not enable publishing')
    seen = set()
    for entry in data['files']:
        name = PurePosixPath(entry['path'])
        if (name.is_absolute() or '..' in name.parts or '\\' in entry['path']
                or ':' in entry['path'] or name.suffix != '.safetensors'
                or entry['path'] in seen):
            raise ValueError('Unsafe or duplicated model path')
        seen.add(entry['path'])
        if entry['repo'] not in ('Lightricks/LTX-2.5', 'Lightricks/LTX-2.5-22b-LoRA-Cinemagraph'):
            raise ValueError('Unexpected model repository')
        if not re.fullmatch('[0-9a-f]{40}', entry['revision']) or not re.fullmatch('[0-9a-f]{64}', entry['sha256']):
            raise ValueError('Immutable revision and SHA256 required')
        if type(entry['bytes']) is not int or entry['bytes'] <= 0:
            raise ValueError('Invalid model size')
    if sum(e['bytes'] for e in data['files']) > 40 * 1024**3:
        raise ValueError('Candidate exceeds approved staging budget')
    return data


def verify(path, entry):
    if path.stat().st_size != entry['bytes']:
        raise ValueError('Downloaded file size mismatch')
    with path.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != entry['sha256']:
            raise ValueError('Downloaded file hash mismatch')


def check_range(response, start, end, total):
    if (response.status_code != 206
            or response.headers.get('content-range') != f'bytes {start}-{end}/{total}'
            or len(response.content) != end - start + 1):
        raise ValueError('Server returned an unexpected byte range')
    return response.content


def download_chunks(entry, target, token, workers=4):
    """Bounded HTTP ranges; partial bytes survive process restarts, never inference."""
    from huggingface_hub import get_hf_file_metadata, hf_hub_url

    def metadata():
        return get_hf_file_metadata(hf_hub_url(entry['repo'], entry['path'],
                                   revision=entry['revision']), token=token)

    return download_ranges(entry, target, metadata, DESTINATION, workers)


def download_ranges(entry, target, metadata, root, workers=4):
    """Checkpoint a pinned file from a caller-verified metadata provider."""
    import httpx
    from filelock import FileLock
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError('Target escapes download directory')
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix('.' + entry['sha256'] + '.partial')
    if not partial.resolve().is_relative_to(root.resolve()):
        raise ValueError('Partial file escapes staging directory')
    with FileLock(str(target) + '.lock', timeout=1):
        if target.exists():
            verify(target, entry)
            return target
        offset = partial.stat().st_size if partial.exists() else 0
        if offset > entry['bytes']:
            raise ValueError('Partial file exceeds expected size')
        started = time.monotonic()
        chunk_size = 16 * 1024**2
        last_report = -1
        with httpx.Client(timeout=60, follow_redirects=True) as client, ThreadPoolExecutor(max_workers=workers) as pool:
            with partial.open('ab') as stream:
                while offset < entry['bytes']:
                    if time.monotonic() - started > 3600:
                        raise TimeoutError('One-hour download bound reached; partial retained')
                    meta = metadata()
                    if meta.size != entry['bytes'] or meta.etag.strip('"') != entry['sha256']:
                        raise ValueError('Remote metadata changed')
                    ranges = [(start, min(start + chunk_size, entry['bytes']) - 1)
                              for start in range(offset, min(offset + workers * chunk_size, entry['bytes']), chunk_size)]

                    def fetch(bounds):
                        start, end = bounds
                        for attempt in range(3):
                            try:
                                response = client.get(meta.location, headers={'Range': f'bytes={start}-{end}'})
                                return check_range(response, start, end, entry['bytes'])
                            except (httpx.HTTPError, ValueError):
                                if attempt == 2:
                                    raise
                                time.sleep(2)

                    for content in pool.map(fetch, ranges):
                        stream.write(content)
                        stream.flush()
                        os.fsync(stream.fileno())
                        offset += len(content)
                    percent = int(offset * 100 / entry['bytes'])
                    if percent // 5 > last_report:
                        print(f"DOWNLOAD {entry['path']}: {percent}%", flush=True)
                        last_report = percent // 5
        verify(partial, entry)
        partial.replace(target)
        return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true', help='Stage only after every access check passes')
    parser.add_argument('--http-chunks', action='store_true', help='Use checkpointed bounded HTTP ranges')
    parser.add_argument('--workers', type=int, choices=(1, 4, 8, 16), default=4)
    args = parser.parse_args()
    data = load_manifest()
    size = sum(e['bytes'] for e in data['files'])
    print(f'Candidate weights: {size / 1024**3:.2f} GiB; runtime unverified; publishing disabled.')
    if shutil.disk_usage(ROOT).free < size + 40 * 1024**3:
        print('BLOCKED: insufficient staging space plus 40 GiB reserve.')
        return 2
    from huggingface_hub import get_token, get_hf_file_metadata, hf_hub_download, hf_hub_url
    # Third-party retry logs may include signed download URLs.
    logging.getLogger('huggingface_hub').setLevel(logging.CRITICAL)
    token = get_token()
    print(f'HF_TOKEN_PRESENT={bool(token)}')
    blocked = False
    for entry in data['files']:
        try:
            meta = get_hf_file_metadata(hf_hub_url(entry['repo'], entry['path'], revision=entry['revision']), token=token)
            if meta.size != entry['bytes'] or meta.etag.strip('"') != entry['sha256']:
                raise ValueError('Pinned remote metadata mismatch')
            print(f"ACCESS_OK: {entry['path']}")
        except Exception as exc:
            # Exception messages may contain signed URLs; expose only the type.
            print(f"BLOCKED: {entry['repo']}: {type(exc).__name__}")
            blocked = True
    if blocked:
        print('Review model terms on Hugging Face and authenticate locally. No weights downloaded.')
        return 2
    if not args.download:
        print('Access checks passed. No download requested; no inference started.')
        return 0
    if not DESTINATION.resolve().is_relative_to((ROOT / 'models').resolve()):
        raise ValueError('Destination escapes model directory')
    DESTINATION.mkdir(parents=True, exist_ok=True)
    marker = DESTINATION / 'staging.json'
    if marker.exists():
        marker.unlink()
    for entry in data['files']:
        target = (DESTINATION / entry['path']).resolve()
        if not target.is_relative_to(DESTINATION.resolve()):
            raise ValueError('Model file escapes staging directory')
        if args.http_chunks:
            path = download_chunks(entry, target, token, workers=args.workers)
        else:
            path = Path(hf_hub_download(entry['repo'], entry['path'], revision=entry['revision'],
                                       local_dir=DESTINATION, token=token))
        verify(path, entry)
        print(f"VERIFIED: {entry['path']}", flush=True)
    marker.write_text(json.dumps(dict(data, sha256_verified=True), indent=2), encoding='utf-8')
    print('Weights verified. Runtime and motion acceptance are still required; publishing unchanged.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f'Staging failed: {type(exc).__name__}; details suppressed to protect credentials.')
        raise SystemExit(1)

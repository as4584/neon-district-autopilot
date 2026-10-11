"""Human-reviewed local I2V candidates; deletion is confined to owned assets."""

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CANDIDATES = ROOT / 'test_outputs' / 'video_candidates'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def folder(candidate_id):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', candidate_id):
        raise ValueError('Invalid candidate ID')
    path = CANDIDATES / candidate_id
    if (not CANDIDATES.resolve().is_relative_to(ROOT.resolve())
            or not path.resolve().is_relative_to(CANDIDATES.resolve()) or path.is_symlink()):
        raise ValueError('Candidate path escapes the review directory')
    return path


def owned_asset(directory, filename):
    if Path(filename).name != filename or filename in ('.', '..', 'review.json'):
        raise ValueError('Invalid candidate asset filename')
    path = directory / filename
    if not path.resolve().is_relative_to(directory.resolve()) or path.is_symlink():
        raise ValueError('Candidate asset escapes its directory')
    return path


def save(path, payload):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    temporary.replace(path)


def register(candidate_id, source, preview):
    directory = folder(candidate_id)
    if (directory / 'review.json').exists():
        raise ValueError('Candidate already registered; use a new ID')
    preview = Path(preview)
    owned = owned_asset(directory, preview.name)
    if preview.resolve() != owned.resolve() or not owned.is_file():
        raise ValueError('Preview must already be in its candidate directory')
    payload = {'id': candidate_id, 'status': 'pending',
               'model': 'Wan-AI/Wan2.2-TI2V-5B-Diffusers',
               'source_image': str(Path(source).resolve()), 'source_sha256': digest(source),
               'created': datetime.now(timezone.utc).isoformat(),
               'assets': [{'name': preview.name, 'sha256': digest(preview), 'bytes': preview.stat().st_size}]}
    save(directory / 'review.json', payload)
    return payload


def decide(candidate_id, decision):
    if decision not in ('approved', 'rejected'):
        raise ValueError('Decision must be approved or rejected')
    directory = folder(candidate_id)
    manifest = directory / 'review.json'
    payload = json.loads(manifest.read_text(encoding='utf-8'))
    cleanup_retry = decision == 'rejected' and payload.get('status') == 'rejected'
    if payload.get('status') != 'pending' and not cleanup_retry:
        raise ValueError('Only pending candidates can be decided')
    assets = []
    for entry in payload['assets']:
        path = owned_asset(directory, entry['name'])
        if cleanup_retry and not path.exists():
            continue
        if not path.is_file() or digest(path) != entry['sha256']:
            raise ValueError('Candidate changed since registration; review blocked')
        assets.append(path)
    if not payload['assets']:
        raise ValueError('Candidate has no preview assets')
    if decision == 'approved' and digest(payload['source_image']) != payload['source_sha256']:
        raise ValueError('Source image changed; review blocked')
    payload['status'] = decision
    payload.setdefault('decided', datetime.now(timezone.utc).isoformat())
    # Persist rejection before deletion so an interrupted cleanup can never publish.
    save(manifest, payload)
    if decision == 'rejected':
        for path in assets:
            path.unlink()
    return payload


def is_approved(candidate_id):
    try:
        directory = folder(candidate_id)
        payload = json.loads((directory / 'review.json').read_text(encoding='utf-8'))
        return (payload.get('status') == 'approved' and bool(payload['assets'])
                and digest(payload['source_image']) == payload['source_sha256']
                and all(digest(owned_asset(directory, entry['name'])) == entry['sha256']
                        for entry in payload['assets']))
    except (OSError, ValueError, KeyError, TypeError):
        return False


def main():
    parser = argparse.ArgumentParser(description='Review a local video candidate; never uploads')
    parser.add_argument('--id', required=True)
    parser.add_argument('--decision', choices=['approved', 'rejected'], required=True)
    args = parser.parse_args()
    result = decide(args.id, args.decision)
    action = 'media deleted' if result['status'] == 'rejected' else 'media retained'
    print(f"{result['id']}: {result['status']}; {action}, source preserved.")


if __name__ == '__main__':
    main()

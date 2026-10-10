"""Explicit pinned public Wan I2V staging; never enables publishing."""

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from download_flux_weights import download

ROOT = Path(__file__).resolve().parents[1]
REPO = 'Wan-AI/Wan2.2-TI2V-5B-Diffusers'
REVISION = 'b8fff7315c768468a5333511427288870b2e9635'
DESTINATION = ROOT / 'models' / 'wan2.2-ti2v-5b'


def main():
    response = requests.get(f'https://huggingface.co/api/models/{REPO}/revision/{REVISION}?blobs=true', timeout=30)
    response.raise_for_status()
    metadata = response.json()
    if metadata['sha'] != REVISION or metadata.get('gated') or metadata.get('cardData', {}).get('license') != 'apache-2.0':
        raise RuntimeError('Pinned ungated Apache model metadata not verified')
    files = [entry for entry in metadata['siblings'] if entry['rfilename'] == 'model_index.json'
             or entry['rfilename'].startswith(('scheduler/', 'tokenizer/', 'text_encoder/', 'transformer/', 'vae/'))]
    size = sum(entry['size'] for entry in files)
    if size > 35 * 1024**3 or shutil.disk_usage(ROOT).free < size + 40 * 1024**3:
        raise RuntimeError('Video model download exceeds disk budget')
    DESTINATION.mkdir(parents=True, exist_ok=True)
    print(f'Pinned Wan I2V staging: {size / 1024**3:.2f} GiB; inference offline; publishing unchanged.', flush=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda entry: download(entry, REVISION, REPO, DESTINATION), files))
    (DESTINATION / 'installation.json').write_text(json.dumps({
        'repo': REPO, 'revision': REVISION, 'sha256_verified': True}, indent=2), encoding='utf-8')
    print('Wan weights verified; local generation acceptance still required.', flush=True)


if __name__ == '__main__':
    main()

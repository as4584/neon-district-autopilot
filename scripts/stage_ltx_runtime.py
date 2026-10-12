"""Stage the official Windows CUDA 13 wheel only; no package execution/install."""

from types import SimpleNamespace

from stage_ltx import ROOT, download_ranges

URL = 'https://download-r2.pytorch.org/whl/cu130/torch-2.11.0%2Bcu130-cp312-cp312-win_amd64.whl'
ENTRY = {
    'path': 'torch-2.11.0+cu130-cp312-cp312-win_amd64.whl',
    'bytes': 1915224818,
    'sha256': 'ef8beae16d781c3244ef28dc7bee6d8871c26bbde65d5bf66e902cb61972c4ab',
}


def main():
    root = ROOT / '.runtimes' / 'wheels'
    metadata = lambda: SimpleNamespace(size=ENTRY['bytes'], etag=ENTRY['sha256'], location=URL)
    path = download_ranges(ENTRY, root / ENTRY['path'], metadata, root, workers=8)
    print(f'Official CUDA wheel size and SHA256 verified: {path.name}')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Runtime staging failed: {type(exc).__name__}; partial retained.')
        raise SystemExit(1)

"""Create an isolated art-direction preview and evidence; never touches the queue."""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import yt_art_director
import yt_local_image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--id', required=True)
    parser.add_argument('--title', required=True)
    parser.add_argument('--scene', required=True)
    parser.add_argument('--attempt', type=int, default=0)
    parser.add_argument('--brief-only', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', args.id) or not 0 <= args.attempt <= 9:
        raise ValueError('Invalid preview ID or attempt')
    output = ROOT / 'test_outputs' / 'art_direction' / args.id
    if output.exists():
        raise ValueError('Preview already exists; choose a new ID')
    item = {'id': args.id, 'title': args.title, 'visual_scene': args.scene}
    plan = yt_art_director.direct(item, attempt=args.attempt, use_agent=not args.brief_only)
    output.mkdir(parents=True)
    if not args.brief_only:
        image = yt_local_image.generate(plan['prompt'], seed=plan['seed'])
        image.save(output / 'preview.png')
        plan['image_sha256'] = hashlib.sha256((output / 'preview.png').read_bytes()).hexdigest()
        plan['status'] = 'pending_review'
    (output / 'direction.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')
    print(f"Preview: {output}; method={plan['method']}; no upload")


if __name__ == '__main__':
    main()

"""Publish a strict structured report, never the production queue or raw logs."""

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE = ROOT / '.publication' / 'neon-district-autopilot'
REMOTE = 'https://github.com/as4584/neon-district-autopilot.git'
MODELS = {'ace-step', 'heartmula-3b-4bit', 'stable-audio-3-small-music'}
STATES = {'baseline', 'staging', 'license-blocked', 'downloaded-awaiting-runtime-review'}
SERIES = {'Chill Jazz / Rainy Nights', 'Rest / Sleep', 'legacy'}


def sanitize(payload):
    if payload.get('schema_version') != 1 or payload.get('window_days') != 14:
        raise ValueError('Unexpected report schema')
    if not re.fullmatch(r'[0-9T:+.\-Z]+', payload.get('checked_at', '')):
        raise ValueError('Invalid report timestamp')
    models = []
    for model in payload['models']:
        if model['id'] not in MODELS or model['state'] not in STATES:
            raise ValueError('Unreviewed model in report')
        models.append({'id': model['id'], 'state': model['state']})
    cohorts = []
    for row in payload['cohorts']:
        if row['model'] not in MODELS or row['series'] not in SERIES or row['duration_hours'] not in (1, 6, 12):
            raise ValueError('Unreviewed cohort')
        output = {key: row[key] for key in ('model', 'series', 'duration_hours')}
        for key in ('videos', 'views', 'watch_minutes', 'minutes_per_view'):
            value = row[key]
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or
                                      not 0 <= value <= 1e12):
                raise ValueError('Invalid numeric metric')
            output[key] = value
        if row['evidence'] not in ('inconclusive', 'eligible-for-review'):
            raise ValueError('Invalid evidence label')
        output['evidence'] = row['evidence']
        cohorts.append(output)
    return {'schema_version': 1, 'checked_at': payload['checked_at'],
            'window_days': 14, 'models': models, 'cohorts': cohorts}


def git(*args):
    result = subprocess.run(['git', '-C', str(SHOWCASE), *args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('Git operation failed; no raw output forwarded')
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--export-only', action='store_true')
    args = parser.parse_args()
    payload = sanitize(json.loads((ROOT / 'reports' / 'public' / 'experiments.json').read_text(encoding='utf-8')))
    target = SHOWCASE / 'findings' / 'experiments.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    if args.export_only:
        target.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
        print('Exported schema-filtered initial findings; no Git operation.')
        return
    remote = git('remote', 'get-url', 'origin')
    if remote != REMOTE:
        raise RuntimeError('Showcase origin does not match the approved public repository')
    if git('status', '--porcelain'):
        raise RuntimeError('Showcase checkout is dirty; automatic publication blocked')
    target.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    git('add', '--', 'findings/experiments.json')
    if not git('diff', '--cached', '--name-only'):
        print('No findings changes to publish.')
        return
    git('commit', '-m', 'Update sanitized equal-age experiment findings')
    git('push', 'origin', 'main')
    print('Published sanitized findings to the public showcase.')


if __name__ == '__main__':
    main()

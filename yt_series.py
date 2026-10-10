"""Idempotent playlist organization for Neon District's two listening series."""

import requests
import yt_upload

API = 'https://www.googleapis.com/youtube/v3'
SERIES = ('Chill Jazz / Rainy Nights', 'Rest / Sleep')


def request(token, method, resource, **kwargs):
    response = requests.request(method, f'{API}/{resource}',
                                headers={'Authorization': f'Bearer {token}'},
                                timeout=30, **kwargs)
    if not response.ok:
        raise RuntimeError(f'YouTube {resource} failed (HTTP {response.status_code})')
    return response.json()


def listing(token, resource, **params):
    items = []
    while True:
        payload = request(token, 'GET', resource, params={**params, 'maxResults': 50})
        items.extend(payload.get('items', []))
        if not payload.get('nextPageToken'):
            return items
        params['pageToken'] = payload['nextPageToken']


def classify(item):
    if item.get('series') in SERIES:
        return item['series']
    text = (item.get('title', '') + ' ' + item.get('prompt', '')).lower()
    if any(word in text for word in ('sleep', 'meditation', 'rest')):
        return SERIES[1]
    return SERIES[0]


def ensure_playlists(token):
    channel = request(token, 'GET', 'channels', params={'part': 'snippet', 'mine': 'true'})['items'][0]
    if channel['id'] != 'UCWO8s_ObXOM5f_9YocsTvuQ':
        raise RuntimeError('Channel identity mismatch; playlist edits blocked')
    existing = {item['snippet']['title']: item['id'] for item in
                listing(token, 'playlists', part='snippet', mine='true')}
    for title in SERIES:
        if title not in existing:
            result = request(token, 'POST', 'playlists', params={'part': 'snippet,status'}, json={
                'snippet': {'title': title,
                            'description': 'Instrumental music for relaxed, unhurried listening. Neon District Archive.'},
                'status': {'privacyStatus': 'public'},
            })
            existing[title] = result['id']
    return {title: existing[title] for title in SERIES}


def add_video(token, playlist_id, video_id, existing=None):
    if existing is None:
        existing = {item['contentDetails']['videoId'] for item in
                    listing(token, 'playlistItems', part='contentDetails', playlistId=playlist_id)}
    if video_id in existing:
        return False
    request(token, 'POST', 'playlistItems', params={'part': 'snippet'}, json={
        'snippet': {'playlistId': playlist_id,
                    'resourceId': {'kind': 'youtube#video', 'videoId': video_id}},
    })
    existing.add(video_id)
    return True


def organize_video(item, video_id):
    token = yt_upload.get_access_token()
    playlists = ensure_playlists(token)
    add_video(token, playlists[classify(item)], video_id)

#!/usr/bin/env python3
"""Disabled-by-default Buffer refill. No write calls unless --live and activation gate."""
import argparse
import base64
import hashlib
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone, time
from pathlib import Path
from zoneinfo import ZoneInfo
import plan

STATE_PATH = 'data/publication-ledger.json'
ORG = '6af5e859fc6295e47dd61383'
CHANNELS = {s: plan.CONFIG[s + '_channel_id'] for s in ('instagram', 'facebook')}
POST_FIELDS = 'id channelId status text dueAt assets { ... on ImageAsset { source } }'
POSTS = '''query($input: PostsInput!, $after: String) {
 posts(input: $input, first: 100, after: $after) {
 edges { node { %s } } pageInfo { endCursor hasNextPage }
 }}''' % POST_FIELDS
CREATE = '''mutation($input: CreatePostInput!) { createPost(input: $input) {
 ... on PostActionSuccess { post { %s } }
 ... on MutationError { message }
 }}''' % POST_FIELDS


def request(url, token, body=None, method=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json',
                 'Accept': 'application/json', 'User-Agent': 'MorningMullyScheduler'}, method=method)
    # No automatic mutation retries: a timeout can mean that Buffer accepted the post.
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response)
    except Exception:
        raise RuntimeError('API request failed; inspect ledger before retrying (response/token suppressed).') from None


class Buffer:
    def __init__(self, token):
        if not token:
            raise RuntimeError('BUFFER_API_KEY is missing')
        self.token = token

    def query(self, query, variables=None):
        result = request('https://api.buffer.com', self.token, {'query': query, 'variables': variables or {}})
        if result.get('errors') or not result.get('data'):
            raise RuntimeError('Buffer GraphQL error; no mutation will be retried automatically')
        return result['data']

    def posts(self):
        result, after = [], None
        while True:
            page = self.query(POSTS, {'input': {'organizationId': ORG,
                'filter': {'channelIds': list(CHANNELS.values())}}, 'after': after})['posts']
            result.extend(e['node'] for e in page['edges'])
            if not page['pageInfo']['hasNextPage']:
                return result
            cursor = page['pageInfo']['endCursor']
            if not cursor or cursor == after:
                raise RuntimeError('Invalid pagination; refusing incomplete queue count')
            after = cursor

    def channels(self):
        return self.query('''query { channels(input: {organizationId: "%s"}) {
          id service timezone isDisconnected isLocked isQueuePaused
          postingSchedule { day times paused }
        }}''' % ORG)['channels']

    def create(self, payload):
        result = self.query(CREATE, {'input': payload})['createPost']
        if not result.get('post'):
            raise RuntimeError('Buffer rejected post; intent retained for manual reconciliation')
        return result['post']


class Ledger:
    """Each intent is durably committed BEFORE a Buffer mutation, using SHA compare-and-swap."""
    def __init__(self):
        self.token = os.environ.get('GITHUB_TOKEN', '')
        repo = os.environ.get('GITHUB_REPOSITORY', '')
        if not self.token or repo != 'claudecodeguy/morning-mully-social':
            raise RuntimeError('Live ledger requires the intended GitHub Actions repository')
        self.url = 'https://api.github.com/repos/' + repo + '/contents/' + STATE_PATH
        record = request(self.url + '?ref=main', self.token)
        self.sha = record['sha']
        self.data = json.loads(base64.b64decode(record['content']))
        validate_state(self.data)

    def save(self):
        encoded = base64.b64encode((json.dumps(self.data, indent=2) + '\n').encode()).decode()
        record = request(self.url, self.token, {'message': 'Record social publishing checkpoint [skip ci]',
            'branch': 'main', 'sha': self.sha, 'content': encoded}, 'PUT')
        self.sha = record['content']['sha']


def validate_state(state):
    if state.get('version') != 1 or not isinstance(state.get('entries'), list):
        raise RuntimeError('Missing or invalid ledger; never reset publication history')
    keys = [e['post_id'] for e in state['entries']]
    if len(keys) != len(set(keys)):
        raise RuntimeError('Duplicate ledger content IDs')


def validate_library(remote=False):
    audit = {r['post_id']: r for r in plan.rows('asset_audit.csv')}
    records = plan.rows('memes.csv') + plan.rows('statistics.csv')
    expected = {f'M{i:03}' for i in range(1, 32)} | {f'S{i:03}' for i in range(1, 31)}
    if len(records) != 61 or {r['post_id'] for r in records} != expected or set(audit) != expected:
        raise RuntimeError('Library IDs/counts do not match 31 memes and 30 statistics')
    paths = set()
    for row in records:
        a = audit[row['post_id']]
        if row['image_path'] != a['image_path'] or row['source_image_filename'] != a['source_filename']:
            raise RuntimeError('Image mapping mismatch: ' + row['post_id'])
        url = plan.image_url(row)
        data = (plan.ROOT / row['image_path']).read_bytes()
        if hashlib.sha256(data).hexdigest() != a['sha256'] or not data.startswith(b'\xff\xd8'):
            raise RuntimeError('Image checksum/format mismatch: ' + row['post_id'])
        if row['image_path'] in paths or not row['instagram_caption'] or not row['alt_text']:
            raise RuntimeError('Duplicate path or missing content: ' + row['post_id'])
        if any(row.get(k) for k in ('buffer_ig_id', 'buffer_fb_id', 'published_at')):
            raise RuntimeError('Legacy publication IDs need ledger import: ' + row['post_id'])
        if len(plan.make_captions(row)['instagram']) > 2200:
            raise RuntimeError('Instagram caption exceeds limit: ' + row['post_id'])
        paths.add(row['image_path'])
        if remote:
            with urllib.request.urlopen(url, timeout=30) as response:
                if hashlib.sha256(response.read()).hexdigest() != a['sha256']:
                    raise RuntimeError('Hosted image mismatch: ' + row['post_id'])
    if paths != {p.relative_to(plan.ROOT).as_posix() for p in (plan.ROOT / 'images').rglob('*.jpg')}:
        raise RuntimeError('Unmapped image files')
    return records


def payload(row, service, due):
    return {'channelId': CHANNELS[service], 'text': plan.make_captions(row)[service],
        'schedulingType': 'automatic', 'mode': 'customScheduled', 'dueAt': due,
        'assets': [{'image': {'url': plan.image_url(row), 'metadata': {'altText': row['alt_text']}}}],
        'metadata': {service: {'type': 'post', **({'shouldShareToFeed': True} if service == 'instagram' else {})}}}


def instant(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def occupied(posts, channel):
    # Include drafts, approvals, and errors conservatively; only sent posts release capacity.
    return sum(p['channelId'] == channel and p['status'] != 'sent' for p in posts)


def matching(post, body):
    return post['channelId'] == body['channelId'] and post['text'] == body['text']


def reconcile(ledger, posts):
    by_id = {p['id']: p for p in posts}
    for entry in ledger.data['entries']:
        for service, record in entry['channels'].items():
            if record['status'] == 'pending':
                raise RuntimeError('Uncertain intent for ' + entry['post_id'] + '/' + service +
                    '; reconcile in Buffer and ledger manually before any retry')
            post = by_id.get(record['id'])
            if not post or post['status'] in ('error', 'draft', 'needs_approval'):
                raise RuntimeError('Missing, failed, or unscheduled Buffer post: ' + record['id'])
            record['status'] = post['status']
    ledger.save()


def refill(api, ledger, records, now, live=False):
    validate_state(ledger.data)
    posts = api.posts()
    channels = {c['id']: c for c in api.channels()}
    for service, cid in CHANNELS.items():
        c = channels[cid]
        if c['service'] != service or any(c[x] for x in ('isDisconnected', 'isLocked', 'isQueuePaused')):
            raise RuntimeError('Channel unavailable: ' + service)
    if live:
        reconcile(ledger, posts)
    used = {e['post_id'] for e in ledger.data['entries']}
    last_kind = ledger.data['entries'][-1]['kind'] if ledger.data['entries'] else 'stat'
    floor = max([now] + [instant(p['dueAt']) for p in posts if p.get('dueAt') and p['status'] != 'sent'])
    bank = {kind: [r for r in records if r['content_type'] == kind and plan.eligible(r) and r['post_id'] not in used]
            for kind in ('meme', 'stat')}
    log = []
    # Repair a known partial pair before considering more content. Unknown intents always fail closed.
    partial = [e for e in ledger.data['entries'] if len(e['channels']) < 2]
    if len(partial) > 1:
        raise RuntimeError('Multiple incomplete pairs require manual review')
    start_day = floor.astimezone(ZoneInfo(plan.CONFIG["timezone"])).date()
    for n in range(92):
        if any(occupied(posts, cid) >= 10 for cid in CHANNELS.values()):
            log.append('Queue capacity reached; no more writes.'); break
        entry = partial.pop(0) if partial else None
        if entry:
            row = next(r for r in records if r['post_id'] == entry['post_id'])
            if not plan.eligible(row):
                raise RuntimeError('Partial pair content is now held')
        else:
            day = start_day + timedelta(days=n)
            kind = plan.CONFIG['calendar'][day.strftime('%A')]
            if kind == 'newsletter':
                log.append(str(day) + ': newsletter reserved; approved graphic integration pending'); continue
            expected = 'meme' if last_kind == 'stat' else 'stat'
            if kind != expected:
                continue
            if not bank[kind]:
                log.append('BLOCKED: no approved ' + kind + '; stopping to preserve alternation'); break
            row = bank[kind][0]
            dues = {}
            for service, cid in CHANNELS.items():
                c = channels[cid]
                slots = [t for s in c['postingSchedule'] if s['day'] == day.strftime('%a').lower()
                         and not s['paused'] for t in s['times']]
                candidates = [datetime.combine(day, time.fromisoformat(t), ZoneInfo(c['timezone'])) for t in slots]
                future = [t for t in candidates if t > floor + timedelta(minutes=15)]
                if future:
                    dues[service] = min(future).astimezone(timezone.utc).isoformat()
            if len(dues) != 2:
                continue
            bank[kind].pop(0)
            entry = {'post_id': row['post_id'], 'kind': kind, 'due': dues, 'channels': {}}
            ledger.data['entries'].append(entry)
            last_kind = kind
        for service, cid in CHANNELS.items():
            if service in entry['channels']:
                continue
            body = payload(row, service, entry['due'][service])
            if instant(body['dueAt']) <= now + timedelta(minutes=15):
                raise RuntimeError('Partial pair schedule expired; manual review required')
            if any(matching(p, body) for p in posts):
                raise RuntimeError('Existing matching caption detected; reconcile history before proceeding')
            log.append(f"{'SCHEDULE' if live else 'WOULD SCHEDULE'} {row['post_id']} {service} {body['dueAt']}")
            if live:
                # Fresh queue count catches manual additions during this run.
                if occupied(api.posts(), cid) >= 10:
                    raise RuntimeError('Queue filled during run; partial pair retained')
                entry['channels'][service] = {'status': 'pending', 'payload': body}
                ledger.save()  # Failure here prevents the mutation.
                post = api.create(body)
                entry['channels'][service] = {'id': post['id'], 'status': 'accepted', 'payload': body}
                ledger.save()
                check = next((p for p in api.posts() if p['id'] == post['id']), None)
                if (not check or check['status'] != 'scheduled' or not matching(check, body)
                        or instant(check['dueAt']) != instant(body['dueAt']) or not check.get('assets')):
                    raise RuntimeError('Buffer scheduling readback failed; recorded ID retained')
                entry['channels'][service]['status'] = check['status']
                ledger.save()
            else:
                post = {'id': 'preview-' + row['post_id'] + service, 'channelId': cid,
                        'text': body['text'], 'dueAt': body['dueAt'], 'status': 'scheduled'}
            posts.append(post)
        # Existing incomplete pair can be followed only on a later date.
        floor = max(floor, *(instant(t) for t in entry['due'].values()))
    return log


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--remote-images', action='store_true')
    parser.add_argument('--connected', action='store_true', help='Read Buffer without writing')
    args = parser.parse_args()
    if args.live and (os.environ.get('PUBLISHING_ENABLED') != 'true' or
                     os.environ.get('GITHUB_REF') != 'refs/heads/main'):
        raise RuntimeError('Publishing is disabled or this is not main')
    records = validate_library(args.remote_images or args.live)
    print('Verified 61 records, file mappings, JPEG signatures and SHA256 checksums.')
    if args.live or args.connected:
        api = Buffer(os.environ.get('BUFFER_API_KEY'))
        ledger = Ledger() if args.live else type('PreviewLedger', (), {
            'data': json.loads((plan.ROOT / STATE_PATH).read_text())})()
        for line in refill(api, ledger, records, datetime.now(timezone.utc), args.live):
            print(line)
    else:
        print('OFFLINE DRY RUN: no Buffer access. Eligible memes:', sum(plan.eligible(r) for r in records if r['content_type'] == 'meme'))
        print('Eligible statistics:', sum(plan.eligible(r) for r in records if r['content_type'] == 'stat'))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('::error::' + str(exc), file=sys.stderr)
        sys.exit(1)

#!/usr/bin/env python3
"""Mac-independent, no-AI-key newsletter publishing with durable Buffer intents."""
import argparse
import base64
import hashlib
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
import newsletter
import plan
import publish

REPO = 'claudecodeguy/morning-mully-social'
ROOT = plan.ROOT


def fetch(url, limit=12_000_000):
    req = urllib.request.Request(url, headers={'User-Agent': 'MorningMullyCloud/1.0'})
    with urllib.request.urlopen(req, timeout=30) as response:
        body = response.read(limit + 1)
    if len(body) > limit:
        raise ValueError('Download exceeded size limit')
    return body


class Store:
    def __init__(self, token):
        if not token or os.environ.get('GITHUB_REPOSITORY') != REPO:
            raise RuntimeError('Cloud writes require the intended GitHub Actions repository')
        self.token = token

    def get(self, path):
        url = f'https://api.github.com/repos/{REPO}/contents/{path}?ref=main'
        req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + self.token,
            'Accept': 'application/vnd.github+json', 'User-Agent': 'MorningMullyCloud'})
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                record = json.load(response)
            return base64.b64decode(record['content']), record['sha']
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None, None
            raise RuntimeError('GitHub state read failed; no Buffer creation permitted') from None

    def put(self, path, body, sha=None):
        payload = {'message': 'Record newsletter checkpoint [skip ci]', 'branch': 'main',
                   'content': base64.b64encode(body).decode()}
        if sha:
            payload['sha'] = sha
        return publish.request(f'https://api.github.com/repos/{REPO}/contents/{path}', self.token, payload, 'PUT')


class History:
    def __init__(self, issue, store=None):
        self.path = 'data/newsletter-' + issue['issue_date'] + '-publication.json'
        self.store, self.sha = store, None
        if store:
            raw, self.sha = store.get(self.path)
            self.data = json.loads(raw) if raw else {'issue_date': issue['issue_date'], 'channels': {}}
        else:
            self.data = newsletter.load_history(issue['issue_date'])
        if self.data['issue_date'] != issue['issue_date'] or not isinstance(self.data['channels'], dict):
            raise RuntimeError('Invalid newsletter history')
        if self.data.get('issue_url') not in (None, issue['issue_url']):
            raise RuntimeError('Another issue already used this date; manual review required')
        self.data['issue_url'] = issue['issue_url']

    def save(self):
        if not self.store:
            raise RuntimeError('A durable remote store is required before publishing')
        result = self.store.put(self.path, (json.dumps(self.data, indent=2, ensure_ascii=False) + '\n').encode(), self.sha)
        self.sha = result['content']['sha']


def font(size, bold=False):
    from PIL import ImageFont
    paths = ['/usr/share/fonts/truetype/dejavu/DejaVuSans' + ('-Bold' if bold else '') + '.ttf',
             '/System/Library/Fonts/Supplemental/Arial' + (' Bold' if bold else '') + '.ttf']
    for p in paths:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    raise RuntimeError('Newsletter font missing')


def lines(draw, text, face, width):
    output, current = [], ''
    for word in text.split():
        candidate = (current + ' ' + word).strip()
        if draw.textlength(candidate, font=face) > width and current:
            output.append(current)
            current = word
        else:
            current = candidate
    if current:
        output.append(current)
    return output


def render(issue, output, download=fetch):
    """Deterministic branded template: remote artwork failure becomes a text-only cover."""
    from PIL import Image, ImageDraw, ImageOps
    green, cream, gold = '#1e5631', '#f7f0df', '#b29438'
    image = Image.new('RGB', (1080, 1350), cream)
    draw = ImageDraw.Draw(image)
    draw.text((55, 45), 'MORNING MULLY', font=font(52, True), fill=green)
    draw.line((55, 120, 1025, 120), fill=gold, width=3)
    day = datetime.fromisoformat(issue['issue_date'])
    draw.text((55, 155), day.strftime('%A, %B %d, %Y').upper(), font=font(25, True), fill=green)
    title = issue['title'].strip()
    if not title or len(title) > 300:
        raise RuntimeError('Missing or excessively long newsletter title')
    for size in range(70, 27, -2):
        face = font(size, True)
        wrapped = lines(draw, title, face, 970)
        if len(wrapped) * (size + 12) <= 295 and all(draw.textlength(x, font=face) <= 970 for x in wrapped):
            break
    else:
        raise RuntimeError('Headline cannot fit safely')
    y = 220
    for line in wrapped:
        draw.text((55, y), line, font=face, fill=green)
        y += size + 12
    # Reuse real artwork from this issue only; skip recurring labels/banner/footer.
    artwork, source = None, None
    for candidate in issue.get('images', []):
        url = candidate['url']
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != 'https' or parsed.hostname != 'media.beehiiv.com':
            continue
        if any(t in url.lower() for t in ('mm-label', 'mm-banner', 'mm-divider', '/logo/')):
            continue
        try:
            candidate_image = Image.open(io.BytesIO(download(url)))
            if candidate_image.width < 600 or candidate_image.height < 250:
                continue
            candidate_image.load()
            artwork = ImageOps.contain(candidate_image.convert('RGB'), (970, 430))
            source = url
            break
        except Exception:
            continue
    if artwork:
        image.paste(artwork, ((1080-artwork.width)//2, 555+(430-artwork.height)//2))
        kind = 'newsletter_artwork'
    else:
        # Entirely local fallback; no hosted photo or image-generation service required.
        draw.rectangle((55, 555, 1025, 985), fill=green)
        logo = Image.open(ROOT/'assets/newsletters/templates/morning-mully-logo.png').convert('RGB')
        logo.thumbnail((325, 325))
        image.paste(logo, ((1080-logo.width)//2, 570))
        draw.text((120, 915), 'GOLF NEWS. GOOD DEALS. A FEW LAUGHS.', font=font(29, True), fill=cream)
        kind = 'local_fallback'
    draw.line((55, 1020, 1025, 1020), fill=gold, width=3)
    draw.text((55, 1050), 'IN TODAY’S MORNING MULLY', font=font(35, True), fill=green)
    draw.text((55, 1110), 'The latest stories, picks and golf worth sharing.', font=font(29), fill=green)
    draw.rectangle((0, 1190, 1080, 1350), fill=green)
    draw.text((55, 1220), 'Read the full issue', font=font(43, True), fill=cream)
    draw.text((55, 1280), 'Link in bio  •  morningmully.beehiiv.com', font=font(25), fill=cream)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, 'PNG', optimize=True)
    return {'renderer': kind, 'source_artwork': source, 'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}


def captions(issue):
    title = issue['title'].strip()
    base = f"Today's Morning Mully is out.\n\n{title}\n\nGolf news, a few laughs, and something to send your foursome."
    tags = '#MorningMully #GolfNews #WeekendGolfer #GolfLife #Golf'
    url = issue['issue_url'] + '?utm_source=facebook&utm_medium=social&utm_campaign=newsletter_' + issue['issue_date']
    return {'instagram': base + '\n\nRead the full issue through the link in bio.\n\n' + tags,
            'facebook': base + '\n\nRead today’s issue: ' + url + '\n\n' + tags}


def confirm(post, body):
    if not publish.matching(post, body) or not post.get('assets'):
        raise RuntimeError('Buffer readback does not match the saved newsletter payload')
    if post['status'] == 'error':
        raise RuntimeError('Buffer reports delivery error; do not create a replacement automatically')
    return post['status']


def deliver(api, history, issue):
    """At most one mutation per missing channel; all ambiguous outcomes stop safely."""
    channels = {c['id']: c for c in api.channels()}
    posts = api.posts()
    for service, cid in publish.CHANNELS.items():
        channel = channels[cid]
        if channel['service'] != service or any(channel[k] for k in ('isDisconnected','isLocked','isQueuePaused')):
            raise RuntimeError('Channel unavailable: ' + service)
        old = history.data['channels'].get(service)
        if old:
            if old.get('status') == 'sent':
                print(service + ': already sent; no creation')
                continue
            post = next((p for p in posts if p['id'] == old.get('buffer_id')), None)
            if not post and old.get('status') == 'pending':
                matches = [p for p in posts if publish.matching(p, old['payload'])]
                post = matches[0] if len(matches) == 1 else None
            if not post:
                raise RuntimeError('Uncertain/missing newsletter intent; manual reconciliation required: ' + service)
            status = confirm(post, old['payload'])
            old.update(buffer_id=post['id'], status=status)
            if status == 'sent':
                old['sent_at'] = datetime.now(newsletter.TZ).isoformat()
            history.save()
            if status != 'sent':
                raise RuntimeError('Newsletter still pending delivery: ' + service)
            continue
        posts = api.posts()
        body = {'channelId': cid, 'mode': 'shareNow', 'schedulingType': 'automatic',
            'text': history.data['captions'][service], 'assets': [{'image': {
                'url': history.data['image_url'], 'metadata': {'altText': history.data['alt_text']}}}],
            'metadata': {service: {'type': 'post', **({'shouldShareToFeed': True} if service == 'instagram' else {})}}}
        if any(publish.matching(p, body) for p in posts):
            raise RuntimeError('Unrecorded matching post detected; reconcile before creation')
        if publish.occupied(posts, cid) >= 10:
            raise RuntimeError('Queue is full: ' + service + '; wait for later retry, never remove queued content')
        history.data['channels'][service] = {'status': 'pending', 'payload': body}
        history.save()  # Durable checkpoint before the irreversible mutation.
        post = api.create(body)
        old = history.data['channels'][service]
        old.update(buffer_id=post['id'], status='accepted')
        history.save()
        check = None
        for attempt in range(4):
            check = next((p for p in api.posts() if p['id'] == post['id']), None)
            if check and check['status'] in ('sent', 'error'):
                break
            if attempt < 3:
                time.sleep(5)
        if not check:
            raise RuntimeError('Accepted post not yet visible; keep ID and retry readback only')
        status = confirm(check, body)
        old['status'] = status
        if status == 'sent':
            old['sent_at'] = datetime.now(newsletter.TZ).isoformat()
        history.save()
        if status != 'sent':
            raise RuntimeError('Post accepted, awaiting delivery; next run will read back the same ID')
        print(service + ': sent ' + post['id'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--feed-file')
    parser.add_argument('--output-dir', default='reports/cloud-newsletter')
    parser.add_argument('--now', help='Offline dry-run clock only')
    parser.add_argument('--watchdog', action='store_true')
    args = parser.parse_args()
    if args.live and (args.feed_file or args.now or os.environ.get('PUBLISHING_ENABLED') != 'true'
                      or os.environ.get('GITHUB_REF') != 'refs/heads/main'):
        raise RuntimeError('Live mode requires enabled main and real current RSS/time')
    now = datetime.fromisoformat(args.now) if args.now and not args.live else datetime.now(newsletter.TZ)
    local = now.astimezone(newsletter.TZ)
    if local.weekday() not in (0,2,4) or (args.live and not args.watchdog and not 11 <= local.hour <= 18):
        print('Outside newsletter publishing window; no writes')
        return
    store = Store(os.environ.get('GITHUB_TOKEN')) if args.live else None
    if args.watchdog:
        path = 'data/newsletter-' + str(local.date()) + '-publication.json'
        raw, _ = store.get(path) if store else (None,None)
        data = json.loads(raw) if raw else newsletter.load_history(str(local.date()))
        if any(data['channels'].get(s,{}).get('status') != 'sent' for s in publish.CHANNELS):
            raise RuntimeError('Newsletter delivery incomplete for ' + str(local.date()))
        if args.live:
            actual = {p['id']: p for p in publish.Buffer(os.environ.get('BUFFER_API_KEY')).posts()}
            for service in publish.CHANNELS:
                record = data['channels'][service]
                post = actual.get(record.get('buffer_id'))
                if not post or post['status'] != 'sent':
                    raise RuntimeError('Watchdog cannot confirm Buffer delivery: ' + service)
        print('Watchdog: both channels sent today’s newsletter')
        return
    xml = Path(args.feed_file).read_bytes() if args.feed_file else fetch(plan.CONFIG['feed_url'],3_000_000)
    issue = newsletter.select_issue(xml, now)
    if not issue:
        if local.hour >= 18:
            raise RuntimeError('No same-day newsletter by final retry; alert required')
        print('No same-day issue yet; a later cloud run will retry')
        return
    history = History(issue, store)
    if all(history.data['channels'].get(s,{}).get('status') == 'sent' for s in publish.CHANNELS):
        print('Both channels already sent this issue; zero Buffer writes')
        return
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    if not history.data.get('image_url'):
        output = out/'newsletter.png'
        meta = render(issue, output)
        history.data.update(captions=captions(issue),alt_text='Morning Mully newsletter: ' + issue['title'],graphic=meta)
        if args.live:
            path = 'assets/newsletters/' + issue['issue_date'] + '-cloud.png'
            _, existing_sha = store.get(path)
            result = store.put(path, output.read_bytes(), existing_sha)
            # Immutable raw URL is immediately available and does not depend on Pages rebuilding.
            url = f"https://raw.githubusercontent.com/{REPO}/{result['commit']['sha']}/{path}"
            if hashlib.sha256(fetch(url)).hexdigest() != meta['sha256']:
                raise RuntimeError('Public graphic checksum failed; no Buffer writes')
            history.data['image_url'] = url
            history.save()
    if not args.live:
        (out/'preview.json').write_text(json.dumps(history.data,indent=2,ensure_ascii=False)+'\n')
        print('DRY RUN: rendered cover/captions; zero Buffer or GitHub writes')
        return
    # Do not call Buffer again until persisted graphic metadata and delivery intent are available.
    deliver(publish.Buffer(os.environ.get('BUFFER_API_KEY')),history,issue)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('::error::' + str(exc), file=sys.stderr)
        sys.exit(1)

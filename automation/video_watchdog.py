#!/usr/bin/env python3
"""Read-only checks for daily video delivery and the next 24 hours of coverage."""
import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import plan
import publish
import video_library


def inspect(posts, channels, ledger, videos, now):
    publish.validate_state(ledger)
    tz = ZoneInfo(plan.CONFIG['timezone'])
    local = now.astimezone(tz)
    issues = []
    by_channel = {c['id']: c for c in channels}
    by_id = {p['id']: p for p in posts}
    entries = [e for e in ledger['entries'] if e['kind'] == 'video']
    used = {e['post_id'] for e in entries}
    remaining = sum(r['approval_status'] == 'APPROVED' and r['post_id'] not in used for r in videos)
    if remaining <= 7:
        issues.append(f'LOW STOCK: {remaining} approved, unscheduled videos remain; upload and approve more.')
    for service, cid in publish.ALL_CHANNELS.items():
        channel = by_channel.get(cid)
        if (not channel or channel.get('service') != service or any(channel.get(k, True)
                for k in ('isDisconnected', 'isLocked', 'isQueuePaused'))):
            issues.append(f'CHANNEL: {service} is missing, disconnected, locked or paused; check Buffer.')
        count = publish.occupied(posts, cid)
        if count > 10:
            issues.append(f'CAPACITY: {service} has {count} occupied posts (Free-plan limit 10).')
    for entry in entries:
        for service in publish.ALL_CHANNELS:
            record = entry['channels'].get(service)
            if record is None and service in entry['due'] and publish.instant(entry['due'][service]) > now + timedelta(hours=24):
                continue  # Normal rolling reservation; the next refill can complete this later slot.
            if record is None:
                issues.append(f'PARTIAL: {entry["post_id"]}/{service} is missing; refill must complete this channel.')
                continue
            if record['status'] == 'pending':
                issues.append(f'UNCERTAIN: {entry["post_id"]}/{service}; inspect Buffer before retrying to avoid duplicates.')
                continue
            if record['status'] == 'sent':
                continue  # Permanent confirmed history can outlive Buffer retention.
            post = by_id.get(record.get('id'))
            if not post or post['status'] not in ('scheduled', 'sending', 'sent'):
                issues.append(f'POST: {entry["post_id"]}/{service} is missing, failed or unscheduled in Buffer.')
    for offset in (0, 1):
        day = local.date() + timedelta(days=offset)
        preferred = datetime.combine(day, datetime.strptime(plan.CONFIG['video_time'], '%H:%M').time(), tz)
        daily = [e for e in entries if any(publish.instant(t).astimezone(tz).date() == day
                                         for t in e['due'].values())]
        for service, cid in publish.ALL_CHANNELS.items():
            records = [(e, e['channels'].get(service)) for e in daily]
            expected = [publish.instant(e['due'][service]) for e,r in records if service in e['due']]
            due = max(expected) if expected else preferred
            confirmed = any(r and r['status'] == 'sent' for _,r in records)
            actual = any(r and by_id.get(r.get('id'), {}).get('status') == 'sent' for _,r in records)
            if confirmed or actual:
                continue
            if offset == 0 and now >= due + timedelta(minutes=90):
                issues.append(f'MISSING DELIVERY: {day} {service}; no confirmed daily video after {due.astimezone(tz):%H:%M} Toronto.')
            elif now < due <= now + timedelta(hours=24):
                queued = any(r and (p := by_id.get(r.get('id'))) and p['status'] == 'scheduled'
                    and p['channelId'] == cid and p.get('dueAt')
                    and publish.instant(p['dueAt']) == publish.instant(e['due'][service])
                    and publish.instant(p['dueAt']).astimezone(tz).date() == day for e,r in records)
                if not queued:
                    issues.append(f'SCHEDULE GAP: {day} {service} daily video is not queued; check capacity and existing post conflicts.')
    return {'checked_at': now.isoformat(), 'timezone': plan.CONFIG['timezone'],
            'approved_unscheduled_videos': remaining, 'issues': issues, 'healthy': not issues}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', help='Offline read-only Buffer snapshot')
    parser.add_argument('--now', help='Offline test clock only; requires --snapshot')
    parser.add_argument('--output', default='/tmp/morning-mully-video-health.json')
    args = parser.parse_args()
    if args.now and not args.snapshot:
        parser.error('--now requires --snapshot')
    ledger = json.loads((plan.ROOT / publish.STATE_PATH).read_text())
    if args.snapshot:
        snapshot = json.loads(Path(args.snapshot).read_text())
        if not snapshot.get('complete'):
            raise RuntimeError('Incomplete Buffer snapshot; refusing a healthy result')
        posts, channels = snapshot['posts'], snapshot['channels']
    else:
        api = publish.Buffer(os.environ.get('BUFFER_API_KEY'))
        posts, channels = api.posts(), api.channels()
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(timezone.utc)
    report = inspect(posts, channels, ledger, video_library.read(), now)
    Path(args.output).write_text(json.dumps(report, indent=2) + '\n')
    for issue in report['issues']:
        print(issue)
    if report['healthy']:
        print('Video health: all checks passed.')
    return 0 if report['healthy'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

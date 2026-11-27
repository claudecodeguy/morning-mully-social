"""Activation-gated mixed media queue, sharing the existing durable ledger."""
import copy
import json
from datetime import datetime, timedelta, timezone, time
from zoneinfo import ZoneInfo
import plan
import video_library


def video_payload(row, service, due):
    import publish
    metadata = {'instagram': {'type':'reel','shouldShareToFeed':True},
                'facebook': {'type':'reel'},
                'youtube': {'type':'short','title':row['youtube_title'], 'categoryId':'17',
                            'privacy':'public','madeForKids':False,'notifySubscribers':True}}
    return {'channelId':publish.ALL_CHANNELS[service], 'text':video_library.captions(row)[service],
            'needsApproval':False, 'schedulingType':'automatic','mode':'customScheduled','dueAt':due,
            'assets':[{'video':{'url':row['public_url']}}], 'metadata':{service:metadata[service]}}


def newsletter_deadline(service, now):
    """First possible newsletter slot still needing capacity on this channel."""
    tz = ZoneInfo(plan.CONFIG['timezone'])
    for n in range(8):
        day = now.astimezone(tz).date() + timedelta(days=n)
        if plan.CONFIG['calendar'][day.strftime('%A')] != 'newsletter':
            continue
        path = plan.ROOT / 'data' / f'newsletter-{day}-publication.json'
        history = json.loads(path.read_text()) if path.exists() else {}
        if history.get('channels', {}).get(service, {}).get('status') == 'sent':
            continue
        return datetime.combine(day, time(11), tz)
    raise RuntimeError('No newsletter deadline found')


def capacity_limit(service, kind, due, posts, now):
    import publish
    if service == 'youtube':
        return 10
    if kind != 'video':
        return 9
    deadline = newsletter_deadline(service, now)
    cid = publish.ALL_CHANNELS[service]
    # The tenth slot is safe if a scheduled post releases it BEFORE the newsletter.
    releases = [publish.instant(p['dueAt']) for p in posts if p['channelId'] == cid
                and p['status'] == 'scheduled' and p.get('dueAt')]
    return 10 if due < deadline or any(now < t < deadline for t in releases) else 9


def video_slots(day, now, posts, services):
    """Prefer 19:00; use a same-day alternative instead of skipping the date."""
    import publish
    tz = ZoneInfo(plan.CONFIG['timezone'])
    preferred = plan.CONFIG['video_time']
    times = list(dict.fromkeys([preferred, '18:00', '17:30', '20:00', '21:00',
                               '16:30', '15:00', '12:00', '09:00', '08:00', '10:00']))
    candidates = [datetime.combine(day,time.fromisoformat(t),tz) for t in times]
    def possible(t, service, spaced=True):
        cid = services[service]
        busy = [publish.instant(p.get('sentAt') or p['dueAt']) for p in posts
                if p['channelId'] == cid and (p.get('sentAt') or p.get('dueAt'))]
        return (t > now + timedelta(minutes=15)
                and publish.occupied(posts,cid) < capacity_limit(service,'video',t,posts,now)
                and not any(abs(t-b) < timedelta(hours=2) if spaced else t == b for b in busy))
    # Keep the three platforms together when possible; a full channel cannot block the others.
    for t in candidates:
        if all(possible(t, s) for s in services):
            return {s:t.astimezone(timezone.utc).isoformat() for s in services}, False
    result = {}
    reduced_spacing = False
    for service in services:
        chosen = next((t for t in candidates if possible(t, service)), None)
        if chosen is None:
            chosen = next((t for t in candidates if possible(t, service, False)), None)
            reduced_spacing |= chosen is not None
        # Keep a durable plan for a temporarily full channel; healthy channels still proceed.
        planned = chosen or datetime.combine(day,time.fromisoformat(preferred),tz)
        result[service] = planned.astimezone(timezone.utc).isoformat()
    return result, reduced_spacing


def refill(api, ledger, images, videos, now, live=False):
    import publish
    publish.validate_state(ledger.data)
    if not live:
        ledger = copy.deepcopy(ledger)
    posts = api.posts()
    channels = {c['id']:c for c in api.channels()}
    for service,cid in publish.ALL_CHANNELS.items():
        c = channels.get(cid)
        if not c or c['service'] != service or any(c[k] for k in ('isDisconnected','isLocked','isQueuePaused')):
            raise RuntimeError('Channel unavailable: ' + service)
    if live:
        publish.reconcile(ledger, posts)
    elif any(r['status'] == 'pending' for e in ledger.data['entries'] for r in e['channels'].values()):
        raise RuntimeError('Uncertain intent; manual reconciliation required')
    # Preserve the image backlog boundary; videos can fill earlier unused slots.
    boundary = ledger.data.get('video_schedule_after')
    if boundary is None:
        boundary = max([now] + [publish.instant(p['dueAt']) for p in posts
            if p.get('dueAt') and p['status'] != 'sent']).isoformat()
        ledger.data['video_schedule_after'] = boundary
    floor = max(now + timedelta(minutes=15), publish.instant(boundary))
    tz = ZoneInfo(plan.CONFIG['timezone'])
    rows = {r['post_id']:r for r in images + videos}
    used = {e['post_id'] for e in ledger.data['entries']}
    banks = {kind:[r for r in images if r['content_type'] == kind and plan.eligible(r)
                         and r['post_id'] not in used] for kind in ('meme','stat')}
    banks['video'] = [r for r in videos if r['approval_status'] == 'APPROVED' and r['post_id'] not in used]
    log = []

    def services(entry):
        return publish.ALL_CHANNELS if entry['kind'] == 'video' else publish.CHANNELS

    def send(entry):
        row = rows.get(entry['post_id'])
        if not row or (entry['kind'] == 'video' and row['approval_status'] != 'APPROVED') or (
                entry['kind'] != 'video' and not plan.eligible(row)):
            raise RuntimeError('Partial content missing or approval revoked: ' + entry['post_id'])
        if entry['kind'] == 'video' and entry.get('sha256') != row['sha256']:
            raise RuntimeError('Partial video bytes changed; manual review required')
        complete = True
        for service,cid in services(entry).items():
            if service in entry['channels']:
                continue  # scheduled/sent/accepted IDs are NEVER recreated
            due = entry['due'][service]
            fresh = api.posts() if live else posts
            if entry['kind'] == 'video':
                day = publish.instant(due).astimezone(tz).date()
                if day < now.astimezone(tz).date():
                    log.append(f'MISSED: {entry["post_id"]}/{service}; prior-day partial retained, no duplicate retry')
                    complete = False
                    continue
                busy = [publish.instant(p.get('sentAt') or p['dueAt']) for p in fresh
                        if p['channelId'] == cid and (p.get('sentAt') or p.get('dueAt'))]
                limit = capacity_limit(service,'video',publish.instant(due),fresh,now)
                if (publish.instant(due) <= now + timedelta(minutes=15)
                        or publish.occupied(fresh,cid) >= limit
                        or any(abs(publish.instant(due)-t) < timedelta(hours=2) for t in busy)):
                    slots, _ = video_slots(day,now,fresh,{service:cid})
                    due = slots[service]
                    entry['due'][service] = due
            if publish.instant(due) <= now + timedelta(minutes=15):
                if entry['kind'] != 'video':
                    raise RuntimeError('Partial schedule expired; manual review required')
                log.append(f'BLOCKED: {entry["post_id"]}/{service}; no remaining same-day slot')
                complete = False
                continue
            body = (video_payload(row,service,due) if entry['kind'] == 'video'
                    else publish.payload(row,service,due))
            limit = capacity_limit(service,entry['kind'],publish.instant(due),fresh,now)
            if publish.occupied(fresh,cid) >= limit:
                log.append('CAPACITY: ' + service + '; partial retained for next run')
                complete = False
                continue
            if any(publish.matching(p,body) or (entry['kind'] == 'video' and p['channelId'] == cid
                   and any(a.get('source') == row['public_url'] for a in p.get('assets',[]))) for p in fresh):
                raise RuntimeError('Unrecorded duplicate detected; reconcile before creating')
            log.append(f"{'SCHEDULE' if live else 'WOULD SCHEDULE'} {row['post_id']} {service} "
                       f"{publish.instant(due).astimezone(tz).isoformat()}")
            if live:
                entry['channels'][service] = {'status':'pending','payload':body}
                ledger.save()  # durable intent BEFORE mutation; ambiguity is never retried
                post = api.create(body)
                entry['channels'][service] = {'id':post['id'],'status':'accepted','payload':body,
                                             'scheduled_at':now.isoformat()}
                ledger.save()
                check = next((p for p in api.posts() if p['id'] == post['id']),None)
                if not check or check['status'] != 'scheduled' or not publish.matching(check,body) or not check.get('assets') or publish.instant(check['dueAt']) != publish.instant(due):
                    raise RuntimeError('Scheduling readback failed; saved ID retained')
                if entry['kind'] == 'video' and not all(a.get('__typename') == 'VideoAsset' for a in check['assets']):
                    raise RuntimeError('Video asset readback failed; saved ID retained')
                entry['channels'][service]['status'] = 'scheduled'
                ledger.save()
                posts.append(check)
            else:
                posts.append({**body,'id':'preview-'+row['post_id']+service,'status':'scheduled'})
                entry['channels'][service] = {'status':'scheduled','id':'preview','payload':body}
        return complete

    # Restore any missing channel, without resending completed channels.
    for entry in ledger.data['entries']:
        if set(entry['channels']) != set(services(entry)):
            send(entry)
    for video_pass in (True, False):
        for n in range(15):
            day = now.astimezone(tz).date() + timedelta(days=n)
            kind = 'video' if video_pass else plan.CONFIG['calendar'][day.strftime('%A')]
            if kind == 'newsletter' or (kind == 'video' and n > int(plan.CONFIG.get('video_queue_days',3))):
                continue
            slot_floor = now + timedelta(minutes=15) if kind == 'video' else floor
            services_for_kind = publish.ALL_CHANNELS if kind == 'video' else publish.CHANNELS
            # Ledger prevents repeated content AND reusing a date even after a post is sent.
            if any(e['kind'] == kind and any(publish.instant(t).astimezone(tz).date() == day
                   for t in e['due'].values()) for e in ledger.data['entries']):
                continue
            if kind == 'video':
                dues, reduced = video_slots(day,now,posts,services_for_kind)
                if all(publish.instant(t) <= now + timedelta(minutes=15) for t in dues.values()):
                    continue
                if reduced:
                    log.append(f'{day} VIDEO PRIORITY: two-hour spacing unavailable; existing posts preserved')
                if any(publish.instant(t).astimezone(tz).strftime('%H:%M') != plan.CONFIG['video_time'] for t in dues.values()):
                    log.append(f'{day} VIDEO PRIORITY: using an alternate time to preserve daily coverage')
            else:
                dues = {}
                for service,cid in services_for_kind.items():
                    c = channels[cid]
                    candidates = [datetime.combine(day,time.fromisoformat(t),ZoneInfo(c['timezone']))
                        for s in c['postingSchedule'] if s['day'] == day.strftime('%a').lower() and not s['paused']
                        for t in s['times']]
                    busy = [publish.instant(p.get('sentAt') or p['dueAt']) for p in posts
                        if p['channelId'] == cid and (p.get('sentAt') or p.get('dueAt'))]
                    video_slot = datetime.combine(day,time.fromisoformat(plan.CONFIG['video_time']),tz)
                    chosen = [t for t in candidates if t > slot_floor
                        and abs(t-video_slot) >= timedelta(hours=2)
                        and not any(abs(t-b) < timedelta(hours=2) for b in busy)]
                    if candidates and not chosen:
                        candidate = datetime.combine(day,time(12),tz)
                        if candidate > slot_floor and not any(abs(candidate-b) < timedelta(hours=2) for b in busy):
                            chosen = [candidate]
                    if chosen:
                        dues[service] = min(chosen).astimezone(timezone.utc).isoformat()
                if len(dues) != len(services_for_kind):
                    continue
            if not banks[kind]:
                log.append(f'{day} BLOCKED: no approved unused {kind}')
                continue
            if kind != 'video' and any(publish.occupied(posts,cid) >= 9 for cid in services_for_kind.values()):
                log.append(f'{day} {kind} CAPACITY: waiting for queue space on all required channels')
                continue
            row = banks[kind].pop(0)
            entry = {'post_id':row['post_id'],'kind':kind,'due':dues,'channels':{}}
            if kind == 'video':
                entry['sha256'] = row['sha256']
                if any(e.get('sha256') == row['sha256'] for e in ledger.data['entries']):
                    raise RuntimeError('Video bytes already used; renamed duplicate blocked')
            ledger.data['entries'].append(entry)
            send(entry)
    return log

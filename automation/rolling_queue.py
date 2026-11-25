"""Activation-gated mixed media queue, sharing the existing durable ledger."""
import copy
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
    targets = {'instagram':9,'facebook':9,'youtube':10}  # one newsletter reserve on image channels
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
        for service,cid in services(entry).items():
            if service in entry['channels']:
                continue  # scheduled/sent/accepted IDs are NEVER recreated
            due = entry['due'][service]
            if publish.instant(due) <= now + timedelta(minutes=15):
                raise RuntimeError('Partial schedule expired; manual review required')
            body = (video_payload(row,service,due) if entry['kind'] == 'video'
                    else publish.payload(row,service,due))
            fresh = api.posts() if live else posts
            if publish.occupied(fresh,cid) >= targets[service]:
                log.append('CAPACITY: ' + service + '; partial retained for next run')
                return False
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
        return True

    # Restore any missing channel, without resending completed channels.
    for entry in ledger.data['entries']:
        if set(entry['channels']) != set(services(entry)):
            if not send(entry):
                return log
    for n in range(15):
        day = now.astimezone(tz).date() + timedelta(days=n)
        kind = plan.CONFIG['video_calendar'][day.strftime('%A')]
        if kind == 'newsletter':
            continue
        slot_floor = now + timedelta(minutes=15) if kind == 'video' else floor
        services_for_kind = publish.ALL_CHANNELS if kind == 'video' else publish.CHANNELS
        dues = {}
        for service,cid in services_for_kind.items():
            if kind == 'video':
                candidates = [datetime.combine(day,time.fromisoformat(plan.CONFIG['video_time']),tz)]
            else:
                c = channels[cid]
                candidates = [datetime.combine(day,time.fromisoformat(t),ZoneInfo(c['timezone']))
                    for s in c['postingSchedule'] if s['day'] == day.strftime('%a').lower() and not s['paused']
                    for t in s['times']]
            # Respect occupied slots and separate videos from any scheduled newsletter by >= 2h.
            busy = [publish.instant(p['dueAt']) for p in posts if p['channelId'] == cid
                    and p.get('dueAt') and p['status'] != 'sent']
            chosen = [t for t in candidates if t > slot_floor and not any(abs(t-b) < timedelta(hours=2) for b in busy)]
            if chosen:
                dues[service] = min(chosen).astimezone(timezone.utc).isoformat()
        if len(dues) != len(services_for_kind):
            continue
        # Ledger prevents repeated content AND reusing a date even after a post is sent.
        if any(e['kind'] == kind and any(publish.instant(t).astimezone(tz).date() == day
               for t in e['due'].values()) for e in ledger.data['entries']):
            continue
        if not banks[kind]:
            log.append(f'{day} BLOCKED: no approved unused {kind}')
            continue
        if any(publish.occupied(posts,cid) >= targets[s] for s,cid in services_for_kind.items()):
            log.append(f'{day} CAPACITY: waiting for queue space on all required channels')
            break
        row = banks[kind].pop(0)
        entry = {'post_id':row['post_id'],'kind':kind,'due':dues,'channels':{}}
        if kind == 'video':
            entry['sha256'] = row['sha256']
            if any(e.get('sha256') == row['sha256'] for e in ledger.data['entries']):
                raise RuntimeError('Video bytes already used; renamed duplicate blocked')
        ledger.data['entries'].append(entry)
        if not send(entry):
            break
    return log

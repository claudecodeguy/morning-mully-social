"""Exercise the real queue across the whole remaining video inventory and image backlog."""
import copy
import json
import unittest
from datetime import datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo
from unittest.mock import patch
import plan
import publish
import rolling_queue
import video_library
import cloud_newsletter
from test_videos import Buffer


class PriorityTests(unittest.TestCase):
    def test_full_inventory_daily_delivery_with_backlog_and_newsletters(self):
        tz=ZoneInfo('America/Toronto')
        api=Buffer()
        api.posts=lambda: list(api.items)  # Snapshot the list; the queue reads post dictionaries without modifying them.
        class State:
            data={'version':1,'entries':[], 'video_schedule_after':'2026-12-09T00:51:00Z'}
            def save(self): pass
        ledger=State()
        images=publish.validate_library()
        videos=video_library.read()
        for row in videos:row['approval_status']='APPROVED'
        now=datetime(2026,11,26,21,15,tzinfo=tz)
        sent_newsletters=set()
        original=[]
        def seed(row,day,times,sent=False):
            kind='video' if row['post_id'].startswith('V') else row['content_type']
            entry={'post_id':row['post_id'],'kind':kind,'due':{},'channels':{}}
            if kind=='video':entry['sha256']=row['sha256']
            for service,clock in times.items():
                due=datetime.combine(datetime.fromisoformat(day).date(),time.fromisoformat(clock),tz).astimezone(timezone.utc).isoformat()
                body=rolling_queue.video_payload(row,service,due) if kind=='video' else publish.payload(row,service,due)
                post=api.create(body)
                if sent:post['status']='sent'
                entry['due'][service]=due
                entry['channels'][service]={'id':post['id'],'status':post['status'],'payload':body}
            ledger.data['entries'].append(entry)
        by_id={r['post_id']:r for r in images}
        for pid,day,ig,fb in [('M001','2026-11-28','22:25','07:31'),('S001','2026-11-29','22:36','10:24'),
                ('M002','2026-12-01','19:51','08:18'),('S002','2026-12-03','10:04','09:59'),
                ('M003','2026-12-05','22:25','07:31'),('S003','2026-12-06','22:36','10:24'),
                ('M004','2026-12-08','19:51','08:18')]:
            seed(by_id[pid],day,{'instagram':ig,'facebook':fb})
        for index,day,sent in [(0,'2026-11-28',False),(1,'2026-11-30',False),
                               (2,'2026-11-25',True),(3,'2026-11-26',True)]:
            seed(videos[index],day,dict.fromkeys(publish.ALL_CHANNELS,'19:00'),sent)
        original=copy.deepcopy(api.items)
        create=api.create
        def checked_create(body):
            self.assertLess(publish.occupied(api.items,body['channelId']),10)
            result=create(body)
            if body['mode']=='shareNow':result['status']='sent'
            return result
        api.create=checked_create
        def deadline(service,clock):
            for n in range(8):
                day=clock.astimezone(tz).date()+timedelta(days=n)
                if plan.CONFIG['calendar'][day.strftime('%A')]=='newsletter' and (day,service) not in sent_newsletters:
                    return datetime.combine(day,time(11),tz)
            raise AssertionError('missing deadline')
        def advance(clock):
            for post in api.items:
                if post['status']=='scheduled' and publish.instant(post['dueAt'])<=clock:
                    post['status']='sent';post['sentAt']=post['dueAt']
        with patch.object(rolling_queue,'newsletter_deadline',side_effect=deadline),patch.object(cloud_newsletter.time,'sleep'):
            rolling_queue.refill(api,ledger,images,videos,now,True)
            for day_index in range(49):
                day=datetime(2026,11,27).date()+timedelta(days=day_index)
                for hour in range(24):
                    now=datetime.combine(day,time(hour,15),tz)
                    advance(now)
                    rolling_queue.refill(api,ledger,images,videos,now,True)
                    if hour==11 and plan.CONFIG['calendar'][day.strftime('%A')]=='newsletter':
                        now=datetime.combine(day,time(11,30),tz)
                        advance(now)
                        class History:
                            data={'channels':{},'image_url':'https://example.com/newsletter.png',
                                  'alt_text':'newsletter','captions':{s:f'Newsletter {day} {s}' for s in publish.CHANNELS}}
                            def save(self):pass
                        history=History()
                        cloud_newsletter.deliver(api,history,{})
                        for service in publish.CHANNELS:sent_newsletters.add((day,service))
                    for cid in publish.ALL_CHANNELS.values():self.assertLessEqual(publish.occupied(api.items,cid),10)
                advance(datetime.combine(day,time(23,59),tz))
                for service,cid in publish.ALL_CHANNELS.items():
                    delivered=[p for p in api.items if p['channelId']==cid and p['status']=='sent'
                        and 'video' in p['assets'][0] and publish.instant(p['dueAt']).astimezone(tz).date()==day]
                    self.assertEqual(len(delivered),1,f'{day} {service}: daily video coverage')
            self.assertEqual(len(sent_newsletters),42)
            for before in original:
                after=next(p for p in api.items if p['id']==before['id'])
                self.assertEqual(after['dueAt'],before['dueAt'])
                self.assertEqual(after['text'],before['text'])
            for cid in publish.ALL_CHANNELS.values():
                urls=[p['assets'][0]['video']['url'] for p in api.items if p['channelId']==cid and 'video' in p['assets'][0]]
                self.assertEqual(len(urls),len(set(urls)))
            scheduled_images=[e for e in ledger.data['entries'] if e['kind']!='video']
            self.assertGreater(len(scheduled_images),7,'Images must keep replenishing alongside videos')

    def test_tenth_slot_requires_release_before_newsletter(self):
        now=datetime.fromisoformat('2026-11-27T02:00:00+00:00')
        with patch.object(rolling_queue,'newsletter_deadline',return_value=datetime.fromisoformat('2026-11-27T16:00:00+00:00')):
            self.assertEqual(rolling_queue.capacity_limit('instagram','video',datetime.fromisoformat('2026-11-27T14:00:00+00:00'),[],now),10)
            self.assertEqual(rolling_queue.capacity_limit('instagram','video',datetime.fromisoformat('2026-11-28T00:00:00+00:00'),[],now),9)
            self.assertEqual(rolling_queue.capacity_limit('instagram','meme',now,[],now),9)


if __name__=='__main__':unittest.main()

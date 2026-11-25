import copy
import hashlib
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
import plan
import publish
import video_library as library
import rolling_queue
from test_publish import FakeBuffer, Ledger

class Buffer(FakeBuffer):
    def create(self,body):
        post=super().create(body)
        for asset in post.get('assets',[]):
            asset['__typename']='VideoAsset' if 'video' in asset else 'ImageAsset'
        return post

    def channels(self):
        return super().channels() + [{'id':publish.ALL_CHANNELS['youtube'],'service':'youtube',
          'timezone':'America/Toronto','isDisconnected':False,'isLocked':False,'isQueuePaused':False,
          'postingSchedule':[]}]

class VideoTests(unittest.TestCase):
    def setUp(self):
        self.api, self.ledger = Buffer(), Ledger()
        self.images = publish.validate_library()
        self.videos = library.read()
        for r in self.videos: r['approval_status']='APPROVED'
        self.now = datetime(2026,11,30,12,tzinfo=timezone.utc)  # Monday

    def run_queue(self,live=True):
        return rolling_queue.refill(self.api,self.ledger,self.images,self.videos,self.now,live)

    def test_library_inventory(self):
        self.assertEqual(len(library.validate()),len(list((plan.ROOT/'videos').glob('*.mp4'))))
        self.assertEqual(len({r['filename'] for r in self.videos}),len(self.videos))

    def test_reels_shorts_and_weekly_dates(self):
        self.run_queue()
        first=self.ledger.data['entries'][0]
        self.assertEqual(first['post_id'],'V001')
        self.assertEqual(set(first['channels']),set(publish.ALL_CHANNELS))
        for s,r in first['channels'].items():
            b=r['payload']
            self.assertEqual(b['metadata'][s]['type'],'short' if s=='youtube' else 'reel')
            self.assertEqual(b['schedulingType'],'automatic')
            self.assertIn('video',b['assets'][0])
            self.assertEqual(b['dueAt'],'2026-12-01T00:00:00+00:00')
        video_dates=[e['due']['youtube'][:10] for e in self.ledger.data['entries'] if e['kind']=='video']
        self.assertEqual(video_dates[:3],['2026-12-01','2026-12-03','2026-12-06'])
        for s,cid in publish.ALL_CHANNELS.items():
            self.assertLessEqual(publish.occupied(self.api.items,cid),10 if s=='youtube' else 9)
        image_kinds=[e['kind'] for e in self.ledger.data['entries'] if e['kind']!='video']
        self.assertEqual(image_kinds[:3],['meme','stat','stat'])

    def test_rerun_and_published_never_repeat(self):
        self.run_queue(); n=len(self.api.writes)
        self.run_queue(); self.assertEqual(len(self.api.writes),n)
        for p in self.api.items: p['status']='sent'
        self.run_queue()
        ids=[e['post_id'] for e in self.ledger.data['entries']]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertTrue(all(r['published_confirmed_at'] for e in self.ledger.data['entries'][:3] for r in e['channels'].values()))

    def test_hold_and_dry_run(self):
        before=copy.deepcopy(self.ledger.data)
        self.run_queue(False)
        self.assertEqual(self.api.writes,[]); self.assertEqual(self.ledger.data,before)
        for r in self.videos: r['approval_status']='NEEDS_REVIEW'
        self.run_queue()
        self.assertTrue(all('video' not in b['assets'][0] for b in self.api.writes))

    def test_timeout_intent_never_retried(self):
        self.api.fail=True
        with self.assertRaises(RuntimeError): self.run_queue()
        self.assertEqual(self.ledger.snapshots[-1]['entries'][0]['channels']['instagram']['status'],'pending')
        with self.assertRaisesRegex(RuntimeError,'Uncertain'): self.run_queue()
        self.assertEqual(len(self.api.writes),1)

    def test_partial_three_channels(self):
        self.run_queue()
        entry=copy.deepcopy(self.ledger.data['entries'][0])
        del entry['channels']['youtube']
        self.ledger.data['entries']=[entry]
        self.api.items=self.api.items[:2];self.api.writes=[]
        self.run_queue()
        self.assertEqual(self.api.writes[0]['channelId'],publish.ALL_CHANNELS['youtube'])
        same=[p for p in self.api.writes if p['text']==library.captions(self.videos[0])['instagram']]
        self.assertEqual(same,[])

    def test_checkpoint_failure_prevents_mutation(self):
        self.ledger.save=lambda: (_ for _ in ()).throw(RuntimeError('denied'))
        with self.assertRaises(RuntimeError): self.run_queue()
        self.assertEqual(self.api.writes,[])

    def test_preserve_existing_queue_and_start_after_it(self):
        original=[{'id':'manual','channelId':publish.CHANNELS['instagram'],'text':'existing',
                   'status':'scheduled','dueAt':'2026-12-08T22:00:00Z'}]
        self.api.items=copy.deepcopy(original)
        self.run_queue()
        self.assertEqual(self.api.items[0],original[0])
        self.assertTrue(all(publish.instant(b['dueAt'])>publish.instant(original[0]['dueAt']) for b in self.api.writes if 'image' in b['assets'][0]))
        video=self.api.writes[0]
        self.assertIn('video',video['assets'][0])
        self.assertEqual(video['dueAt'],'2026-12-01T00:00:00+00:00')

    def test_first_video_can_fill_tomorrow_without_moving_existing_queue(self):
        self.now=datetime(2026,11,25,1,tzinfo=timezone.utc)
        self.api.items=[{'id':'future-'+str(i),'channelId':cid,'text':'existing',
                        'status':'scheduled','dueAt':'2026-12-09T00:51:00Z'}
                       for cid in publish.CHANNELS.values() for i in range(8)]
        original=copy.deepcopy(self.api.items)
        self.run_queue()
        self.assertEqual(self.api.items[:16],original)
        self.assertEqual(len(self.api.writes),3)
        self.assertTrue(all(p['dueAt']=='2026-11-26T00:00:00+00:00' for p in self.api.writes))
        self.assertEqual({p['channelId'] for p in self.api.writes},set(publish.ALL_CHANNELS.values()))

    def test_full_youtube_stops_video_without_touching_posts(self):
        self.api.items=[{'id':str(i),'channelId':publish.ALL_CHANNELS['youtube'],'text':'manual',
                         'status':'draft','dueAt':None} for i in range(10)]
        self.run_queue();self.assertEqual(self.api.writes,[])

    def test_external_duplicate_source_blocks_even_with_new_caption(self):
        self.api.items=[{'id':'old','channelId':publish.CHANNELS['instagram'],'text':'different',
                         'status':'sent','assets':[{'source':self.videos[0]['public_url']}]}]
        with self.assertRaisesRegex(RuntimeError,'duplicate'): self.run_queue()
        self.assertEqual(self.api.writes,[])

    def test_confirmed_sent_history_survives_buffer_archival(self):
        self.run_queue()
        for e in self.ledger.data['entries']:
            for r in e['channels'].values(): r['status']='sent'
        self.api.items=[]
        self.run_queue()

    def test_sync_stable_ids_and_replacement_revokes_approval(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'videos').mkdir();(root/'data').mkdir()
            p=root/'videos/a.mp4';p.write_bytes(b'0000ftyporiginal')
            with patch.object(plan,'ROOT',root):
                a=library.sync();self.assertEqual(a[0]['post_id'],'V001')
                a[0]['approval_status']='APPROVED';library.write(a)
                p.write_bytes(b'0000ftypchanged')
                b=library.sync();self.assertEqual(b[0]['post_id'],'V001')
                self.assertEqual(b[0]['approval_status'],'NEEDS_REVIEW')
                (root/'videos/b.mp4').write_bytes(b'0000ftypsecond')
                self.assertEqual(library.sync()[1]['post_id'],'V002')

    def test_video_live_preview_cannot_bypass_gate(self):
        with patch.dict('os.environ',{'PUBLISHING_ENABLED':'true','GITHUB_REF':'refs/heads/main'},clear=True),patch.object(sys,'argv',['publish.py','--live','--video-preview']):
            with self.assertRaisesRegex(RuntimeError,'cannot be combined'): publish.main()

    def test_toronto_dst(self):
        self.now=datetime(2027,3,13,12,tzinfo=timezone.utc)
        self.run_queue()
        dates=[e['due']['youtube'] for e in self.ledger.data['entries'] if e['kind']=='video']
        self.assertEqual(dates[:2],['2027-03-14T00:00:00+00:00','2027-03-15T23:00:00+00:00'])

    def test_capacity_race_retains_partial_without_overfilling(self):
        original=self.api.create
        def create(body):
            result=original(body)
            if body['channelId']==publish.CHANNELS['instagram']:
                self.api.items.extend({'id':'manual-'+str(i),'channelId':publish.CHANNELS['facebook'],
                    'text':'manual','status':'draft'} for i in range(9))
            return result
        self.api.create=create
        self.run_queue()
        self.assertEqual(len(self.api.writes),1)
        self.assertEqual(set(self.ledger.data['entries'][0]['channels']),{'instagram'})
        self.api.items=[p for p in self.api.items if p['channelId']!=publish.CHANNELS['facebook']]
        self.api.create=original
        self.run_queue()
        self.assertEqual(self.api.writes[1]['channelId'],publish.CHANNELS['facebook'])
        self.assertEqual(self.api.writes[2]['channelId'],publish.ALL_CHANNELS['youtube'])

    def test_accepted_readback_failure_never_recreates_video(self):
        original=self.api.create
        def create(body):
            result=original(body)
            self.api.items[-1]['assets']=[]
            return result
        self.api.create=create
        with self.assertRaisesRegex(RuntimeError,'readback'): self.run_queue()
        self.assertEqual(self.ledger.data['entries'][0]['channels']['instagram']['status'],'accepted')
        self.api.items[0]['status']='error'
        with self.assertRaisesRegex(RuntimeError,'failed'): self.run_queue()
        self.assertEqual(len(self.api.writes),1)

    def test_partial_replaced_video_requires_manual_review(self):
        self.run_queue()
        self.ledger.data['entries']=self.ledger.data['entries'][:1]
        del self.ledger.data['entries'][0]['channels']['youtube']
        self.videos[0]['sha256']='changed'
        with self.assertRaisesRegex(RuntimeError,'bytes changed'): self.run_queue()

    def test_duplicate_video_bytes_cannot_be_reintroduced_under_new_id(self):
        self.run_queue()
        old_hash=self.videos[0]['sha256']
        self.now=datetime(2026,12,15,12,tzinfo=timezone.utc)
        for p in self.api.items: p['status']='sent'
        for row in self.videos:
            if row['post_id'] not in {e['post_id'] for e in self.ledger.data['entries']}:
                row['sha256']=old_hash
        with self.assertRaisesRegex(RuntimeError,'already used'): self.run_queue()

    def test_proposed_calendar_includes_newsletters_and_video_days(self):
        from datetime import date
        items=plan.create_video_plan(date(2026,11,30),7,[],'Offline')
        self.assertEqual(sum(i['type']=='newsletter' for i in items),3)
        self.assertEqual(sum(i['type']=='video' for i in items),3)
        self.assertEqual(sum(i['type']=='meme' for i in items),1)
        self.assertEqual(sum(i['type']=='stat' for i in items),2)
        self.assertTrue(all(i['platforms']==['instagram','facebook','youtube'] for i in items if i['type']=='video'))

if __name__=='__main__': unittest.main()

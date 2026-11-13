import copy
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parent))
import publish
import plan

class Ledger:
    def __init__(self):
        self.data = {'version': 1, 'entries': []}
        self.snapshots = []
    def save(self):
        self.snapshots.append(copy.deepcopy(self.data))

class FakeBuffer:
    def __init__(self):
        self.items = []
        self.writes = []
        self.fail = False
    def posts(self):
        return copy.deepcopy(self.items)
    def channels(self):
        return [{'id': cid, 'service': service, 'timezone': 'America/Toronto',
                 'isDisconnected': False, 'isLocked': False, 'isQueuePaused': False,
                 'postingSchedule': [{'day': day, 'times': ['12:00'], 'paused': False}
                                     for day in ('mon','tue','wed','thu','fri','sat','sun')]}
                for service, cid in publish.CHANNELS.items()]
    def create(self, body):
        self.writes.append(body)
        if self.fail:
            raise RuntimeError('Simulated uncertain timeout')
        item = {**body, 'id': str(len(self.items)), 'status': 'scheduled'}
        self.items.append(item)
        return item

class PublishingTests(unittest.TestCase):
    def setUp(self):
        self.api, self.ledger = FakeBuffer(), Ledger()
        self.records = publish.validate_library()
        self.now = datetime(2026,11,13,tzinfo=timezone.utc)

    def run_refill(self, live=True):
        # Simulate user approvals without altering the actual library.
        with patch.object(plan, 'eligible', return_value=True):
            return publish.refill(self.api, self.ledger, self.records, self.now, live)

    def test_all_assets_and_urls(self):
        self.assertEqual(len(self.records),61)
        for row in self.records:
            self.assertTrue(plan.image_url(row).endswith(row['image_path']))

    def test_refill_alternates_caps_and_rerun_is_idempotent(self):
        self.run_refill()
        self.assertEqual(len(self.api.writes),20)
        entries=self.ledger.data['entries']
        self.assertEqual([e['kind'] for e in entries], ['meme','stat']*5)
        for e in entries:
            self.assertEqual(len(e['channels']),2)
            for s,r in e['channels'].items():
                body=r['payload']
                self.assertEqual(body['mode'],'customScheduled')
                self.assertTrue(body['assets'][0]['image']['metadata']['altText'])
        self.run_refill()
        self.assertEqual(len(self.api.writes),20)
        # Publishing frees one slot on both channels; next run refills exactly one pair.
        for p in self.api.items[:2]: p['status']='sent'
        self.run_refill()
        self.assertEqual(len(self.api.writes),22)
        self.assertEqual(self.ledger.data['entries'][0]['channels']['instagram']['status'],'sent')

    def test_dry_run_has_zero_writes_and_no_checkpoints(self):
        self.run_refill(False)
        self.assertEqual(self.api.writes,[])
        self.assertEqual(self.ledger.snapshots,[])

    def test_approval_hold_blocks_refill_and_preserves_alternation(self):
        with patch.object(plan, "eligible", return_value=False):
            log=publish.refill(self.api,self.ledger,self.records,self.now,True)
        self.assertTrue(any('BLOCKED' in s for s in log))
        self.assertEqual(self.api.writes,[])

    def test_intent_saved_before_uncertain_write_and_never_retried(self):
        self.api.fail=True
        with self.assertRaises(RuntimeError): self.run_refill()
        self.assertEqual(self.ledger.snapshots[-1]['entries'][0]['channels']['instagram']['status'],'pending')
        with self.assertRaisesRegex(RuntimeError,'Uncertain intent'): self.run_refill()
        self.assertEqual(len(self.api.writes),1)

    def test_failed_checkpoint_prevents_write(self):
        def fail(): raise RuntimeError('GitHub write denied')
        self.ledger.save=fail
        with self.assertRaises(RuntimeError): self.run_refill()
        self.assertEqual(self.api.writes,[])

    def test_partial_pair_recovers_without_resending_first_channel(self):
        self.run_refill()
        first=copy.deepcopy(self.ledger.data['entries'][0])
        first['channels'].pop('facebook')
        self.ledger.data['entries']=[first]
        self.api.items=self.api.items[:1]
        self.api.writes=[]
        self.run_refill()
        self.assertEqual(self.api.writes[0]['channelId'],publish.CHANNELS['facebook'])
        self.assertEqual(sum(b['text']==first['channels']['instagram']['payload']['text'] and b['channelId']==publish.CHANNELS['instagram'] for b in self.api.writes),0)

    def test_preexisting_caption_blocks_duplicate(self):
        body=publish.payload(self.records[0],'instagram','2026-11-14T17:00:00+00:00')
        self.api.items=[{**body,'id':'external','status':'sent'}]
        with self.assertRaisesRegex(RuntimeError,'matching caption'): self.run_refill()
        self.assertEqual(self.api.writes,[])

    def test_channel_error_stops_refill(self):
        self.run_refill()
        self.api.items[0]['status']='error'
        with self.assertRaisesRegex(RuntimeError,'failed'): self.run_refill()
        self.assertEqual(len(self.api.writes),20)

    def test_full_manual_queue_prevents_writes(self):
        self.api.items=[{'id':str(i),'channelId':publish.CHANNELS['facebook'],'status':'scheduled',
                         'text':'manual','dueAt':'2026-11-20T12:00:00Z'} for i in range(10)]
        self.run_refill()
        self.assertEqual(self.api.writes,[])

    def test_ledger_invalid_fails_closed(self):
        self.ledger.data={}
        with self.assertRaises(RuntimeError): self.run_refill()

    def test_gate_prevents_live_before_network(self):
        with patch.dict('os.environ',{},clear=True),patch.object(sys,'argv',['publish.py','--live']):
            with self.assertRaisesRegex(RuntimeError,'disabled'): publish.main()

if __name__ == '__main__': unittest.main()

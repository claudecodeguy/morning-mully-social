import copy
import sys
import unittest
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import publish
import video_watchdog


class WatchdogTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.fromisoformat('2026-11-27T01:45:00+00:00')  # 20:45 Toronto
        self.ledger = {'version':1, 'entries':[]}
        self.posts = []
        self.channels = [{'id':cid, 'service':s, 'isDisconnected':False,
                          'isLocked':False, 'isQueuePaused':False}
                         for s,cid in publish.ALL_CHANNELS.items()]
        self.videos = [{'post_id':f'V{i:03}', 'approval_status':'APPROVED'} for i in range(1,30)]
        for n, due, status in [(1,'2026-11-27T00:00:00Z','sent'),
                               (2,'2026-11-28T00:00:00Z','scheduled')]:
            entry = {'post_id':f'V{n:03}', 'kind':'video', 'due':{}, 'channels':{}}
            for s,cid in publish.ALL_CHANNELS.items():
                pid = f'{n}-{s}'
                entry['due'][s] = due
                entry['channels'][s] = {'id':pid, 'status':status}
                self.posts.append({'id':pid,'channelId':cid,'status':status,'dueAt':due})
            self.ledger['entries'].append(entry)

    def check(self):
        return video_watchdog.inspect(self.posts,self.channels,self.ledger,self.videos,self.now)

    def test_sent_today_and_queued_tomorrow_are_healthy(self):
        self.assertTrue(self.check()['healthy'])

    def test_missing_delivery_on_one_platform_is_detected(self):
        self.ledger['entries'][0]['channels']['youtube']['status']='accepted'
        self.posts[2]['status']='sending'
        issues=self.check()['issues']
        self.assertEqual(len(issues),1)
        self.assertIn('MISSING DELIVERY',issues[0])
        self.assertIn('youtube',issues[0])

    def test_successful_refill_with_empty_next_day_is_not_healthy(self):
        self.ledger['entries'].pop()
        self.posts=self.posts[:3]
        self.assertEqual(sum('SCHEDULE GAP' in i for i in self.check()['issues']),3)

    def test_ledger_schedule_alone_does_not_prove_it_is_queued(self):
        self.posts.pop()
        issues=self.check()['issues']
        self.assertTrue(any('SCHEDULE GAP' in i and 'youtube' in i for i in issues))
        self.assertTrue(any('POST:' in i for i in issues))

    def test_buffer_sent_status_can_precede_ledger_reconciliation(self):
        self.ledger['entries'][0]['channels']['youtube']['status']='accepted'
        self.assertTrue(self.check()['healthy'])

    def test_archived_confirmed_delivery_remains_valid(self):
        self.posts=self.posts[3:]
        self.assertTrue(self.check()['healthy'])

    def test_disconnected_channel_and_uncertain_partial_are_reported(self):
        self.channels[0]['isDisconnected']=True
        entry=self.ledger['entries'][1]
        entry['channels']['facebook']['status']='pending'
        del entry['channels']['youtube']
        issues=self.check()['issues']
        self.assertTrue(any('CHANNEL:' in i for i in issues))
        self.assertTrue(any('UNCERTAIN:' in i for i in issues))
        self.assertTrue(any('PARTIAL:' in i for i in issues))

    def test_low_stock_warns_before_exhaustion(self):
        self.videos=self.videos[:9]  # two in ledger, seven unused
        self.assertTrue(any('LOW STOCK: 7' in i for i in self.check()['issues']))

    def test_wrong_time_does_not_satisfy_daily_coverage(self):
        for post in self.posts[3:]:post['dueAt']='2026-11-28T01:00:00Z'
        self.assertEqual(sum('SCHEDULE GAP' in i for i in self.check()['issues']),3)

    def test_reads_do_not_mutate_posts_or_publication_history(self):
        original=copy.deepcopy((self.posts,self.channels,self.ledger,self.videos))
        self.check()
        self.assertEqual((self.posts,self.channels,self.ledger,self.videos),original)

    def test_toronto_summer_time_and_delivery_grace(self):
        self.now=datetime.fromisoformat('2027-03-15T00:00:00+00:00')  # 20:00 EDT
        self.ledger['entries']=[];self.posts=[]
        issues=self.check()['issues']
        self.assertFalse(any('MISSING DELIVERY' in i for i in issues))
        self.assertTrue(all('2027-03-15 19:00' in i for i in issues))
        self.now=datetime.fromisoformat('2027-03-15T00:30:00+00:00')
        self.assertTrue(any('MISSING DELIVERY: 2027-03-14' in i for i in self.check()['issues']))


if __name__ == '__main__':
    unittest.main()

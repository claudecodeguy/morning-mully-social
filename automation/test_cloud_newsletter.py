import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import cloud_newsletter as cloud
import publish
from test_publish import FakeBuffer

class History:
    def __init__(self):
        self.data={'issue_date':'2026-11-16','channels':{},'image_url':'https://example.com/cover.png',
                   'captions':{'instagram':'Monday IG','facebook':'Monday FB'},'alt_text':'Monday issue'}
        self.snapshots=[]
    def save(self):
        self.snapshots.append(copy.deepcopy(self.data))

class Buffer(FakeBuffer):
    def create(self,body):
        post=super().create(body)
        post['status']='sent'
        self.items[-1]['status']='sent'
        return post

class CloudTests(unittest.TestCase):
    def setUp(self):
        self.api=Buffer()
        self.history=History()
        self.issue={'issue_date':'2026-11-16','title':'Monday golf: the weekend in review',
                    'issue_url':'https://morningmully.beehiiv.com/p/monday','images':[]}

    def test_publishes_once_and_readback_is_idempotent(self):
        cloud.deliver(self.api,self.history,self.issue)
        self.assertEqual(len(self.api.writes),2)
        self.assertEqual(self.history.snapshots[0]['channels']['instagram']['status'],'pending')
        cloud.deliver(self.api,self.history,self.issue)
        self.assertEqual(len(self.api.writes),2)
        self.assertTrue(all(x['status']=='sent' for x in self.history.data['channels'].values()))

    def test_timeout_never_recreates_uncertain_request(self):
        self.api.fail=True
        with self.assertRaises(RuntimeError): cloud.deliver(self.api,self.history,self.issue)
        self.api.fail=False
        with self.assertRaisesRegex(RuntimeError,'Uncertain'): cloud.deliver(self.api,self.history,self.issue)
        self.assertEqual(len(self.api.writes),1)

    def test_pending_intent_recovers_if_post_is_visible(self):
        cloud.deliver(self.api,self.history,self.issue)
        self.history.data['channels']['instagram'].pop('buffer_id')
        self.history.data['channels']['instagram']['status']='pending'
        cloud.deliver(self.api,self.history,self.issue)
        self.assertEqual(len(self.api.writes),2)
        self.assertEqual(self.history.data['channels']['instagram']['status'],'sent')

    def test_failed_checkpoint_prevents_mutation(self):
        with patch.object(self.history,'save',side_effect=RuntimeError('GitHub write failed')):
            with self.assertRaises(RuntimeError): cloud.deliver(self.api,self.history,self.issue)
        self.assertEqual(self.api.writes,[])

    def test_full_queue_does_not_mutate_or_delete(self):
        self.api.items=[{'id':str(i),'channelId':publish.CHANNELS['instagram'],'status':'scheduled','text':'manual'} for i in range(10)]
        with self.assertRaisesRegex(RuntimeError,'full'): cloud.deliver(self.api,self.history,self.issue)
        self.assertEqual(self.api.writes,[])
        self.assertEqual(len(self.api.items),10)

    def test_first_channel_is_not_reposted_after_second_channel_failure(self):
        original=self.api.create
        def create(body):
            if body['channelId']==publish.CHANNELS['facebook']: raise RuntimeError('timeout')
            return original(body)
        self.api.create=create
        with self.assertRaises(RuntimeError): cloud.deliver(self.api,self.history,self.issue)
        self.assertEqual(self.history.data['channels']['instagram']['status'],'sent')
        self.assertEqual(self.history.data['channels']['facebook']['status'],'pending')
        self.api.create=original
        with self.assertRaisesRegex(RuntimeError,'Uncertain'): cloud.deliver(self.api,self.history,self.issue)
        self.assertEqual(len(self.api.writes),1)

    def test_live_rejects_simulated_clock_and_missing_gate(self):
        for argv in (['x','--live'],['x','--live','--now','2026-11-16T12:00:00-05:00']):
            with patch.dict('os.environ',{},clear=True),patch.object(sys,'argv',argv):
                with self.assertRaisesRegex(RuntimeError,'requires'): cloud.main()

    def test_caption_uses_exact_issue_link_and_five_tags(self):
        captions=cloud.captions(self.issue)
        self.assertIn(self.issue['issue_url'],captions['facebook'])
        self.assertEqual(captions['instagram'].count('#'),5)
        self.assertIn(self.issue['title'],captions['instagram'])

    @unittest.skipUnless(importlib.util.find_spec('PIL'),'Pillow installed in cloud rendering environment')
    def test_image_service_failure_renders_local_cover(self):
        from PIL import Image
        self.issue['images']=[{'url':'https://media.beehiiv.com/story.png'}]
        def fail(_): raise OSError('Photo host unavailable')
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'cover.png'
            meta=cloud.render(self.issue,output,download=fail)
            self.assertEqual(meta['renderer'],'local_fallback')
            with Image.open(output) as image:
                self.assertEqual(image.size,(1080,1350))

    @unittest.skipUnless(importlib.util.find_spec('PIL'),'Pillow installed in cloud rendering environment')
    def test_uses_real_issue_artwork_without_cropping(self):
        from PIL import Image
        import io
        data=io.BytesIO();Image.new('RGB',(1000,600),'green').save(data,'PNG')
        self.issue['images']=[{'url':'https://media.beehiiv.com/story.png'}]
        with tempfile.TemporaryDirectory() as temp:
            meta=cloud.render(self.issue,Path(temp)/'cover.png',download=lambda _:data.getvalue())
            self.assertEqual(meta['renderer'],'newsletter_artwork')

if __name__=='__main__': unittest.main()

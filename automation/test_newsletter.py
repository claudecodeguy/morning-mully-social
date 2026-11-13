import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import newsletter


def feed(day='Mon, 16 Nov 2026 16:00:00 +0000', url='https://morningmully.beehiiv.com/p/monday'):
    return f'''<rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><item>
    <title>Monday golf</title><pubDate>{day}</pubDate><link>{url}</link>
    <content:encoded><![CDATA[<style>hidden</style><p>Real story</p><img src="https://example.com/photo.jpg" alt="Golf"/>]]></content:encoded>
    </item></channel></rss>'''

class NewsletterTests(unittest.TestCase):
    def test_same_day_issue_and_clean_content(self):
        issue = newsletter.select_issue(feed(), datetime(2026,11,16,17,tzinfo=timezone.utc))
        self.assertEqual(issue['text'],'Real story')
        self.assertEqual(issue['images'][0]['alt'],'Golf')

    def test_stale_and_future_issues_are_not_reused(self):
        self.assertIsNone(newsletter.select_issue(feed(),datetime(2026,11,18,17,tzinfo=timezone.utc)))
        self.assertIsNone(newsletter.select_issue(feed(),datetime(2026,11,16,15,tzinfo=timezone.utc)))

    def test_non_newsletter_days_are_skipped(self):
        self.assertIsNone(newsletter.select_issue(feed(),datetime(2026,11,17,17,tzinfo=timezone.utc)))

    def test_unexpected_issue_host_fails_closed(self):
        with self.assertRaises(ValueError):
            newsletter.select_issue(feed(url='https://other.example/p/x'),datetime(2026,11,16,17,tzinfo=timezone.utc))

    def test_durable_intents_block_duplicate_creations(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(newsletter.plan,'ROOT',Path(temp)):
            (Path(temp)/'data').mkdir()
            body={'channelId':newsletter.plan.CONFIG['instagram_channel_id'],'mode':'shareNow','text':'hello','assets':[{'image':{'url':'https://example.com/a.jpg'}}]}
            newsletter.checkpoint('2026-11-16','instagram','pending',body)
            with self.assertRaises(ValueError): newsletter.checkpoint('2026-11-16','instagram','pending',body)
            newsletter.checkpoint('2026-11-16','instagram','accepted',post_id='id')
            newsletter.checkpoint('2026-11-16','instagram','sent',post_id='id',sent_at='2026-11-16T17:00:00Z')
            self.assertEqual(newsletter.load_history('2026-11-16')['channels']['instagram']['status'],'sent')
            with self.assertRaises(ValueError): newsletter.checkpoint('2026-11-16','instagram','sent',post_id='other',sent_at='now')

if __name__=='__main__': unittest.main()

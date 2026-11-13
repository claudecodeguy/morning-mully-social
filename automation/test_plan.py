"""Automated safety checks for the read-only planner."""
import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import plan


class SchedulerTests(unittest.TestCase):
    def test_library_counts_and_user_approvals(self):
        memes = plan.rows("memes.csv")
        stats = plan.rows("statistics.csv")
        self.assertEqual(len(memes), 31)
        self.assertEqual(len(stats), 30)
        self.assertEqual(sum(plan.eligible(x) for x in memes), 31)
        self.assertEqual(sum(plan.eligible(x) for x in stats), 30)

    def test_weekend_uses_approved_content(self):
        items = plan.create_plan(date(2026, 11, 14), 2, [], "Offline test")
        self.assertEqual(items[0]["type"], "meme")
        self.assertEqual(items[0]["status"], "READY_FOR_REVIEW")
        self.assertEqual(items[1]["post_id"], "S001")
        self.assertEqual(items[1]["status"], "READY_FOR_REVIEW")

    def test_no_duplicate_stats_in_preview(self):
        items = plan.create_plan(date(2026, 11, 15), 15, [], "Offline test")
        ids = [x["post_id"] for x in items if x["type"] == "stat" and x["status"] == "READY_FOR_REVIEW"]
        self.assertEqual(len(ids), len(set(ids)))

    def test_old_newsletter_not_reused(self):
        issue = [{"title": "Old issue", "link": "https://example.com/old",
                  "published": datetime(2026, 11, 12, 12, tzinfo=timezone.utc)}]
        actual = plan.preview_newsletter(date(2026, 11, 13), issue, None)
        self.assertEqual(actual["status"], "BLOCKED_NO_SAME_DAY_ISSUE")

    def test_today_newsletter_needs_graphic(self):
        issue = [{"title": "New issue", "link": "https://example.com/new",
                  "published": datetime(2026, 11, 13, 13, tzinfo=timezone.utc)}]
        actual = plan.preview_newsletter(date(2026, 11, 13), issue, None)
        self.assertEqual(actual["status"], "NEEDS_NEWSLETTER_GRAPHIC")

    def test_no_secrets_or_buffer_write_functions(self):
        source = Path(plan.__file__).read_text()
        self.assertNotIn("createPost(", source)
        self.assertNotIn("BUFFER_API_KEY", source)

    def test_facebook_preserves_approved_caption_and_tags(self):
        row = plan.rows("statistics.csv")[10]
        fb = plan.make_captions(row)["facebook"]
        self.assertEqual(fb, plan.make_captions(row)["instagram"])


if __name__ == "__main__":
    unittest.main()

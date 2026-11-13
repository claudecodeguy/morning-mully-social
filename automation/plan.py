#!/usr/bin/env python3
"""Morning Mully read-only schedule preview. Never calls Buffer or publishes."""
import argparse
import csv
import json
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((Path(__file__).parent / "settings.json").read_text())
APPROVED = {"APPROVED", "READY_AS_SUPPLIED"}


def rows(filename):
    with (ROOT / "data" / filename).open(encoding="utf-8-sig", newline="") as f:
        return sorted(list(csv.DictReader(f)), key=lambda row: row["post_id"])


def eligible(row):
    audit = {r["post_id"]: r for r in rows("asset_audit.csv")}
    return (row.get("approval_status") in APPROVED
            and audit.get(row["post_id"], {}).get("approval_status") in APPROVED
            and row.get("publish_status") == "UNPUBLISHED")


def image_url(row):
    path = Path(row["image_path"])
    if path.is_absolute() or ".." in path.parts or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise ValueError("Unsafe image path: " + str(path))
    if not (ROOT / path).is_file():
        raise FileNotFoundError("Missing image: " + str(path))
    return CONFIG["pages_base_url"].rstrip("/") + "/" + path.as_posix()


def make_captions(row):
    ig = (row.get("instagram_caption") or "").strip()
    tags = (row.get("hashtags") or "").strip()
    if tags and tags not in ig:
        ig += "\n\n" + tags
    fb = (row.get("facebook_caption") or "").strip()
    if not fb:
        fb = (row.get("instagram_caption") or "").strip()
    if tags and tags not in fb:
        fb += "\n\n" + tags
    return {"instagram": ig, "facebook": fb}


def parse_pubdate(value):
    if not value:
        return None
    try:
        d = parsedate_to_datetime(value)
    except (ValueError, TypeError, IndexError):
        try:
            d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def text_of(item, names):
    for name in names:
        node = item.find(name)
        if node is not None and (node.text or "").strip():
            return node.text.strip()
    return ""


def read_feed():
    req = urllib.request.Request(
        CONFIG["feed_url"],
        headers={"User-Agent": "MorningMullySocialPlanner/1.0", "Accept": "application/rss+xml, application/xml"}
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        data = response.read(3_000_000)
    root = ET.fromstring(data)
    items = root.findall("./channel/item") or root.findall("{*}entry")
    issues = []
    for item in items:
        title = text_of(item, ["title", "{*}title"])
        link = text_of(item, ["link", "{*}link"])
        if not link:
            for n in item.findall("{*}link"):
                if n.get("href") and n.get("rel", "alternate") == "alternate":
                    link = n.get("href")
                    break
        pub = parse_pubdate(text_of(item, ["pubDate", "{*}published", "{*}updated"]))
        if title and link and link.startswith("https://") and pub:
            issues.append({"title": title, "link": link, "published": pub})
    return issues


def preview_asset(row, kind, day):
    item = {
        "date": day.isoformat(), "type": kind,
        "post_id": row["post_id"], "title": row.get("title", ""),
        "approval_status": row.get("approval_status"),
    }
    if not eligible(row):
        return item | {"status": "BLOCKED_APPROVAL", "reason": "This asset is not approved for automatic publishing."}
    try:
        item["image_url"] = image_url(row)
    except (ValueError, FileNotFoundError) as exc:
        return item | {"status": "BLOCKED_IMAGE", "reason": str(exc)}
    item["captions"] = make_captions(row)
    item["status"] = "READY_FOR_REVIEW"
    if kind == "stat":
        item["source_url"] = row.get("source_url")
        item["warning"] = "Statistic is marked ready as supplied, not independently fact-checked."
    return item


def preview_newsletter(day, feed, feed_error):
    item = {"date": day.isoformat(), "type": "newsletter"}
    if feed_error:
        return item | {"status": "BLOCKED_FEED", "reason": feed_error}
    tz = ZoneInfo(CONFIG["timezone"])
    matches = [i for i in feed if i["published"].astimezone(tz).date() == day]
    if not matches:
        return item | {"status": "BLOCKED_NO_SAME_DAY_ISSUE", "reason": "No issue dated this day; an older newsletter will not be reused."}
    issue = max(matches, key=lambda i: i["published"])
    title, link = issue["title"], issue["link"]
    return item | {
        "title": title, "issue_url": link,
        "status": "NEEDS_NEWSLETTER_GRAPHIC",
        "reason": "A branded, approved graphic is required for Instagram before publishing.",
        "captions": {
            "instagram": f"{title}\n\nRead the full issue through the link in bio.",
            "facebook": f"{title}\n\nRead the issue: {link}",
        },
    }


def create_plan(start, days, feed=None, feed_error=None):
    bank = {"meme": rows("memes.csv"), "stat": rows("statistics.csv")}
    used = set()
    output = []
    for n in range(days):
        day = start + timedelta(days=n)
        kind = CONFIG["calendar"][day.strftime("%A")]
        if kind == "newsletter":
            output.append(preview_newsletter(day, feed or [], feed_error))
            continue
        available = [r for r in bank[kind] if r["post_id"] not in used and eligible(r)]
        if available:
            chosen = available[0]
        else:
            blocked = [r for r in bank[kind] if r.get("publish_status") == "UNPUBLISHED" and r["post_id"] not in used]
            chosen = blocked[0] if blocked else None
        if chosen is None:
            output.append({"date": day.isoformat(), "type": kind,
                           "status": "BLOCKED_EMPTY", "reason": "No unused content in this category."})
        else:
            used.add(chosen["post_id"])
            output.append(preview_asset(chosen, kind, day))
    return output


def make_markdown(plan):
    lines = [
        "# Morning Mully: read-only content schedule", "",
        "**No posts were queued, scheduled or published.**", "",
        "| Date | Content | ID | Result |", "|---|---|---|---|"
    ]
    for item in plan:
        lines.append(f"| {item['date']} | {item['type']} | {item.get('post_id', '—')} | {item['status']} |")
    for item in plan:
        lines.extend(["", f"## {item['date']} — {item['type']}", f"Status: {item['status']}"])
        for field in ("title", "reason", "warning", "image_url", "issue_url", "source_url"):
            if item.get(field):
                lines.append(f"{field}: {item[field]}")
        if item.get("captions"):
            lines.extend(["", "**Instagram caption**", "", item["captions"]["instagram"], "",
                          "**Facebook caption**", "", item["captions"]["facebook"], ""])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="Start date YYYY-MM-DD; defaults to today, New York time")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--offline", action="store_true", help="Skip external RSS request")
    parser.add_argument("--output-dir", default="reports")
    opts = parser.parse_args()
    if not 1 <= opts.days <= 31:
        parser.error("--days must be 1–31")
    try:
        day = date.fromisoformat(opts.date) if opts.date else datetime.now(ZoneInfo(CONFIG["timezone"])).date()
    except ValueError:
        parser.error("--date must be YYYY-MM-DD")
    feed, feed_error = [], None
    if opts.offline:
        feed_error = "Offline mode; no RSS lookup attempted."
    else:
        try:
            feed = read_feed()
        except (OSError, ET.ParseError, ValueError) as e:
            feed_error = "Beehiiv feed unavailable: " + str(e).splitlines()[0][:140]
    plan = create_plan(day, opts.days, feed, feed_error)
    dest = Path(opts.output_dir)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "preview.json").write_text(json.dumps({
        "mode": "DRY_RUN", "buffer_writes": 0, "items": plan,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (dest / "preview.md").write_text(make_markdown(plan), encoding="utf-8")
    print("DRY RUN ONLY. NO BUFFER POSTING.")
    for item in plan:
        print(item["date"], item["type"].ljust(11), item.get("post_id", "—").ljust(5), item["status"])
    print("Report:", dest / "preview.md")


if __name__ == "__main__":
    sys.exit(main())

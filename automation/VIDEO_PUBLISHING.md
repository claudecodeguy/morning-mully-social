# Morning Mully video publishing

Owner approved all 14 initial videos and live activation on November 24, 2026. This branch does not change Buffer posts, activate repository variables, or alter publication history. The existing meme/statistic refill and cloud newsletter continue to use their current paths until `VIDEO_PUBLISHING_ENABLED=true`.

## Proposed weekly calendar

All dates use `America/Toronto`, including daylight saving changes.

| Day | Content |
| --- | --- |
| Monday | Existing newsletter + video at 19:00 |
| Tuesday | Meme, using existing Buffer channel times |
| Wednesday | Existing newsletter + video at 19:00 |
| Thursday | Statistic, using existing Buffer channel times |
| Friday | Existing newsletter |
| Saturday | Video at 19:00 |
| Sunday | Statistic, using existing Buffer channel times |

Newsletters retain the existing same-day cloud workflow and its daytime delivery window. New videos use custom scheduled times, independent of Buffer's posting schedule. A video slot within two hours of an already queued post on any required channel is skipped. Existing Buffer posts are never moved or deleted. Videos fill the next unoccupied Monday/Wednesday/Saturday evening slot, including slots before the existing backlog ends. New images retain the boundary after the latest existing queued post. Existing Buffer posts keep their dates. It scans a rolling 15-day horizon on each existing six-hour refill run.

## Library and captions

`data/videos.csv` maps stable V-series IDs to the **unchanged original filenames**, GitHub Pages URLs and SHA256 checksums. It contains separate Instagram/Facebook captions, shared hashtags, YouTube title/description, approval status and review notes. All initial captions refer to verified on-screen text. No spoken dialogue has been transcribed or invented. All 14 initial entries are owner-approved, including audio and `ROUGH` final edits. Future uploads still require explicit approval.

Videos use the existing GitHub Pages site at `https://claudecodeguy.github.io/morning-mully-social/videos/`. No new hosting service or subscription is needed. All 14 URLs were downloaded and checksum-verified during implementation. Format checks found portrait H.264 MP4s, 4.4–13.6 seconds long. New uploads must pass format checks before approval.

## Add or approve a video without editing CSV

1. Upload an MP4 to `/videos` on GitHub's `main` branch. **Video library and approval** automatically discovers it, assigns the next stable ID and adds a `NEEDS_REVIEW` row. New rows start with blank captions rather than guessing their contents. Download the workflow's `video-library` artifact or open `data/videos.csv` to see the ID.
2. In GitHub **Actions → Morning Mully - Video library and approval → Run workflow**, select `main`, enter the video ID, add captions/title/description (or leave fields blank to retain existing drafts), and check the approval box after reviewing the full clip. Run once per video. A title is limited to 100 characters.
3. After activation, the existing refill workflow schedules the next approved unused video to Instagram Reels, Facebook Reels and YouTube Shorts together as capacity permits.

Approving captions does **not** activate video publishing. Renaming a used video does not permit republishing its bytes. Replacing a file revokes its approval. Keep previously published files and rows; missing assets stop validation instead of discarding history. Do not renumber IDs. The CSV can also be edited in GitHub if preferred.

## Queue capacity and safe recovery

Instagram and Facebook cap the combined automated image/video backlog at **9** posts each, preserving one of the Free plan's 10 slots for the same-day newsletter. YouTube caps at 10. Counts include existing/manual posts, drafts, approval requests and errors conservatively. All pages of all three channels are read before planning, and capacity is checked again immediately before each mutation. The shared existing writer concurrency group serializes newsletter and refill jobs. Manual changes during a run are caught on the next fresh read; Buffer enforces the account's hard limit as well.

The version-1 publication ledger is extended in place. Each video records per-channel scheduled time, Buffer ID and status; `sent` is tracked separately, with actual `sentAt` when returned and a delivery confirmation timestamp. Confirmed sent history remains permanent when Buffer archives posts. No history is reset or imported over existing entries.

Before each create request, a pending intent is durably committed to GitHub using the existing SHA compare-and-swap. Known successful channel IDs are never recreated. A known missing channel can resume if its original due time is still future and capacity is available. Uncertain timeouts, failed posts, missing IDs and expired partial schedules stop with an actionable error. Inspect Buffer and the saved payload/ID, then reconcile that specific ledger record; never clear history or retry an ambiguous mutation blindly. This deliberately prefers a missed slot over a duplicate. All required channels must have room before starting a new video.

The stock is finite: 14 videos cover four full weeks plus two slots. Exhausted or held video stock is reported and never recycled; image/newsletter processing continues. Three videos per week requires enough approved stock and available queue capacity.

## Verification and activation

```sh
python3 -m pip install -r automation/requirements.txt
python3 -m unittest discover -s automation -p 'test_*.py' -v
python3 automation/publish.py
python3 automation/video_library.py verify --remote
python3 automation/video_library.py probe  # requires ffprobe; installed by the library workflow
python3 automation/video_dry_run.py
python3 automation/video_dry_run.py --assume-approved
python3 automation/plan.py --videos --date 2026-12-09 --days 14 --offline
```

`video_dry_run.py` uses the complete read-only Buffer snapshot captured on November 24, 2026, and makes zero network calls. `--assume-approved` changes only in-memory simulation rows. The calendar preview is illustrative; the queue preview accounts for existing posts and capacity. See `VIDEO_DRY_RUN.md` for the results.

After reviewing and merging this feature branch, approve the desired captions. Run **Buffer refill → connected_check=true, live=false** for a fresh read-only queue preview using the existing secret. Only after owner activation approval, set repository Actions variable `VIDEO_PUBLISHING_ENABLED` to `true`; leave the existing `PUBLISHING_ENABLED` setting and `BUFFER_API_KEY` unchanged. Then the existing six-hour job handles replenishment in GitHub Actions without a running personal computer. No videos have been submitted live for integration testing: final Buffer ingestion and delivery can only be confirmed after activation approval.

To pause new video creation, set `VIDEO_PUBLISHING_ENABLED=false`. Already scheduled Buffer posts remain scheduled. Do not disable the existing newsletter or global publishing variable just to pause future videos.

## API references

Payloads follow Buffer's official [video example](https://developers.buffer.com/examples/create-video-post.html), [Instagram metadata](https://developers.buffer.com/types/InstagramPostMetadataInput.html), [Facebook metadata](https://developers.buffer.com/types/FacebookPostMetadataInput.html) and [YouTube metadata](https://developers.buffer.com/types/YoutubePostMetadataInput.html). YouTube uses `type: short`, category 17 (Sports), public visibility and an explicit title; its description is the post text. Reels use the platform-specific `type: reel` metadata and automatic publishing.

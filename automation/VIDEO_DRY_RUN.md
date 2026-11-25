# Video dry-run results — November 24, 2026

No Buffer posts, channel schedules, approvals, publication history or activation variables were changed. All 54 automated tests passed, including existing image and newsletter tests and newsletter graphic rendering. All 14 public MP4s were downloaded from GitHub Pages with matching SHA256 checksums and checked with ffprobe.

## Current approvals and actual queue capacity

The complete two-page Buffer snapshot contains 39 posts: 16 scheduled and 23 sent. There are 8 queued posts each on Instagram and Facebook and none on YouTube. The latest existing scheduled item is December 8 at 19:51 Toronto time. Initial new scheduling therefore begins after that boundary.

```text
DRY RUN: zero API calls, zero Buffer writes, zero approval changes.
Snapshot: 2026-11-24 America/Toronto (capacity may change before activation)
Approvals: actual library approvals
instagram currently occupied: 8
facebook currently occupied: 8
youtube currently occupied: 0
2026-12-09 BLOCKED: no approved unused video
WOULD SCHEDULE S008 instagram 2026-12-10T10:04:00-05:00
WOULD SCHEDULE S008 facebook 2026-12-10T09:59:00-05:00
2026-12-12 BLOCKED: no approved unused video
2026-12-13 CAPACITY: waiting for queue space on all required channels
```

## Conditional preview with captions assumed approved

This simulation changes approval values only in memory. No row has been approved. It schedules one initial three-channel video, then waits for existing posts to free capacity. Instagram/Facebook retain one free newsletter slot.

```text
DRY RUN: zero API calls, zero Buffer writes, zero approval changes.
Snapshot: 2026-11-24 America/Toronto (capacity may change before activation)
Approvals: ASSUMED FOR SIMULATION ONLY
instagram currently occupied: 8
facebook currently occupied: 8
youtube currently occupied: 0
WOULD SCHEDULE V001 instagram 2026-12-09T19:00:00-05:00
WOULD SCHEDULE V001 facebook 2026-12-09T19:00:00-05:00
WOULD SCHEDULE V001 youtube 2026-12-09T19:00:00-05:00
2026-12-10 CAPACITY: waiting for queue space on all required channels
```

## Illustrative rollout after approval

The following dates assume all captions and edits are approved, activation is approved, and rolling capacity becomes available. They are calendar targets, not live reservations. Every entry targets Instagram Reels, Facebook Reels and YouTube Shorts at **19:00 America/Toronto**. Slots may be skipped if occupied or blocked; the queue never exceeds capacity or repeats an asset.

| ID | Existing filename | Target local date | Review |
| --- | --- | --- | --- |
| V001 | [01_One_Good_Drive.mp4](https://claudecodeguy.github.io/morning-mully-social/videos/01_One_Good_Drive.mp4) | 2026-12-09 | Full audio + owner approval |
| V002 | [02_Green_Fee_213_SOUND_ON.mp4](https://claudecodeguy.github.io/morning-mully-social/videos/02_Green_Fee_213_SOUND_ON.mp4) | 2026-12-12 | Full audio + owner approval |
| V003 | [03_ProV1_Thief_Organic.mp4](https://claudecodeguy.github.io/morning-mully-social/videos/03_ProV1_Thief_Organic.mp4) | 2026-12-14 | Full audio + owner approval |
| V004 | [04_Creative_Scorekeeping_SOUND_ON.mp4](https://claudecodeguy.github.io/morning-mully-social/videos/04_Creative_Scorekeeping_SOUND_ON.mp4) | 2026-12-16 | Full audio + owner approval |
| V005 | [05_Driver_310_When_Not_Watching_ROUGH.mp4](https://claudecodeguy.github.io/morning-mully-social/videos/05_Driver_310_When_Not_Watching_ROUGH.mp4) | 2026-12-19 | Full audio + owner approval + ROUGH final edit |
| V006 | [05_Gimme_Hypocrite_SOUND_ON.mp4](https://claudecodeguy.github.io/morning-mully-social/videos/05_Gimme_Hypocrite_SOUND_ON.mp4) | 2026-12-21 | Full audio + owner approval |
| V007 | [05_I_Know_Where_It_Landed.mp4](https://claudecodeguy.github.io/morning-mully-social/videos/05_I_Know_Where_It_Landed.mp4) | 2026-12-23 | Full audio + owner approval |
| V008 | [06_Early_Trash_Talk_SOUND_ON.mp4](https://claudecodeguy.github.io/morning-mully-social/videos/06_Early_Trash_Talk_SOUND_ON.mp4) | 2026-12-26 | Full audio + owner approval |
| V009 | [06_Scratch_If_I_Could_Putt_ROUGH.mp4](https://claudecodeguy.github.io/morning-mully-social/videos/06_Scratch_If_I_Could_Putt_ROUGH.mp4) | 2026-12-28 | Full audio + owner approval + ROUGH final edit |
| V010 | [08_Seven_Hundred_Dollar_Golf_Outfit_ROUGH.mp4](https://claudecodeguy.github.io/morning-mully-social/videos/08_Seven_Hundred_Dollar_Golf_Outfit_ROUGH.mp4) | 2026-12-30 | Full audio + owner approval + ROUGH final edit |
| V011 | [08_Waiting_For_Beer_Cart_SOUND_ON.mp4](https://claudecodeguy.github.io/morning-mully-social/videos/08_Waiting_For_Beer_Cart_SOUND_ON.mp4) | 2027-01-02 | Full audio + owner approval |
| V012 | [10_Municipal_Course_Ryder_Cup_ROUGH.mp4](https://claudecodeguy.github.io/morning-mully-social/videos/10_Municipal_Course_Ryder_Cup_ROUGH.mp4) | 2027-01-04 | Full audio + owner approval + ROUGH final edit |
| V013 | [11_Twilight_Rate_Organic.mp4](https://claudecodeguy.github.io/morning-mully-social/videos/11_Twilight_Rate_Organic.mp4) | 2027-01-06 | Full audio + owner approval |
| V014 | [21_Weather_Checks_ROUGH.mp4](https://claudecodeguy.github.io/morning-mully-social/videos/21_Weather_Checks_ROUGH.mp4) | 2027-01-09 | Full audio + owner approval + ROUGH final edit |

All captions, hashtags, titles and descriptions are available in [the CSV](../data/videos.csv). The first three targets are V001 on Wednesday December 9, V002 on Saturday December 12, and V003 on Monday December 14.

## Remaining activation steps

Merge the reviewed branch, approve the desired video captions through the library workflow, run a fresh connected read-only preflight, and obtain owner activation approval before enabling `VIDEO_PUBLISHING_ENABLED`. Live media ingestion and final delivery have deliberately not been tested without that approval. Existing `PUBLISHING_ENABLED` and newsletter workflows retain their current settings.

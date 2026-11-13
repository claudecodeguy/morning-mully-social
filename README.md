# Morning Mully social content library

This repository structure was prepared from the 31 meme images, 30 statistics images and their two spreadsheets received November 13, 2026.

## Files

- `images/memes/M001.jpg`–`M031.jpg`: 31 social meme images.
- `images/statistics/S001.jpg`–`S030.jpg`: 30 social statistics graphics.
- `data/memes.csv`: original meme captions, hashtags, alt text and approval status.
- `data/statistics.csv`: original statistics captions, hashtags, alt text, source URLs and approval status.
- `data/asset_audit.csv`: exact source-image mapping, dimensions, checksum and review status.
- `index.html`: GitHub Pages hosting entry page.

Published-image file conversion is **JPEG re-encoding only**; no cropping, logo replacement or copy edits occurred. The original PNG ZIPs remain as the user's source files.

## Approval and content warnings

- **M001–M031**: `NEEDS_CREATIVE_REVIEW` because the supplied spreadsheet explicitly calls for human review.
- **S001–S010**: `HOLD_REBRAND_AND_RATIO`; the original files display GreenFeeTracker branding and are taller than the standard Instagram 4:5 feed format. Do not schedule until a branded 4:5 version is approved.
- **S011–S030**: `READY_AS_SUPPLIED` based on the user's spreadsheet; the original statistics were *not independently fact-checked as part of this file-organization pass*.
- Every item starts with `publish_status=UNPUBLISHED`. No Buffer credentials or live workflows are included.
- `facebook_caption` is intentionally empty for all rows; prepare Facebook-specific captions during the publishing automation phase.

## GitHub Pages image URL

For example, if Pages is configured for `https://claudecodeguy.github.io/morning-mully-social/`, M001 should be accessible as:

`https://claudecodeguy.github.io/morning-mully-social/images/memes/M001.jpg`

After upload, go to **Settings → Pages**, choose **Deploy from a branch**, `main`, `/ (root)`.

## Publishing development contract

Build a dry-run-first GitHub Actions scheduler that reads these two CSVs, checks `approval_status`, and queues only approved content through Buffer (separate channel calls for IG and FB). Use the Beehiiv RSS feed `https://rss.beehiiv.com/feeds/eDs7x5FU1F.xml` for Monday/Wednesday/Friday newsletter posts.

Important: Don't alter rows or mark items published merely because Buffer accepted a scheduling request; store channel IDs and verify actual post completion. Do not require Supabase or additional paid services.

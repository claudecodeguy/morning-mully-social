# Morning Mully social content library

61 image posts: 31 memes and 30 statistics. Original XLSX planners and caption CSVs are preserved. GitHub Pages serves the JPEG files at `https://claudecodeguy.github.io/morning-mully-social/`.

## Current status

- All 61 CSV IDs map to unique existing JPEGs and public URLs. All hosted image bytes were verified against the current local files on November 13, 2026.
- The user explicitly approved all 31 memes and 30 statistics on November 13, 2026. Both caption CSVs and the asset audit now record `APPROVED`.
- S001–S030 were previously `READY_AS_SUPPLIED` in the statistics CSV. S001–S010 were replaced in commit `1c91b8b` with 1080×1350 Morning Mully graphics, followed by the CSV update in `389295a`. The former README and asset audit were stale; the audit now reflects those replacement files. Statistics have not been independently fact-checked.
- All image files and caption text are unchanged. Only approval fields were updated in the caption CSVs; audit metadata for S001–S010 was also refreshed.
- Both configured Buffer channels were confirmed connected through read-only MCP checks: Instagram `morningmully` and Facebook `Morning Mully`. Neither had queued posts; one unrelated Facebook post was already sent.
- **Publishing remains disabled: repository variable `PUBLISHING_ENABLED=false`. No posts have been created in Buffer by this automation.**

## Components

- `automation/plan.py`: existing seven-day, read-only preview with RSS support; no Buffer access.
- `automation/publish.py`: validated library loader, Buffer GraphQL client, paired-channel refill, durable intent ledger, delivery reconciliation and disabled-by-default CLI.
- `data/publication-ledger.json`: permanent scheduling and delivery history. CSV `publish_status` is not changed when scheduling succeeds.
- `.github/workflows/social-dry-run.yml`: existing daily/manual preview.
- `.github/workflows/buffer-test.yml`: existing manual, read-only channel discovery.
- `.github/workflows/buffer-refill.yml`: tests plus gated publishing. Every six hours after explicit activation, reconcile Buffer and refill up to nine evergreen posts per channel, reserving one newsletter slot.

## Calendar and content preservation

The existing calendar is retained: M/W/F newsletter reservations; Tuesday/Saturday memes; Thursday/Sunday statistics. Refill reads the live Buffer schedule and timezone for each channel and uses the first available slot for the appropriate day, at least 15 minutes ahead. It schedules after existing queued content, preserving order. Missed days are not backfilled. The two channels may post at different times, matching their existing schedules.

Image posts strictly alternate meme/statistic, starting with a meme. If the next category has no approved content, refill stops rather than sending consecutive statistics. All 61 assets now have user approval; scheduling remains disabled until deployment and activation. Newsletter posts are handled by a local Codex automation on M/W/F at 11:30 a.m. Toronto time, with fallback checks at 12:30 and 1:30. It uses the approved graphic template, same-day RSS content, and Buffer MCP; it requires the Mac awake and Codex running. See `automation/NEWSLETTER_RUNBOOK.md`. The existing preview still flags its own newsletter output as requiring a graphic because generation occurs in Codex, not in the preview script.

Both CSV and asset-audit approval status must allow an item. Supplied captions, Unicode, hashtags, alt text and image URLs are retained. A blank Facebook caption falls back to the Instagram caption plus any missing hashtag block; no automatic wording, branding or signup-link rewrite is applied. Approve platform-specific wording in `facebook_caption` if desired.

## Local checks (no publishing)

```sh
python3 -m unittest discover -s automation -p 'test_*.py' -v
python3 automation/publish.py
python3 automation/publish.py --remote-images
python3 automation/plan.py --offline --days 7
```

`--remote-images` downloads public images to verify checksums; it never accesses Buffer. `--connected` additionally reads Buffer and prints proposed scheduling actions without any Buffer or GitHub writes. It requires an API key in the process environment; GitHub secrets are not available locally. Do not paste keys into the repository, command line or chat.

See [NEXT_STEP_README.md](NEXT_STEP_README.md) for verification results, activation and failure recovery.

## Newsletter automation

The recurring Codex automation begins Monday, November 16, 2026. `automation/newsletter.py` validates same-day issues and manages durable pending/accepted/sent channel checkpoints in date-specific manifests. The built-in ImageGen tool generates the approved visual style; no new API key is required. The existing GitHub workflow reserves one queue slot by targeting nine pending evergreen posts per channel. Existing queued posts are preserved. Disabling repository variable `PUBLISHING_ENABLED` stops both automated creation paths.

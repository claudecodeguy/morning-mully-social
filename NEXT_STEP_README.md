# Morning Mully — social schedule DRY RUN

Prepared for `claudecodeguy/morning-mully-social`.

## What this adds
- `automation/plan.py`: reads the existing 31 meme and 30 statistics CSV rows plus Beehiiv RSS to preview 7 days.
- `automation/settings.json`: feed URL, public GitHub Pages image base, both confirmed Buffer channel IDs and M–Su content mix.
- `automation/test_plan.py`: safety and library validation tests (standard library only).
- `.github/workflows/social-dry-run.yml`: manual run plus daily read-only run at 16:15 UTC.

This release **does not call Buffer at all** and cannot schedule or publish. It does not use the API key and does not update spreadsheets.

## Exact upload procedure
1. Extract the ZIP locally.
2. Open `https://github.com/claudecodeguy/morning-mully-social`.
3. Choose **Add file → Upload files** and drag the `automation` folder from the extracted ZIP into the upload area. Check that the three files show under `automation/`. Commit to `main`.
4. In GitHub, choose **Add file → Create new file**.
5. Enter `.github/workflows/social-dry-run.yml` as the filename. Open the matching `.yml` file in the ZIP in a text editor, copy its full contents, paste into GitHub, and commit to `main`. (Hidden `.github` folders can be difficult to upload from macOS Finder.)
6. Open **Actions → Morning Mully - Social content dry run → Run workflow**.
7. Open the run, then see **Summary** for the 7-day content table and caption previews. A downloadable JSON/Markdown artifact will also appear.

## Current library holds (as supplied)
- M001–M031: `NEEDS_CREATIVE_REVIEW`. Meme days will be blocked until those assets are approved.
- S001–S010: `HOLD_REBRAND_AND_RATIO`. Do not publish until reformatted and approved.
- S011–S030: `READY_AS_SUPPLIED` (these still need factual verification before unattended publication).
- M/W/F newsletters: only a new issue dated that day can be used. A branded newsletter graphic is required before Instagram publishing; this phase flags it as a blocker.

No approval states are modified by this release.

## Next engineering phase — ONLY after approving dry-run results
- Add a persistent publication ledger and compare scheduled posts from Buffer to avoid duplicate queueing across workflow runs.
- Create approved newsletter graphics using exact brand assets and templates, and verify RSS extraction.
- Add separate Facebook and Instagram image posts to Buffer through the GraphQL API.
- Enforce the 10-queued-posts-per-channel limit for Buffer Free.
- Write channel post IDs and final delivery status to the ledger only after API success/readback.
- Run one explicitly authorized live test, then enable automatic publication.

Do not use `BUFFER_API_KEY` in this preview workflow. No AI API, Supabase, Make, or Zapier is required.

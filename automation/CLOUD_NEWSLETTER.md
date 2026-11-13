# Cloud newsletter publisher — active, no Mac required

This supersedes the former Codex heartbeat. That heartbeat is PAUSED to avoid two publishers.

GitHub Actions workflow `newsletter-cloud.yml` polls Monday/Wednesday/Friday hourly from 11:30 a.m. through 6:30 p.m. America/Toronto (UTC cron covers both daylight-saving offsets; Python enforces local hours). It uses the existing `BUFFER_API_KEY` secret and automatic `GITHUB_TOKEN`; no local app, Mac, AI service or new credential is required. Both workflows honor repository variable `PUBLISHING_ENABLED=true`.

Each issue must be published that same Toronto day. Old issues and future-dated issues are rejected. An unavailable feed is retried by the next hourly run; absence at the final check fails visibly. The first eligible run builds a 1080×1350 branded cover from the exact RSS title and a real artwork image from that issue, with the original Morning Mully logo available for fallback. Source artwork is contained rather than cropped. If all source images fail, a fully local branded headline/logo cover is used. There is no generative-AI dependency. This deterministic default is simpler than the custom AI faces montage; generating a fresh bespoke montage unattended would require a separate image-generation API credential/integration. Preprepared custom graphics and captions can be used through the date-specific publication manifest, so the publisher is not limited to the default renderer.

Captions use the actual issue title with five golf hashtags, Instagram's link-in-bio CTA, Facebook's exact issue URL and UTM parameters, and descriptive alt text. It does not independently invent story details, choose a winner, or generate fake faces. No claim is made that the Instagram bio was modified.

Generated PNGs and manifests are stored through GitHub Contents API with SHA compare-and-swap. Buffer receives an immutable public URL pinned to the image-upload commit, so it does not depend on Pages rebuilding. The public bytes are checksum-verified first. This also works for writes made using the Actions token, which do not necessarily trigger a new Pages build.

A pending intent with the exact payload is durably saved before each Buffer mutation. Each channel is created once, immediately, and then read back to confirm sent. The returned ID is saved before readback. Later runs finish missing channels or reconcile known IDs instead of reposting. An uncertain intent can be recovered only if exactly one matching post is visible in Buffer; otherwise it stops and alerts rather than risk duplication. A failed channel never causes the successful channel to be recreated. All cloud/evergreen publishing uses the same non-cancelling workflow concurrency group. Evergreen capacity targets nine posts, reserving one slot; the hard guard remains ten, without removing approved queued posts.

Failures appear as red Actions runs and create one deduplicated GitHub issue titled `Newsletter publishing needs attention`. GitHub Actions/issue notification delivery depends on the owner's GitHub notification settings. An independent workflow, `newsletter-watchdog.yml`, runs at 23:50 UTC M/W/F (6:50 p.m. Toronto in winter; 7:50 p.m. in summer). It checks both the manifest and actual sent statuses in Buffer, and creates a distinct watchdog issue if delivery is missing. It can detect a publisher that never started, assuming GitHub itself is working. GitHub schedules can be delayed; no same-provider setup can guarantee delivery during a total GitHub outage. This removes Mac and AI/image-host dependencies, but Buffer/social-network outages may still require manual resolution. Close alert issues after resolution so a future failure can create a fresh alert.

## Validation without publication

```
python3 -m pip install -r automation/requirements.txt
python3 -m unittest discover -s automation -p 'test_*.py' -v
python3 automation/cloud_newsletter.py
```

Manual dispatch with `live=false` is read-only: no GitHub/Buffer writes. `live=true` uses the real current feed/time only; simulated clocks and fixture inputs are forbidden in live mode. Tests cover the photo-host outage fallback, rendering, same-day checks, queue full, checkpoint failures, ambiguous results, partial-channel recovery and idempotence. The November 13 issue is already sent on both channels, so a live verification today performs zero post creations. No extra public test post is required.

## Recovery and stop

Set `PUBLISHING_ENABLED=false` to stop all future automatic creation. Existing queued posts still publish unless Buffer itself is paused. Inspect cloud workflow logs, the date-specific JSON manifest and Buffer before retrying failed intents. Never delete successful IDs, reset history, or blindly recreate a timed-out request. Raw GraphQL/auth bodies and tokens are not logged.

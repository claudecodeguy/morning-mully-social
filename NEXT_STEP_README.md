# Publishing handoff — disabled pending approval

## Completed and verified locally

- Reviewed every tracked repository file, workflow, CSV record, source XLSX workbook cells, and all 61 images through contact sheets.
- Verified exact IDs (M001–M031/S001–S030), source filename mappings, JPEG signatures, local SHA256 checksums, and all 61 public GitHub Pages image checksums.
- Corrected stale audit dimensions, size, hash and review metadata for the ten already-replaced statistics images. Current images and caption text were not edited. The user subsequently approved all 61 assets; approval fields in both CSVs and the audit now record `APPROVED`.
- Read-only Buffer MCP checks confirmed both channel IDs, active connections, current channel schedules, Free-plan limit of 10, and empty queues.
- Existing workflows only previewed content or read channel information. Neither could publish.
- Added GraphQL image scheduling for both channels, preserved calendar and captions, strict alternation, conservative queue capacity checks, and persistent per-channel history.
- 19 unit tests pass, including simulated queue filling/refilling, repeated runs, external duplicates, approval blocks, delivery failures, partial channel pairs, failed ledger writes, uncertain API outcomes and activation gates. Offline library audit and preview pass.

The new API client and GitHub ledger writes have NOT been exercised against live services. MCP authorization is separate from the GitHub Actions secret. Local GitHub CLI authentication was unavailable; secret presence, repository permissions and branch rules were not independently verified. No live publishing run has been authorized. Run the read-only Actions preflight after deployment.

## How duplicate prevention works

The sole publishing workflow has a non-cancelling concurrency group. Before each Buffer creation, it commits a `pending` intent and full payload to `data/publication-ledger.json` on `main` using the GitHub Contents API and the file's expected SHA. A failed/conflicting checkpoint prevents the Buffer write. Successful creations store their Buffer ID immediately and then verify scheduling by readback. Later runs reconcile IDs to actual Buffer statuses; only `sent` records mean delivery completed.

The ledger never expires like caches/artifacts and is never automatically reset. Existing matching captions anywhere in visible Buffer history stop scheduling for manual reconciliation. Failed, removed or unscheduled known posts stop refill. A timeout or crash after an intent was written leaves an uncertain intent that blocks all further writes; it is never automatically retried. A known partial pair can finish its missing channel if its scheduled time has not passed. Content changes do not cause already-recorded IDs to be posted again.

There is no distributed transaction across GitHub and Buffer. The design prefers stopping for review over risking a duplicate. Manual scheduling or another publisher can race the fresh queue count; Buffer's own plan limit is the final guard. Use this workflow as the only automated writer. Drafts, approval requests and failed posts conservatively consume counted capacity. Never delete ledger history to make space.

## Before activation

1. The user approved committing and pushing this implementation. The repository variable `PUBLISHING_ENABLED` was explicitly set to `false` before deployment; keep it false through preflight.
2. Content approval is complete for all 61 assets. Approve any future Facebook-specific caption changes separately; fallback currently preserves Instagram's wording, including any link-in-bio reference.
3. Decide whether newsletter automation is in scope for activation. It remains blocked pending approved graphics/templates; M/W/F slots are preserved. Do not assume this release publishes RSS issues.
4. After pushing, leave repository variable `PUBLISHING_ENABLED` unset or `false`. Run **Morning Mully - Buffer refill → Run workflow**, `live=false`, `connected_check=true`. This uses the existing Actions secret for read-only API/queue/image checks. It does not create posts or ledger commits. Review its summary.
5. Verify the Actions token can write the ledger on `main` under repository rules. `contents: write` is requested only by the gated live job. Branch protection may require an explicitly approved alternative token/workflow policy. Never weaken protections implicitly.
6. Enable GitHub Actions failure notifications in your GitHub notification settings. Failures produce red Actions runs, error annotations and summaries; email delivery depends on your account settings. No unsolicited email, external webhook or issue is created.
7. Only after separate authorization for real scheduling, set repository variable `PUBLISHING_ENABLED=true` and run `live=true`. **This fills up to 10 actual posts per channel, which Buffer will publish at their scheduled times. It is not a harmless live test.** Review the read-only preflight first. The six-hour cron is also enabled by that variable. The activation variable is explicitly set to `false`.

To stop future refills, set the variable to `false` or disable the workflow. Posts already scheduled in Buffer remain scheduled; pause the Buffer channels separately if you need to stop their publication.

## Failure recovery

Open the failed Actions run, ledger and Buffer. Do not retry a `pending` entry blindly. Match its channel, full caption, image and intended timestamp in Buffer (including sent/error history). If found, replace the pending record with the confirmed ID/status while retaining its payload. If absence is conclusively established, an operator may remove only that channel's pending record to permit recovery of the partial pair. If a planned time has expired, resolve the pair and reschedule deliberately; automatic catch-up is blocked. Preserve all successful channel IDs and all prior entries.

HTTP/auth/rate-limit failures and GraphQL/typed errors fail the run without logging tokens or raw API bodies. No mutation is automatically retried. Fix the cause, reconcile the ledger, then rerun. Library validation/checksum failures require reviewing the actual image change before refreshing audit metadata.

Official payload references: [image posts](https://developers.buffer.com/examples/create-image-post.html), [scheduled posts](https://developers.buffer.com/examples/create-scheduled-post.html), [GraphQL reference](https://developers.buffer.com/reference.html).

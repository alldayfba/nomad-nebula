# Cloud Monitoring SOP

> Directive: cloud-monitoring-sop.md
> Owner: CEO Agent
> Last updated: 2026-03-19

## Purpose

Every Modal webhook execution sends a Discord notification on completion — success or failure. This gives real-time visibility into automated cloud jobs without needing to check logs manually.

## How It Works

1. A Modal webhook function runs (triggered by schedule or HTTP call)
2. The function wraps its core logic in a try/except block
3. On success: Discord receives `[MODAL] ✅ {slug} completed in {duration}s`
4. On failure: Discord receives `[MODAL] ❌ {slug} FAILED: {error}`
5. The notification fires even if the main logic crashes — monitoring never silently fails

## Discord Webhook Setup

**Environment variable:** `DISCORD_WEBHOOK_URL` in `.env`

If `DISCORD_WEBHOOK_URL` is empty, the monitoring helper falls back to `DISCORD_CLOUD_LOG_WEBHOOK`. If both are empty, monitoring is skipped silently (no crash).

To create a Discord webhook:
1. Open the target Discord server
2. Go to Server Settings → Integrations → Webhooks
3. Click "New Webhook", name it "Modal Cloud Monitor", select the #logs or #automation channel
4. Copy the webhook URL
5. Set in `.env`: `DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...`

## The Monitoring Helper

The `notify_discord` helper lives at the top of each Modal webhook file:

```python
import time
import urllib.request
import urllib.parse

def notify_discord(slug: str, success: bool, duration: float, error: str = ""):
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL") or os.environ.get("DISCORD_CLOUD_LOG_WEBHOOK", "")
    if not webhook_url:
        return
    if success:
        message = f"[MODAL] ✅ {slug} completed in {duration:.1f}s"
    else:
        short_error = str(error)[:200]
        message = f"[MODAL] ❌ {slug} FAILED: {short_error}"
    payload = urllib.parse.urlencode({"content": message}).encode()
    req = urllib.request.Request(webhook_url, data=payload, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass  # Never let monitoring crash the monitored function
```

The wrapper pattern around any Modal function:

```python
@app.function(...)
@modal.web_endpoint(...)
def my_endpoint():
    slug = "my-endpoint"
    start = time.time()
    try:
        result = _run_core_logic()
        notify_discord(slug, success=True, duration=time.time() - start)
        return result
    except Exception as e:
        notify_discord(slug, success=False, duration=time.time() - start, error=str(e))
        raise
```

## Adding a New Modal Deployment to Monitoring

When creating a new Modal webhook file:

1. Copy the `notify_discord` helper function into the file (top of module, after imports)
2. For each `@modal.web_endpoint` function, wrap the body with the try/except pattern above
3. Use the function's label or a descriptive slug for the `slug` parameter
4. Add `DISCORD_WEBHOOK_URL` to the Modal secret if running in production (or rely on env mount)
5. Test with `modal run execution/your_webhook.py::your_function` locally first

**Existing monitored deployments:**
| File | Slug(s) | Schedule |
|---|---|---|
| `execution/training_officer_webhook.py` | `training-officer-scan`, `training-officer-health`, `training-officer-pending`, `training-officer-drift` | Daily 6 AM UTC |

## What Good Logs Look Like

```
[MODAL] ✅ training-officer-scan completed in 47.2s
[MODAL] ✅ training-officer-health completed in 3.1s
```

These are expected and require no action.

## What Requires Action

| Pattern | Meaning | Action |
|---|---|---|
| `❌ FAILED: ModuleNotFoundError` | Dependency not in Modal image | Add to `.pip_install()` and redeploy |
| `❌ FAILED: FileNotFoundError` | Mount path wrong or file missing | Check `modal.Mount` condition filters |
| `❌ FAILED: anthropic.APIStatusError` | Anthropic API down or key invalid | Check API status, rotate key if needed |
| `❌ FAILED: TimeoutError` | Task exceeded Modal timeout | Increase `timeout=` or split task |
| Success but 0 proposals generated for 3+ days | Scan running but stuck | Check `detect_changes` logic, verify file hashes |
| No messages for 24h on scheduled jobs | Cron not firing or Modal down | Check Modal dashboard at modal.com |

## Known Issues

- Modal containers do not have access to `.env` by default — secrets must be mounted via `modal.Secret` or the env file must be included in the mount
- `urllib.request` is used instead of `requests` to avoid adding a dependency to the Modal image
- Discord webhook rate limit: 5 messages/2 seconds per webhook. Cloud monitoring sends at most 1 message per job execution so this is never an issue in practice.

## Learnings <!-- updated: 2026-03-19 -->

### 2026-03-19 — Initial setup
- Discord is the notification target (not Slack) — `DISCORD_WEBHOOK_URL` is already defined in `.env` for the Storefront Stalker feature, reuse it for cloud monitoring
- `urllib.request` chosen over `requests` to keep Modal image slim (no extra pip_install needed)
- Webhook notifications wrapped in their own try/except so a Discord outage never causes a Modal job failure

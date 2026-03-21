# Security Guardrails SOP
> directives/security-guardrails-sop.md | Version 1.0

---

## Purpose

Kabrin waited months before deploying OpenClaw because of security concerns. He set it up right: separate hardware, separate user, scoped access only. This SOP codifies those rules so nothing gets misconfigured.

The risk is real: one bad prompt + too much access = bot deletes your files, orders 400 pounds of meat, or charges your ad account. Don't give it access it doesn't need.

---

## Hardware Setup

- **Dedicated machine:** Run bots on a Mac Mini or dedicated PC — not your primary laptop
- **Separate user profile:** Create a new macOS/OS user specifically for the bot. The bot operates only within that user's home directory.
- **Why:** If something goes wrong, the blast radius is limited to that user's files, not your entire system

```bash
# macOS: create a new user
# System Settings → Users & Groups → Add Account
# User type: Standard (not Admin)
# Give it a name like "SabboAI" or "OpenClaw"
```

---

## File Access Rules

| Access | Allowed | Notes |
|---|---|---|
| Local project directory (`/Users/SabboAI/...`) | Yes | Bot's working space |
| Shared folder (`/Users/Shared/antigravity/`) | Yes, limited | Read/write for inbox/outbox/memory only |
| Google Drive | Read-only | Set to read-only in Google Drive settings |
| Other user profiles | No | Never |
| System files | No | Never |
| `/Users/sabbojb/` (your main user) | No | Never — separate user enforces this |

---

## Authentication Rules

- **API keys only.** Never store passwords in bot files or `.env`.
- **No saved browser sessions.** Bots don't use browsers that are logged into accounts.
- **No billing credentials.** Credit card info, Stripe keys, PayPal — never in bot files.
- **Principle of least privilege.** Give read-only access. Give write access only where explicitly required.

---

## Meta Ads Access

**Rule: The bot never has publishing access to Meta Ads.**

What it CAN do:
- Scrape the public Meta Ad Library (no auth required)
- Read performance data if you manually paste it in

What it CANNOT do:
- Log into Meta Ads Manager
- Create, edit, pause, or publish any ad
- Access billing or payment methods in Meta

If you ever want to give it read access to Ads Manager API:
1. Create a dedicated System User in Meta Business Manager
2. Grant read-only permissions only (no ads_management, no business_management)
3. Store the access token in `.env` only, not in any markdown file
4. Never grant it payment method access

---

## Google Account Access

Current setup (matches Kabrin's):
- **Read-only access to Gmail** — bot can receive and read emails sent to it, cannot reply or send
- **Read-only access to Google Drive** — can read files, cannot create or delete
- **No Google Ads access**

```env
# .env — example
GMAIL_ACCESS=read_only
GDRIVE_ACCESS=read_only
```

---

## Telegram Bot Security

- The Telegram bot token lives in `.env` only — never in a markdown file
- Restrict the bot to respond only to your Telegram user ID (add `TELEGRAM_ALLOWED_USERS` to `.env`)
- If you share access with a team member, create a separate bot token for them

```env
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
TELEGRAM_ALLOWED_USERS=your_user_id_here
```

---

## Prompt Safety Rules

The silicon Valley problem: vague instructions like "clear these files" caused a bot to delete everything it could find. Prompting discipline prevents this.

Rules for all instructions given to bots:
1. **Scope every instruction.** "Delete the temp files in `.tmp/ads/`" not "delete the old files."
2. **No open-ended file operations.** Never say "clean up" without specifying exactly what.
3. **Approval gates on destructive actions.** Any file delete or overwrite requires explicit confirmation before executing.
4. **Test in `.tmp/` first.** New scripts always test on temporary files before touching real data.

---

## Incident Response

If a bot does something unexpected:
1. Kill the process immediately: `kill [PID]` or shut down the Mac Mini user session
2. Check what it did: review file modification timestamps, check logs
3. Restore from backup if needed (keep backups of key files)
4. Update this SOP with what went wrong and how to prevent it
5. Do not re-enable until you understand the cause

---

## Backup Protocol

Key files to back up regularly:
- All files in `bots/` (identity, memory, skills, heartbeat, tools)
- All files in `directives/`
- `.env` (encrypted or in a password manager — not in git)

```bash
# Simple backup to an external location
cp -r /Users/SabboAI/bots/ /path/to/backup/bots_$(date +%Y%m%d)/
```

---

## Automated Enforcement — CodeSec Agent

The CodeSec agent (`SabboOS/Agents/CodeSec.md`) continuously enforces these guardrails programmatically:

- **Always-on file watcher** (`execution/codesec_watch.sh`) monitors all code changes via fswatch
- **Security scanning** (SEC-001 through SEC-010) catches hardcoded secrets, injection patterns, insecure calls, and OWASP Top 10 issues
- **Infrastructure integrity** (INF-001 through INF-008) verifies launchd daemons, bridge directories, .env keys, and script health
- **Daily full scan** at 8:00 AM via launchd (`com.sabbo.codesec-scan`)
- **Approval-gated** — generates CodeSec Reports (CSRs) for Sabbo to review, never modifies files directly

Run manually: `python execution/codesec_scan.py`
SOP: `directives/codesec-sop.md`

---

*Last updated: 2026-02-22*

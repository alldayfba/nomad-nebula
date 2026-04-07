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

## Claude Code Security — AI-Specific Vulnerabilities

These vulnerabilities are specific to AI agent workflows and apply on top of all rules above. Source: Nick Saraev Advanced Course (2026-04).

### VULN-1: API Key Chat History Exposure

**Risk:** Every conversation in Claude Code is logged as JSON in `~/.claude/`. Any API key pasted in chat is permanently stored in plain text across potentially hundreds of session files. An attacker who accesses `~/.claude/` gets every key ever mentioned.

**Rules:**
- Store ALL API keys in `.env` files exclusively — never paste them in chat
- Reference keys by variable name only: "use the KEEPA_API_KEY from .env" not the actual value
- Never `cat .env`, `echo $KEY`, or display key values in conversation
- Add to CLAUDE.md: "Never read, display, or output .env file contents"
- Periodically audit: `grep -r "sk-" ~/.claude/` to check for leaks

### VULN-2: Supply Chain / Package Hallucination

**Risk:** LLMs hallucinate legitimate-sounding package names due to token encoding. Attackers register typosquatted packages (e.g., "acorns" instead of "acorn") that exfiltrate API keys and conversation logs on install.

**Rules:**
- Before any `npm install` or `pip install`, audit the package list for unfamiliar names
- Prompt Claude: "Verify all packages are legitimate with verified histories. Flag suspicious names."
- Never enable unlimited API billing — always set spending limits
- Regularly audit `package.json` / `requirements.txt` for unexpected additions
- Pin dependency versions to prevent supply chain attacks via updates

### VULN-3: Database Row-Level Security (RLS)

**Risk:** Supabase does NOT enable RLS by default. Without it, anyone with the public anon key can READ, WRITE, and DELETE all rows in all tables. Real-world example: Molt (AI agent platform) had zero RLS — attacker read all agents in 2 seconds, created 100K fake profiles.

**Rules:**
- Enable RLS on ALL Supabase tables immediately (2-second toggle in dashboard)
- Restrict access so users only see their own data (`auth.uid() = user_id`)
- Verify RLS is enabled on every new table as part of deployment checklist
- Test with `supabase.from('table').select('*')` using anon key — should return empty or user-scoped data only

### VULN-4: Public-Facing Agent Endpoints

**Risk:** Running unauthenticated Claude/agent instances on public URLs. Bot farms scan all cloud providers (VPS, Hostinger, etc.) constantly testing thousands of requests/second for known vulnerabilities.

**Rules:**
- Never expose agent endpoints without authentication
- Implement firewall rules on all public-facing services
- Never share SSN, passport, credit card data with public Claude instances
- Use local instances authenticated through trusted channels (Telegram bot, Discord bot)
- Modal webhooks: always include API key validation (`X-API-Key` header check)

### VULN-5: Credit Card Data in AI Context

**Risk:** If an agent reads a credit card number, it gets permanently logged in conversation history. Attackers search logs for 16-20 digit patterns matching Visa/MC formats. Creates PCI compliance liability.

**Rules:**
- NEVER pass raw credit card numbers to any AI agent
- Use Stripe or certified payment processors exclusively
- Never store, display, or process raw CC data in any script or conversation
- If a user accidentally pastes CC data: flag immediately, do not store, advise rotation

### Security Audit Template

Run this audit using a **fresh agent conversation** (no existing context bias) to get an unbiased assessment. Use a **separate agent** to implement any fixes (avoids confirmation bias from the audit agent).

**Audit prompt for fresh agent:**
```
Perform a comprehensive security audit of this codebase:
1. Architecture summary — what services are exposed, what databases exist
2. API token search — grep for: sk-live, sk-test, sk-bearer, sk-ant, Bearer, Authorization headers
3. Secrets in git — check .gitignore covers: .env, credentials.json, token.json, *.pem, *.key
4. Supply chain — audit package.json/requirements.txt for suspicious or unfamiliar packages
5. Database security — check all Supabase tables have RLS enabled
6. Public endpoints — list all routes, verify authentication on each
7. ML-specific — check for exposed model weights, training data, or inference endpoints
8. Compliance — PCI (no raw CC data), data privacy (no PII in logs)
Document all findings with severity (CRITICAL/HIGH/MEDIUM/LOW) and remediation steps.
```

---

*Last updated: 2026-04-03*

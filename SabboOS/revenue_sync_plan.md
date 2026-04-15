## Revenue sync — what's needed

Whop API:
- OAuth key: WHOP_API_KEY
- Endpoint: https://api.whop.com/api/v5/app/memberships (list all + GET details)
- Webhook: membership.went_valid, membership.went_invalid, membership.cancelled
  → POST /api/webhooks/whop → upsert into 'subscriptions' table
- Use that to populate subscription_status + plan on users

Fanbasis:
- Webhook-only API (no pull endpoint surfaced publicly)
- Configure in Fanbasis dashboard: send events to /api/webhooks/fanbasis
- Events: subscription.created, subscription.charged, subscription.failed
- Same shape: upsert into 'subscriptions'

Revenue math:
- MRR = SUM(amount_cents / 100) for all subscriptions with status IN ('active', 'trialing')
  grouped by billing_interval (monthly adds as-is, annual divides by 12)
- ARR = MRR * 12
- All-time revenue = SUM of all 'payments' rows, which already gets populated by the webhooks

247growth cross-link:
- GHL (leadconnector) already posts to /api/ghl/webhook
- EOC reports come from closer_submissions table
- Revenue from coaching sales lives in 247growth.org DB
- To merge: scheduled job pulls 247growth daily totals via API key into
  247profits 'external_revenue' table, combined MRR widget reads both

Build order:
1. Whop webhook handler (fastest, Whop already used for credit packs)
2. Dashboard revenue widget reads from subscriptions table
3. Fanbasis webhook handler
4. 247growth cross-sync (scheduled daily)

# Automation Builder — SOP
> directives/automation-builder-sop.md | Version 1.0

---

## Purpose

Step-by-step execution guide for designing, building, testing, and maintaining automations in Zapier and GoHighLevel.

---

## When This Runs

- User requests a new automation ("set up a Zap", "create a GHL workflow", "automate X")
- CEO dispatches AutomationBuilder for a detected manual process
- Monthly automation audit (manual trigger or scheduled)

---

## Workflow: New Automation

### Step 1 — Understand the Request

Gather:
1. **What triggers it?** (new lead, form submission, payment, tag change, time-based)
2. **What should happen?** (send email, update sheet, move pipeline, notify Slack)
3. **Which business?** (agency, coaching, internal)
4. **What data flows?** (field names, formats, required vs optional)
5. **What's the error case?** (what happens if the trigger fires but an action fails)

If unclear, ask. Don't guess on automation logic — wrong wiring wastes time and creates ghost data.

### Step 2 — Choose Platform

```
Is the workflow entirely within GHL?
├── YES → Build in GHL
└── NO → Does it connect 2+ external tools?
    ├── YES → Build in Zapier
    └── NO → Is it lead/client-facing?
        ├── YES → GHL
        └── NO → Zapier
```

### Step 3 — Write the Spec

Produce the YAML spec (Zapier or GHL format from the agent directive). Save to `.tmp/automations/specs/{id}-{name}.yaml`.

Present spec to user for approval before building.

### Step 4 — Build

**Zapier:**
1. Create new Zap in correct folder
2. Configure trigger app + event + account
3. Test trigger — confirm sample data pulls correctly
4. Configure each action step with field mappings
5. Test each step individually
6. Add filter/path logic if needed
7. Configure error handling (auto-retry + Slack notification)
8. Run full end-to-end test

**GHL:**
1. Create new Workflow
2. Set trigger type + conditions
3. Build action sequence with wait steps
4. Set goal event (what exits the workflow)
5. Configure enrollment settings (once/multiple)
6. Test with a test contact
7. Review SMS/email copy in the workflow
8. Publish workflow

### Step 5 — Test

Run 3 test cycles with real (or realistic) data:
- **Test 1:** Happy path — everything works as expected
- **Test 2:** Edge case — missing field, unusual data format
- **Test 3:** Error case — simulate a failure, verify notification fires

### Step 6 — Register

Add entry to `SabboOS/automation-registry.yaml` with all fields.

### Step 7 — Go Live

- Turn on the Zap / publish the GHL workflow
- Monitor first 24 hours for errors
- Confirm at least one real trigger fires correctly

---

## Workflow: Fix Broken Automation

### Step 1 — Diagnose

1. Check Zapier task history / GHL workflow analytics
2. Identify which step is failing
3. Check if the connected app changed (API update, field rename, auth expired)
4. Check if the trigger data format changed

### Step 2 — Fix

Common fixes:
- **Auth expired** → Reconnect account in Zapier/GHL
- **Field mapping broken** → Re-map fields with current schema
- **API change** → Update webhook URL or payload format
- **Rate limit** → Add delay step or reduce trigger frequency
- **App deprecated** → Find replacement app or use webhook

### Step 3 — Test + Verify

Run the same 3-test protocol as new automations.

### Step 4 — Update Registry

Update `last_tested` and `notes` in the registry entry.

---

## Workflow: Automation Audit

Run monthly or on-demand. Full protocol in agent directive (AutomationBuilder.md → Audit Protocol).

Output goes to `.tmp/automations/audit-{YYYY-MM-DD}.md`.

Present findings to user with recommendations:
- Automations to kill (unused/redundant)
- Automations to fix (error rate >5%)
- Automations to add (detected manual processes)
- Cost optimizations (Zapier plan vs usage)

---

## Zapier Plan Awareness

| Plan | Monthly Tasks | Price |
|---|---|---|
| Free | 100 | $0 |
| Starter | 750 | $19.99/mo |
| Professional | 2,000 | $49/mo |
| Team | 50,000 | $69/mo |

Track total monthly tasks across all Zaps. Alert if approaching plan limit.

**Cost reduction tactics:**
- Replace multi-step Zaps with single webhook + code step
- Move GHL-only workflows out of Zapier
- Use Zapier Paths instead of duplicate Zaps
- Batch operations where possible (Zapier Digest)

---

## GHL Workflow Limits

- Max 100 active workflows per sub-account
- SMS: respect daily sending limits per number
- Email: warm up new sending domains before high volume
- Webhooks: 30-second timeout — keep payloads lean

---

## Common Mistakes to Avoid

1. **No error handling** — every Zap/workflow MUST notify on failure
2. **Duplicate automations** — check registry before building
3. **Over-automating** — if it runs once a month, a manual step is fine
4. **Hardcoded values** — use dynamic fields from trigger data, not static text
5. **No testing** — never go live without the 3-test protocol
6. **Ignoring Zapier task counts** — premium apps + multi-step = burns tasks fast
7. **SMS without opt-in** — GHL SMS requires proper consent tracking

---

## Integration Points

| System | Role | Connection |
|---|---|---|
| GHL | CRM, pipeline, lead nurture, SMS/email | Native workflows + Zapier webhooks |
| Zapier | Integration hub, data routing | Connects everything else |
| Google Sheets | KPI tracking, data logging | Zapier destination |
| Slack | Team notifications | Zapier destination |
| Stripe | Payments | Zapier trigger |
| Calendly | Appointments | Zapier trigger |
| Typeform/Tally | Forms | Zapier trigger |
| Modal webhooks | Custom execution | Zapier Webhooks by Zapier |

---

## Self-Annealing

When an automation breaks:
1. Fix it (Steps above)
2. Update this SOP if the failure reveals a new edge case
3. Add the error pattern to the Common Mistakes section
4. Update the registry entry with what went wrong
5. If it's a recurring failure pattern → propose a structural change

---

*SabboOS — Automation Builder SOP v1.0*

# Closer Bot — Skills
> bots/closer/skills.md | Version 1.0

---

## Purpose

This file catalogs every skill the Closer bot can execute. Each skill references specific SOPs, scripts, and execution tools. Skills are invoked by trigger phrases or scheduled execution. This is the routing map — read this before doing any task.

---

## Owned Claude Code Skills (Slash Commands)

| Skill | Slash Command | Directive | Script |
|---|---|---|---|
| Lead Gen / Signal Scan | `/lead-gen` | `directives/lead-gen-sop.md` | `execution/run_scraper.py` |
| ICP Filtering | `/filter-icp` | `directives/lead-gen-sop.md` | `execution/filter_icp.py` |
| Outreach Sequence | `/outreach-sequence` | `directives/outreach-sequencer-sop.md` | `execution/outreach_sequencer.py` |
| Cold Email | `/cold-email` | `directives/email-generation-sop.md` | `execution/generate_emails.py` |
| Sales Prep | `/sales-prep` | — | `execution/research_prospect.py` |
| Pipeline Analytics | `/pipeline-analytics` | `directives/pipeline-analytics-sop.md` | `execution/pipeline_analytics.py` |
| Follow-Up | `/follow-up` | `directives/outreach-sequencer-sop.md` | `execution/outreach_sequencer.py` |

---

## Skill: Signal Scan

**When to use:** Every morning at 8:00 AM, or when Sabbo says "find leads" / "prospect"
**Reference in order:**
1. `directives/lead-gen-sop.md` → Signal sources and classification rules
2. `bots/closer/memory.md` → Recent patterns (what types of signals converted)
3. Discord channel scan → Engagement signals from sourcing/general channels
4. Instagram DM/comment scan
5. YouTube comment scan on recent videos

**Output standard:** List of new signals with channel, content snippet, initial tier classification (A/B/C/unclear), and recommended next action (run ICP gates / direct book / VSL route / ignore)

---

## Skill: ICP Qualification

**When to use:** Immediately after a new signal is identified, or when Sabbo says "qualify [name]"
**Reference in order:**
1. `directives/lead-gen-sop.md` → ICP definition (capital, motivation, timeline, time, coachability)
2. `SabboOS/Amazon_OS.md` → Sections 1 and 4 (offer and funnel)
3. `execution/filter_icp.py` → Run the script on the lead data
4. `.tmp/24-7-profits-sales-optimization.md` → NEPQ qualification questions (Deliverable 1)
5. `bots/closer/memory.md` → Past disqualification patterns (what to watch for)

**Output standard:** PASS / FAIL / SLOW per gate, overall result (Qualified/VSL Route/Disqualified), tier tag if qualified, recommended outreach message

---

## Skill: Pipeline Stage Management

**When to use:** After any lead interaction, or when Sabbo says "pipeline" / "what's in the pipeline?"
**Reference in order:**
1. `execution/pipeline_analytics.py` → Pull current stage counts and velocity
2. `execution/dashboard_client.py contacts` → Cross-reference with GHL CRM
3. `bots/closer/memory.md` → Baseline stage conversion rates for comparison

**Output standard:** Stage breakdown table (Aware / Engaged / Qualified / VSL Routed / Booked / Called / Closed / Archive), velocity vs prior week, stale lead flags with recommended re-engagement actions

---

## Skill: VSL Routing

**When to use:** When a lead passes some but not all ICP gates, or shows interest but is not ready to book
**Reference in order:**
1. `SabboOS/Agents/Closer.md` → VSL Routing Decision Tree
2. `clients/kd-amazon-fba/scripts/vsl-script.md` → What the VSL covers (for personalized context message)
3. `directives/outreach-sequencer-sop.md` → Nurture sequence configuration
4. `.tmp/creators/hormozi-docx-extractions/pre-call-nurture-email-sms-1.md` → Email + SMS templates

**Output standard:** Personalized VSL routing message (DM or email), sequence trigger command for outreach_sequencer.py, CRM tag recommendation

---

## Skill: Booking Outreach

**When to use:** After a lead passes all 5 ICP gates — generate and send booking CTA
**Reference in order:**
1. `clients/kd-amazon-fba/scripts/setter-outreach-script.md` → Active setter scripts and DM templates
2. `.tmp/creators/hormozi-docx-extractions/dm-setting-breakdown.md` → DM-based setting framework
3. `bots/creators/nik-setting-brain.md` → Profile funnel, 1% Rule, show rate optimization
4. `bots/closer/memory.md` → What booking messages converted best

**Output standard:** Personalized DM/email with booking CTA (no price mentioned), calendar link, follow-up schedule if no response within 24 hours

---

## Skill: Pre-Call Research Brief

**When to use:** For every lead that books a call — 24 hours before the scheduled call
**Reference in order:**
1. `execution/research_prospect.py` → Run automated research
2. `execution/dashboard_client.py journey --contact-id <id>` → Lead history in CRM
3. `clients/kd-amazon-fba/scripts/closing-call-script.md` → What the closer needs to know to personalize the call

**Output standard:** One-page research brief including: background, signal history, tier classification, ICP gate results, likely objections, personalization hooks, recommended opener for the closer

---

## Skill: Show Rate Protection

**When to use:** After any call is booked — immediately trigger the confirmation sequence
**Reference in order:**
1. `.tmp/creators/hormozi-docx-extractions/post-call-show-rate-booking-process-1.md` → 11-touchpoint system
2. `clients/kd-amazon-fba/emails/all-email-sequences.md` → Pre-call nurture templates
3. `directives/outreach-sequencer-sop.md` → Sequence timing and channels

**Output standard:** Confirmation sequence triggered via outreach_sequencer.py — Day 0 (booking confirmation), Day -1 (reminder + value), Day -4hrs (same-day reminder), channels: email + SMS + DM

---

## Skill: Follow-Up Close Support

**When to use:** After any "Called → No Close" or "Called → No Show" disposition
**Reference in order:**
1. `.tmp/creators/hormozi-pdf-extractions/closing.md` → Objection-specific closes (7 closes + 28 rules)
2. `.tmp/24-7-profits-sales-optimization.md` → Objection battle cards (Deliverable 2)
3. `clients/kd-amazon-fba/emails/all-email-sequences.md` → No-close and no-show email sequences
4. `bots/closer/memory.md` → Which objections this lead raised, their tier, history

**Output standard:** Classified objection type, recommended close framework, personalized follow-up message (Day 0/1/3/7), outreach_sequencer.py command to trigger the sequence

---

## Skill: Re-Engagement Campaign

**When to use:** For leads in "Cold Archive" stage that are > 60 days dormant, or when Sabbo says "re-engage"
**Reference in order:**
1. `clients/kd-amazon-fba/emails/all-email-sequences.md` → Cold nurture sequence
2. `execution/generate_emails.py` → Personalized re-engagement email generation
3. `bots/closer/memory.md` → Why the lead went cold, original tier, objection history

**Output standard:** Re-engagement message (specific, not generic — references their original signal or conversation), recommended channel (email vs DM), CRM stage move recommendation

---

## Skill: Pipeline Constraint Detection

**When to use:** When pipeline velocity drops, booking rate falls, or Sabbo asks "where is it breaking?"
**Reference in order:**
1. `execution/pipeline_analytics.py report` → Full funnel data
2. `SabboOS/Agents/Closer.md` → Prospect Pipeline Constraint Waterfall
3. `bots/creators/jeremy-haynes-brain.md` → Bottleneck analysis framework
4. `bots/closer/memory.md` → Historical conversion rates for comparison

**Output standard:** First constraint identified (top of the waterfall), data supporting the diagnosis, recommended fix with specific script or tool reference, expected improvement if fixed

---

## Allocated SOPs

| SOP | Purpose |
|---|---|
| `directives/lead-gen-sop.md` | Signal sourcing, ICP definition, lead classification |
| `directives/outreach-sequencer-sop.md` | Sequence engine rules, timing, channel mix |
| `directives/email-generation-sop.md` | Email outreach standards and generation rules |
| `directives/pipeline-analytics-sop.md` | Pipeline reporting, velocity calculation, bottleneck detection |
| `directives/reverse-prompting-sop.md` | Clarifying questions before complex outreach campaigns |

---

*Closer Bot Skills v1.0 — 2026-03-16*

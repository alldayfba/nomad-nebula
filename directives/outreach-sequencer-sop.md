# Outreach Sequencer SOP
> directives/outreach-sequencer-sop.md | Version 1.0

---

## Purpose

Manage multi-touch personalized outreach sequences. Takes qualified leads, generates personalized copy per prospect, tracks pipeline from draft to booked. Owned by the outreach bot.

---

## Trigger

- User says "create outreach sequence" or "outreach pipeline"
- CEO dispatches outreach-agent for pipeline velocity
- After lead gen produces filtered CSV
- Client health < 60 triggers retention sequence

---

## Script

`execution/outreach_sequencer.py`

**DB:** `.tmp/outreach/sequences.db`
**LLM:** Claude Sonnet 4.6 (via Anthropic API)

---

## Commands

### Create a sequence from leads CSV
```bash
python execution/outreach_sequencer.py create-sequence --leads .tmp/filtered_leads.csv --template dream100
```

Templates:
| Template | Touches | Duration | Use Case |
|---|---|---|---|
| `dream100` | 7 | 30 days | High-value prospects, full Dream 100 pipeline |
| `cold_email` | 4 | 14 days | Standard cold outreach |
| `warm_followup` | 3 | 10 days | Re-engaging warm leads |

### View touches due today
```bash
python execution/outreach_sequencer.py next-touches --due today
python execution/outreach_sequencer.py next-touches --due 2026-02-25
```

### Mark pipeline progress
```bash
python execution/outreach_sequencer.py mark-sent --touch-id 5
python execution/outreach_sequencer.py mark-replied --prospect-id 3 --notes "Interested in agency services"
python execution/outreach_sequencer.py mark-booked --prospect-id 3
```

### Pipeline stats
```bash
python execution/outreach_sequencer.py stats
```
Returns: total prospects, response rate, book rate, touches sent/pending.

### List all sequences
```bash
python execution/outreach_sequencer.py list-sequences
```

### Export
```bash
python execution/outreach_sequencer.py export --format json
```

---

## Sequence Templates

### Dream 100 (7 touches, 30 days)
| Touch | Day | Type | Purpose |
|---|---|---|---|
| 1 | 0 | email | Initial value delivery (GammaDoc or audit) |
| 2 | 3 | linkedin_dm | Soft connection request |
| 3 | 7 | email | Follow-up with new insight |
| 4 | 14 | email | Case study relevant to their niche |
| 5 | 18 | linkedin_dm | Quick question about their challenge |
| 6 | 24 | email | Social proof + results |
| 7 | 30 | email | Final touch / breakup |

### Cold Email (4 touches, 14 days)
| Touch | Day | Type | Purpose |
|---|---|---|---|
| 1 | 0 | email | Cold intro with value prop |
| 2 | 3 | email | Follow-up with proof |
| 3 | 7 | email | New angle / question |
| 4 | 14 | email | Breakup email |

---

## Personalization

The sequencer generates personalized copy per prospect using:
- Prospect data from CSV (name, website, niche)
- Sender context from Agency_OS.md or Amazon_OS.md
- Touch template structure

**Hard rule:** No mass-blast. Every message must reference something specific about the prospect.

---

## Integration Points

| System | Connection |
|---|---|
| CEO Agent | Dispatches when pipeline stalled or client at-risk |
| Lead Gen | `run_scraper.py` → `filter_icp.py` → `outreach_sequencer.py` |
| Dream 100 | `run_dream100.py` → feeds into dream100 template |
| Business Audit | `generate_business_audit.py` → audit link in touch 1 |
| Outreach Bot | `bots/outreach/skills.md` references this sequencer |
| Training Officer | Grades outreach output via `grade_agent_output.py` |

---

## Guardrails

- Sabbo reviews all generated sequences before actual sending
- All touches logged with timestamp, recipient, content
- No access to personal accounts without per-campaign approval
- Daily send caps must be set before activation

---

## Self-Annealing

- Track response rates per template → prefer higher-performing templates
- Track which touch numbers get most replies → optimize sequence timing
- Store winning subject lines and hooks in `bots/outreach/memory.md`

---

*Outreach Sequencer SOP v1.0 — 2026-02-21*

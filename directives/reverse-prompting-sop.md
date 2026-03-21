# Reverse Prompting SOP
> directives/reverse-prompting-sop.md | Version 1.0

---

## Purpose

Instead of the human writing a perfect prompt, the agent asks clarifying questions first. This flips the interaction: the agent prompts the human to gather missing context before executing. Result: better input = better output.

---

## When to Use Reverse Prompting

**Always use when:**
- Starting a new client deliverable (landing page, ad campaign, email sequence)
- Task has 3+ ambiguous dimensions (audience, tone, format, scope, timeline)
- The user's request is less than 2 sentences
- A prompt contract exists for the task and required fields are missing

**Skip when:**
- User explicitly says "just do it" or provides comprehensive context
- Task is deterministic (scrape this URL, export this CSV)
- User has provided all required contract fields
- Follow-up on a task already in progress

---

## How It Works

1. Agent receives a task request
2. Agent loads the relevant prompt contract (if one exists)
3. Agent identifies missing/ambiguous required fields
4. Agent generates 3-7 numbered questions, prioritized by impact
5. User answers (can skip with "use your best judgment")
6. Agent assembles complete prompt from answers + defaults
7. Agent executes the task

---

## Question Design Rules

1. **Prioritize** — Ask the highest-impact questions first
2. **Offer defaults** — "What tone? (default: professional casual)"
3. **Multiple choice when possible** — "Format: A) Email, B) Landing page, C) Ad script"
4. **Max 7 questions** — More than 7 and the user loses patience
5. **Group related questions** — Don't ask about audience in Q1 and then again in Q5
6. **Never ask what you can infer** — If you can figure it out from context, don't ask

---

## Pre-Built Question Sets

### Client Onboarding
1. What's the business model? (product, service, SaaS, coaching)
2. Who is the ICP? (demographics, pain points, buying triggers)
3. What's the current traffic source and volume?
4. What's the primary goal? (leads, sales, awareness)
5. Budget range for this engagement?
6. Timeline or deadline?

### Ad Campaign
1. Platform? (Meta, Google, YouTube, TikTok)
2. Campaign objective? (awareness, leads, sales)
3. Target audience? (demographics, interests, behaviors)
4. Budget? (daily/total)
5. Do you have existing creative assets?
6. Landing page URL?

### Content Piece
1. Topic or subject?
2. Target audience?
3. Format? (blog, social post, video script, email)
4. Tone? (professional, casual, authoritative, friendly)
5. Call-to-action?
6. Distribution channel?

### FBA Product Evaluation
1. ASIN or product URL?
2. Buy cost (or source)?
3. Expected sell price?
4. Category?
5. Is this OA, RA, or wholesale?

---

## Execution

### Scripted (for automation pipelines)

```bash
python execution/reverse_prompt.py \
  --task-type "ad_campaign" \
  --context "Client: KD Amazon FBA, Platform: Meta"
```

Output: numbered questions with defaults for missing fields.

### Inline (for interactive sessions)

Agent detects incomplete request → asks questions before proceeding. No script needed — this is a prompting pattern, not a tool dependency.

---

## Integration with Prompt Contracts

Reverse prompting and prompt contracts work together:

1. User says "write me an email for the new leads"
2. Agent loads `lead_gen_email.yaml` contract
3. Contract says `required: [company_name, contact_name, pain_points]`
4. Agent checks: company_name? ✗ missing. contact_name? ✗ missing. pain_points? ✗ missing.
5. Agent asks:
   > Before I write this email, a few quick questions:
   > 1. Which company/lead are we targeting?
   > 2. Contact name?
   > 3. What are their main pain points? (or should I pull from ICP filter?)
6. User answers
7. Agent writes email with all fields filled

---

## Meta-Prompt (Add to CLAUDE.md)

```markdown
## Reverse Prompting Protocol
For complex tasks (client deliverables, campaigns, new features):
Before executing, ask 3-5 clarifying questions to fill gaps in required fields.
Only skip if the user explicitly says "just do it" or provides comprehensive context.
If a prompt contract exists for the task, check required fields against what was provided.
```

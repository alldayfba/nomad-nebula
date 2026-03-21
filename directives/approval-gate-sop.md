# Approval Gate SOP

> Version 1.0 | Based on Kabrin Johal's "agent proposes → human approves → agent executes" pattern

## Purpose

Prevent agents from taking high-risk actions without human approval. Agents propose actions, Sabbo reviews and approves/rejects, then agents execute only what's approved. This enables safe scaling — you can run agents 24/7 without worrying about runaway actions.

## Risk Classification

### AUTO-APPROVE (No gate needed)
- Reading files, searching, research
- Generating drafts (saved to `.tmp/`)
- Running analysis scripts
- Updating memory/brain files
- Internal agent communication

### REVIEW-BEFORE-SEND (Gate required)
- Sending outreach emails/DMs to real prospects
- Posting content to social media
- Submitting contact forms
- Making API calls that cost money (Keepa tokens, paid APIs)
- Publishing anything externally visible

### REQUIRES-EXPLICIT-APPROVAL (Hard gate)
- Spending money (ad spend, purchases, subscriptions)
- Accessing payment processors (Stripe, WAP)
- Modifying production databases
- Pushing code to production
- Sending to more than 10 recipients at once
- Any action involving PII or client data externally

## Approval Flow

```
Agent generates proposal
    ↓
Writes to .tmp/approvals/pending/AP-{date}-{seq}.yaml
    ↓
Sabbo reviews (via /approve skill or dashboard)
    ↓
Approved → moves to .tmp/approvals/approved/ → agent executes
Rejected → moves to .tmp/approvals/rejected/ → agent logs reason
```

## Proposal Format

```yaml
id: AP-2026-03-16-001
agent: outreach
action: send_dream100_batch
risk_level: review_before_send
timestamp: 2026-03-16T10:30:00
description: "Send 25 Dream 100 packages to dental clinics in Miami"
details:
  recipients: 25
  channel: email
  template: dream100_dental
  personalization: brand_voice_matched
estimated_cost: "$0.50 (API tokens)"
requires_approval: true
status: pending
```

## How Agents Use This

Before any REVIEW-BEFORE-SEND or REQUIRES-EXPLICIT-APPROVAL action:

1. Generate the proposal YAML
2. Save to `.tmp/approvals/pending/`
3. Notify user: "Proposal AP-{id} ready for review: {description}"
4. Wait for approval (don't execute)
5. On approval: execute and log result
6. On rejection: log reason, suggest alternative

## Batch Approvals

For high-volume tasks (50+ Dream 100/day):
- Agent generates batch proposal with full list
- Sabbo can approve entire batch or cherry-pick
- Approved items execute in parallel
- Results logged per-item

## Integration Points

- **Outreach agent**: All sends require review_before_send
- **Content agent**: All posts require review_before_send
- **Sourcing agent**: Keepa deep-verify (21 tokens/ea) requires review if batch > 50
- **MediaBuyer agent**: All ad spend changes require explicit_approval
- **CEO agent**: Can auto-approve read-only actions, must gate external actions

## Known Issues

<!-- Append issues discovered during use below this line -->

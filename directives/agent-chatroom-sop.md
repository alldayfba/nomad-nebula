# Agent Chat Rooms SOP
> directives/agent-chatroom-sop.md | Version 1.0

---

## Purpose

Centralized debate spaces where multiple AI agents argue different perspectives on a topic. Pushes toward higher quality answers than any single agent alone through dialectic.

---

## When to Use

- Offer positioning decisions ("what angle should we lead with?")
- Content strategy debates ("which content pillar should we double down on?")
- Architecture trade-offs ("monolith vs microservice for this feature?")
- Ad copy ideation ("generate 3 contrasting hook angles")
- Pricing strategy ("$5K or $10K entry point for coaching?")
- Any decision where you want multiple perspectives before committing

---

## Available Personas

| Key | Name | Role |
|---|---|---|
| `devils_advocate` | Devil's Advocate | Challenge every assumption, find flaws |
| `optimizer` | The Optimizer | Find the most efficient path, cut waste |
| `user_advocate` | User Advocate | Represent end user, focus on UX |
| `security_analyst` | Security Analyst | Flag risks, vulnerabilities, compliance |
| `business_strategist` | Business Strategist | Revenue, ROI, market fit |
| `creative_director` | Creative Director | Bold, differentiated, memorable |
| `moderator` | Moderator | Auto-used for final synthesis |

Custom personas can be added to `execution/chatroom_personas.json`.

---

## Recommended Combos

| Decision Type | Personas | Why |
|---|---|---|
| Ad hook ideation | creative_director + business_strategist + devils_advocate | Creative tension + business grounding |
| Architecture decision | optimizer + security_analyst + devils_advocate | Efficiency vs safety vs risk |
| Pricing decision | business_strategist + user_advocate + optimizer | Revenue vs value perception vs simplicity |
| Content strategy | creative_director + user_advocate + business_strategist | Engagement vs relevance vs ROI |

---

## Execution

```bash
# 3-agent, 3-round debate
python execution/agent_chatroom.py \
    --topic "Should we lead with pain or aspiration in our Amazon FBA coaching ads?" \
    --personas creative_director,business_strategist,devils_advocate \
    --rounds 3 \
    --save .tmp/chatrooms/fba_ad_debate.json

# Quick 2-round with Gemini
python execution/agent_chatroom.py \
    --topic "Dark mode or light mode for the growth dashboard?" \
    --personas user_advocate,optimizer \
    --rounds 2 \
    --model gemini

# List all personas
python execution/agent_chatroom.py --list-personas
```

---

## Output

Each chatroom produces:
1. **Transcript** — Full round-by-round debate
2. **Synthesis** — Moderator's final recommendation with:
   - Key points from each agent
   - Areas of consensus
   - Areas of dissent
   - Clear final recommendation

Results saved to `.tmp/chatrooms/` for reference.

---

## Cost Estimate

| Setup | Turns | Est. Tokens | Est. Cost |
|---|---|---|---|
| 3 agents × 2 rounds + synthesis | 7 | ~10K | ~$0.09 |
| 3 agents × 3 rounds + synthesis | 10 | ~15K | ~$0.14 |
| 5 agents × 3 rounds + synthesis | 16 | ~24K | ~$0.22 |

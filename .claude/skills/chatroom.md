---
name: chatroom
description: Run a multi-agent debate room where different personas argue perspectives on a topic
trigger: when user says "debate this", "chatroom", "agent debate", "get different perspectives", "argue this out"
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# Agent Chat Room

## Directive
Read `directives/agent-chatroom-sop.md` for the full SOP before proceeding.

## Goal
Create a multi-agent debate space where agents with different personas argue a topic, then a moderator synthesizes the final recommendation.

## Inputs
| Input | Required | Default |
|---|---|---|
| topic | Yes | — (the question or decision to debate) |
| personas | No | `business_strategist,devils_advocate,creative_director` |
| rounds | No | 3 |
| model | No | `claude` |

Extract the topic from the user's message. Choose personas based on the topic:
- **Ad/copy decisions** → `creative_director,business_strategist,devils_advocate`
- **Architecture/tech** → `optimizer,security_analyst,devils_advocate`
- **Pricing/offer** → `business_strategist,user_advocate,optimizer`
- **Content strategy** → `creative_director,user_advocate,business_strategist`

## Available Personas
`devils_advocate`, `optimizer`, `user_advocate`, `security_analyst`, `business_strategist`, `creative_director`

List all: `python execution/agent_chatroom.py --list-personas`

## Execution
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate
python execution/agent_chatroom.py --topic "{topic}" --personas {personas} --rounds {rounds} --model {model} --save .tmp/chatrooms/debate_$(date +%Y%m%d_%H%M%S).json
```

## Output
- Console: round-by-round debate transcript + moderator synthesis with final recommendation
- File: full results JSON saved to `.tmp/chatrooms/`

## Self-Annealing
If execution fails:
1. Check API key in `.env`
2. If a persona name is wrong → check `execution/chatroom_personas.json`
3. Fix the script, update `directives/agent-chatroom-sop.md`
4. Log fix in `SabboOS/CHANGELOG.md`

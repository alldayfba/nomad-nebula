# Multi-Chrome Agent SOP — Parallel Browser Automation

> Version 1.0 | Based on Nick Saraev's multi-chrome-agent-skill

## Purpose

Spin up 1-5 parallel Chrome browser instances, each controlled by an independent Claude Code agent. Used for tasks that require real browser interaction across multiple targets simultaneously: filling contact forms, scraping JS-rendered pages, submitting applications.

## When to Use

- Submitting contact forms across a list of websites
- Filling out applications on multiple platforms
- Scraping JS-rendered pages that need real browser interaction
- Any repetitive browser task where sequential is too slow

## Architecture

```
.tmp/multi-chrome-agent/
├── chat.md                    # Shared coordination file
├── launch_chrome.sh           # Spawns Chrome instances on ports 9223-9227
├── kill_chrome.sh             # Tears down all Chrome instances
├── chrome-agent-1/            # Workspace for Agent 1
│   ├── .mcp.json              # Chrome DevTools on port 9223
│   └── CLAUDE.md              # Agent behavior instructions
├── chrome-agent-2/            # Port 9224
├── chrome-agent-3/            # Port 9225
├── chrome-agent-4/            # Port 9226
└── chrome-agent-5/            # Port 9227
```

## Prerequisites

- Google Chrome installed
- Chrome DevTools MCP server available
- Ports 9222-9227 free

## Execution

### Step 1: Determine Agent Count

Look at the task:
- 3-5 contact forms → 2-3 agents
- 10+ forms → 4-5 agents
- Don't over-provision

### Step 2: Launch Chrome Instances

```bash
bash .tmp/multi-chrome-agent/launch_chrome.sh [COUNT]
```

Wait for "READY" confirmation on each port.

### Step 3: Write Task Assignments to chat.md

```markdown
## Orchestrator
[timestamp] Launching N agents for [task description].

### Agent 1 Tasks
1. Go to https://example1.com/contact → fill: name, email, message
2. Go to https://example2.com/contact → same

### Agent 2 Tasks
1. Go to https://example3.com/contact → fill form
2. Go to https://example4.com/contact → fill form

## Agent 1
## Agent 2
```

### Step 4: Spawn Claude Code Agents

Each agent runs in its own terminal with its own Chrome DevTools MCP:

```bash
# Programmatic launch (strips CLAUDECODE env var to allow nested sessions)
for i in 1 2 3; do
    osascript -e "tell application \"Terminal\" to do script \"cd $(pwd)/.tmp/multi-chrome-agent/chrome-agent-$i && env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT claude --dangerously-skip-permissions -p 'You are Agent $i. Read chat.md, find your tasks, execute them using Chrome DevTools MCP. Mark [WORKING] while active, [DONE] when finished.'\""
    sleep 2
done
```

### Step 5: Monitor Progress

Read chat.md periodically for status tags:
- `[WORKING]` — agent is actively processing
- `[DONE]` — agent completed all tasks
- `[ERROR]` — agent hit a blocker (CAPTCHA, timeout)
- `[WAITING]` — agent is idle

### Step 6: Tear Down

```bash
bash .tmp/multi-chrome-agent/kill_chrome.sh
```

## Chat Protocol

Agents communicate via the shared chat.md file:
- Always prepend updates with a timestamp
- Never overwrite other agents' sections — only append to your own
- Use status tags consistently

## Port Map

| Agent | Chrome Port | Workspace |
|-------|------------|-----------|
| 1 | 9223 | chrome-agent-1/ |
| 2 | 9224 | chrome-agent-2/ |
| 3 | 9225 | chrome-agent-3/ |
| 4 | 9226 | chrome-agent-4/ |
| 5 | 9227 | chrome-agent-5/ |

Port 9222 is reserved for the main (non-parallel) Chrome DevTools MCP.

## Edge Cases

- **CAPTCHA:** Agent reports `[ERROR] CAPTCHA` — orchestrator can skip or reassign
- **Rate limiting:** Spread URLs across more agents to reduce per-site hits
- **Login required:** Pre-authenticate in each Chrome instance before assigning
- **Long-running:** Agents check chat.md every 30s. Write `[ABORT]` to stop all.

## Known Issues

<!-- Append issues discovered during use below this line -->

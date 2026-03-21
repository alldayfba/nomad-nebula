# Multi-Agent MCP Orchestration SOP
> directives/multi-agent-mcp-sop.md | Version 1.0

---

## Purpose

Register Gemini and OpenAI as MCP (Model Context Protocol) servers so Claude Code can delegate tasks to the best model for the job — all from a single conversation.

---

## Architecture

```
Claude Code (orchestrator)
  ├── gemini-mcp-server (Gemini API)
  │   ├── gemini_generate — text generation
  │   └── gemini_analyze_image — multimodal image analysis
  └── openai-mcp-server (OpenAI API)
      ├── openai_generate — text generation
      └── openai_code_review — code review
```

Claude remains the orchestrator. It decides when to call Gemini or GPT based on the routing table below.

---

## Model Routing Table

| Task | Route To | Why |
|---|---|---|
| Orchestration, planning, multi-step reasoning | **Claude** (self) | Most interpretable reasoning |
| Frontend design, UI/UX | **Gemini** via `gemini_generate` | Best visual design output |
| Image/screenshot analysis | **Gemini** via `gemini_analyze_image` | Native multimodal |
| Video frame extraction | **Gemini** via `gemini_analyze_image` | Native video understanding |
| Backend code, algorithms | **GPT** via `openai_generate` | Strongest at pure code |
| Math-heavy calculations | **GPT** via `openai_generate` | Best math reasoning |
| Code review | **GPT** via `openai_code_review` | TDD-oriented review |
| Ad copy, VSL scripts | **Claude** (self) | Best persuasive writing |
| Research synthesis | **Claude** (self) | Best at long-context reasoning |
| Quick classification/tagging | **Gemini** (flash) | Fastest, cheapest |

---

## Setup

### 1. API Keys

Add to `.env`:
```
GOOGLE_API_KEY=your_gemini_key_here
OPENAI_API_KEY=your_openai_key_here
```

### 2. Install Dependencies

```bash
pip install mcp google-generativeai openai
```

### 3. Register MCP Servers

Add to `.claude/settings.json` (or project-level MCP config):

```json
{
  "mcpServers": {
    "gemini": {
      "command": "python",
      "args": ["execution/mcp_servers/gemini_mcp_server.py"],
      "cwd": "/Users/Shared/antigravity/projects/nomad-nebula"
    },
    "openai": {
      "command": "python",
      "args": ["execution/mcp_servers/openai_mcp_server.py"],
      "cwd": "/Users/Shared/antigravity/projects/nomad-nebula"
    }
  }
}
```

### 4. Test

From Claude Code:
- Call `gemini_generate` with a simple prompt
- Call `openai_generate` with a simple prompt
- Verify both return structured responses

---

## Usage Examples

### Route frontend task to Gemini
```
Use gemini_generate to design a minimal landing page for Agency OS.
System prompt: "You are a senior UI designer. Output clean HTML + Tailwind CSS."
```

### Route code review to GPT
```
Use openai_code_review to review this Python script.
Focus: security
Code: [paste code]
```

### Route image analysis to Gemini
```
Use gemini_analyze_image to analyze this screenshot.
Prompt: "What UI issues do you see? Suggest improvements."
Image path: .tmp/screenshot.png
```

---

## Cost Awareness

| Provider | Model | Input (per 1M tokens) | Output (per 1M tokens) |
|---|---|---|---|
| Google | gemini-2.0-flash | ~$0.10 | ~$0.40 |
| Google | gemini-2.0-pro | ~$1.25 | ~$5.00 |
| OpenAI | gpt-4.1-mini | ~$0.40 | ~$1.60 |
| OpenAI | gpt-4.1 | ~$2.00 | ~$8.00 |

Default to flash/mini for routine tasks. Use pro/4.1 only when quality matters.

---

## Guardrails

1. **Never send secrets** — No API keys, passwords, or .env contents to external models
2. **Truncate large inputs** — Max 50K chars per request
3. **Log usage** — All MCP calls should be tracked via `token_tracker.py`
4. **Fallback** — If an MCP server is down, Claude handles the task directly

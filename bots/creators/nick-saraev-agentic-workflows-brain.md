# Nick Saraev — Agentic Workflows 6-Hour Course (2026)

<!-- Last Updated: 2026-04-01 -->
<!-- Source: https://www.youtube.com/watch?v=MxyRjL7NG18 -->
<!-- Transcript: /Users/sabbojb/Downloads/tactiq-free-transcript-MxyRjL7NG18 (2).txt -->
<!-- Length: ~6 hours, 10,978 lines -->

## Overview

Definitive guide on agentic workflows for business. Nick built two AI-based service agencies to $160K/month combined revenue. Consulted for billion-dollar businesses. Course is business-focused — everything shown is generating revenue right now.

## Core Concept: The AI Overhang

Current AI capabilities are FAR beyond what most people believe, expect, or know how to use. The gap between reality and public perception = the "overhang." Most people use AI as glorified copy-paste tools ("drinking the Pacific Ocean through a tiny straw"). The arbitrage window is closing as people learn — but right now it's wide open.

## Key Frameworks

### 1. DOE Framework (Directive, Orchestration, Execution)

The foundational architecture. Separation of concerns:

- **Directives** (Layer 1): Clear, unambiguous instructions in markdown. SOPs for the AI. "What to do."
- **Orchestration** (Layer 2): The LLM itself. Makes routing decisions, chooses what to do in what order. "Decision making."
- **Execution** (Layer 3): Deterministic Python scripts. API calls, data transforms, file ops. Always the same output for the same input. "Doing the work."

**Why this works:** LLMs are flexible + adaptive but unpredictable. Code is rigid but 100% reliable. Combining both = best of both worlds.

**Key principle:** "Anything deterministic goes into code. Reserve LLM tokens for actual thinking."

**Sorting demo:** LLM took ~30 seconds to sort a list. Python script: 53 milliseconds. Several hundred times faster AND essentially free.

### 2. PTMRO Loop (Plan, Tool, Monitor, Reflect, Output)

How agentic workflows function:
1. **Plan** — Agent decides what to do next
2. **Tool** — Agent calls a tool (script, API, search)
3. **Monitor** — Agent checks the result
4. **Reflect** — Agent decides if the result is good enough
5. **Output** — Agent delivers the result or loops back to Plan

This loop is what separates "agents" from "chatbots." The agent keeps going until the task is complete.

### 3. Self-Annealing

When something breaks:
1. Read the error
2. Fix the script
3. Test again
4. Update the directive with what was learned
5. System is now stronger

"I just realized — why don't I make it explicit: solve the problem yourself?" That's what resulted in the self-annealing concept. Put it in CLAUDE.md.

### 4. Configuration Files

- **agents.md / CLAUDE.md** — Persistent context injected at start of every conversation. Explains the DOE framework to the orchestrator. Defines error handling. Gets better over time as you add edge cases.
- **.env** — API keys and credentials. Scripts reference env vars instead of hardcoded keys.

### 5. Claude Skills

Reusable prompt templates that can be invoked with slash commands. Skills reference directives at runtime (never duplicate content). Can be scheduled via YAML config.

### 6. MCP (Model Context Protocol)

Tools that extend what the agent can do — Gmail, Google Calendar, Slack, browser automation, etc. Each MCP gives the model access to specific capabilities.

### 7. Sub-Agents (Context Pollution Solution)

**Problem:** Context windows fill up fast. Tools, debugging, MCPs all burn tokens. More tokens in context = poorer quality outputs. The relationship is: quality peaks around 10K tokens then degrades.

**Solution:** Sub-agents get their own fresh, clean context window. They do the messy work in isolation and return only relevant findings. Like hiring a contractor who does the work offsite and brings back just the deliverable.

### 8. Hooks

Shell commands that execute in response to events (tool calls, task completion). Common use case: play a chime sound when a workflow finishes so you know to come back. Set up via Claude Code settings.

### 9. Background Tasks

For long-running workflows (e.g., 45-min video editing with FFmpeg), open an extra agent window and use background tasks. Set up hooks to notify when done. This lets you run multiple workflows simultaneously.

### 10. Workflow Chaining (Umbrellas)

Group individual workflows under an "umbrella" (e.g., "new client onboarding"). Run all of them by triggering the umbrella instead of manually handing off deliverables between workflows.

## Practical Build Demos

### Lead Scraping Workflow
- LinkedIn Sales Navigator → Vein scraper → AnyMailFinder enrichment → Google Sheets export
- First build: serial requests (slow). Optimization: parallelize requests (200 records in ~15 seconds vs minutes)
- Agent self-annealed when API call to Vein failed — automatically fixed and continued
- Key lesson: Don't test with model-generated test data (it will match its own expected format). Test with real, new data.

### Meal Prep Email Outreach
- Claude autonomously: searched for local meal prep companies → found email addresses → sent personalized emails via MCP
- Demonstrated the power of autonomous multi-step task completion

### YouTube Outlier Detection
- Searched for recent videos on "agents" topic
- Filtered for outlier performance (views vs subscriber count)
- Returned thumbnails, titles, metrics for content inspiration

### School Community Engagement
- Auto-found good questions to answer in Skool community
- Auto-formatted responses
- Engaged with posts faster than manual

## Key Quotes

- "AI is currently in an overhang state. Current capabilities are very far beyond what most people believe."
- "Most people are using AI as glorified copy and paste tools. They are drinking the Pacific Ocean with a tiny straw."
- "Anything deterministic goes into code. Reserve LLM tokens for actual thinking."
- "The first time an agent builds a workflow, it does so in as simple a way as humanly possible. Then you optimize."
- "Building is the most effective way to learn anything."
- "Nothing says you can't use AI inside your execution scripts" — e.g., process_leads_with_claude.py that reads a sheet, passes each row through Claude, updates the sheet. Still deterministic flow, just uses AI for the reasoning step.
- "Make execution scripts very atomic. Make them do one thing. Make them as deterministic as possible."
- "If I'm going to spend time working, my whole time should be spent developing intuition for how these models actually function."
- "Most people could automate 50% or more of their day-to-day work using flows like this."

## Relevance to Our System

Everything in this course validates and mirrors our existing 3-layer architecture (directives → orchestration → execution). Our system already implements:
- DOE framework (directives/, execution/, CLAUDE.md)
- Self-annealing (learned-rules-sop.md)
- Skills (.claude/skills/)
- Sub-agents (.claude/agents/)
- Hooks (settings.json)
- Background tasks
- MCP servers

**New insights to apply:**
1. **Workflow chaining/umbrellas** — We have this partially with `/auto-outreach` but could formalize more umbrella workflows
2. **Context pollution awareness** — Be more aggressive about using sub-agents for research tasks
3. **Parallel workflow execution** — Run 5 Claude Code instances simultaneously, each with hooks to chime on completion
4. **Test with real data, not model-generated test data** — Always validate with production-like inputs
5. **Intuition building** — Watch the model's reasoning, catch sideways thinking early, press X and redirect

## Updates Log

- **2026-04-01**: Initial brain file created from 6-hour course transcript

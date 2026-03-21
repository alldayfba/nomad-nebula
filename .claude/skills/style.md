---
name: style
description: Switch response style mode — Concise, Explanatory, Learning, or Formal
trigger: when user says "/style", "be concise", "explain this", "short version", "make it formal", "teach me", "tldr", "client version"
tools: [Read]
---

# Style — Response Mode Switcher

## Directive
Read `directives/response-style-sop.md` for the full spec before proceeding.

## Goal
Set the active response style mode for the remainder of the conversation.

## Inputs
| Input | Required | Default |
|---|---|---|
| mode | Yes | — |

## Modes
| Command | Mode | Use for |
|---|---|---|
| `/style concise` | Concise | Sabbo's default — minimum tokens, lead with answer |
| `/style explain` | Explanatory | Learning something new, building mental models |
| `/style learn` | Learning | Guided discovery, skill-building through doing |
| `/style formal` | Formal | Client-facing output, send-ready copy |

## Execution
No script needed. Set the mode and confirm in one line:

> "Concise mode on. Leading with answers, no filler."

Then immediately apply the mode to all subsequent responses in this session.

## Output
One-line confirmation. Mode stays active until explicitly changed.

## Notes
- Mode affects format/tone only — never reduces code quality or accuracy
- Default for Claude Code sessions is Concise
- `/style reset` returns to Concise

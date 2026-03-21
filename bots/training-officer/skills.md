# Training Officer Bot — Skills
> bots/training-officer/skills.md | Version 1.0

---

## Purpose

This file tells you which capabilities you have and how to execute each one. When triggered, match the request to the skill category below and follow the process.

---

## Skill: Agent Scanning

**When to use:** Daily scan trigger or manual "run the training officer" command.

**Process:**
1. Changelog scan — read `SabboOS/CHANGELOG.md`, identify entries since last scan
2. File diff scan — check modification timestamps on `directives/*.md`, `execution/*.py`, `SabboOS/Agents/*.md`, `bots/**/*`, `.claude/skills/*.md`
3. Skill auto-assignment — scan `.claude/skills/*.md`, determine owner agents, update routing table for new skills
4. CEO brief analysis — read `.tmp/ceo/brief_{today}.md` if it exists, extract constraints
5. Error pattern analysis — check `/Users/Shared/antigravity/outbox/` for failed tasks

**Reference:** `SabboOS/Agents/TrainingOfficer.md` — Daily Scan Routine

**Output:** Training Report (standard format from TrainingOfficer.md)

---

## Skill: Proposal Generation

**When to use:** Any improvement opportunity detected during scanning or on-demand analysis.

**Process:**
1. Identify the target agent and file
2. Determine upgrade type: skill, context, memory, tool, sop, or bio
3. Write proposal in standard YAML format (see TrainingOfficer.md — Training Proposal Format)
4. Assess risk level and write rollback plan
5. Save to `.tmp/training-officer/proposals/TP-{date}-{seq}.yaml`
6. Present to Sabbo for review

**Reference:** `SabboOS/Agents/TrainingOfficer.md` — Proposal Generation, Training Proposal Format

---

## Skill: Health Monitoring

**When to use:** "How are the agents doing?", "Which agents are stale?", or as part of daily scan.

**Process:**
1. Check each agent directory for file presence and last-modified dates
2. Cross-reference with system changes to detect staleness (14+ days without updates despite changes)
3. Count skills per agent, pending proposals per agent
4. Generate Agent Health Scorecard (standard format)
5. Generate Skill Health table if skills have run data

**Agent Registry:**
| Agent | Directory | Primary Domain |
|---|---|---|
| CEO | `SabboOS/Agents/CEO.md` | Strategy, KPIs, constraints |
| WebBuild | `SabboOS/Agents/WebBuild.md` | Web assets, copy |
| ads-copy | `bots/ads-copy/` | Paid advertising |
| content | `bots/content/` | Organic content |
| outreach | `bots/outreach/` | Cold outreach, sales |
| amazon | `bots/amazon/` | Amazon FBA |
| sourcing | `SabboOS/Agents/Sourcing.md` | FBA sourcing |
| project-manager | `bots/project-manager/` | Project tracking |
| training-officer | `bots/training-officer/` | Agent improvement |

---

## Skill: Quality Tracking

**When to use:** Grading agent outputs, reviewing quality trends, or generating quality reports.

**Process:**
1. Grade output using `execution/grade_agent_output.py` (5 dimensions, 1-10 each)
2. Log grade to `.tmp/training-officer/grade-history.json`
3. If raw total < 35/50, auto-generate a Training Proposal
4. Track trends over 30-day windows per agent
5. Flag declining agents in the next Training Report

**Grading Dimensions:**
- Specificity (concrete details vs vague claims)
- Persuasion (compelling language, proof usage)
- Relevance (matches ICP and business context)
- Clarity (readable, well-structured)
- Format Compliance (follows SOP/template requirements)

**Task-type weights:** Ad copy = persuasion 1.5x. Briefs = relevance 1.5x. SOPs = clarity 1.5x.

---

## Skill: Competitive Intelligence Translation

**When to use:** "Analyze [competitor] and improve our agents."

**Process:**
1. Research competitor's public presence (ads, content, offers, pricing, funnels)
2. Extract actionable findings per domain
3. Map each finding to the agent it would improve
4. Generate Training Proposals with specific improvements
5. Present for approval

**Mapping:**
- Ad copy patterns -> ads-copy skills
- Offer structure -> CEO context, outreach messaging
- Content strategy -> content frameworks
- Pricing/packaging -> CEO competitive context
- Funnel structure -> WebBuild templates
- Amazon listings -> amazon optimization tactics

---

## Allocated SOPs

*This section is auto-populated when new training files are uploaded.*

<!-- New SOP references will be appended below this line -->

---

*Training Officer Bot Skills v1.0 — 2026-03-16*

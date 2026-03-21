# Agent Routing Table
> directives/agent-routing-table.md | Version 1.0
> Maps every directive and script to its owner agent.
> Used by Training Officer for skill ownership enforcement.

---

## Directive → Agent Mapping

| Directive | Primary Agent | Secondary Agents | Purpose |
|---|---|---|---|
| `ceo-agent-sop.md` | CEO | all (awareness) | Master routing + constraint waterfall |
| `openclaw-handoff-sop.md` | CEO | — | OpenClaw ↔ Claude Code task handoff |
| `lead-gen-sop.md` | lead-gen | CEO (delegation) | Google Maps scrape → CSV |
| `agent-training-sop.md` | CEO | — | Bot onboarding protocol |
| `api-cost-management-sop.md` | CEO | all (awareness) | LLM model routing + budget rules |
| `security-guardrails-sop.md` | CEO | all (awareness) | Access + incident rules |
| `dream100-sop.md` | outreach | — | Dream 100 hyper-personalized outreach |
| `email-generation-sop.md` | outreach | — | Cold email sequence generation |
| `asset-generation-sop.md` | ads-copy | content (secondary) | Ad scripts + VSL generation |
| `jeremy-haynes-vsl-sop.md` | content | WebBuild (LP), ads-copy (hooks) | VSL framework |
| `business-audit-sop.md` | CEO | outreach (delivery) | 4-asset audit generation |
| `knowledge-ingestion-sop.md` | CEO | — | Material ingestion pipeline |
| `morning-briefing-sop.md` | CEO | — | Daily CEO brief generation |
| `sop-allocation-sop.md` | CEO | — | SOP routing to agents |
| `ads-competitor-research-sop.md` | ads-copy | outreach (positioning) | Meta Ad Library scraping |
| `client-brand-voice-sop.md` | content | WebBuild (web copy) | Client brand voice extraction |
| `icp-filter-sop.md` | lead-gen | — | ICP scoring and filtering |
| `amazon-sourcing-sop.md` | sourcing | amazon (inventory) | FBA sourcing pipeline |
| `training-officer-sop.md` | CEO | — | Training Officer scan protocol |
| `agent-routing-table.md` | CEO | — | THIS FILE — routing reference |
| `sales-manager-sop.md` | Sales Manager | CEO (delegation) | Sales org daily/weekly/monthly rhythm |
| `pipeline-analytics-sop.md` | Sales Manager | CEO (awareness) | Pipeline funnel tracking + bottleneck detection |
| `client-health-sop.md` | Sales Manager | CEO (awareness) | Client health scoring + retention |
| `outreach-sequencer-sop.md` | Sales Manager | outreach (execution) | Follow-up sequences for non-closes |
| `video-editing-sop.md` | VideoEditor | MediaBuyer (ad creatives), content (briefs) | Programmatic video editing engine |
| `youtube-foundations-sop.md` | content | VideoEditor (thumbnails/editing) | YouTube strategy, scripting, Outlier Theory |

---

## Script → Agent Mapping

| Script | Owner Agent | Purpose |
|---|---|---|
| `run_scraper.py` | lead-gen | Google Maps scraping |
| `filter_icp.py` | lead-gen | ICP scoring/filtering |
| `generate_emails.py` | outreach | Cold email generation |
| `generate_ad_scripts.py` | ads-copy | Ad script generation |
| `generate_vsl.py` | content | VSL script generation |
| `research_prospect.py` | outreach | Prospect research |
| `generate_dream100_assets.py` | outreach | Dream 100 asset generation |
| `assemble_gammadoc.py` | outreach | GammaDoc assembly |
| `run_dream100.py` | outreach | Dream 100 pipeline orchestrator |
| `generate_business_audit.py` | CEO | Business audit generation |
| `scrape_competitor_ads.py` | ads-copy | Meta Ad Library scraping |
| `scrape_client_profile.py` | content | Client profile extraction |
| `send_morning_briefing.py` | CEO | Morning brief dispatch |
| `ingest_docs.py` | CEO | Document ingestion |
| `allocate_sops.py` | CEO | SOP allocation to agents |
| `watch_inbox.py` | CEO | OpenClaw inbox daemon |
| `push_to_github.py` | WebBuild | GitHub Pages deployment |
| `upload_to_gdrive.py` | CEO | Google Drive upload |
| `run_sourcing_pipeline.py` | sourcing | FBA sourcing orchestrator |
| `scrape_retail_products.py` | sourcing | Retail product scraping |
| `match_amazon_products.py` | sourcing | Amazon ASIN matching |
| `calculate_fba_profitability.py` | sourcing | FBA profitability calculator |
| `price_tracker.py` | sourcing | Price history + alerts |
| `scheduled_sourcing.py` | sourcing | Recurring sourcing runs |
| `sourcing_alerts.py` | sourcing | Telegram/email alerts |
| `reverse_sourcing.py` | sourcing | ASIN → retail source finder |
| `batch_asin_checker.py` | sourcing | Bulk ASIN lookup |
| `storefront_stalker.py` | sourcing | Seller storefront scraper |
| `inventory_tracker.py` | amazon | P&L + inventory status |
| `scrape_cardbear.py` | sourcing | Gift card discount scraper |
| `export_to_sheets.py` | sourcing | Google Sheets export |
| `retailer_configs.py` | sourcing | Per-retailer CSS selectors |
| `training_officer_scan.py` | CEO | Training Officer scan engine |
| `apply_proposal.py` | CEO | Proposal approve/reject CLI |
| `agent_quality_tracker.py` | CEO | Quality scoring + drift |
| `agent_benchmark.py` | CEO | Automated agent testing |
| `self_healing_engine.py` | CEO | Error capture + auto-fix |
| `proposal_rollback.py` | CEO | Backup + rollback engine |
| `sop_coverage_analyzer.py` | CEO | SOP coverage analysis |
| `competitive_intel_cron.py` | CEO | Weekly competitor scrape |
| `training_officer_watch.sh` | CEO | fswatch file watcher |
| `training_officer_webhook.py` | CEO | Modal scheduled webhook |
| `update_ceo_brain.py` | CEO | Brain.md session update |
| `brain_maintenance.py` | CEO | Brain archiving + pruning |
| `save_session.py` | CEO | Session history capture |
| `project_manager.py` | project-manager | Project tracking, milestones, health, congruence |
| `dashboard_client.py` | Sales Manager | 247growth dashboard API bridge (PRIMARY data source) |
| `pipeline_analytics.py` | Sales Manager | Pipeline funnel tracking + bottleneck detection |
| `client_health_monitor.py` | Sales Manager | Client health scoring + at-risk detection |
| `outreach_sequencer.py` | Sales Manager | Follow-up sequences for non-closes |
| `video_editor.py` | VideoEditor | Programmatic video editing engine |
| `video_caption_renderer.py` | VideoEditor | Pillow text frame generation |
| `video_overlay_templates.py` | VideoEditor | Motion graphic templates |
| `video_manifest_builder.py` | VideoEditor | Instruction → manifest conversion |
| `video_thumbnail_generator.py` | VideoEditor | YouTube thumbnail generation |
| `remotion_renderer.py` | VideoEditor | Python → Remotion CLI bridge |
| `sfx_library.py` | VideoEditor | SFX auto-sync mapper |

---

## Skill → Agent Mapping

Skills in `.claude/skills/` are slash-command invocable workflows. Each skill is owned by exactly one agent.

| Skill | Owner Agent | Directive | Script |
|---|---|---|---|
| `/lead-gen` | lead-gen | `lead-gen-sop.md` | `run_scraper.py` |
| `/cold-email` | outreach | `email-generation-sop.md` | `generate_emails.py` |
| `/business-audit` | CEO | `business-audit-sop.md` | `generate_business_audit.py` |
| `/dream100` | outreach | `dream100-sop.md` | `run_dream100.py` |
| `/source-products` | sourcing | `amazon-sourcing-sop.md` | `source.py` |
| `/morning-brief` | CEO | `morning-briefing-sop.md` | `send_morning_briefing.py` |
| `/client-health` | Sales Manager | `client-health-sop.md` | `client_health_monitor.py` |
| `/pipeline-analytics` | Sales Manager | `pipeline-analytics-sop.md` | `pipeline_analytics.py` |
| `/outreach-sequence` | outreach | `outreach-sequencer-sop.md` | `outreach_sequencer.py` |
| `/content-engine` | content | `content-engine-sop.md` | `content_engine.py` |
| `/student-onboard` | CEO | `student-onboarding-sop.md` | `upload_onboarding_gdoc.py` |
| `/competitor-intel` | ads-copy | `ads-competitor-research-sop.md` | `scrape_competitor_ads.py` |
| `/doe` | CEO | — (meta-skill) | — |
| `/build-site` | WebBuild | `WebBuild.md` | `push_to_github.py` |
| `/vsl` | content | `jeremy-haynes-vsl-sop.md` | `generate_vsl.py` |
| `/deal-drop` | sourcing | — | `format_deal_drop.py` |
| `/project-status` | project-manager | `project-manager-sop.md` | `project_manager.py` |
| `/sales-prep` | Sales Manager | — | `research_prospect.py` |
| `/follow-up` | Sales Manager | `outreach-sequencer-sop.md` | `outreach_sequencer.py` |
| `/auto-research` | CEO | `auto-research-sop.md` | `auto-research/*/orchestrator.py` |
| `/auto-outreach` | CEO | — (orchestration) | chains: `run_scraper.py` → `filter_icp.py` → `generate_emails.py` |
| `/frontend-design` | WebBuild | `frontend-design-sop.md` | — (agent-driven, uses shadcn MCP + magic dry MCP) |
| `/video-edit` | VideoEditor | `video-editing-sop.md` | `video_editor.py` |

---

## Skill Auto-Assignment Protocol

When a new skill is created in `.claude/skills/`:

1. **Training Officer** detects the new file via change detection
2. Match skill's directive to existing Directive → Agent Mapping above
3. Assign ownership to the corresponding agent
4. Add a `/skill-name` reference to the agent's `bots/<agent>/skills.md`
5. Add the skill to the Skill → Agent Mapping table above
6. Generate a Training Proposal (TP) for Sabbo's approval
7. Log the assignment in `SabboOS/CHANGELOG.md`

If no matching directive exists → route to CEO as fallback owner.

---

## Routing Rules

1. **Primary agent** gets full skill training proposals
2. **Secondary agents** get awareness-only context (1-line mention + delegation pointer)
3. **"all (awareness)"** means every agent should know this exists but NOT get full training
4. **CEO is the fallback** — any unmatched file routes to CEO for triage
5. **Training Officer enforces ownership** via `SKILL_OWNERSHIP` map in `training_officer_scan.py`
6. **Skills follow directives** — a skill's owner is always the same as its directive's primary agent

---

*Agent Routing Table v4.0 — 2026-03-17*

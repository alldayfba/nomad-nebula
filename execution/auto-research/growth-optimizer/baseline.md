# Growth Optimizer — Current Baseline Configuration

## System Capabilities
- B2B Lead Gen: scraper.py → filter_icp.py → generate_emails.py
- FBA Sourcing: source.py (8 modes) → keepa verification → profitability calc
- Business Audit: 4-asset package (SSE)
- Pipeline Analytics: pipeline_analytics.py + client_health_monitor.py

## Key Scripts Health
- 11 core scripts tracked
- All should be importable without syntax errors
- Sourcing DB should have data < 7 days old

## Pipeline Stages Tracked
- lead_generated → lead_contacted → call_booked → deal_closed
- product_sourced → product_profitable
- audit_sent → audit_responded
- script_success / script_error

## Environment Requirements
- ANTHROPIC_API_KEY (Claude API)
- KEEPA_API_KEY (Amazon data)
- GHL_API_KEY (CRM/pipeline)

## Current Metrics (auto-updated)
- Baseline score: 66.00
- Last updated: 2026-03-16

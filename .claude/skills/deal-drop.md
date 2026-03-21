---
name: deal-drop
description: Format FBA sourcing results as Inner Circle CSV and Discord deal drop messages
trigger: when user says "deal drop", "format deals", "drop deals", "send deals to discord", "IC drop"
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# Deal Drop Formatter


## Directive
Read `directives/amazon-sourcing-sop.md` for the full SOP before proceeding.


## Goal
Take sourcing results JSON from `/source-products` and format as Inner Circle approved product CSV + Discord @everyone messages ready to paste into the student channel.

## Inputs
| Input | Required | Default |
|---|---|---|
| results JSON | Yes | latest file in `.tmp/sourcing/` |
| format | No | csv (options: csv, discord, both) |
| min-verdict | No | BUY (options: BUY, MAYBE) |
| output path | No | `.tmp/sourcing/deal_drop_{ts}.csv` |

If user doesn't specify a results file, find the most recent `results*.json` in `.tmp/sourcing/`.

## Execution
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate

# CSV format (Inner Circle sheet)
python execution/format_deal_drop.py --input {results_json}

# Discord format (@everyone messages)
python execution/format_deal_drop.py --input {results_json} --discord

# BUY verdict only
python execution/format_deal_drop.py --input {results_json} --min-verdict BUY

# Custom output
python execution/format_deal_drop.py --input {results_json} --output {path}
```

## IC CSV Columns
Image | Product Name | ASIN | Source URL | Cost Price | Sale Price | Profit | ROI | Coupons | VA Comments

## Discord Message Format
Each product gets an @everyone block with:
- Financials (Buy, Sell, Profit, Margin, ROI)
- Market Intel (BSR, FBA sellers, estimated monthly sales)
- Discount Stack (coupons + cashback)
- Notes (quality signals)
- Links (retail + Amazon)

## Typical Chain
1. `/source-products` → finds profitable products
2. `/deal-drop` → formats for students
3. Paste Discord messages into Inner Circle channel

## Self-Annealing
If execution fails:
1. Check if input JSON exists and has valid product data
2. Check for required fields: asin, product_name, profitability dict
3. If no products pass min-verdict filter, lower threshold to MAYBE
4. Fix the script, update directive Known Issues
5. Log fix in `SabboOS/CHANGELOG.md`

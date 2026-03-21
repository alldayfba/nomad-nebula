# ICP Filter SOP

## Purpose
Score and filter a raw leads CSV against the Ideal Customer Profile (ICP) using Claude.
Reduces a broad scrape down to the highest-probability prospects before running asset generation.

## When to Use
After running `execution/run_scraper.py`. Before running any email/ad/VSL generation.
Do not run asset generation on unfiltered leads — it's expensive and dilutes quality.

## ICP Definition (Agency)
- **Type:** Founder-led service businesses, e-commerce brands, coaching/consulting firms, professional services
- **Revenue signals:** Has a website, real phone number, physical address, 4+ Google rating
- **Size:** Small-to-mid market — not a solo freelancer, not a Fortune 500
- **Pain:** Revenue plateau — growing but stuck, underinvesting in marketing or lacking a growth system
- **Good signals:** Real email, professional category, established presence
- **Bad signals:** Government entity, nonprofit, residential address, "Store" as category, no website, no phone

To update the ICP, edit the `ICP_DEFINITION` constant in `execution/filter_icp.py`.

## Inputs
- `--input` — CSV from `run_scraper.py` (9 columns: business_name, owner_name, category, phone, email, website, address, rating, maps_url)
- `--threshold` — Minimum ICP score to include (1-10, default: 6). Lower = more permissive.
- `--output` — Optional. Defaults to `.tmp/filtered_leads_<timestamp>.csv`

## Outputs
- Filtered CSV in `.tmp/` with three new columns appended:
  - `icp_score` — 1-10 integer score from Claude
  - `icp_include` — true/false
  - `icp_reason` — one-sentence explanation

## How to Run
```bash
source .venv/bin/activate

# Basic usage (threshold 6/10)
python execution/filter_icp.py --input .tmp/leads_20250120_143000.csv

# Stricter filter (only 8+)
python execution/filter_icp.py --input .tmp/leads_20250120_143000.csv --threshold 8

# Custom output path
python execution/filter_icp.py --input leads.csv --output .tmp/filtered.csv
```

## Prerequisites
- `.env` file with `ANTHROPIC_API_KEY` set
- `anthropic` and `python-dotenv` installed (`pip install -r requirements.txt`)

## Cost Estimate
- ~200 tokens per lead (input + output)
- At 1,000 leads: ~200K tokens ≈ $0.60 with claude-opus-4-6
- At 10,000 leads: ~$6.00

## Known Issues / Edge Cases
- Leads with no website and no category are usually low-score — expected behavior
- Some Google Maps categories are very generic ("Store", "Service") — these will score low unless other signals are strong
- If Claude returns malformed JSON, the lead is marked as score 0 / excluded — check logs for errors
- Rate limits: Claude API allows ~1,000 RPM on standard tier. For 10K+ leads, add a `time.sleep(0.1)` between calls

## Next Step After Filtering
Run `execution/generate_emails.py` on the filtered output.

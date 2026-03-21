#!/usr/bin/env python3
"""
Script: run_scraper.py
Purpose: CLI wrapper to run the Google Maps B2B lead scraper and save results to CSV
Inputs:  --query, --location, --max (int), --no-emails (flag), --output (csv path)
Outputs: CSV file at --output path (default: leads_output.csv)
"""

import argparse
import csv
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper import run_scraper


def main():
    parser = argparse.ArgumentParser(description="Scrape Google Maps for B2B leads")
    parser.add_argument("--query", required=True, help="Search query (e.g. 'roofing companies')")
    parser.add_argument("--location", required=True, help="Location (e.g. 'Austin TX')")
    parser.add_argument("--max", type=int, default=20, dest="max_results", help="Max results to scrape (default: 20)")
    parser.add_argument("--no-emails", action="store_false", dest="fetch_emails", help="Skip email extraction (faster)")
    parser.add_argument("--output", default="leads_output.csv", help="Output CSV path (default: leads_output.csv)")
    args = parser.parse_args()

    print(f"[run_scraper] Starting: query='{args.query}' location='{args.location}' max={args.max_results} fetch_emails={args.fetch_emails}")

    try:
        results = run_scraper(args.query, args.location, args.max_results, args.fetch_emails)
    except Exception as e:
        print(f"[run_scraper] ERROR: Scraper failed — {e}", file=sys.stderr)
        sys.exit(1)

    if not results:
        print("[run_scraper] WARNING: No results returned. Check query/location or Google Maps availability.")
        sys.exit(0)

    fieldnames = ["business_name", "owner_name", "category", "phone", "email", "website", "address", "rating", "maps_url"]

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow({k: row.get(k, "N/A") for k in fieldnames})

    print(f"[run_scraper] Done. {len(results)} leads saved to {args.output}")


if __name__ == "__main__":
    main()

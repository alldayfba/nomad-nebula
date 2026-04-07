#!/usr/bin/env python3
"""
Google Sheets → Discord Poller — replaces Zapier ZAP-005 (IC Product Lead Sender).

Polls a Google Sheet for new rows and sends them to Discord.
Tracks last-seen row in .tmp/sheet_poll_state.json to avoid duplicates.

Usage:
    python execution/sheet_poll_discord.py --sheet-id 1sB4NwWjaOVjDrY7aC041vv31_bF_m7F4f1Ynq7xSkmM
    python execution/sheet_poll_discord.py --sheet-id <ID> --worksheet "APPROVED PRODUCTS"
    python execution/sheet_poll_discord.py --sheet-id <ID> --dry-run

Cron: every 5 minutes via launchd or scheduled-skills.yaml
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("sheet-poll")

STATE_FILE = PROJECT_ROOT / ".tmp" / "sheet_poll_state.json"

# Default: IC Product-Pre Approval Sheet
DEFAULT_SHEET_ID = "1sB4NwWjaOVjDrY7aC041vv31_bF_m7F4f1Ynq7xSkmM"
DEFAULT_WORKSHEET = "APPROVED PRODUCTS Zap -INNE CIRCLE Product Drops"

# Column mapping (from Zapier ZAP-005 field refs)
# COL$B=Product, COL$D=ASIN, COL$E=Amazon Link, COL$F=Buy Link,
# COL$G=Buy Price, COL$H=Sell Price, COL$I=Profit, COL$J=ROI,
# COL$K=Margin, COL$L=Notes, COL$M=Coupons
COL_PRODUCT = 1   # B
COL_ASIN = 3      # D
COL_AMAZON = 4    # E
COL_BUY_LINK = 5  # F
COL_BUY_PRICE = 6 # G
COL_SELL_PRICE = 7 # H
COL_PROFIT = 8    # I
COL_ROI = 9       # J
COL_MARGIN = 10   # K
COL_NOTES = 11    # L
COL_COUPONS = 12  # M


def get_sheets_service():
    """Build Google Sheets API service using service account."""
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    creds_path = PROJECT_ROOT / "service_account.json"
    if not creds_path.exists():
        creds_path = PROJECT_ROOT / "credentials.json"

    creds = Credentials.from_service_account_file(
        str(creds_path),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    return build("sheets", "v4", credentials=creds)


def load_state() -> dict:
    """Load polling state (last seen row index per sheet)."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict) -> None:
    """Persist polling state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def fetch_rows(sheet_id: str, worksheet: str) -> list:
    """Fetch all rows from the specified worksheet."""
    service = get_sheets_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"'{worksheet}'",
    ).execute()
    return result.get("values", [])


def format_product_embed(row: list) -> dict:
    """Format a sheet row into a Discord embed matching the Zapier format."""
    def col(idx: int) -> str:
        return row[idx] if idx < len(row) else ""

    product = col(COL_PRODUCT)
    asin = col(COL_ASIN)
    amazon_link = col(COL_AMAZON)
    buy_link = col(COL_BUY_LINK)
    buy_price = col(COL_BUY_PRICE)
    sell_price = col(COL_SELL_PRICE)
    profit = col(COL_PROFIT)
    roi = col(COL_ROI)
    margin = col(COL_MARGIN)
    notes = col(COL_NOTES)
    coupons = col(COL_COUPONS)

    return {
        "title": f"\U0001f6d2 New Product Lead: {product[:50]}",
        "description": "\n".join([
            f"\U0001f3f7 **Product:** {product}",
            f"\U0001f6d2 **Buy Price:** {buy_price}",
            f"\U0001f4b0 **Sell Price:** {sell_price}",
            f"\U0001f4c8 **Profit:** {profit}",
            f"\U0001f9ee **Profit Margin:** {margin}",
            f"\U0001f4ca **ROI:** {roi}",
            f"\U0001f4e6 **ASIN:** {asin}",
            f"\U0001f39f **Coupons:** {coupons}" if coupons else "",
            f"\U0001f4dd **NOTES:** {notes}" if notes else "",
            "",
            "\U0001f517 **Links:**",
            f"**Buy Here:** {buy_link}" if buy_link else "",
            f"**Sell Here:** {amazon_link}" if amazon_link else "",
        ]),
        "color": 0x00FF88,
        "footer": {"text": "Google Sheets \u2192 Direct (no Zapier)"},
    }


def main():
    parser = argparse.ArgumentParser(description="Poll Google Sheet → Discord")
    parser.add_argument("--sheet-id", default=DEFAULT_SHEET_ID)
    parser.add_argument("--worksheet", default=DEFAULT_WORKSHEET)
    parser.add_argument("--channel", default="ic-product-leads")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from execution.ghl_automations import discord_send

    state = load_state()
    state_key = f"{args.sheet_id}:{args.worksheet}"
    last_row = state.get(state_key, 0)

    logger.info(f"Polling sheet {args.sheet_id} worksheet '{args.worksheet}' from row {last_row + 1}")

    rows = fetch_rows(args.sheet_id, args.worksheet)

    if not rows:
        logger.info("No rows found")
        return

    # Skip header row (index 0) and already-processed rows
    new_rows = rows[max(1, last_row + 1):]

    if not new_rows:
        logger.info(f"No new rows (total: {len(rows)}, last processed: {last_row})")
        return

    logger.info(f"Found {len(new_rows)} new row(s)")

    for i, row in enumerate(new_rows):
        row_idx = max(1, last_row + 1) + i
        # Skip empty rows
        if not any(cell.strip() for cell in row if isinstance(cell, str)):
            continue

        embed = format_product_embed(row)

        if args.dry_run:
            logger.info(f"[DRY RUN] Row {row_idx}: {row[COL_PRODUCT] if COL_PRODUCT < len(row) else 'empty'}")
        else:
            try:
                discord_send(args.channel, content="@everyone", embed=embed)
                logger.info(f"Sent row {row_idx} to #{args.channel}")
            except Exception as e:
                logger.error(f"Failed to send row {row_idx}: {e}")
                # Save state up to last successful row
                state[state_key] = row_idx - 1
                save_state(state)
                return

    # Update state to last row
    state[state_key] = len(rows) - 1
    save_state(state)
    logger.info(f"Updated state: last_row = {len(rows) - 1}")


if __name__ == "__main__":
    main()

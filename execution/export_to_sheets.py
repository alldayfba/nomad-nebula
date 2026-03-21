#!/usr/bin/env python3
"""
Script: export_to_sheets.py
Purpose: Export FBA sourcing results (BUY/MAYBE products) to Google Sheets
         using service account auth (same pattern as upload_to_gdrive.py).
Inputs:  --input (JSON from calculate_fba_profitability.py)
Outputs: Google Sheet "FBA Sourcing Results" shared with GOOGLE_SHARE_EMAIL,
         with a date-named tab, bold headers, and color-coded rows.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build

# ── Config ────────────────────────────────────────────────────────────────────

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

PROJECT_ROOT = Path(__file__).parent.parent
SA_FILE = PROJECT_ROOT / "service_account.json"
SPREADSHEET_NAME = "FBA Sourcing Results"
LAST_URL_FILE = PROJECT_ROOT / ".tmp" / "sourcing" / "last_sheet_url.txt"

SHARE_WITH_EMAIL = os.getenv("GOOGLE_SHARE_EMAIL", "")

HEADERS = [
    "Verdict", "Product", "Retailer", "Buy Cost", "Amazon Price", "ASIN",
    "Profit", "ROI%", "BSR", "Est Monthly Sales", "Est Monthly Profit",
    "FBA Sellers", "Competition", "Match Confidence", "Retail URL", "Amazon URL",
]

# Colors (RGB 0-1 floats)
GREEN_BG = {"red": 0.85, "green": 0.93, "blue": 0.83}   # light green for BUY
YELLOW_BG = {"red": 1.0, "green": 0.95, "blue": 0.8}    # light yellow for MAYBE
HEADER_BG = {"red": 0.2, "green": 0.2, "blue": 0.2}     # dark header
HEADER_FG = {"red": 1.0, "green": 1.0, "blue": 1.0}     # white text


# ── Auth ──────────────────────────────────────────────────────────────────────

def get_services():
    """Authenticate with Google using service account. Returns (sheets_service, drive_service)."""
    if not SA_FILE.exists():
        print(f"\nERROR: service_account.json not found at:\n   {SA_FILE}", file=sys.stderr)
        print("\n   Steps:", file=sys.stderr)
        print("   1. console.cloud.google.com -> IAM & Admin -> Service Accounts", file=sys.stderr)
        print("   2. Create Service Account -> name it 'antigravity-uploader' -> Done", file=sys.stderr)
        print("   3. Click the service account -> Keys -> Add Key -> JSON -> Create", file=sys.stderr)
        print(f"   4. Save the downloaded file as: {SA_FILE}", file=sys.stderr)
        sys.exit(1)

    creds = service_account.Credentials.from_service_account_file(str(SA_FILE), scopes=SCOPES)
    sheets = build("sheets", "v4", credentials=creds)
    drive = build("drive", "v3", credentials=creds)
    return sheets, drive


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_or_create_spreadsheet(sheets_service, drive_service, name):
    """Find an existing spreadsheet by name or create a new one. Returns spreadsheet_id."""
    # Search for existing spreadsheet owned by the service account
    query = (
        f"name='{name}' "
        f"and mimeType='application/vnd.google-apps.spreadsheet' "
        f"and trashed=false"
    )
    results = drive_service.files().list(q=query, fields="files(id,name)").execute()
    files = results.get("files", [])

    if files:
        spreadsheet_id = files[0]["id"]
        print(f"[sheets] Found existing spreadsheet: {name} ({spreadsheet_id})", file=sys.stderr)
        return spreadsheet_id

    # Create new spreadsheet
    body = {"properties": {"title": name}}
    spreadsheet = sheets_service.spreadsheets().create(body=body, fields="spreadsheetId").execute()
    spreadsheet_id = spreadsheet["spreadsheetId"]
    print(f"[sheets] Created new spreadsheet: {name} ({spreadsheet_id})", file=sys.stderr)
    return spreadsheet_id


def _share_spreadsheet(drive_service, spreadsheet_id, email):
    """Share the spreadsheet with a specific email (writer) and make link-accessible."""
    # Share with specific email if provided
    if email:
        try:
            drive_service.permissions().create(
                fileId=spreadsheet_id,
                body={"type": "user", "role": "writer", "emailAddress": email},
                sendNotificationEmail=False,
            ).execute()
            print(f"[sheets] Shared with {email}", file=sys.stderr)
        except Exception as e:
            print(f"[sheets] Warning: could not share with {email}: {e}", file=sys.stderr)

    # Also make accessible to anyone with the link
    try:
        drive_service.permissions().create(
            fileId=spreadsheet_id,
            body={"type": "anyone", "role": "writer"},
        ).execute()
        print("[sheets] Link sharing enabled (anyone with link can edit)", file=sys.stderr)
    except Exception as e:
        print(f"[sheets] Warning: could not enable link sharing: {e}", file=sys.stderr)


def _get_existing_sheet_titles(sheets_service, spreadsheet_id):
    """Get list of existing sheet/tab titles in the spreadsheet."""
    metadata = sheets_service.spreadsheets().get(
        spreadsheetId=spreadsheet_id, fields="sheets.properties.title"
    ).execute()
    return [s["properties"]["title"] for s in metadata.get("sheets", [])]


def _product_to_row(product):
    """Convert a product dict (with profitability) to a row of cell values."""
    prof = product.get("profitability", {})
    amazon = product.get("amazon", {})

    verdict = prof.get("verdict", "SKIP")
    product_name = product.get("name", "") or amazon.get("title", "")
    retailer = product.get("retailer", "")
    buy_cost = prof.get("buy_cost")
    sell_price = prof.get("sell_price")
    asin = amazon.get("asin", "")
    profit = prof.get("profit_per_unit")
    roi = prof.get("roi_percent")
    bsr = amazon.get("sales_rank")
    monthly_sales = prof.get("estimated_monthly_sales")
    monthly_profit = prof.get("estimated_monthly_profit")
    fba_sellers = amazon.get("fba_seller_count")
    competition = prof.get("competition_score", "")
    match_conf = amazon.get("match_confidence")
    retail_url = product.get("url", "")
    amazon_url = amazon.get("product_url", "")

    def fmt_dollar(val):
        return f"${val:.2f}" if val is not None else ""

    def fmt_pct(val):
        return f"{val:.1f}%" if val is not None else ""

    def fmt_int(val):
        return str(val) if val is not None else ""

    def fmt_conf(val):
        return f"{val:.0%}" if val is not None else ""

    return [
        verdict,
        product_name,
        retailer,
        fmt_dollar(buy_cost),
        fmt_dollar(sell_price),
        asin,
        fmt_dollar(profit),
        fmt_pct(roi),
        fmt_int(bsr),
        fmt_int(monthly_sales),
        fmt_dollar(monthly_profit),
        fmt_int(fba_sellers),
        competition,
        fmt_conf(match_conf),
        retail_url,
        amazon_url,
    ]


def write_results_to_sheet(sheets_service, spreadsheet_id, results):
    """Write BUY and MAYBE products to a new date-named tab. Returns tab name."""
    products = results.get("products", [])

    # Filter to BUY and MAYBE only
    actionable = [
        p for p in products
        if p.get("profitability", {}).get("verdict") in ("BUY", "MAYBE")
    ]

    if not actionable:
        print("[sheets] No BUY or MAYBE products to export.", file=sys.stderr)
        return None

    # Tab name = today's date
    tab_name = datetime.now().strftime("%Y-%m-%d")

    # Check if tab already exists; if so, add a suffix
    existing_titles = _get_existing_sheet_titles(sheets_service, spreadsheet_id)
    final_tab_name = tab_name
    suffix = 1
    while final_tab_name in existing_titles:
        suffix += 1
        final_tab_name = f"{tab_name} ({suffix})"

    # Create the new sheet tab
    add_sheet_request = {
        "requests": [{
            "addSheet": {
                "properties": {"title": final_tab_name}
            }
        }]
    }
    resp = sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body=add_sheet_request
    ).execute()
    sheet_id = resp["replies"][0]["addSheet"]["properties"]["sheetId"]

    # Build rows: headers + data
    rows = [HEADERS]
    for product in actionable:
        rows.append(_product_to_row(product))

    # Write values
    range_str = f"'{final_tab_name}'!A1"
    sheets_service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=range_str,
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()

    print(f"[sheets] Wrote {len(actionable)} products to tab '{final_tab_name}'", file=sys.stderr)

    # ── Apply formatting ──────────────────────────────────────────────────
    format_requests = []

    num_cols = len(HEADERS)
    num_rows = len(rows)

    # Bold header row with dark background and white text
    format_requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": 1,
                "startColumnIndex": 0,
                "endColumnIndex": num_cols,
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": HEADER_BG,
                    "textFormat": {
                        "bold": True,
                        "foregroundColor": HEADER_FG,
                    },
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat)",
        }
    })

    # Freeze header row
    format_requests.append({
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {"frozenRowCount": 1},
            },
            "fields": "gridProperties.frozenRowCount",
        }
    })

    # Color-code data rows by verdict
    for row_idx, product in enumerate(actionable, start=1):
        verdict = product.get("profitability", {}).get("verdict", "")
        if verdict == "BUY":
            bg_color = GREEN_BG
        elif verdict == "MAYBE":
            bg_color = YELLOW_BG
        else:
            continue

        format_requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": row_idx,
                    "endRowIndex": row_idx + 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": num_cols,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": bg_color,
                    }
                },
                "fields": "userEnteredFormat.backgroundColor",
            }
        })

    # Auto-resize columns
    format_requests.append({
        "autoResizeDimensions": {
            "dimensions": {
                "sheetId": sheet_id,
                "dimension": "COLUMNS",
                "startIndex": 0,
                "endIndex": num_cols,
            }
        }
    })

    if format_requests:
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": format_requests},
        ).execute()
        print("[sheets] Formatting applied (bold headers, row colors, auto-resize)", file=sys.stderr)

    return final_tab_name


# ── Main Export Function ──────────────────────────────────────────────────────

def export_to_sheets(results_path):
    """Export sourcing results to Google Sheets. Returns sheet URL."""
    results_path = Path(results_path)
    if not results_path.exists():
        print(f"ERROR: Results file not found: {results_path}", file=sys.stderr)
        sys.exit(1)

    with open(results_path) as f:
        results = json.load(f)

    # Count actionable products
    actionable = [
        p for p in results.get("products", [])
        if p.get("profitability", {}).get("verdict") in ("BUY", "MAYBE")
    ]
    buy_count = sum(1 for p in actionable if p["profitability"]["verdict"] == "BUY")
    maybe_count = len(actionable) - buy_count

    if not actionable:
        print("[sheets] No BUY or MAYBE products found in results. Nothing to export.", file=sys.stderr)
        return None

    print(f"[sheets] Exporting {len(actionable)} products ({buy_count} BUY, {maybe_count} MAYBE)...",
          file=sys.stderr)

    # Authenticate
    print("[sheets] Authenticating with Google (service account)...", file=sys.stderr)
    sheets_service, drive_service = get_services()
    print("[sheets] Authenticated", file=sys.stderr)

    # Get or create spreadsheet
    spreadsheet_id = get_or_create_spreadsheet(sheets_service, drive_service, SPREADSHEET_NAME)
    sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"

    # Share with configured email
    if SHARE_WITH_EMAIL:
        _share_spreadsheet(drive_service, spreadsheet_id, SHARE_WITH_EMAIL)
    else:
        print("[sheets] Warning: GOOGLE_SHARE_EMAIL not set, skipping share", file=sys.stderr)
        # Still enable link sharing
        _share_spreadsheet(drive_service, spreadsheet_id, None)

    # Write data to new tab
    tab_name = write_results_to_sheet(sheets_service, spreadsheet_id, results)

    if tab_name:
        print(f"\n{'─' * 60}", file=sys.stderr)
        print(f"DONE - Exported to Google Sheets", file=sys.stderr)
        print(f"{'─' * 60}", file=sys.stderr)
        print(f"Spreadsheet: {sheet_url}", file=sys.stderr)
        print(f"Tab: {tab_name}", file=sys.stderr)
        print(f"Products: {buy_count} BUY, {maybe_count} MAYBE", file=sys.stderr)
        print(f"{'─' * 60}", file=sys.stderr)

        # Save URL for other scripts to reference
        LAST_URL_FILE.parent.mkdir(parents=True, exist_ok=True)
        LAST_URL_FILE.write_text(sheet_url)
        print(f"[sheets] URL saved to {LAST_URL_FILE}", file=sys.stderr)

        # Print URL to stdout for piping
        print(sheet_url)
        return sheet_url

    return None


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Export FBA sourcing results to Google Sheets"
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to results JSON (from calculate_fba_profitability.py)"
    )
    args = parser.parse_args()

    url = export_to_sheets(args.input)
    if not url:
        sys.exit(1)


if __name__ == "__main__":
    main()

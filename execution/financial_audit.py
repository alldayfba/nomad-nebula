#!/usr/bin/env python3
"""
Financial Audit — Multi-source bank statement parser + analyzer.
Processes BofA, CashApp, Apple Cash, and Self Financial PDFs.
Outputs CSV data + comprehensive markdown report.
"""
from __future__ import annotations

import csv
import glob
import os
import re
import sys
from collections import defaultdict
from datetime import datetime

import pdfplumber

DOWNLOADS = os.path.expanduser("~/Downloads")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".tmp", "financial-audit")

# ─── Categorization Engine ───────────────────────────────────────────

CATEGORIES = [
    # (category, keywords_list, case_insensitive)
    ("Inter-Account Transfer", [
        "transfer from sav", "transfer to sav", "transfer from chk", "transfer to chk",
        "online banking transfer from sav", "online banking transfer to sav",
        "online banking transfer from chk", "online banking transfer to chk",
        "to savings", "from savings", "from bank of america",
        "instant transfer to bank", "transfer to bank",
        "to cash app", "from cash app",
        "apple cash inst xfer", "apple pay", "pmnt sent", "pmnt rcvd",
        "mobile purchase", "apple cash sent",
    ], True),
    ("Rent/Housing", [
        "society las olas", "apartment", "rent ", "lease",
        "fpl:", "fpl speedpay", "fpl direct debit", "aci fl power",
        "t mobile", "courtyard fort lauderdale",
    ], True),
    ("Food/Dining", [
        "chipotle", "doordash", "uber eats", "ubereats", "publix", "whole foods",
        "aldi", "wendy", "mcdonald", "burger", "pizza", "subway", "chick-fil",
        "crema gourmet", "cluck face", "pura vida", "hemingways", "burnies",
        "burnie's", "racetrac", "wawa", "starbucks", "dunkin", "taco bell", "popeyes",
        "grubhub", "postmates", "seamless", "restaurant", "grill", "diner",
        "bakery", "cafe", "coffee", "sushi", "thai", "chinese", "indian",
        "tst*", "grocery", "food", "eat",
        "domino's", "dominos", "7 eleven", "7-eleven", "cumberland farms",
        "bridge mart", "snack soda vending", "wal mart", "wal-mart", "walmart",
        "wm supercenter", "wmt plus", "pbc taunton", "st joseph med", "walgreens",
        "boozy bites", "florios", "florio's", "kfc ", "sarpino", "aura bistro",
        "jrk mia", "fiesta mexican", "el santo taqueria", "oasis by the sea",
        "crema ", "shaws", "shaw's", "ck at downtown", "dania point",
        "bsu marketplace", "rosies pizzeria", "pizzeria regina", "ihop",
        "mee king garden", "haagen dazs", "denny's", "raising cane",
        "munchies", "it italy", "north italia", "moxies", "miller s ale",
        "tayrona", "hogfish", "winn dixie", "instacart", "home depot",
        "costco", "bjs wholesale", "dicks last resort", "red rooster",
    ], True),
    ("Nightlife/Entertainment", [
        "e11even", "eleven miami", "dicey riley", "booze", "sway",
        "vice city", "cc rooftop", "rooftop social", "club", "lounge",
        "liquor", "bar ", "nightclub", "hookah",
        "ls ocean wine", "america's backyard", "vape", "smoke shop",
        "lucky's tavern", "lucky&apos;s", "squiggy", "colosseum", "crusoe wynwood",
        "bridgewater discount liqu", "bridgewater disco", "fancy puffs",
        "flicker lite", "priceless", "yolo ", "space invaders", "shrine miami",
        "bsmnt ", "aficionados", "the river miami", "blackbird ordinary",
        "el tiesto", "sunshine 93", "se* eeven", "margaritavill",
        "reef miami", "komodo miami", "sugar miami", "dice.fm",
        "flow brickell", "nowhere ftl",
    ], True),
    ("Transportation", [
        "uber ", "uber trip", "uber.com", "ubr pending", "lyft", "toyota",
        "enterprise rent", "spirit air", "delta air", "frontier air",
        "gas ", "chevron", "shell ", "exxon", "bp ", "sunpass", "toll",
        "towing", "parking", "hertz", "avis", "www.uber",
        "american airlines", "american airli", "fort lauderdale airpor",
        "jetblue", "united ", "spirit ai", "frontier ", "delta ",
        "u-haul", "u haul", "citgo ", "speedway", "boston's finest fuel",
        "sunpass", "baumgardner auto", "superior auto",
    ], True),
    ("SaaS/Subscriptions", [
        "highlevel", "manychat", "calendly", "smartscout", "clickfunnels",
        "clickfunne", "notion", "loom", "zapier", "openai", "keepa",
        "selleramp", "seller amp", "capcut", "genspark", "claude.ai",
        "shopify", "styleseat", "typeform", "dashpass", "microsoft",
        "onlinejobsph", "pikzels", "fanbasis sub", "anthropic",
        "neverbounce", "slack ", "porkbun", "godaddy", "google one",
        "experian", "pirate ship", "1infiniteloop", "google *gsuite",
        "google gsuite", "google *youtub", "zoom.com", "squarespace",
        "elevenlabs", "spocket", "bqool", "tiktok shop", "vidiq",
        "vturb", "kit.com", "simpletexting", "urlgenius", "paddle.net",
        "reincubate", "base44", "mcgrawhillg", "p.skool", "dimeswithd",
        "eytmedia", "air9.co",
    ], True),
    ("Apple Purchases", [
        "apple.com/bill", "apple.com bill",
    ], True),
    ("Advertising", [
        "facebook ads", "snap ads", "meta ads", "facebk xppndtqsk",
        "fb ads", "instagram ads", "google ads",
        "facebk ", "facebook ", "facebk q", "facebk l", "facebk z", "facebk 6",
    ], True),
    ("Debt Payments", [
        "self lender", "self lend", "leadbank", "lead bank", "kikoff",
        "capital one", "dave ", "loan repayment", "self financial",
        "progressive *insu",
    ], True),
    ("Amazon Payouts", [
        "amazon", "amzn",
    ], True),
    ("Business Income", [
        "whop", "masspay", "fanbasis", "paypal",
    ], True),
    ("Crypto", [
        "moonpay", "coinbase", "meld", "paybis", "bitcoin",
    ], True),
    ("International Transfers", [
        "remitly", "rmtly", "remit",
    ], True),
    ("Rent/Housing (Cashier's Check)", [
        "bkofamerica bc",
    ], True),
    ("Cash Withdrawals", [
        "atm ", "atm withdrawal", "bank of amer withdraw", "cash withdrawal",
        "counter withdrawal", "withdrwl",
    ], True),
    ("Bank Fees", [
        "overdraft", "maintenance fee", "service fee", "wire fee",
        "non-bank of america atm", "insufficient funds", "nsf fee",
        "nsf charge", "returned item", "monthly fee business",
        "return of posted check", "temporary credit",
        "interest earned", "wire transfer fee",
        "bank of america od",
    ], True),
    ("Personal Care", [
        "barber", "the spot barber", "zara ", "target ", "macy",
        "ross ", "tjmaxx", "marshalls", "old navy", "h&m",
        "crunch braintree", "gym ", "florida commercial vacuum",
        "ca secretary of state", "storage", "nike", "ray ban",
        "spirit halloween", "apple store", "best buy", "bestbuy",
        "loop worldwide", "alter native", "target.com", "ups store",
        "usps ", "pj distributors", "tint worl", "little havana laundry",
        "mk shop", "pos pay",
    ], True),
    ("Travel", [
        "airbnb", "expedia", "hotel", "ncl cruise", "ncl getaw", "cruise",
        "booking.com", "vrbo", "norwegian getaway", "coral by the sea",
        "seminole h",
    ], True),
]

# Known people for Zelle/CashApp identification
KNOWN_PEOPLE_INCOME = [
    "yan silva", "ysilva llc", "thomas tran", "marjorie bright",
    "nicholas batchelder", "nasim khan", "bessellzllc",
]


def categorize(description: str, details: str = "") -> str:
    """Categorize a transaction by description keywords."""
    desc_lower = description.lower().strip()
    details_lower = details.lower().strip()
    combined = desc_lower + " " + details_lower

    # Check Zelle first
    if "zelle payment" in combined:
        return "People (Zelle)"

    # CashApp internal transfers (description is "Cash App", "Savings", etc. with Transfer details)
    if details_lower in ("transfer", "standard transfer"):
        if desc_lower in ("cash app", "savings") or \
           desc_lower.startswith("to cash app") or desc_lower.startswith("from cash app") or \
           desc_lower.startswith("from bank of america") or \
           desc_lower.startswith("bank of america") or \
           desc_lower.startswith("mastercard debit") or \
           desc_lower.startswith("visa debit") or \
           desc_lower.startswith("chase bank") or \
           desc_lower.startswith("fiserv"):
            return "Inter-Account Transfer"

    # Check all categories
    for category, keywords, _ in CATEGORIES:
        for kw in keywords:
            if kw.lower() in combined:
                return category

    return "UNCATEGORIZED"


def parse_direction(amount: float, description: str, category: str) -> str:
    """Determine if transaction is income or expense."""
    if category.startswith("Inter-Account"):
        return "transfer"
    if amount > 0:
        return "income"
    return "expense"


# ─── Parser 1: BofA ──────────────────────────────────────────────────

def detect_bofa_account(text: str) -> tuple[str, str]:
    """Detect BofA account type and number from page 1 text."""
    account_type = "Unknown BofA"
    if "Adv Plus Banking" in text:
        account_type = "Personal Checking (5021)"
    elif "Advantage Savings" in text and "Business" not in text:
        account_type = "Personal Savings (5018)"
    elif "Business Advantage Savings" in text:
        account_type = "Biz Savings (1697)"
    elif "Business Advantage Relationship" in text:
        account_type = "Biz Checking (1707)"

    # Extract account number
    m = re.search(r'Account number:\s*([\d\s]+)', text)
    acct_num = m.group(1).strip().replace(" ", "") if m else ""

    return account_type, acct_num


def extract_bofa_period(text: str) -> tuple[str, str]:
    """Extract statement period from BofA page 1."""
    m = re.search(r'for\s+(\w+ \d+,\s*\d{4})\s+to\s+(\w+ \d+,\s*\d{4})', text)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", ""


def extract_bofa_balances(text: str) -> tuple[float, float]:
    """Extract beginning and ending balances."""
    begin = 0.0
    end = 0.0
    m = re.search(r'Beginning balance.*?\$?([\d,]+\.\d{2})', text)
    if m:
        val = m.group(1).replace(",", "")
        begin = float(val)
        # Check if negative (preceded by minus or the line says negative)
        line = text[max(0, m.start()-20):m.end()]
        if '-' in line and '-$' not in line:
            pass  # keep positive
    m = re.search(r'Ending balance.*?\$?([\d,]+\.\d{2})', text)
    if m:
        val = m.group(1).replace(",", "")
        end = float(val)
    return begin, end


def parse_bofa_transactions(pdf_path: str) -> list[dict]:
    """Parse all transactions from a BofA statement PDF."""
    transactions = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if not pdf.pages:
                return transactions

            # Page 1: detect account
            page1_text = pdf.pages[0].extract_text() or ""
            account_type, acct_num = detect_bofa_account(page1_text)
            period_start, period_end = extract_bofa_period(page1_text)

            # Parse all pages for transactions
            full_text = ""
            for page in pdf.pages:
                full_text += (page.extract_text() or "") + "\n"

            # Find transaction sections
            # BofA transactions follow pattern: MM/DD/YY Description Amount
            current_section = "unknown"
            lines = full_text.split("\n")
            i = 0
            while i < len(lines):
                line = lines[i].strip()

                # Detect section headers
                if "Deposits and other" in line:
                    current_section = "deposits"
                elif "ATM and debit card" in line:
                    current_section = "atm_debit"
                elif "Other subtractions" in line or "Withdrawals and other" in line:
                    current_section = "withdrawals"
                elif line.startswith("Checks") and "checks" not in current_section:
                    current_section = "checks"
                elif "Daily ledger balance" in line:
                    current_section = "skip"
                elif "Total deposits" in line or "Total withdrawals" in line or "Total ATM" in line or "Total other" in line:
                    i += 1
                    continue

                # Parse transaction lines: MM/DD/YY Description Amount
                m = re.match(r'^(\d{2}/\d{2}/\d{2})\s+(.+?)\s+([\-]?[\d,]+\.\d{2})$', line)
                if m and current_section != "skip":
                    date_str = m.group(1)
                    desc = m.group(2).strip()
                    amount = float(m.group(3).replace(",", ""))

                    # Check next line for continuation
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        # If next line doesn't start with a date or section header, it's a continuation
                        if next_line and not re.match(r'^\d{2}/\d{2}/\d{2}', next_line) and \
                           not any(kw in next_line for kw in ["Deposits and", "ATM and", "Other subtractions",
                                                               "Withdrawals and", "Checks", "Daily ledger",
                                                               "Total ", "continued", "Page ", "BANK OF AMERICA",
                                                               "SABBYJORY", "ALLDAYFBA", "Account #",
                                                               "Scheduled and", "Tips to help",
                                                               "Account security"]):
                            # Check if continuation line has an amount at the end
                            cont_m = re.match(r'^(.+?)\s+([\-]?[\d,]+\.\d{2})$', next_line)
                            if cont_m:
                                desc += " " + cont_m.group(1).strip()
                            elif not re.match(r'^[\d,]+\.\d{2}$', next_line):
                                desc += " " + next_line
                            i += 1

                    # Parse date (MM/DD/YY)
                    try:
                        dt = datetime.strptime(date_str, "%m/%d/%y")
                        full_date = dt.strftime("%Y-%m-%d")
                    except ValueError:
                        full_date = date_str

                    # Determine sign based on section
                    if current_section in ("atm_debit", "withdrawals", "checks"):
                        amount = -abs(amount)
                    elif current_section == "deposits":
                        amount = abs(amount)

                    transactions.append({
                        "date": full_date,
                        "description": desc,
                        "amount": amount,
                        "source": "BofA",
                        "account": account_type,
                        "details": "",
                        "fee": 0.0,
                    })

                # Also catch service fees
                if "service fee" in line.lower() or "maintenance fee" in line.lower():
                    m2 = re.search(r'(-?[\d,]+\.\d{2})', line)
                    if m2 and not re.match(r'^\d{2}/\d{2}/\d{2}', line):
                        # This is the summary line, skip (individual fees are in transactions)
                        pass

                i += 1

    except Exception as e:
        print(f"  ERROR parsing {os.path.basename(pdf_path)}: {e}", file=sys.stderr)

    return transactions


# ─── Parser 2: CashApp ───────────────────────────────────────────────

def parse_cashapp_transactions(pdf_path: str) -> list[dict]:
    """Parse all transactions from a CashApp monthly statement PDF."""
    transactions = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if not pdf.pages:
                return transactions

            # Page 1: get month/year
            page1_text = pdf.pages[0].extract_text() or ""

            # Extract month and year from header
            month_year = ""
            m = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})', page1_text)
            if m:
                month_year = f"{m.group(1)} {m.group(2)}"

            # Extract year for date parsing
            year = ""
            if m:
                year = m.group(2)

            # Parse transaction pages (usually page 2+)
            for page in pdf.pages:
                text = page.extract_text() or ""
                lines = text.split("\n")

                in_transactions = False
                i = 0
                while i < len(lines):
                    line = lines[i].strip()

                    if line == "Transactions" or line.startswith("Date "):
                        in_transactions = True
                        i += 1
                        continue

                    if not in_transactions:
                        i += 1
                        continue

                    # CashApp format: "MonthAbbr Day  Description  Details  Fee  Amount"
                    # Amount can be "+ $X.XX" or "$X.XX" (expense)
                    # Try to match transaction line
                    m = re.match(
                        r'^([A-Z][a-z]{2}\s+\d{1,2})\s+'  # Date: "Jan 1" or "Feb 12"
                        r'(.+?)\s+'                         # Description
                        r'(Standard transfer|Cash App Card|Transfer|Loan repayment.*?|Bitcoin.*?|Cash out|Deposit|Payment|Peer to Peer|Direct Deposit|Paper Money Deposit|Boost)\s+'  # Details
                        r'\$?([\d.]+)\s+'                   # Fee
                        r'([+\-\s]*\$?[\d,.]+)',            # Amount
                        line
                    )

                    if not m:
                        # Try simpler pattern
                        m = re.match(
                            r'^([A-Z][a-z]{2}\s+\d{1,2})\s+'
                            r'(.+?)\s{2,}'
                            r'(.+?)\s{2,}'
                            r'\$?([\d.]+)\s+'
                            r'([+\-\s]*\$?[\d,.]+)',
                            line
                        )

                    if m:
                        date_str = m.group(1).strip()
                        desc = m.group(2).strip()
                        details = m.group(3).strip()
                        fee = float(m.group(4).replace(",", ""))
                        amount_str = m.group(5).strip().replace(" ", "").replace(",", "")

                        # Parse amount
                        is_income = "+" in amount_str
                        amount_str = amount_str.replace("+", "").replace("$", "").replace("-", "")
                        try:
                            amount = float(amount_str)
                        except ValueError:
                            i += 1
                            continue

                        if not is_income:
                            amount = -amount

                        # Parse date
                        try:
                            dt = datetime.strptime(f"{date_str} {year}", "%b %d %Y")
                            full_date = dt.strftime("%Y-%m-%d")
                        except ValueError:
                            full_date = f"{year}-{date_str}"

                        transactions.append({
                            "date": full_date,
                            "description": desc,
                            "amount": amount,
                            "source": "CashApp",
                            "account": "CashApp",
                            "details": details,
                            "fee": fee,
                        })

                    i += 1

    except Exception as e:
        print(f"  ERROR parsing {os.path.basename(pdf_path)}: {e}", file=sys.stderr)

    return transactions


# ─── Parser 3: Apple Cash ────────────────────────────────────────────

def parse_apple_cash_transactions(pdf_path: str) -> list[dict]:
    """Parse all transactions from Apple Cash statement PDF.

    Format: Each transaction starts with MM/DD/YYYY on a line, followed by
    continuation lines. The amount (+$X.XX or -$X.XX) appears in the
    continuation lines, and the balance ($X.XX) is at the end.
    """
    transactions = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Collect all lines across all pages
            all_lines = []
            for page in pdf.pages:
                text = page.extract_text() or ""
                for line in text.split("\n"):
                    line = line.strip()
                    if line:
                        all_lines.append(line)

            # Group lines into transactions
            # A transaction starts with MM/DD/YYYY
            skip_lines = {
                "Account Statement", "NAME", "Sabbyjory", "APPLE ID",
                "webethunder", "Summary ", "SUBTOTAL", "Starting Balance",
                "Money In", "Money Out", "Ending Balance", "Transactions ",
                "DATE", "DESCRIPTION", "Copyright", "Page ", "No Transactions",
                "All Rights", "Privacy Policy", "Terms and Conditions",
            }

            current_date = None
            current_lines = []

            def flush_transaction():
                nonlocal current_date, current_lines
                if not current_date or not current_lines:
                    current_date = None
                    current_lines = []
                    return

                full_text = " ".join(current_lines)

                # Extract all dollar amounts from the transaction text
                amounts = re.findall(r'([+-]?\$[\d,]+\.\d{2})', full_text)

                if not amounts:
                    current_date = None
                    current_lines = []
                    return

                # The AMOUNT is typically the second-to-last or last +/- prefixed value
                # The BALANCE is the last value (no +/- or has one)
                # Find the main transaction amount (the one with +/- prefix)
                tx_amount = None
                fee_amount = 0.0

                for amt_str in amounts:
                    clean = amt_str.replace("$", "").replace(",", "").replace("+", "")
                    if amt_str.startswith("+") or amt_str.startswith("-"):
                        # Check if this is labeled as account fee
                        idx = full_text.find(amt_str)
                        before = full_text[max(0, idx-15):idx].lower()
                        if "fee" in before or "account fee" in before:
                            try:
                                fee_amount = abs(float(clean))
                            except ValueError:
                                pass
                        else:
                            try:
                                tx_amount = float(clean) if not amt_str.startswith("-") else -float(clean.lstrip("-"))
                            except ValueError:
                                pass

                if tx_amount is None:
                    current_date = None
                    current_lines = []
                    return

                # Build description (first line after date, clean up)
                desc = current_lines[0] if current_lines else ""
                # Add second line if it's descriptive (not just a hash)
                if len(current_lines) > 1:
                    line2 = current_lines[1]
                    if not re.match(r'^[a-f0-9]{12}$', line2) and not line2.startswith("From "):
                        desc += " " + line2

                # Clean up description
                desc = re.sub(r'\s+[+-]?\$[\d,]+\.\d{2}.*$', '', desc).strip()
                desc = re.sub(r'\s+Total Payment.*$', '', desc).strip()

                try:
                    dt = datetime.strptime(current_date, "%m/%d/%Y")
                    full_date = dt.strftime("%Y-%m-%d")
                except ValueError:
                    full_date = current_date

                transactions.append({
                    "date": full_date,
                    "description": desc,
                    "amount": tx_amount,
                    "source": "Apple Cash",
                    "account": "Apple Cash (3078)",
                    "details": "",
                    "fee": fee_amount,
                })

                current_date = None
                current_lines = []

            for line in all_lines:
                # Skip boilerplate
                if any(line.startswith(s) for s in skip_lines):
                    continue
                if line in ("$0.00",):
                    continue

                # Check if line starts with a date
                m = re.match(r'^(\d{2}/\d{2}/\d{4})\s+(.*)', line)
                if m:
                    # Flush previous transaction
                    flush_transaction()
                    current_date = m.group(1)
                    remainder = m.group(2).strip()
                    if remainder:
                        current_lines = [remainder]
                    else:
                        current_lines = []
                elif current_date:
                    # Continuation line
                    current_lines.append(line)

            # Flush last transaction
            flush_transaction()

    except Exception as e:
        print(f"  ERROR parsing Apple Cash: {e}", file=sys.stderr)

    return transactions


# ─── Parser 4: Self Financial ────────────────────────────────────────

def parse_self_financial(pdf_path: str) -> list[dict]:
    """Parse Self Financial credit builder loan statement."""
    transactions = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if not pdf.pages:
                return transactions

            text = pdf.pages[0].extract_text() or ""

            # Extract statement date
            m = re.search(r'Statement Date\s+(\w+ \d+,\s*\d{4})', text)
            stmt_date = ""
            if m:
                try:
                    dt = datetime.strptime(m.group(1).strip(), "%b %d, %Y")
                    stmt_date = dt.strftime("%Y-%m-%d")
                except ValueError:
                    stmt_date = m.group(1).strip()

            # Extract amounts
            def extract_amount(pattern):
                m2 = re.search(pattern, text)
                if m2:
                    return float(m2.group(1).replace(",", ""))
                return 0.0

            total_due = extract_amount(r'Total due.*?\$([\d,.]+)')
            principal = extract_amount(r'Principal\s+\$([\d,.]+)')
            interest = extract_amount(r'Interest\s+\$([\d,.]+)')
            past_due = extract_amount(r'Past due\s+\$([\d,.]+)')
            late_fees = extract_amount(r'Late fees\s+\$([\d,.]+)')
            unpaid = extract_amount(r'Unpaid principal balance\s+\$([\d,.]+)')

            if stmt_date and total_due > 0:
                transactions.append({
                    "date": stmt_date,
                    "description": f"Self Financial payment due (Principal: ${principal:.2f}, Interest: ${interest:.2f}, Late fees: ${late_fees:.2f}, Past due: ${past_due:.2f})",
                    "amount": -total_due,
                    "source": "Self Financial",
                    "account": "Credit Builder Loan",
                    "details": f"Unpaid balance: ${unpaid:.2f}",
                    "fee": late_fees,
                })

    except Exception as e:
        print(f"  ERROR parsing {os.path.basename(pdf_path)}: {e}", file=sys.stderr)

    return transactions


# ─── Main Pipeline ───────────────────────────────────────────────────

def find_files():
    """Find all statement files in Downloads."""
    bofa = sorted(glob.glob(os.path.join(DOWNLOADS, "eStmt_*.pdf")))
    cashapp = sorted(glob.glob(os.path.join(DOWNLOADS, "monthly-statement*.pdf")))
    apple = [os.path.join(DOWNLOADS, "Apple Cash Statement.pdf")]
    self_fin = sorted(glob.glob(os.path.join(DOWNLOADS, "download (*.pdf")))

    # Check apple exists
    apple = [f for f in apple if os.path.exists(f)]

    return bofa, cashapp, apple, self_fin


def process_all():
    """Process all statement files and generate output."""
    bofa_files, cashapp_files, apple_files, self_files = find_files()

    print(f"Found files:")
    print(f"  BofA:          {len(bofa_files)}")
    print(f"  CashApp:       {len(cashapp_files)}")
    print(f"  Apple Cash:    {len(apple_files)}")
    print(f"  Self Financial: {len(self_files)}")
    print(f"  TOTAL:         {len(bofa_files) + len(cashapp_files) + len(apple_files) + len(self_files)}")
    print()

    all_transactions = []

    # Parse BofA
    print("Parsing BofA statements...")
    for i, f in enumerate(bofa_files):
        txns = parse_bofa_transactions(f)
        all_transactions.extend(txns)
        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/{len(bofa_files)} done ({len(txns)} transactions)")
    print(f"  BofA complete: {sum(1 for t in all_transactions if t['source'] == 'BofA')} transactions")

    # Parse CashApp
    print("Parsing CashApp statements...")
    for i, f in enumerate(cashapp_files):
        txns = parse_cashapp_transactions(f)
        all_transactions.extend(txns)
        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/{len(cashapp_files)} done ({len(txns)} transactions)")
    print(f"  CashApp complete: {sum(1 for t in all_transactions if t['source'] == 'CashApp')} transactions")

    # Parse Apple Cash
    print("Parsing Apple Cash statement...")
    for f in apple_files:
        txns = parse_apple_cash_transactions(f)
        all_transactions.extend(txns)
    print(f"  Apple Cash complete: {sum(1 for t in all_transactions if t['source'] == 'Apple Cash')} transactions")

    # Parse Self Financial
    print("Parsing Self Financial statements...")
    for f in self_files:
        txns = parse_self_financial(f)
        all_transactions.extend(txns)
    print(f"  Self Financial complete: {sum(1 for t in all_transactions if t['source'] == 'Self Financial')} transactions")

    print(f"\nTOTAL TRANSACTIONS: {len(all_transactions)}")

    # Categorize
    print("\nCategorizing transactions...")
    for txn in all_transactions:
        txn["category"] = categorize(txn["description"], txn.get("details", ""))
        txn["direction"] = parse_direction(txn["amount"], txn["description"], txn["category"])

    # Count categories
    cat_counts = defaultdict(int)
    for txn in all_transactions:
        cat_counts[txn["category"]] += 1

    print("Category distribution:")
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")

    # Sort by date
    all_transactions.sort(key=lambda x: x["date"])

    # Write outputs
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    write_all_transactions(all_transactions)
    write_needs_clarification(all_transactions)
    write_monthly_summary(all_transactions)
    write_category_breakdown(all_transactions)
    write_people_payments(all_transactions)
    write_full_report(all_transactions)

    print(f"\nAll output written to {OUTPUT_DIR}/")


def write_all_transactions(transactions: list[dict]):
    """Write all transactions to CSV."""
    path = os.path.join(OUTPUT_DIR, "all_transactions.csv")
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "date", "description", "amount", "source", "account",
            "category", "direction", "details", "fee"
        ])
        writer.writeheader()
        for txn in transactions:
            writer.writerow(txn)
    print(f"  Wrote {len(transactions)} transactions to all_transactions.csv")


def write_needs_clarification(transactions: list[dict]):
    """Write uncategorized transactions for review."""
    unclear = [t for t in transactions if t["category"] == "UNCATEGORIZED"]
    path = os.path.join(OUTPUT_DIR, "needs_clarification.csv")
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "date", "description", "amount", "source", "account", "details"
        ])
        writer.writeheader()
        for txn in unclear:
            writer.writerow({k: txn[k] for k in writer.fieldnames})
    print(f"  Wrote {len(unclear)} unclear transactions to needs_clarification.csv")


def write_monthly_summary(transactions: list[dict]):
    """Write monthly income vs expenses summary."""
    monthly = defaultdict(lambda: {"income": 0.0, "expenses": 0.0, "transfers": 0.0, "fees": 0.0})

    for txn in transactions:
        month = txn["date"][:7]  # YYYY-MM
        if txn["direction"] == "income":
            monthly[month]["income"] += txn["amount"]
        elif txn["direction"] == "expense":
            monthly[month]["expenses"] += txn["amount"]
        elif txn["direction"] == "transfer":
            monthly[month]["transfers"] += txn["amount"]
        monthly[month]["fees"] += txn.get("fee", 0.0)

    path = os.path.join(OUTPUT_DIR, "monthly_summary.csv")
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Month", "Income", "Expenses", "Net", "Transfers", "Fees"])
        for month in sorted(monthly.keys()):
            d = monthly[month]
            net = d["income"] + d["expenses"]
            writer.writerow([month, f"{d['income']:.2f}", f"{d['expenses']:.2f}",
                           f"{net:.2f}", f"{d['transfers']:.2f}", f"{d['fees']:.2f}"])
    print(f"  Wrote {len(monthly)} months to monthly_summary.csv")


def write_category_breakdown(transactions: list[dict]):
    """Write category totals."""
    cats = defaultdict(lambda: {"total": 0.0, "count": 0})
    for txn in transactions:
        if txn["direction"] != "transfer":
            cats[txn["category"]]["total"] += txn["amount"]
            cats[txn["category"]]["count"] += 1

    path = os.path.join(OUTPUT_DIR, "category_breakdown.csv")
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Category", "Total", "Count", "Avg per Transaction"])
        for cat, data in sorted(cats.items(), key=lambda x: x[1]["total"]):
            avg = data["total"] / data["count"] if data["count"] else 0
            writer.writerow([cat, f"{data['total']:.2f}", data['count'], f"{avg:.2f}"])
    print(f"  Wrote {len(cats)} categories to category_breakdown.csv")


def write_people_payments(transactions: list[dict]):
    """Write person-level payment breakdown."""
    people = defaultdict(lambda: {"sent": 0.0, "received": 0.0, "count": 0})

    for txn in transactions:
        desc = txn["description"].lower()
        name = None

        # Zelle
        m = re.search(r'zelle payment (?:to|from)\s+(.+?)(?:\s+conf#|\s*$)', desc, re.IGNORECASE)
        if m:
            name = m.group(1).strip().title()

        # CashApp person-to-person (not merchants/transfers)
        if not name and txn["source"] == "CashApp":
            details = txn.get("details", "").lower()
            if details in ("transfer", "standard transfer") and "bank of america" in desc.lower():
                continue  # Bank transfer, not person
            if details == "peer to peer" or details == "payment":
                name = txn["description"].strip().title()

        if name:
            people[name]["count"] += 1
            if txn["amount"] > 0:
                people[name]["received"] += txn["amount"]
            else:
                people[name]["sent"] += txn["amount"]

    path = os.path.join(OUTPUT_DIR, "people_payments.csv")
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Person", "Total Sent", "Total Received", "Net", "Transaction Count"])
        for person, data in sorted(people.items(), key=lambda x: x[1]["sent"]):
            net = data["received"] + data["sent"]
            writer.writerow([person, f"{data['sent']:.2f}", f"{data['received']:.2f}",
                           f"{net:.2f}", data["count"]])
    print(f"  Wrote {len(people)} people to people_payments.csv")


def write_full_report(transactions: list[dict]):
    """Write comprehensive markdown audit report."""
    path = os.path.join(OUTPUT_DIR, "full_report.md")

    # Compute all metrics
    total_income = sum(t["amount"] for t in transactions if t["direction"] == "income")
    total_expenses = sum(t["amount"] for t in transactions if t["direction"] == "expense")
    total_transfers = sum(abs(t["amount"]) for t in transactions if t["direction"] == "transfer")
    total_fees = sum(t.get("fee", 0.0) for t in transactions)

    # By source
    source_stats = defaultdict(lambda: {"income": 0.0, "expenses": 0.0, "count": 0})
    for t in transactions:
        source_stats[t["source"]]["count"] += 1
        if t["direction"] == "income":
            source_stats[t["source"]]["income"] += t["amount"]
        elif t["direction"] == "expense":
            source_stats[t["source"]]["expenses"] += t["amount"]

    # Categories (expenses only)
    cat_totals = defaultdict(float)
    for t in transactions:
        if t["direction"] == "expense":
            cat_totals[t["category"]] += t["amount"]

    # Monthly P&L
    monthly = defaultdict(lambda: {"income": 0.0, "expenses": 0.0})
    for t in transactions:
        month = t["date"][:7]
        if t["direction"] == "income":
            monthly[month]["income"] += t["amount"]
        elif t["direction"] == "expense":
            monthly[month]["expenses"] += t["amount"]

    # Large transactions
    large = [t for t in transactions if abs(t["amount"]) >= 500 and t["direction"] != "transfer"]
    large.sort(key=lambda x: abs(x["amount"]), reverse=True)

    # SaaS/Subscriptions monthly
    saas_total = sum(t["amount"] for t in transactions
                     if t["category"] in ("SaaS/Subscriptions", "Apple Purchases")
                     and t["direction"] == "expense")
    saas_months = len(set(t["date"][:7] for t in transactions
                         if t["category"] in ("SaaS/Subscriptions", "Apple Purchases")))
    saas_monthly_avg = saas_total / saas_months if saas_months else 0

    # People
    people = defaultdict(float)
    for t in transactions:
        if t["category"] == "People (Zelle)" and t["amount"] < 0:
            m = re.search(r'zelle payment to\s+(.+?)(?:\s+conf#|\s*$)', t["description"], re.IGNORECASE)
            if m:
                people[m.group(1).strip().title()] += t["amount"]

    # Uncategorized count
    uncat_count = sum(1 for t in transactions if t["category"] == "UNCATEGORIZED")

    # Date range
    dates = [t["date"] for t in transactions if t["date"]]
    date_range = f"{min(dates)} to {max(dates)}" if dates else "Unknown"

    with open(path, "w") as f:
        f.write("# Full Financial Audit Report\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"**Period:** {date_range}\n")
        f.write(f"**Total Transactions:** {len(transactions):,}\n")
        f.write(f"**Uncategorized (needs review):** {uncat_count}\n\n")

        f.write("---\n\n")
        f.write("## 1. Executive Summary\n\n")
        f.write(f"| Metric | Amount |\n|---|---|\n")
        f.write(f"| **Total Income** | **${total_income:,.2f}** |\n")
        f.write(f"| **Total Expenses** | **${total_expenses:,.2f}** |\n")
        f.write(f"| **Net** | **${total_income + total_expenses:,.2f}** |\n")
        f.write(f"| Total Inter-Account Transfers | ${total_transfers:,.2f} |\n")
        f.write(f"| Total Fees (CashApp + Bank) | ${total_fees:,.2f} |\n\n")

        f.write("## 2. Income by Source\n\n")
        f.write("| Source | Transactions | Income | Expenses |\n|---|---|---|---|\n")
        for src, stats in sorted(source_stats.items(), key=lambda x: -x[1]["income"]):
            f.write(f"| {src} | {stats['count']:,} | ${stats['income']:,.2f} | ${stats['expenses']:,.2f} |\n")
        f.write("\n")

        f.write("## 3. Monthly P&L\n\n")
        f.write("| Month | Income | Expenses | Net | Cumulative |\n|---|---|---|---|---|\n")
        cumulative = 0.0
        for month in sorted(monthly.keys()):
            d = monthly[month]
            net = d["income"] + d["expenses"]
            cumulative += net
            emoji = "" if net >= 0 else ""
            f.write(f"| {month} | ${d['income']:,.2f} | ${d['expenses']:,.2f} | {emoji}${net:,.2f} | ${cumulative:,.2f} |\n")
        f.write("\n")

        f.write("## 4. Top Spending Categories\n\n")
        f.write("| Rank | Category | Total Spent |\n|---|---|---|\n")
        for rank, (cat, total) in enumerate(sorted(cat_totals.items(), key=lambda x: x[1]), 1):
            f.write(f"| {rank} | {cat} | ${total:,.2f} |\n")
        f.write("\n")

        f.write("## 5. SaaS/Subscription Burn Rate\n\n")
        f.write(f"- **Total SaaS + Apple purchases spent:** ${saas_total:,.2f}\n")
        f.write(f"- **Avg monthly SaaS burn:** ${saas_monthly_avg:,.2f}\n")
        f.write(f"- **Active months:** {saas_months}\n\n")

        # List unique SaaS merchants
        saas_merchants = defaultdict(float)
        for t in transactions:
            if t["category"] in ("SaaS/Subscriptions", "Apple Purchases") and t["direction"] == "expense":
                saas_merchants[t["description"][:40]] += t["amount"]
        if saas_merchants:
            f.write("| Subscription | Total |\n|---|---|\n")
            for merchant, total in sorted(saas_merchants.items(), key=lambda x: x[1]):
                f.write(f"| {merchant} | ${total:,.2f} |\n")
            f.write("\n")

        f.write("## 6. People Payments (Zelle Outbound)\n\n")
        if people:
            f.write("| Person | Total Sent |\n|---|---|\n")
            for person, total in sorted(people.items(), key=lambda x: x[1]):
                f.write(f"| {person} | ${total:,.2f} |\n")
            f.write("\n")

        f.write("## 7. Large Transactions (>$500)\n\n")
        f.write("| Date | Amount | Description | Source |\n|---|---|---|---|\n")
        for t in large[:50]:
            f.write(f"| {t['date']} | ${t['amount']:,.2f} | {t['description'][:60]} | {t['source']} |\n")
        f.write("\n")

        f.write("## 8. Bank & Platform Fees\n\n")
        fee_txns = [t for t in transactions if t["category"] == "Bank Fees"]
        fee_total = sum(t["amount"] for t in fee_txns)
        cashapp_fees = sum(t.get("fee", 0.0) for t in transactions if t["source"] == "CashApp")
        f.write(f"- **Bank fees (overdraft, maintenance, etc.):** ${fee_total:,.2f}\n")
        f.write(f"- **CashApp fees:** ${cashapp_fees:,.2f}\n")
        f.write(f"- **Combined avoidable fees:** ${fee_total + cashapp_fees:,.2f}\n\n")

        f.write("## 9. Cash Withdrawals\n\n")
        cash = [t for t in transactions if t["category"] == "Cash Withdrawals"]
        cash_total = sum(t["amount"] for t in cash)
        f.write(f"- **Total cash withdrawn:** ${cash_total:,.2f}\n")
        f.write(f"- **Number of withdrawals:** {len(cash)}\n\n")
        if cash:
            f.write("| Date | Amount | Description | Source |\n|---|---|---|---|\n")
            for t in sorted(cash, key=lambda x: x["amount"]):
                f.write(f"| {t['date']} | ${t['amount']:,.2f} | {t['description'][:50]} | {t['source']} |\n")
            f.write("\n")

        f.write("## 10. Self Financial Loan Status\n\n")
        self_txns = [t for t in transactions if t["source"] == "Self Financial"]
        self_total = sum(t["amount"] for t in self_txns)
        f.write(f"- **Total payments due:** ${self_total:,.2f}\n")
        f.write(f"- **Number of statements:** {len(self_txns)}\n")
        if self_txns:
            latest = self_txns[-1]
            f.write(f"- **Latest:** {latest['description']}\n")
            f.write(f"- **Details:** {latest['details']}\n\n")

        f.write("## 11. Uncategorized Transactions (Needs Review)\n\n")
        f.write(f"**{uncat_count} transactions** need manual categorization.\n")
        f.write("See `needs_clarification.csv` for the full list.\n\n")

        # Sample of uncategorized
        uncat = [t for t in transactions if t["category"] == "UNCATEGORIZED"]
        if uncat:
            # Group by description similarity
            uncat_descs = defaultdict(lambda: {"count": 0, "total": 0.0})
            for t in uncat:
                key = t["description"][:40]
                uncat_descs[key]["count"] += 1
                uncat_descs[key]["total"] += t["amount"]

            f.write("### Top uncategorized by frequency:\n\n")
            f.write("| Description | Count | Total |\n|---|---|---|\n")
            for desc, data in sorted(uncat_descs.items(), key=lambda x: -x[1]["count"])[:30]:
                f.write(f"| {desc} | {data['count']} | ${data['total']:,.2f} |\n")
            f.write("\n")

    print(f"  Wrote full_report.md")


if __name__ == "__main__":
    process_all()

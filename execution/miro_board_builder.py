#!/usr/bin/env python3
"""
Miro Board Builder v2 — Nik Setting premium visual style.
White backgrounds, yellow sticky notes, multi-zone layouts, color-coded flowcharts.

All frames on "AllDayFBA Content Miro" board (uXjVGKN_Qa4=).

Usage:
    python execution/miro_board_builder.py --frame 1        # Build one frame
    python execution/miro_board_builder.py --frame all      # Build all 8
    python execution/miro_board_builder.py --test           # Test API
"""

import argparse
import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

# ─── Config ───────────────────────────────────────────────────────────────────

MIRO_API_KEY = os.getenv("MIRO_API_KEY")
BASE_URL = "https://api.miro.com/v2"
HEADERS = {
    "Authorization": f"Bearer {MIRO_API_KEY}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

BOARD_ID = "uXjVGKN_Qa4="
BOARD_URL = f"https://miro.com/app/board/{BOARD_ID}/"
API_DELAY = 0.35

# Offset from old dark frames — place new ones further right
# v4 positions — further right to avoid all previous attempts
FRAME_POSITIONS = {
    1: (35000, 0),
    2: (42000, 0),
    3: (35000, 5500),
    4: (42000, 5500),
    5: (35000, 11000),
    6: (42000, 11000),
    7: (35000, 16500),
    8: (42000, 16500),
}

# ─── Nik Setting Color Palette ────────────────────────────────────────────────

C = {
    "white": "#ffffff",
    "off_white": "#f5f5f5",
    "yellow": "#f9e154",
    "light_yellow": "#fff9b1",
    "blue": "#4262ff",
    "light_blue": "#a6ccf5",
    "purple": "#6c6edc",
    "red": "#f24726",
    "pink": "#da0063",
    "green": "#12b886",
    "lime": "#8fd14f",
    "orange": "#ff9d48",
    "warm_orange": "#fac710",
    "gray": "#e6e6e6",
    "dark": "#1a1a1a",
    "mid_gray": "#808080",
    "light_gray": "#c4c4c4",
}

# ─── API Helpers ──────────────────────────────────────────────────────────────


def _post(endpoint, payload):
    url = f"{BASE_URL}{endpoint}"
    try:
        resp = requests.post(url, headers=HEADERS, json=payload)
    except Exception as e:
        print(f"  ERR request failed: {e}")
        return None
    time.sleep(API_DELAY)
    if resp.status_code not in (200, 201):
        print(f"  ERR {resp.status_code}: {resp.text[:200]}")
        return None
    return resp.json()


def frame(title, x, y, w, h):
    """White background frame (Nik style)."""
    data = _post(f"/boards/{BOARD_ID}/frames", {
        "data": {"title": title, "format": "custom"},
        "position": {"x": x, "y": y},
        "geometry": {"width": w, "height": h},
        "style": {"fillColor": C["white"]},
    })
    return data["id"] if data else None


def sh(content, shape_type, x, y, w, h,
       fill="#ffffff", text_color="#1a1a1a", border_color="#1a1a1a",
       font_size=18, border_width=2):
    """Shape with Nik-style defaults (white fill, dark border, dark text)."""
    data = _post(f"/boards/{BOARD_ID}/shapes", {
        "data": {"content": f"<p>{content}</p>", "shape": shape_type},
        "style": {
            "fillColor": fill,
            "fillOpacity": "1.0",
            "borderColor": border_color,
            "borderWidth": str(border_width),
            "borderOpacity": "1.0",
            "borderStyle": "normal",
            "color": text_color,
            "fontSize": str(font_size),
            "textAlign": "center",
            "textAlignVertical": "middle",
            "fontFamily": "arial",
        },
        "position": {"x": x, "y": y},
        "geometry": {"width": w, "height": h},
    })
    return data["id"] if data else None


def tx(content, x, y, font_size=16, color="#1a1a1a", width=300, align="center"):
    """Text block."""
    data = _post(f"/boards/{BOARD_ID}/texts", {
        "data": {"content": f"<p>{content}</p>"},
        "style": {
            "color": color,
            "fontSize": str(font_size),
            "fontFamily": "arial",
            "textAlign": align,
        },
        "position": {"x": x, "y": y},
        "geometry": {"width": width},
    })
    return data["id"] if data else None


def st(content, x, y, color="yellow", w=200):
    """Sticky note (Nik's signature element)."""
    data = _post(f"/boards/{BOARD_ID}/sticky_notes", {
        "data": {"content": content, "shape": "square"},
        "style": {"fillColor": color},
        "position": {"x": x, "y": y},
        "geometry": {"width": w},
    })
    return data["id"] if data else None


def cn(start_id, end_id, color="#1a1a1a", caption="", line_type="elbowed"):
    """Thin clean connector (Nik style — dark, thin, no glow)."""
    if not start_id or not end_id:
        return None
    payload = {
        "startItem": {"id": str(start_id)},
        "endItem": {"id": str(end_id)},
        "style": {
            "strokeColor": color,
            "strokeWidth": "2.0",
            "strokeStyle": "normal",
            "endStrokeCap": "stealth",
            "startStrokeCap": "none",
        },
        "shape": line_type,
    }
    if caption:
        payload["captions"] = [{"content": f"<p>{caption}</p>"}]
    data = _post(f"/boards/{BOARD_ID}/connectors", payload)
    return data["id"] if data else None


# ─── Compound Helpers ─────────────────────────────────────────────────────────


def zone_header(title, x, y, w=400):
    """Bordered rectangle zone title (like Nik's 'Profile Funnel Breakdown')."""
    return sh(f"<strong>{title}</strong>", "rectangle", x, y, w, 60,
              fill=C["white"], border_color=C["dark"], font_size=20, border_width=2)


def colored_rect(content, x, y, w, h, fill, text_color="#ffffff", font_size=18):
    """Colored filled rectangle (process step)."""
    return sh(content, "rectangle", x, y, w, h,
              fill=fill, text_color=text_color, border_color=fill,
              font_size=font_size, border_width=2)


def decision(content, x, y, size=120, fill=C["light_yellow"]):
    """Diamond decision shape."""
    return sh(content, "rhombus", x, y, size, size,
              fill=fill, text_color=C["dark"], border_color=C["dark"],
              font_size=14, border_width=2)


# ─── Additional Helpers ───────────────────────────────────────────────────────


def callout(content, x, y, w=280, h=80, fill=C["light_yellow"]):
    """Speech bubble callout shape — key insight."""
    return sh(content, "wedge_round_rectangle_callout", x, y, w, h,
              fill=fill, text_color=C["dark"], border_color=C["dark"],
              font_size=13, border_width=2)


def metric(value, label, x, y, fill=C["green"]):
    """Circle badge with a key metric."""
    nid = sh(f"<strong>{value}</strong>", "circle", x, y, 100, 100,
             fill=fill, text_color=C["white"], border_color=fill,
             font_size=20, border_width=2)
    tx(label, x, y + 65, 11, C["mid_gray"], 120)
    return nid


def sub_header(title, x, y, w=300):
    """Smaller zone sub-section header."""
    return sh(f"<strong>{title}</strong>", "round_rectangle", x, y, w, 45,
              fill=C["gray"], text_color=C["dark"], border_color=C["gray"],
              font_size=14, border_width=2)


# ─── Frame Builders ───────────────────────────────────────────────────────────


def build_frame_1():
    """The AI Sourcing Pipeline — v4 organized complexity (70+ elements)"""
    print("\n[Frame 1] The AI Sourcing Pipeline")
    ox, oy = FRAME_POSITIONS[1]
    frame("The AI Sourcing Pipeline", ox, oy, 5000, 4200)

    # ── Frame title bar (wide, bold, dark — like Nik's board titles) ──
    colored_rect("<strong>THE AI SOURCING PIPELINE</strong>",
                 ox, oy - 1850, 1200, 70, C["dark"], font_size=28)
    tx("How a single scan finds profitable products in under 8 minutes — fully automated",
       ox, oy - 1790, 14, C["mid_gray"], 800)

    # ══════════════════════════════════════════════════════════════
    # ZONE A (Top-Left): DATA COLLECTION ENGINE
    # ══════════════════════════════════════════════════════════════
    # Light background grouping rectangle
    sh("", "round_rectangle", ox - 1550, oy - 1350, 1400, 1500,
       fill="#f8f8f8", border_color=C["gray"], border_width=2)

    zone_header("① DATA COLLECTION", ox - 1550, oy - 1650, 450)
    tx("Where the raw data comes from — zero manual work",
       ox - 1550, oy - 1590, 12, C["mid_gray"], 450)

    # Step 1: Category Selection
    step1_badge = sh("<strong>1</strong>", "circle", ox - 1900, oy - 1450, 50, 50,
                     fill=C["blue"], text_color=C["white"], border_color=C["blue"],
                     font_size=20, border_width=2)
    n1 = colored_rect("<strong>Choose Category</strong>", ox - 1650, oy - 1450, 280, 70, C["blue"])
    tx("Pick any Amazon category: Grocery, Health,<br>Beauty, Home, Kitchen, Baby, Pet...",
       ox - 1650, oy - 1380, 11, C["mid_gray"], 280)

    # Category examples as small stickies
    st("Grocery &\nGourmet", ox - 1880, oy - 1280, "light_yellow", 130)
    st("Health &\nHousehold", ox - 1720, oy - 1280, "light_yellow", 130)
    st("Beauty &\nPersonal Care", ox - 1560, oy - 1280, "light_yellow", 130)
    st("Home &\nKitchen", ox - 1400, oy - 1280, "light_yellow", 130)

    tx("↓", ox - 1650, oy - 1170, 28, C["blue"], 50)

    # Step 2: Keepa Bestseller Pull
    step2_badge = sh("<strong>2</strong>", "circle", ox - 1900, oy - 1100, 50, 50,
                     fill=C["blue"], text_color=C["white"], border_color=C["blue"],
                     font_size=20, border_width=2)
    n2 = colored_rect("<strong>Keepa: Pull Top 200 ASINs</strong>",
                      ox - 1650, oy - 1100, 320, 70, C["blue"])
    tx("API call returns the top 200 bestselling products<br>in that category. Cost: 1 Keepa token.",
       ox - 1650, oy - 1020, 11, C["mid_gray"], 320)

    callout("This is the unfair advantage.\nYou start with products that\nALREADY sell — not guessing.",
            ox - 1200, oy - 1100, 280, 80)

    tx("↓", ox - 1650, oy - 920, 28, C["blue"], 50)

    # Step 3: Batch Product Data
    step3_badge = sh("<strong>3</strong>", "circle", ox - 1900, oy - 850, 50, 50,
                     fill=C["blue"], text_color=C["white"], border_color=C["blue"],
                     font_size=20, border_width=2)
    n3 = colored_rect("<strong>Keepa: Batch Data Pull</strong>",
                      ox - 1650, oy - 850, 320, 70, C["blue"])

    # Data fields as small rectangles
    data_fields = ["Price", "UPC", "BSR", "Sellers", "Brand", "Weight"]
    for i, field in enumerate(data_fields):
        col = i % 3
        row = i // 3
        sh(f"<strong>{field}</strong>", "round_rectangle",
           ox - 1820 + col * 140, oy - 720 + row * 50, 120, 40,
           fill=C["light_blue"], text_color=C["dark"], border_color=C["light_blue"],
           font_size=11, border_width=2)
    tx("1 token per ASIN (batch call — all 200 at once)",
       ox - 1650, oy - 620, 10, C["mid_gray"], 320)

    # ══════════════════════════════════════════════════════════════
    # ZONE B (Top-Center): RETAIL PRICE CHECK
    # ══════════════════════════════════════════════════════════════
    sh("", "round_rectangle", ox - 50, oy - 1350, 1200, 1100,
       fill="#f8f8f8", border_color=C["gray"], border_width=2)

    zone_header("② RETAIL PRICE CHECK", ox - 50, oy - 1650, 450)
    tx("Browser automation finds live retail prices — $0 cost",
       ox - 50, oy - 1590, 12, C["mid_gray"], 450)

    # Retailer cards (larger, more detail)
    # Walmart
    wm = colored_rect("<strong>WALMART</strong>", ox - 350, oy - 1430, 260, 65, C["blue"], font_size=16)
    st("Search via SerpAPI\n250 free searches/mo\nUPC-first, then title\nMost reliable source", ox - 350, oy - 1310, "light_yellow", 230)
    sh("SerpAPI", "round_rectangle", ox - 350, oy - 1210, 100, 35,
       fill=C["light_blue"], text_color=C["dark"], border_color=C["light_blue"], font_size=10, border_width=2)

    # Target
    tg = colored_rect("<strong>TARGET</strong>", ox, oy - 1430, 260, 65, C["red"], font_size=16)
    st("Playwright browser\nSearch by TITLE only\n(UPC returns no match)\nWorks consistently", ox, oy - 1310, "light_yellow", 230)
    sh("Playwright", "round_rectangle", ox, oy - 1210, 120, 35,
       fill="#ffcccc", text_color=C["dark"], border_color="#ffcccc", font_size=10, border_width=2)

    # Walgreens
    wg = colored_rect("<strong>WALGREENS</strong>", ox + 350, oy - 1430, 260, 65, C["green"], font_size=16)
    st("Playwright browser\nSearch by product name\nGood for health items\nPharmacy brands", ox + 350, oy - 1310, "light_yellow", 230)
    sh("Playwright", "round_rectangle", ox + 350, oy - 1210, 120, 35,
       fill="#ccf5e6", text_color=C["dark"], border_color="#ccf5e6", font_size=10, border_width=2)

    # Warning callout
    callout("⚠ CVS is fully blocked.\nWalmart needs SerpAPI key.\nTarget: name search ONLY.",
            ox - 50, oy - 1120, 300, 70, "#fff0f0")

    # Arrow from data collection to retail check
    tx("→ → →", ox - 850, oy - 1100, 24, C["light_gray"], 200)
    tx("For each product,\ncheck all 3 retailers", ox - 850, oy - 1050, 10, C["mid_gray"], 200)

    # ══════════════════════════════════════════════════════════════
    # ZONE C (Top-Right): DECISION ENGINE
    # ══════════════════════════════════════════════════════════════
    sh("", "round_rectangle", ox + 1350, oy - 1350, 1100, 1100,
       fill="#f8f8f8", border_color=C["gray"], border_width=2)

    zone_header("③ DECISION ENGINE", ox + 1350, oy - 1650, 400)
    tx("Every product gets a machine-calculated verdict",
       ox + 1350, oy - 1590, 12, C["mid_gray"], 400)

    # Decision diamond (larger)
    d1 = decision("Retail <\nAmazon\nprice?", ox + 1350, oy - 1400, 160)

    # Yes path
    yes_id = colored_rect("<strong>YES</strong><br>Run FBA Calculator", ox + 1600, oy - 1400, 240, 70, C["green"], font_size=14)
    cn(d1, yes_id, C["green"])

    # No path
    no_id = colored_rect("<strong>NO</strong><br>Skip — No margin", ox + 1350, oy - 1200, 200, 60, C["red"], font_size=13)
    cn(d1, no_id, C["red"])
    tx("~70% of products\nget eliminated here", ox + 1350, oy - 1120, 10, C["mid_gray"], 200)

    # FBA Fee Waterfall (compact)
    sub_header("FBA Fee Waterfall", ox + 1350, oy - 1050, 350)

    fees = [
        ("Referral Fee 15%", "-$4.20", C["red"]),
        ("FBA Fulfillment", "-$3.68", "#d63031"),
        ("Inbound Shipping", "-$0.55", "#e17055"),
        ("Storage + Returns", "-$1.15", "#e17055"),
    ]
    for i, (label, amount, color) in enumerate(fees):
        y = oy - 970 + i * 60
        colored_rect(f"{label}  <strong>{amount}</strong>",
                     ox + 1350, y, 350, 45, color, font_size=11)

    colored_rect("Profit: <strong>$7.24/unit</strong>  |  ROI: <strong>63%</strong>",
                 ox + 1350, oy - 710, 380, 55, C["green"], font_size=14)

    # Second decision diamond
    d2 = decision("ROI >\n20%?", ox + 1350, oy - 600, 130)
    cn(yes_id, d2, C["dark"], line_type="straight")

    # Verdict shapes
    buy_v = colored_rect("<strong>BUY ✓</strong>", ox + 1180, oy - 470, 140, 70, C["green"], font_size=20)
    maybe_v = colored_rect("<strong>MAYBE</strong>", ox + 1350, oy - 470, 140, 70, C["warm_orange"],
                           text_color=C["dark"], font_size=20)
    skip_v = colored_rect("<strong>SKIP ✗</strong>", ox + 1520, oy - 470, 140, 70, C["red"], font_size=20)
    cn(d2, buy_v, C["green"])
    cn(d2, maybe_v, C["warm_orange"])
    cn(d2, skip_v, C["red"])

    # ══════════════════════════════════════════════════════════════
    # ZONE D (Bottom-Left): VERDICT CRITERIA DEEP DIVE
    # ══════════════════════════════════════════════════════════════
    sh("", "round_rectangle", ox - 1550, oy + 250, 1400, 1200,
       fill="#f8f8f8", border_color=C["gray"], border_width=2)

    zone_header("④ VERDICT CRITERIA", ox - 1550, oy + 50, 400)
    tx("What separates a winning product from a money pit",
       ox - 1550, oy + 110, 12, C["mid_gray"], 400)

    # BUY column
    colored_rect("<strong>BUY</strong>", ox - 1800, oy + 200, 200, 80, C["green"], font_size=24)
    buy_criteria = [
        "✓ ROI > 20% after ALL fees",
        "✓ BSR under 50,000 (stable)",
        "✓ Less than 5 FBA sellers",
        "✓ Price flat for 6+ months",
        "✓ National brand (not PL)",
        "✓ Available at real retailers",
    ]
    for i, c in enumerate(buy_criteria):
        tx(c, ox - 1800, oy + 280 + i * 35, 12, C["green"], 250, "left")

    st("This is the ONLY verdict\nthat means \"spend money.\"\n\nEverything else = pass.\nNo exceptions. Ever.",
       ox - 1800, oy + 520, "yellow", 250)

    # MAYBE column
    colored_rect("<strong>MAYBE</strong>", ox - 1500, oy + 200, 200, 80, C["warm_orange"],
                 text_color=C["dark"], font_size=24)
    maybe_criteria = [
        "~ ROI 10-20%",
        "~ BSR 50K-100K",
        "~ 5-7 FBA sellers",
        "~ Price slightly declining",
        "~ Needs manual review",
    ]
    for i, c in enumerate(maybe_criteria):
        tx(c, ox - 1500, oy + 280 + i * 35, 12, C["warm_orange"], 250, "left")

    callout("Most beginners buy\n'MAYBE' products. That's\nhow they lose money.\nDiscipline = only green.",
            ox - 1500, oy + 520, 260, 90, "#fff3e0")

    # SKIP column
    colored_rect("<strong>SKIP</strong>", ox - 1200, oy + 200, 200, 80, C["red"], font_size=24)
    skip_criteria = [
        "✗ ROI < 10%",
        "✗ BSR > 100K or volatile",
        "✗ 8+ sellers or rising",
        "✗ Price declining trend",
        "✗ Private label brand",
    ]
    for i, c in enumerate(skip_criteria):
        tx(c, ox - 1200, oy + 280 + i * 35, 12, C["red"], 250, "left")

    st("These products look\ntempting on the surface.\nThat's the trap.\n\n$16 spread ≠ $16 profit",
       ox - 1200, oy + 520, "gray", 250)

    # Warning callout at bottom of zone
    callout("⚠ COMMON MISTAKE: Buying based\non Amazon price minus buy price.\nThat ignores $9+ in fees per unit.\nThe pipeline catches this automatically.",
            ox - 1550, oy + 720, 500, 80, "#ffe0e0")

    # ══════════════════════════════════════════════════════════════
    # ZONE E (Bottom-Center): REAL PRODUCT WALKTHROUGH
    # ══════════════════════════════════════════════════════════════
    sh("", "round_rectangle", ox - 50, oy + 250, 1200, 1550,
       fill="#fffff0", border_color=C["warm_orange"], border_width=2)

    zone_header("⑤ REAL EXAMPLE WALKTHROUGH", ox - 50, oy + 50, 500)
    tx("Actual product traced through the entire pipeline — real numbers",
       ox - 50, oy + 110, 12, C["mid_gray"], 500)

    # Product identity card
    colored_rect("<strong>Clorox Disinfecting Wipes, 75ct</strong><br>ASIN: B07NPDPK3N  |  Health & Household",
                 ox - 50, oy + 230, 500, 70, C["blue"], font_size=13)

    # Step-by-step trace
    st("STEP 1: KEEPA FINDS IT\n\n• Top 200 in Health category\n• BSR: 8,432 (stable 8 months)\n• Rank: #47 in category\n• Keepa flags: all green",
       ox - 300, oy + 380, "light_yellow", 280)

    st("STEP 2: DATA PULL\n\n• Amazon price: $26.99\n• FBA sellers: 3 (stable)\n• No new sellers in 60 days\n• Brand: Clorox (national ✓)\n• Weight: 1.3 lbs",
       ox + 200, oy + 380, "light_yellow", 280)

    st("STEP 3: RETAIL CHECK\n\n• Walmart: $11.47 ← BEST\n• Target: $12.99\n• Walgreens: $13.49\n\nBuy at: Walmart",
       ox - 300, oy + 620, "light_yellow", 280)

    st("STEP 4: FEE CALCULATION\n\n• Buy: $11.47\n• Sell: $26.99 (spread: $15.52)\n• Referral: -$4.05\n• FBA: -$3.68\n• Ship+Storage: -$0.90\n• Returns: -$0.65\n• NET: $7.24/unit",
       ox + 200, oy + 620, "light_yellow", 280)

    # Verdict banner
    colored_rect("VERDICT: <strong>BUY ✓</strong>  |  ROI: 63%  |  $7.24 profit/unit",
                 ox - 50, oy + 850, 500, 65, C["green"], font_size=16)

    # Comparison callout
    callout("If you checked this manually:\n• 25 min to find the product\n• 10 min to check 3 stores\n• 5 min on FBA calculator\n= 40 minutes for ONE product\n\nThe pipeline: 2.4 seconds.",
            ox - 50, oy + 990, 380, 120, C["light_yellow"])

    # Buy link emphasis
    colored_rect("Direct buy link generated → walmart.com/product/...",
                 ox - 50, oy + 1140, 450, 45, C["blue"], font_size=12)
    tx("Every winner includes a clickable link straight to the product page.",
       ox - 50, oy + 1190, 10, C["mid_gray"], 450)

    # ══════════════════════════════════════════════════════════════
    # ZONE F (Bottom-Right): OUTPUT + METRICS
    # ══════════════════════════════════════════════════════════════
    sh("", "round_rectangle", ox + 1350, oy + 250, 1100, 1200,
       fill="#f8f8f8", border_color=C["gray"], border_width=2)

    zone_header("⑥ OUTPUT & METRICS", ox + 1350, oy + 50, 400)
    tx("What you get at the end of every scan",
       ox + 1350, oy + 110, 12, C["mid_gray"], 400)

    # Metric badges (2x3 grid)
    metric("200", "Products\nScanned", ox + 1100, oy + 250, C["blue"])
    metric("10-15", "Pass All\nFilters", ox + 1300, oy + 250, C["green"])
    metric("8 min", "Total\nReview Time", ox + 1500, oy + 250, C["purple"])
    metric("$0.50", "Cost Per\n200 Products", ox + 1100, oy + 430, C["orange"])
    metric("63%", "Average\nWinner ROI", ox + 1300, oy + 430, C["lime"])
    metric("$7+", "Avg Profit\nPer Unit", ox + 1500, oy + 430, C["green"])

    # What's included in output
    sub_header("Every Winner Includes:", ox + 1350, oy + 580, 400)
    output_items = [
        "✓ Product name + ASIN + image",
        "✓ Amazon price + BSR + seller count",
        "✓ Best retail price + store name",
        "✓ Complete fee breakdown (5 fees)",
        "✓ Net profit per unit + ROI %",
        "✓ Direct buy link to retailer",
        "✓ BUY / MAYBE / SKIP verdict",
        "✓ Risk notes (if any flags)",
    ]
    for i, item in enumerate(output_items):
        tx(item, ox + 1350, oy + 640 + i * 35, 12, C["dark"], 400, "left")

    callout("You spend 8 minutes\nreviewing 10-15 winners.\nNot 6 hours browsing\n200 products manually.",
            ox + 1350, oy + 960, 350, 80)

    # Token cost breakdown
    sub_header("Token Costs (Keepa)", ox + 1350, oy + 1100, 350)
    costs = [
        ("Bestsellers pull", "1 token", C["lime"]),
        ("Product batch (200)", "200 tokens", C["warm_orange"]),
        ("Retail check", "FREE", C["green"]),
        ("Total per scan", "~201 tokens", C["blue"]),
    ]
    for i, (label, cost, color) in enumerate(costs):
        x = ox + 1150 + (i % 2) * 250
        y = oy + 1170 + (i // 2) * 55
        sh(f"{label}: <strong>{cost}</strong>", "round_rectangle",
           x, y, 220, 40, fill=color, text_color=C["white"] if color != C["warm_orange"] else C["dark"],
           border_color=color, font_size=10, border_width=2)

    # ══════════════════════════════════════════════════════════════
    # BOTTOM SUMMARY BAR (full width)
    # ══════════════════════════════════════════════════════════════
    colored_rect(
        "<strong>200 products scanned  →  5 filters applied  →  10-15 winners  →  8 min review  →  Buy links + full math  →  Send to FBA</strong>",
        ox, oy + 1500, 2800, 70, C["dark"], font_size=16)

    st("This isn't a tool.\nIt's a system.\n\nIt runs whether you're\nthere or not. It doesn't\nget tired. It doesn't\nskip fees. It doesn't\nguess.\n\nYou just review the winners.",
       ox - 800, oy + 1500, "yellow", 320)

    st("What takes a manual seller\n6 hours of browsing tabs,\nthe pipeline does in under\n5 minutes — with better\naccuracy, zero emotion,\nand every fee calculated\nto the penny.",
       ox + 800, oy + 1500, "yellow", 320)

    # Cross-zone reference arrows (text-based since we can't easily connect across zones)
    tx("←── feeds into ──→", ox - 800, oy, 12, C["light_gray"], 200)
    tx("←── feeds into ──→", ox + 800, oy, 12, C["light_gray"], 200)

    print("  Done!")


def build_frame_2():
    """Why 95% of Amazon Sellers Fail — 2-column comparison"""
    print("\n[Frame 2] Why 95% of Amazon Sellers Fail")
    ox, oy = FRAME_POSITIONS[2]
    frame("Why 95% of Amazon Sellers Fail", ox, oy, 2800, 2200)

    # Section headers
    zone_header("What Most Sellers Do", ox - 550, oy - 900, 450)
    zone_header("What Profitable Sellers Do", ox + 550, oy - 900, 450)

    # Wrong path (left — red accent)
    wrong = [
        ("Start on Amazon", "Same lists as 10,000 other sellers"),
        ("Find 'good' product", "Looks profitable at surface level"),
        ("Buy 200 units", "All-in on one product, no diversification"),
        ("12 sellers appear", "Everyone found the same product"),
        ("Price drops $4", "Race to the bottom begins"),
        ("Break even or lose", "Fees eat what's left of margin"),
        ("Search again", "Back to square one, no system"),
        ("QUIT", "80% stop here within 6 months"),
    ]
    wrong_ids = []
    for i, (label, desc) in enumerate(wrong):
        y = oy - 750 + i * 180
        fill = C["red"] if i == 7 else C["white"]
        tc = C["white"] if i == 7 else C["dark"]
        bc = C["red"]
        nid = sh(f"<strong>{label}</strong>", "rectangle",
                 ox - 550, y, 400, 70, fill=fill, text_color=tc,
                 border_color=bc, font_size=16, border_width=2)
        wrong_ids.append(nid)
        tx(desc, ox - 550, y + 55, 12, C["mid_gray"], 380)

    for i in range(len(wrong_ids) - 1):
        cn(wrong_ids[i], wrong_ids[i + 1], C["red"], line_type="straight")

    # Right path (right — green accent)
    right = [
        ("Start at Retail Stores", "Products others aren't checking"),
        ("AI pipeline filters", "200 products → 10-15 survivors"),
        ("Verify on Keepa", "Price history, seller count, BSR stability"),
        ("Calculate EVERY fee", "Referral + FBA + shipping + storage + returns"),
        ("Only buy 20%+ ROI", "Real ROI, not fake surface margin"),
        ("Diversify across 3-5", "Never all-in on one product"),
        ("Consistent monthly profit", "System runs whether you're there or not"),
        ("SCALE", "Double capital → double products → double profit"),
    ]
    right_ids = []
    for i, (label, desc) in enumerate(right):
        y = oy - 750 + i * 180
        fill = C["green"] if i == 7 else C["white"]
        tc = C["white"] if i == 7 else C["dark"]
        bc = C["green"]
        nid = sh(f"<strong>{label}</strong>", "rectangle",
                 ox + 550, y, 400, 70, fill=fill, text_color=tc,
                 border_color=bc, font_size=16, border_width=2)
        right_ids.append(nid)
        tx(desc, ox + 550, y + 55, 12, C["mid_gray"], 380)

    for i in range(len(right_ids) - 1):
        cn(right_ids[i], right_ids[i + 1], C["green"], line_type="straight")

    # Center divider sticky
    st("The difference isn't skill.\nIt's system.", ox, oy - 100, "yellow", 280)
    st("Same market.\nSame products.\nDifferent process.\nDifferent outcome.", ox, oy + 200, "yellow", 280)

    print("  Done!")


def build_frame_3():
    """5 Filters Every Product Must Pass — Funnel + annotations"""
    print("\n[Frame 3] The 5 Product Filters")
    ox, oy = FRAME_POSITIONS[3]
    frame("5 Filters Every Product Must Pass", ox, oy, 2800, 2200)

    zone_header("The Sourcing Funnel", ox - 200, oy - 900, 400)

    filters = [
        ("200 Products Enter", 700, C["red"], C["white"],
         "Keepa bestsellers in any category.\nPulled automatically by the pipeline."),
        ("Filter 1: Price Stability", 620, "#e74c3c", C["white"],
         "Keepa green line must be FLAT for 6+ months.\nDeclining = margin will shrink before you sell."),
        ("Filter 2: Seller Count", 540, C["orange"], C["dark"],
         "Less than 5 FBA sellers on the listing.\nNo new sellers in the last 60 days."),
        ("Filter 3: BSR Consistency", 460, C["warm_orange"], C["dark"],
         "BSR under 50,000 and STABLE range.\nBouncing BSR = unpredictable daily sales."),
        ("Filter 4: Real ROI > 20%", 380, C["green"], C["white"],
         "After EVERY fee: referral, FBA, shipping,\nstorage, and estimated returns."),
        ("10-15 WINNERS", 300, C["lime"], C["dark"],
         "These are the only products worth your money.\nReview takes ~8 minutes."),
    ]

    bar_ids = []
    for i, (label, width, fill, tc, note) in enumerate(filters):
        y = oy - 700 + i * 220
        nid = colored_rect(f"<strong>{label}</strong>", ox - 200, y, width, 80,
                           fill, text_color=tc, font_size=18 if i < 5 else 22)
        bar_ids.append(nid)
        # Annotation sticky to the right
        st(note, ox + 500, y, "yellow", 300)

    for i in range(len(bar_ids) - 1):
        cn(bar_ids[i], bar_ids[i + 1], C["dark"], line_type="straight")

    # Filter 5 note (separate — retailers)
    zone_header("Filter 5: Available at Retailers", ox - 200, oy + 500, 450)
    st("Walmart", ox - 400, oy + 620, "light_yellow", 150)
    st("Target", ox - 200, oy + 620, "light_yellow", 150)
    st("Walgreens", ox, oy + 620, "light_yellow", 150)
    tx("Product must be purchasable at an authorized national retailer.<br>No eBay. No deal aggregators. Real stores only.",
       ox - 200, oy + 750, 13, C["mid_gray"], 500)

    print("  Done!")


def build_frame_4():
    """Manual vs AI Sourcing — comparison table"""
    print("\n[Frame 4] Manual vs AI Sourcing")
    ox, oy = FRAME_POSITIONS[4]
    frame("Manual Sourcing vs AI Sourcing", ox, oy, 2800, 2000)

    # Headers
    colored_rect("<strong>MANUAL SOURCING</strong>", ox - 500, oy - 800, 400, 70,
                 C["red"], font_size=20)
    zone_header("Category", ox, oy - 800, 200)
    colored_rect("<strong>AI PIPELINE</strong>", ox + 500, oy - 800, 400, 70,
                 C["green"], font_size=20)

    rows = [
        ("Browse Amazon bestsellers", "Method", "Pipeline scans 200 products"),
        ("Open 30 browser tabs", "Process", "Automated batch processing"),
        ("Run FBA calculator by hand", "Fees", "Auto-calculated per product"),
        ("Check Keepa one by one", "Data", "Keepa batch pull (1 call)"),
        ("4-6 hours per session", "Time", "8 minutes to review"),
        ("Find 0-2 products", "Output", "Find 10-15 products"),
        ("Same products as everyone", "Edge", "Products others miss"),
        ("Burnout → Quit", "Outcome", "Consistent → Scale"),
    ]

    for i, (manual, category, ai) in enumerate(rows):
        y = oy - 650 + i * 150
        bg = C["white"] if i % 2 == 0 else C["off_white"]
        # Manual side (red text)
        sh(manual, "rectangle", ox - 500, y, 400, 80,
           fill=bg, text_color=C["red"], border_color=C["gray"],
           font_size=14, border_width=2)
        # Category (center)
        sh(f"<strong>{category}</strong>", "rectangle", ox, y, 200, 80,
           fill=bg, text_color=C["dark"], border_color=C["gray"],
           font_size=14, border_width=2)
        # AI side (green text)
        sh(ai, "rectangle", ox + 500, y, 400, 80,
           fill=bg, text_color=C["green"], border_color=C["gray"],
           font_size=14, border_width=2)

    # Bottom sticky
    st("Same goal. Different system.\nDifferent outcome.", ox, oy + 650, "yellow", 350)

    print("  Done!")


def build_frame_5():
    """$8K → $8K/mo Scaling Map — Timeline"""
    print("\n[Frame 5] $8K → $8K/mo Scaling Map")
    ox, oy = FRAME_POSITIONS[5]
    frame("$8K Starting Capital → $8K/Month in 90 Days", ox, oy, 3200, 2000)

    zone_header("The 90-Day Scaling Timeline", ox, oy - 850, 500)

    phases = [
        ("WEEK 1", "Setup", C["blue"],
         "Seller Central account\nKeepa subscription ($50)\nCapital split:\n• $2,500 products\n• $500 tools\n• $1,000 restock buffer\n• $4,000 safety net",
         "Don't spend the safety net.\nIt's there for mistakes."),
        ("WEEK 2-3", "First Products", C["purple"],
         "Pipeline scans categories\n14 products pass filters\nBuy 3 products (48 units)\nTotal investment: $576\nShip to FBA warehouse",
         "Start with 3 products,\nnot 1. Diversify risk."),
        ("WEEK 3-4", "First Sales", C["green"],
         "Inventory checked in (3-7 days)\nFirst sale on Day 15\nSold out in 7 days\nRevenue: $1,190\nProfit: $412 | ROI: 72%",
         "Don't panic during\nthe check-in wait."),
        ("MONTH 2", "Compound", C["purple"],
         "Restock original 3 products\nSource 3 new products\nTotal invested: $2,100\nMonthly profit: $800\n38% monthly return",
         "Reinvest ALL profit.\nDon't withdraw yet."),
        ("MONTH 3", "Scale", C["green"],
         "6-8 products rotating\n$5,000 actively invested\n$2,000/month profit\nReinvest → $8K/mo by month 5",
         "Now you have a system,\nnot a side hustle."),
    ]

    for i, (period, label, color, details, warning) in enumerate(phases):
        x = ox - 1200 + i * 600
        # Timeline marker
        colored_rect(f"<strong>{period}</strong><br>{label}", x, oy - 650, 220, 80,
                     color, font_size=16)
        # Details below
        st(details, x, oy - 400, "light_yellow", 250)
        # Warning/tip in red-ish sticky
        st(warning, x, oy - 50, "gray", 220)

    # Connect timeline markers
    # (can't easily connect by position, using text arrow)
    tx("→ → → → → → → → → → → → → → → → → → →",
       ox, oy - 650, 24, C["light_gray"], 2400)

    # Bottom summary
    st("Not flashy. Not fast.\nConsistent. Scalable.\nThat's how $8K becomes $8K/month.",
       ox, oy + 400, "yellow", 400)

    print("  Done!")


def build_frame_6():
    """The FBA Fee Breakdown — Scenario + Waterfall"""
    print("\n[Frame 6] The FBA Fee Breakdown")
    ox, oy = FRAME_POSITIONS[6]
    frame("The FBA Fee Breakdown — What You Actually Keep", ox, oy, 2800, 2000)

    # ── Left zone: THE SCENARIO ──
    zone_header("The Scenario", ox - 700, oy - 800, 350)

    colored_rect("Buy at Walmart<br><strong>$12.00</strong>",
                 ox - 700, oy - 650, 300, 90, C["blue"], font_size=18)
    colored_rect("Sell on Amazon<br><strong>$28.00</strong>",
                 ox - 700, oy - 500, 300, 90, C["green"], font_size=18)

    st("Most beginners think:\n$28 - $12 = $16 profit!\n\nThat's 133% ROI!\n\nWRONG.",
       ox - 700, oy - 300, "yellow", 280)

    # ── Right zone: THE REALITY ──
    zone_header("The Reality (Fee Waterfall)", ox + 300, oy - 800, 450)

    # Revenue bar
    colored_rect("<strong>$28.00</strong> Revenue", ox + 300, oy - 650, 400, 60,
                 C["green"], font_size=16)

    # Fee deductions (stacked, getting smaller)
    fees = [
        ("Referral Fee (15%)", "-$4.20"),
        ("FBA Fulfillment", "-$4.15"),
        ("Inbound Shipping", "-$0.60"),
        ("Monthly Storage", "-$0.35"),
        ("Returns (~3%)", "-$0.84"),
    ]
    for i, (label, amount) in enumerate(fees):
        y = oy - 550 + i * 80
        colored_rect(f"{label}  <strong>{amount}</strong>",
                     ox + 300, y, 400, 55, C["red"], font_size=14)

    # Result
    colored_rect("<strong>$5.86</strong>  Actual Profit Per Unit",
                 ox + 300, oy - 100, 400, 80, C["green"], font_size=18)

    # ROI comparison
    sh("Real ROI: <strong>49%</strong>", "rectangle",
       ox + 150, oy + 30, 200, 60, fill=C["lime"],
       text_color=C["dark"], border_color=C["lime"], font_size=16)
    sh("NOT 133%", "rectangle",
       ox + 450, oy + 30, 200, 60, fill=C["red"],
       text_color=C["white"], border_color=C["red"], font_size=16)

    # Key takeaway stickies
    st("49% is still GREAT.\nBut you have to know\nit's 49%, not 133%.\n\nThat's the difference\nbetween profit and loss.",
       ox + 300, oy + 200, "yellow", 300)

    st("The pipeline calculates\nEVERY fee automatically.\nYou never see a product\nwithout the real math.",
       ox - 700, oy + 200, "yellow", 280)

    # Bottom
    tx("<strong>Calculate every fee BEFORE you buy. Every single one.</strong>",
       ox, oy + 500, 20, C["dark"], 600)

    print("  Done!")


def build_frame_7():
    """Content Ecosystem — Hub and spoke"""
    print("\n[Frame 7] Content Ecosystem")
    ox, oy = FRAME_POSITIONS[7]
    frame("1 YouTube Video → 15 Pieces of Content", ox, oy, 2800, 2000)

    zone_header("Content Repurposing System", ox, oy - 850, 450)

    # Center hub
    colored_rect("<strong>1 YouTube<br>Video</strong>",
                 ox, oy - 400, 280, 140, C["purple"], font_size=24)

    # Spokes
    spokes = [
        ("3-5 IG Reels", ox - 700, oy - 650, C["pink"], "Clip best moments\nAdd captions\nVertical format"),
        ("2-3 TikToks", ox - 700, oy - 350, "#00bcd4", "Reformat for TikTok\nTrending sounds\nShorter cuts"),
        ("1 YouTube Short", ox - 700, oy - 50, C["red"], "Strongest 60-sec hook\nVertical crop\nDifferent title"),
        ("1 IG Carousel", ox + 700, oy - 650, C["orange"], "Key takeaways as slides\n5-7 slides\nSwipeable format"),
        ("1 Email Newsletter", ox + 700, oy - 350, C["blue"], "Summary + CTA\nLink to full video\nWeekly send"),
        ("3-5 IG Stories", ox + 700, oy - 50, C["green"], "Behind the scenes\nFilming process\nDaily engagement"),
        ("1 Miro Board Reel", ox, oy + 100, C["warm_orange"], "Visual system map\nSide-angle filming\nNik Setting style"),
    ]

    hub_id = colored_rect("", ox, oy - 400, 1, 1, C["white"])  # invisible connector anchor

    for label, x, y, color, note in spokes:
        nid = colored_rect(f"<strong>{label}</strong>", x, y, 220, 70, color, font_size=15)
        st(note, x, y + 80, "light_yellow", 200)
        # We can't easily connect to center shape by ID from colored_rect
        # So we use visual proximity — the layout makes the hub-spoke clear

    st("Film once.\nDistribute everywhere.\nCompound forever.\n\n1 video = 15 content pieces\n= 15 chances to be found",
       ox, oy + 400, "yellow", 350)

    print("  Done!")


def build_frame_8():
    """Keepa Chart Reading Guide — 3-column reference"""
    print("\n[Frame 8] Keepa Chart Reading Guide")
    ox, oy = FRAME_POSITIONS[8]
    frame("How to Read a Keepa Chart in 60 Seconds", ox, oy, 2800, 2000)

    zone_header("Keepa Chart Reading Guide", ox, oy - 850, 450)
    tx("The 3 things you check on every single product. In this order.",
       ox, oy - 780, 14, C["mid_gray"], 500)

    # Column 1: Price (Green Line)
    colored_rect("<strong>GREEN LINE</strong><br>Amazon Price", ox - 700, oy - 650, 350, 80,
                 C["green"], font_size=18)

    signals_1 = [
        ("FLAT 6+ months", "STABLE — Buy signal", C["green"], C["white"]),
        ("Declining steadily", "DANGER — Margin shrinking", C["red"], C["white"]),
        ("Spiking up and down", "VOLATILE — Can't predict", C["warm_orange"], C["dark"]),
    ]
    for i, (label, desc, fill, tc) in enumerate(signals_1):
        y = oy - 500 + i * 140
        colored_rect(f"<strong>{label}</strong>", ox - 700, y, 320, 60, fill, tc, font_size=14)
        tx(desc, ox - 700, y + 50, 12, C["mid_gray"], 300)

    st("Quick test: Would you\nbet $500 that the price\nstays the same next month?",
       ox - 700, oy + 50, "yellow", 250)

    # Column 2: Seller Count (Triangles)
    colored_rect("<strong>TRIANGLES</strong><br>Seller Count", ox, oy - 650, 350, 80,
                 C["purple"], font_size=18)

    signals_2 = [
        ("3-5 sellers, stable", "SAFE — Good Buy Box rotation", C["green"], C["white"]),
        ("8+ sellers, rising", "RACE — Price war incoming", C["red"], C["white"]),
        ("1 seller only", "AMAZON OWNS IT — Can't win", C["warm_orange"], C["dark"]),
    ]
    for i, (label, desc, fill, tc) in enumerate(signals_2):
        y = oy - 500 + i * 140
        colored_rect(f"<strong>{label}</strong>", ox, y, 320, 60, fill, tc, font_size=14)
        tx(desc, ox, y + 50, 12, C["mid_gray"], 300)

    st("Quick test: Are new\nsellers showing up?\nIf yes, expect price drops.",
       ox, oy + 50, "yellow", 250)

    # Column 3: BSR (Sales Rank)
    colored_rect("<strong>BSR</strong><br>Sales Rank", ox + 700, oy - 650, 350, 80,
                 C["blue"], font_size=18)

    signals_3 = [
        ("Under 20K, stable", "DAILY SALES — Predictable", C["green"], C["white"]),
        ("Bouncing 5K-80K", "RANDOM — Some days 20, some 0", C["warm_orange"], C["dark"]),
        ("Over 100K", "SLOW — Might sit for months", C["red"], C["white"]),
    ]
    for i, (label, desc, fill, tc) in enumerate(signals_3):
        y = oy - 500 + i * 140
        colored_rect(f"<strong>{label}</strong>", ox + 700, y, 320, 60, fill, tc, font_size=14)
        tx(desc, ox + 700, y + 50, 12, C["mid_gray"], 300)

    st("Quick test: Is the BSR\nconsistently under 50K?\nIf not, demand is unreliable.",
       ox + 700, oy + 50, "yellow", 250)

    # Bottom summary
    st("30 minutes to learn this.\nSaves you thousands.\n\nEvery product. Every time.\nNo exceptions.",
       ox, oy + 400, "yellow", 400)

    print("  Done!")


# ─── CLI ──────────────────────────────────────────────────────────────────────

BUILDERS = {
    "1": build_frame_1, "2": build_frame_2, "3": build_frame_3,
    "4": build_frame_4, "5": build_frame_5, "6": build_frame_6,
    "7": build_frame_7, "8": build_frame_8,
}

FRAME_NAMES = {
    "1": "The AI Sourcing Pipeline",
    "2": "Why 95% of Amazon Sellers Fail",
    "3": "5 Filters Every Product Must Pass",
    "4": "Manual Sourcing vs AI Sourcing",
    "5": "$8K → $8K/mo Scaling Map",
    "6": "The FBA Fee Breakdown",
    "7": "1 YouTube Video → 15 Pieces of Content",
    "8": "Keepa Chart Reading Guide",
}


def test_connection():
    print("Testing Miro API connection...")
    try:
        resp = requests.get(f"{BASE_URL}/boards/{BOARD_ID}", headers=HEADERS)
    except Exception as e:
        print(f"  FAILED: request error: {e}")
        return False
    if resp.status_code == 200:
        print(f"  Connected to: {resp.json()['name']}")
        print(f"  URL: {BOARD_URL}")
        return True
    print(f"  FAILED: {resp.status_code}")
    return False


def main():
    parser = argparse.ArgumentParser(description="Build Miro frames (Nik Setting style)")
    parser.add_argument("--frame", type=str, help="Frame 1-8 or 'all'")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    if not MIRO_API_KEY:
        print("ERROR: MIRO_API_KEY not found in .env")
        sys.exit(1)

    if args.test:
        return test_connection()
    if args.list:
        print(f"Frames on: {BOARD_URL}")
        for n, name in FRAME_NAMES.items():
            print(f"  {n}. {name}")
        return

    if not args.frame:
        return parser.print_help()

    if args.frame == "all":
        print(f"Building all 8 frames on: {BOARD_URL}\n")
        for num, builder in BUILDERS.items():
            builder()
        print(f"\nAll done! Open: {BOARD_URL}")
    elif args.frame in BUILDERS:
        print(f"Board: {BOARD_URL}")
        BUILDERS[args.frame]()
        print(f"\nDone! Open: {BOARD_URL}")
    else:
        print(f"Unknown: {args.frame}. Use 1-8 or 'all'.")


if __name__ == "__main__":
    main()

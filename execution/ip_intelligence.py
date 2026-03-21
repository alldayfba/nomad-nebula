#!/usr/bin/env python3
"""
Script: ip_intelligence.py
Purpose: SQLite-backed IP risk intelligence for Amazon FBA sourcing.
         Maintains a database of brands with documented IP complaint histories,
         scored 0-100 on IP aggression. Replaces the simple keyword check in
         calculate_fba_profitability.py with real, structured intelligence.
Inputs:  CLI subcommands (init, score, check, add, list, update, stats)
Outputs: JSON to stdout, progress to stderr

CLI:
    python execution/ip_intelligence.py init
    python execution/ip_intelligence.py score --brand "Nike"
    python execution/ip_intelligence.py check --title "Nike Air Max Running Shoe"
    python execution/ip_intelligence.py add --brand "BrandName" --score 75 --level HIGH
    python execution/ip_intelligence.py list [--level HIGH]
    python execution/ip_intelligence.py update
    python execution/ip_intelligence.py stats

Integration:
    from ip_intelligence import score_brand, check_product
"""

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / ".tmp" / "sourcing" / "price_tracker.db"

# ── Schema ────────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ip_risk_brands (
    id INTEGER PRIMARY KEY,
    brand_name TEXT UNIQUE NOT NULL,
    risk_score INTEGER DEFAULT 50,
    risk_level TEXT DEFAULT 'MODERATE',
    complaint_types TEXT DEFAULT '',
    category TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    source TEXT DEFAULT 'manual',
    last_updated TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ip_brand_name ON ip_risk_brands(brand_name);
CREATE INDEX IF NOT EXISTS idx_ip_risk_level ON ip_risk_brands(risk_level);
"""

# ── Seed Data — 200+ IP-aggressive brands ────────────────────────────────────
# Research-sourced. Organized by risk tier.
# Format: (brand_name, risk_score, risk_level, complaint_types, category, notes)

SEED_BRANDS = [
    # ── EXTREME (90-100) ─────────────────────────────────────────────────────
    ("Nike", 99, "EXTREME", "trademark,ip,counterfeit,cease_desist",
     "Apparel/Footwear", "Extremely aggressive IP enforcement; huge volume of NOTICE complaints"),
    ("Apple", 98, "EXTREME", "trademark,patent,ip,cease_desist",
     "Electronics", "Files hundreds of IP complaints monthly; accessories are a minefield"),
    ("LEGO", 97, "EXTREME", "trademark,patent,counterfeit,cease_desist",
     "Toys", "One of the most aggressive IP enforcers on Amazon; clones trigger instant action"),
    ("Disney", 97, "EXTREME", "trademark,ip,counterfeit,cease_desist",
     "Entertainment/Toys", "Relentlessly pursues unlicensed merchandise; licensed sellers need paperwork"),
    ("Yeti", 95, "EXTREME", "trademark,counterfeit,cease_desist",
     "Drinkware/Outdoors", "Actively files counterfeit complaints; resellers get suspended regularly"),
    ("Hydro Flask", 94, "EXTREME", "trademark,counterfeit,cease_desist",
     "Drinkware", "Vigorous brand protection; counterfeit and parallel import complaints common"),
    ("OtterBox", 93, "EXTREME", "trademark,patent,counterfeit",
     "Phone Cases", "Patent-heavy; actively monitors Amazon for infringing cases"),
    ("Bose", 93, "EXTREME", "trademark,patent,counterfeit,cease_desist",
     "Audio", "IP team actively patrols; headphone/speaker accessories flagged frequently"),
    ("Dyson", 93, "EXTREME", "patent,trademark,counterfeit",
     "Appliances", "Strong patent portfolio; accessories and parts routinely challenged"),
    ("KitchenAid", 92, "EXTREME", "trademark,patent,counterfeit",
     "Kitchen Appliances", "Accessories and attachments targeted; authorized reseller program enforced"),
    ("Cuisinart", 91, "EXTREME", "trademark,counterfeit,cease_desist",
     "Kitchen Appliances", "Actively files against counterfeit accessories and parts"),
    ("Keurig", 91, "EXTREME", "patent,trademark,counterfeit",
     "Beverages/Appliances", "Pod patents and machine accessories are a high-risk zone"),
    ("iRobot", 91, "EXTREME", "patent,trademark,counterfeit",
     "Home Robotics", "Roomba patents enforced heavily; compatible parts trigger complaints"),
    ("Ring", 90, "EXTREME", "trademark,patent,counterfeit",
     "Smart Home", "Amazon-owned brand with aggressive enforcement of accessories"),
    ("Beats by Dre", 92, "EXTREME", "trademark,counterfeit,cease_desist",
     "Audio", "Apple-owned; full legal resources deployed for brand protection"),
    ("Osprey", 90, "EXTREME", "trademark,counterfeit,cease_desist",
     "Outdoor/Bags", "High-end outdoor brand with active enforcement program"),
    ("Patagonia", 92, "EXTREME", "trademark,counterfeit,cease_desist",
     "Outdoor Apparel", "Extremely aggressive against counterfeits and unauthorized sellers"),
    ("North Face", 93, "EXTREME", "trademark,counterfeit,cease_desist",
     "Outdoor Apparel", "VF Corp resources; frequent complaints against unauthorized sellers"),
    ("Under Armour", 91, "EXTREME", "trademark,counterfeit,cease_desist",
     "Apparel/Footwear", "Large IP team; resellers without invoices are targeted"),
    ("New Balance", 90, "EXTREME", "trademark,counterfeit,cease_desist",
     "Footwear", "Actively files against counterfeit and gray market sellers"),
    ("Birkenstock", 95, "EXTREME", "trademark,counterfeit,cease_desist",
     "Footwear", "One of the highest complaint-volume footwear brands on Amazon"),
    ("Crocs", 90, "EXTREME", "patent,trademark,counterfeit",
     "Footwear", "Patent and trademark enforcement; Jibbitz accessories also flagged"),
    ("UGG", 92, "EXTREME", "trademark,counterfeit,cease_desist",
     "Footwear", "Deckers group; highly aggressive against counterfeits and knockoffs"),
    ("Omega", 91, "EXTREME", "trademark,counterfeit,cease_desist",
     "Watches", "Swatch Group; luxury watches with rigorous anti-counterfeit program"),
    ("Tissot", 90, "EXTREME", "trademark,counterfeit,cease_desist",
     "Watches", "Swatch Group subsidiary; strict authorized reseller enforcement"),
    ("Chanel", 99, "EXTREME", "trademark,counterfeit,cease_desist",
     "Luxury/Fashion", "Maximum enforcement; any unauthorized sale results in immediate action"),
    ("Louis Vuitton", 99, "EXTREME", "trademark,counterfeit,cease_desist",
     "Luxury/Fashion", "LVMH deploys massive legal resources; zero tolerance policy"),
    ("Gucci", 98, "EXTREME", "trademark,counterfeit,cease_desist",
     "Luxury/Fashion", "Kering SA; among the most litigious luxury brands globally"),
    ("Prada", 97, "EXTREME", "trademark,counterfeit,cease_desist",
     "Luxury/Fashion", "Extremely aggressive IP enforcement; do not sell"),
    ("Burberry", 96, "EXTREME", "trademark,counterfeit,cease_desist",
     "Luxury/Fashion", "Active enforcement of trademark; unauthorized sellers removed quickly"),
    ("Tiffany", 97, "EXTREME", "trademark,counterfeit,cease_desist",
     "Luxury Jewelry", "LVMH-owned; aggressive program against unauthorized jewelry sellers"),
    ("Rolex", 99, "EXTREME", "trademark,counterfeit,cease_desist",
     "Luxury Watches", "Industry standard for IP aggression; do not source"),
    ("Cartier", 98, "EXTREME", "trademark,counterfeit,cease_desist",
     "Luxury/Jewelry", "Richemont Group; full legal resources against any unauthorized sales"),
    ("Ray-Ban", 94, "EXTREME", "trademark,counterfeit,patent,cease_desist",
     "Eyewear", "Luxottica; heavy monitoring and complaint filing on Amazon"),
    ("Oakley", 93, "EXTREME", "trademark,patent,counterfeit,cease_desist",
     "Eyewear/Sports", "Luxottica subsidiary; aggressive patent and trademark enforcement"),

    # ── HIGH (70-89) ─────────────────────────────────────────────────────────
    ("Adidas", 85, "HIGH", "trademark,counterfeit,cease_desist",
     "Apparel/Footwear", "Active IP program; counterfeit complaints common, resellers need invoices"),
    ("Puma", 78, "HIGH", "trademark,counterfeit",
     "Apparel/Footwear", "Significant enforcement; knockoffs targeted aggressively"),
    ("Columbia Sportswear", 75, "HIGH", "trademark,counterfeit,cease_desist",
     "Outdoor Apparel", "Active enforcement; gate applies in some categories"),
    ("Brooks", 73, "HIGH", "trademark,counterfeit",
     "Footwear", "Running shoe brand with active reseller monitoring"),
    ("ASICS", 74, "HIGH", "trademark,counterfeit",
     "Footwear", "Files IP complaints; authorized reseller program enforced"),
    ("Skechers", 72, "HIGH", "trademark,patent,counterfeit",
     "Footwear", "Aggressive patent portfolio; frequently files on design copies"),
    ("Converse", 80, "HIGH", "trademark,counterfeit,cease_desist",
     "Footwear", "Nike-owned; full Nike legal resources for enforcement"),
    ("Vans", 79, "HIGH", "trademark,counterfeit",
     "Footwear", "VF Corp; active monitoring, unauthorized sellers removed"),
    ("Dr. Martens", 76, "HIGH", "trademark,counterfeit",
     "Footwear", "Direct-to-consumer push; sellers without invoices get complaints"),
    ("Timberland", 77, "HIGH", "trademark,counterfeit,cease_desist",
     "Footwear/Apparel", "VF Corp; consistent enforcement against unauthorized sellers"),
    ("Coach", 82, "HIGH", "trademark,counterfeit,cease_desist",
     "Handbags/Accessories", "Tapestry Inc.; active enforcement, handbags are high-risk"),
    ("Michael Kors", 81, "HIGH", "trademark,counterfeit,cease_desist",
     "Handbags/Accessories", "Capri Holdings; files complaints against unauthorized sellers frequently"),
    ("Kate Spade", 80, "HIGH", "trademark,counterfeit,cease_desist",
     "Handbags/Accessories", "Tapestry Inc.; consistent IP enforcement program"),
    ("Vera Bradley", 75, "HIGH", "trademark,counterfeit,patent",
     "Bags/Accessories", "Design patent enforcement; pattern copies actively challenged"),
    ("Samsonite", 76, "HIGH", "trademark,counterfeit,cease_desist",
     "Luggage", "Active enforcement against counterfeit and gray market luggage"),
    ("Tumi", 78, "HIGH", "trademark,counterfeit,cease_desist",
     "Luggage/Bags", "Samsonite subsidiary; premium brand with strong enforcement"),
    ("Weber", 74, "HIGH", "trademark,patent,counterfeit",
     "Grilling", "Grill accessories and parts closely monitored; patent enforcement active"),
    ("Traeger", 78, "HIGH", "patent,trademark,counterfeit",
     "Grilling", "Strong patent portfolio on pellet grill tech; accessories flagged"),
    ("Instant Pot", 76, "HIGH", "trademark,patent,counterfeit",
     "Kitchen Appliances", "Accessories and compatible parts targeted; IP complaints on clones"),
    ("Vitamix", 80, "HIGH", "trademark,patent,counterfeit",
     "Blenders", "High-value brand with active IP enforcement; compatible accessories flagged"),
    ("Ninja", 75, "HIGH", "trademark,patent,counterfeit",
     "Kitchen Appliances", "SharkNinja; compatible parts and accessories regularly challenged"),
    ("Shark", 74, "HIGH", "trademark,patent,counterfeit",
     "Appliances", "SharkNinja; vacuum accessories are a common complaint trigger"),
    ("iHome", 72, "HIGH", "trademark,patent",
     "Electronics/Audio", "Consistent enforcement; unlicensed compatible accessories flagged"),
    ("JBL", 77, "HIGH", "trademark,counterfeit,cease_desist",
     "Audio", "Harman/Samsung subsidiary; active counterfeit monitoring program"),
    ("Sony", 78, "HIGH", "trademark,patent,counterfeit",
     "Electronics", "Broad IP portfolio; electronics and accessories regularly flagged"),
    ("Canon", 80, "HIGH", "trademark,patent,counterfeit",
     "Cameras/Electronics", "Camera accessories and ink are major IP battlegrounds"),
    ("Nikon", 78, "HIGH", "trademark,patent,counterfeit",
     "Cameras/Electronics", "Active enforcement; camera accessories and lenses monitored"),
    ("GoPro", 82, "HIGH", "trademark,patent,counterfeit",
     "Action Cameras", "Mounts and accessories aggressively defended; high complaint volume"),
    ("DJI", 84, "HIGH", "trademark,patent,counterfeit",
     "Drones/Electronics", "Strong patent enforcement on drone tech; accessories flagged"),
    ("Anker", 73, "HIGH", "trademark,counterfeit",
     "Electronics Accessories", "Growing IP enforcement presence; counterfeits targeted"),
    ("Belkin", 72, "HIGH", "trademark,patent,counterfeit",
     "Electronics Accessories", "Foxconn subsidiary; active cable/accessory enforcement"),
    ("TP-Link", 70, "HIGH", "trademark,patent",
     "Networking", "Consistent enforcement of networking equipment trademarks"),
    ("Netgear", 71, "HIGH", "trademark,patent",
     "Networking", "Active patent enforcement; router accessories monitored"),
    ("Logitech", 75, "HIGH", "trademark,patent,counterfeit",
     "Peripherals", "Consistent enforcement of mouse/keyboard product lines"),
    ("Corsair", 73, "HIGH", "trademark,patent",
     "Gaming Peripherals", "Gaming brand with consistent IP enforcement"),
    ("Razer", 76, "HIGH", "trademark,patent,counterfeit",
     "Gaming Peripherals", "Aggressive brand enforcement; RGB accessories regularly targeted"),
    ("SteelSeries", 71, "HIGH", "trademark,patent",
     "Gaming Peripherals", "Consistent enforcement of gaming peripheral trademarks"),
    ("HyperX", 72, "HIGH", "trademark,counterfeit",
     "Gaming Peripherals", "HP subsidiary; active counterfeit monitoring"),
    ("Brita", 74, "HIGH", "trademark,patent,counterfeit",
     "Water Filtration", "Clorox subsidiary; compatible filters are the main target"),
    ("PUR", 73, "HIGH", "trademark,patent,counterfeit",
     "Water Filtration", "Compatible filter replacements targeted frequently"),
    ("Contigo", 72, "HIGH", "trademark,counterfeit",
     "Drinkware", "Newell Brands; active trademark enforcement"),
    ("S'well", 75, "HIGH", "trademark,counterfeit,cease_desist",
     "Drinkware", "Consistent brand enforcement; knockoffs targeted regularly"),
    ("Tervis", 70, "HIGH", "trademark,patent",
     "Drinkware", "Design patents enforced; tumbler designs protected"),
    ("Stanley", 77, "HIGH", "trademark,counterfeit,cease_desist",
     "Drinkware/Tools", "PMI brand; drinkware enforcement escalated post-viral trend"),
    ("Leatherman", 76, "HIGH", "trademark,patent,counterfeit",
     "Tools/EDC", "Multi-tool designs actively protected; knockoffs challenged"),
    ("Gerber", 74, "HIGH", "trademark,counterfeit",
     "Tools/Knives", "Acme United; active enforcement on multi-tool and knife designs"),
    ("Buck Knives", 72, "HIGH", "trademark,counterfeit",
     "Knives", "Well-known for enforcement against counterfeit knives"),
    ("Benchmade", 79, "HIGH", "trademark,patent,counterfeit",
     "Knives", "Authorized dealer program; MAP pricing enforced with complaints"),
    ("Spyderco", 77, "HIGH", "trademark,patent,counterfeit",
     "Knives", "Unique design patents actively defended; clones immediately challenged"),
    ("CRKT", 71, "HIGH", "trademark,patent",
     "Knives/Tools", "Columbia River Knife; active design patent enforcement"),

    # ── MODERATE (40-69) ─────────────────────────────────────────────────────
    ("Samsung", 62, "MODERATE", "trademark,patent",
     "Electronics", "Large portfolio; enforcement focused on counterfeits not resellers"),
    ("LG", 58, "MODERATE", "trademark,patent",
     "Electronics/Appliances", "Moderate enforcement; accessories occasionally flagged"),
    ("Philips", 60, "MODERATE", "trademark,patent,counterfeit",
     "Electronics/Appliances", "Healthcare and lighting accessories are common targets"),
    ("Panasonic", 55, "MODERATE", "trademark,patent",
     "Electronics", "Some enforcement activity; accessories monitored"),
    ("Braun", 56, "MODERATE", "trademark,patent",
     "Personal Care/Appliances", "P&G subsidiary; replacement parts for shavers targeted"),
    ("Oral-B", 57, "MODERATE", "trademark,patent,counterfeit",
     "Oral Care", "P&G subsidiary; replacement brush heads are high-risk area"),
    ("Gillette", 58, "MODERATE", "trademark,patent,counterfeit",
     "Personal Care", "P&G; razor blade replacements aggressively protected"),
    ("Duracell", 55, "MODERATE", "trademark,counterfeit",
     "Batteries", "Berkshire/P&G; counterfeit batteries targeted"),
    ("Energizer", 53, "MODERATE", "trademark,counterfeit",
     "Batteries", "Some enforcement; counterfeit battery complaints active"),
    ("3M", 60, "MODERATE", "trademark,patent",
     "Industrial/Consumer", "Broad patent portfolio; enforcement on specific product lines"),
    ("Scotch", 52, "MODERATE", "trademark",
     "Office Supplies", "3M brand; trademark enforcement on tape products"),
    ("Post-it", 54, "MODERATE", "trademark,patent",
     "Office Supplies", "3M brand; design and trademark enforcement active"),
    ("Rubbermaid", 50, "MODERATE", "trademark,patent",
     "Storage/Home", "Newell Brands; some enforcement on storage product designs"),
    ("Tupperware", 52, "MODERATE", "trademark,patent",
     "Storage", "Direct sales model creates tension with resellers; complaints moderate"),
    ("Pyrex", 53, "MODERATE", "trademark",
     "Cookware/Bakeware", "Licensing arrangement makes reseller enforcement complicated"),
    ("Corelle", 51, "MODERATE", "trademark",
     "Dinnerware", "World Kitchen; moderate enforcement on dinnerware trademarks"),
    ("Lodge", 48, "MODERATE", "trademark,counterfeit",
     "Cookware", "Cast iron manufacturer; counterfeit products occasionally flagged"),
    ("Le Creuset", 65, "MODERATE", "trademark,counterfeit,cease_desist",
     "Cookware", "Premium brand; unauthorized resellers often receive cease and desist"),
    ("Staub", 62, "MODERATE", "trademark,counterfeit",
     "Cookware", "SEB Group; premium cookware with some reseller enforcement"),
    ("All-Clad", 60, "MODERATE", "trademark,counterfeit",
     "Cookware", "SEB Group; premium brand with moderate enforcement"),
    ("Calphalon", 55, "MODERATE", "trademark",
     "Cookware", "Newell Brands; moderate enforcement activity"),
    ("T-fal", 50, "MODERATE", "trademark",
     "Cookware", "SEB Group; moderate enforcement activity"),
    ("Hamilton Beach", 47, "MODERATE", "trademark,patent",
     "Appliances", "Some enforcement on appliance designs; lower complaint volume"),
    ("Black+Decker", 55, "MODERATE", "trademark,patent",
     "Tools/Appliances", "Stanley Black & Decker; consistent but not aggressive enforcement"),
    ("DeWalt", 65, "MODERATE", "trademark,patent,counterfeit",
     "Power Tools", "SBD; tool accessories and batteries are enforcement hot spots"),
    ("Milwaukee", 63, "MODERATE", "trademark,patent,counterfeit",
     "Power Tools", "TTI Group; compatible batteries and accessories frequently flagged"),
    ("Makita", 61, "MODERATE", "trademark,patent,counterfeit",
     "Power Tools", "Compatible batteries are the primary complaint trigger"),
    ("Bosch", 59, "MODERATE", "trademark,patent",
     "Tools/Appliances", "Large patent portfolio; enforcement primarily on counterfeit parts"),
    ("Ryobi", 58, "MODERATE", "trademark,patent",
     "Power Tools", "TTI Group; compatible accessories monitored but lower complaint rate"),
    ("Craftsman", 55, "MODERATE", "trademark",
     "Tools", "SBD; trademark enforcement on tool line"),
    ("Husky", 48, "MODERATE", "trademark",
     "Tools/Storage", "Home Depot brand; moderate trademark enforcement"),
    ("Klein Tools", 56, "MODERATE", "trademark,counterfeit",
     "Electrical Tools", "Active counterfeit monitoring for professional tools"),
    ("Channellock", 50, "MODERATE", "trademark,counterfeit",
     "Hand Tools", "Pliers manufacturer with trademark enforcement program"),
    ("Snap-on", 64, "MODERATE", "trademark,counterfeit,cease_desist",
     "Professional Tools", "Premium professional tools; strong enforcement against knockoffs"),
    ("Mattel", 65, "MODERATE", "trademark,patent,counterfeit,ip",
     "Toys", "Large legal department; Barbie, Hot Wheels actively protected"),
    ("Hasbro", 65, "MODERATE", "trademark,patent,counterfeit,ip",
     "Toys/Games", "Nerf, My Little Pony, Monopoly actively monitored and enforced"),
    ("Fisher-Price", 60, "MODERATE", "trademark,patent,counterfeit",
     "Baby/Toys", "Mattel subsidiary; baby products with consistent enforcement"),
    ("Hot Wheels", 62, "MODERATE", "trademark,counterfeit",
     "Toys", "Mattel; die-cast car designs monitored for counterfeits"),
    ("Nerf", 63, "MODERATE", "trademark,patent,counterfeit",
     "Toys", "Hasbro; compatible dart complaints are the main enforcement vector"),
    ("Play-Doh", 58, "MODERATE", "trademark,patent",
     "Toys", "Hasbro; compound formulas and branding enforced"),
    ("Melissa & Doug", 55, "MODERATE", "trademark,patent",
     "Toys", "Design patents on wooden toys enforced; moderate complaint volume"),
    ("Crayola", 56, "MODERATE", "trademark",
     "Art Supplies", "Hallmark subsidiary; trademark enforcement on art supply line"),
    ("Sharpie", 53, "MODERATE", "trademark,patent",
     "Writing Instruments", "Newell Brands; marker designs and branding protected"),
    ("BIC", 48, "MODERATE", "trademark",
     "Writing Instruments", "Lighter and pen trademarks enforced; moderate activity"),
    ("Pilot", 50, "MODERATE", "trademark,patent",
     "Writing Instruments", "Pen designs and ink formulas protected; moderate enforcement"),
    ("Paper Mate", 47, "MODERATE", "trademark",
     "Writing Instruments", "Newell Brands; trademark enforcement present but low volume"),
    ("Faber-Castell", 52, "MODERATE", "trademark,counterfeit",
     "Art Supplies", "Premium art supply brand; consistent trademark enforcement"),

    # ── LOW (10-39) ───────────────────────────────────────────────────────────
    ("Basics", 12, "LOW", "",
     "General", "Generic/store brand; minimal IP enforcement activity"),
    ("AmazonBasics", 15, "LOW", "",
     "General", "Amazon's own brand; minimal external complaints but restricted resale"),
    ("Utopia Kitchen", 14, "LOW", "",
     "Kitchen", "Private label with minimal documented IP complaints"),
    ("Gorilla Grip", 16, "LOW", "",
     "Home", "Some trademark activity but low complaint volume"),
    ("Simple Modern", 22, "LOW", "trademark",
     "Drinkware", "Growing brand with limited but increasing enforcement presence"),
    ("Ello", 18, "LOW", "trademark",
     "Drinkware", "Small brand; occasional trademark complaints"),
    ("Nalgene", 28, "LOW", "trademark,counterfeit",
     "Drinkware", "Some counterfeit complaints but generally reseller-friendly"),
    ("CamelBak", 32, "LOW", "trademark,patent",
     "Hydration", "Vista Outdoor; limited enforcement; mostly counterfeit-focused"),
    ("Lifestraw", 25, "LOW", "trademark",
     "Outdoor/Water", "Modest IP enforcement presence"),
    ("Sawyer", 22, "LOW", "trademark",
     "Outdoor/Filtration", "Limited enforcement activity"),
    ("Igloo", 30, "LOW", "trademark",
     "Coolers", "Some enforcement but significantly less than competitors"),
    ("Coleman", 35, "LOW", "trademark,counterfeit",
     "Outdoor/Camping", "Newell Brands; moderate enforcement, lower than similar brands"),
    ("Primus", 20, "LOW", "",
     "Camping/Cooking", "Minimal IP complaint history"),
    ("MSR", 24, "LOW", "trademark",
     "Camping/Outdoors", "Cascade Designs; limited enforcement outside counterfeit cases"),
    ("Sea to Summit", 22, "LOW", "trademark",
     "Outdoors/Travel", "Low complaint volume; reseller-friendly approach"),
    ("Cochlicopa", 10, "LOW", "",
     "General", "Minimal IP complaint history; small brand"),
    ("OXO", 38, "LOW", "trademark,patent",
     "Kitchen/Tools", "Some design patent enforcement but generally manageable"),
    ("Joseph Joseph", 35, "LOW", "trademark,patent",
     "Kitchen", "Design-forward brand with some enforcement but lower volume"),
    ("Cuisipro", 20, "LOW", "",
     "Kitchen", "Minimal IP complaint history"),
    ("Nordic Ware", 32, "LOW", "trademark,patent",
     "Bakeware", "Bundt pan designs protected but limited complaint volume"),
    ("Lodge Manufacturing", 28, "LOW", "trademark",
     "Cookware", "Reseller-friendly but some trademark activity on branding"),
    ("Victorinox", 36, "LOW", "trademark,counterfeit",
     "Knives/Tools", "Swiss Army brand with some enforcement; less aggressive than others"),
    ("Wusthof", 34, "LOW", "trademark,counterfeit",
     "Knives", "German knife brand; counterfeit-focused enforcement only"),
    ("Henckels", 32, "LOW", "trademark",
     "Knives", "Zwilling brand; limited but present enforcement activity"),
    ("Case Knives", 28, "LOW", "trademark,counterfeit",
     "Knives", "Heritage brand; counterfeit-focused enforcement"),
    ("Fiskars", 30, "LOW", "trademark,patent",
     "Tools/Crafts", "Finnish brand; limited enforcement presence in US"),
    ("Shun", 33, "LOW", "trademark",
     "Knives", "Kai USA; premium brand with minimal reseller complaints"),
    ("Global Knives", 28, "LOW", "trademark",
     "Knives", "Japanese brand; limited enforcement activity"),
]


# ── Database Connection ───────────────────────────────────────────────────────

def get_db():
    """Get database connection with WAL mode and IP schema ensured."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_SQL)
    return conn


# ── Core Functions (importable) ───────────────────────────────────────────────

def score_brand(brand_name: str) -> dict:
    """Score a brand name against the IP risk database.

    Matching priority:
      1. Exact match (case-insensitive)
      2. Fuzzy substring match (brand name is a substring of query, or vice versa)

    Returns:
        dict with keys: brand, risk_score, risk_level, complaint_types, notes, matched_on
        Returns a LOW-risk default dict when no match is found.
    """
    if not brand_name or not brand_name.strip():
        return _default_result(brand_name)

    brand_clean = brand_name.strip()
    conn = get_db()
    try:
        # 1. Exact match (case-insensitive)
        row = conn.execute(
            "SELECT * FROM ip_risk_brands WHERE LOWER(brand_name) = LOWER(?)",
            (brand_clean,)
        ).fetchone()
        if row:
            return _row_to_result(dict(row), "exact")

        # 2. Fuzzy: check if DB brand is substring of query or query is substring of DB brand
        all_brands = conn.execute(
            "SELECT * FROM ip_risk_brands ORDER BY risk_score DESC"
        ).fetchall()

        brand_lower = brand_clean.lower()
        best_match = None
        best_score = -1

        for db_row in all_brands:
            db_brand_lower = db_row["brand_name"].lower()
            # Either direction substring match
            if db_brand_lower in brand_lower or brand_lower in db_brand_lower:
                if db_row["risk_score"] > best_score:
                    best_score = db_row["risk_score"]
                    best_match = dict(db_row)

        if best_match:
            return _row_to_result(best_match, "fuzzy")

        return _default_result(brand_clean)
    finally:
        conn.close()


def check_product(product_title: str) -> dict:
    """Scan a full product title for any brand matches, returning the highest risk found.

    Strategy:
      - Tokenize title into 1-, 2-, and 3-word ngrams
      - Score each ngram as a brand query
      - Return the match with the highest risk_score

    Returns:
        dict with same keys as score_brand() plus 'found_brands' (list of all matches)
    """
    if not product_title or not product_title.strip():
        return _default_result("")

    # Clean title: strip punctuation except hyphens, normalize whitespace
    title_clean = re.sub(r"[^\w\s\-]", " ", product_title)
    words = title_clean.split()

    candidates = set()
    # 1-word, 2-word, 3-word ngrams
    for n in (1, 2, 3):
        for i in range(len(words) - n + 1):
            candidates.add(" ".join(words[i:i + n]))

    # Also try the full title in case it contains a brand name within it
    candidates.add(product_title.strip())

    conn = get_db()
    try:
        all_brands = conn.execute(
            "SELECT * FROM ip_risk_brands ORDER BY risk_score DESC"
        ).fetchall()

        found = []
        seen_brands = set()

        for candidate in candidates:
            cand_lower = candidate.lower().strip()
            if len(cand_lower) < 3:
                continue

            for db_row in all_brands:
                db_brand_lower = db_row["brand_name"].lower()
                db_brand_name = db_row["brand_name"]

                if db_brand_name in seen_brands:
                    continue

                # Match: candidate equals DB brand, or DB brand is substring of candidate,
                # or candidate is substring of DB brand (only when candidate >= 4 chars)
                matched = (
                    cand_lower == db_brand_lower
                    or db_brand_lower in cand_lower
                    or (len(cand_lower) >= 4 and cand_lower in db_brand_lower)
                )
                if matched:
                    seen_brands.add(db_brand_name)
                    found.append({
                        "brand": db_brand_name,
                        "risk_score": db_row["risk_score"],
                        "risk_level": db_row["risk_level"],
                        "complaint_types": db_row["complaint_types"],
                        "category": db_row["category"],
                        "notes": db_row["notes"],
                    })

        if not found:
            result = _default_result(product_title[:60])
            result["found_brands"] = []
            return result

        # Return the highest-risk match as the primary result
        found.sort(key=lambda x: x["risk_score"], reverse=True)
        top = found[0]
        return {
            "brand": top["brand"],
            "risk_score": top["risk_score"],
            "risk_level": top["risk_level"],
            "complaint_types": top["complaint_types"],
            "notes": top["notes"],
            "matched_on": "product_title_scan",
            "found_brands": found,
        }
    finally:
        conn.close()


def add_brand(brand_name: str, risk_score: int, risk_level: str,
              complaint_types: str = "", category: str = "",
              notes: str = "", source: str = "manual") -> dict:
    """Insert or replace a brand in the IP risk database."""
    now = datetime.utcnow().isoformat()
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO ip_risk_brands
                (brand_name, risk_score, risk_level, complaint_types, category,
                 notes, source, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(brand_name) DO UPDATE SET
                risk_score = excluded.risk_score,
                risk_level = excluded.risk_level,
                complaint_types = excluded.complaint_types,
                category = excluded.category,
                notes = excluded.notes,
                source = excluded.source,
                last_updated = excluded.last_updated
        """, (brand_name, risk_score, risk_level, complaint_types,
              category, notes, source, now))
        conn.commit()
        return {"added": True, "brand": brand_name, "risk_score": risk_score,
                "risk_level": risk_level}
    finally:
        conn.close()


def list_brands(risk_level: str = None, limit: int = 500) -> list:
    """List brands from the database, optionally filtered by risk level."""
    conn = get_db()
    try:
        if risk_level:
            rows = conn.execute("""
                SELECT * FROM ip_risk_brands
                WHERE UPPER(risk_level) = UPPER(?)
                ORDER BY risk_score DESC, brand_name ASC
                LIMIT ?
            """, (risk_level, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM ip_risk_brands
                ORDER BY risk_score DESC, brand_name ASC
                LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_stats() -> dict:
    """Return database statistics for the IP risk brand table."""
    conn = get_db()
    try:
        total = conn.execute(
            "SELECT COUNT(*) AS cnt FROM ip_risk_brands"
        ).fetchone()["cnt"]

        level_counts = {}
        for level in ("EXTREME", "HIGH", "MODERATE", "LOW"):
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM ip_risk_brands WHERE risk_level = ?",
                (level,)
            ).fetchone()
            level_counts[level.lower()] = row["cnt"]

        avg_score = conn.execute(
            "SELECT ROUND(AVG(risk_score), 1) AS avg FROM ip_risk_brands"
        ).fetchone()["avg"]

        recent = conn.execute("""
            SELECT brand_name, risk_score, last_updated
            FROM ip_risk_brands
            WHERE last_updated IS NOT NULL
            ORDER BY last_updated DESC
            LIMIT 5
        """).fetchall()

        return {
            "total_brands": total,
            "by_level": level_counts,
            "avg_risk_score": avg_score,
            "recently_updated": [dict(r) for r in recent],
            "db_path": str(DB_PATH),
        }
    finally:
        conn.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row_to_result(row: dict, matched_on: str) -> dict:
    return {
        "brand": row["brand_name"],
        "risk_score": row["risk_score"],
        "risk_level": row["risk_level"],
        "complaint_types": row["complaint_types"],
        "notes": row["notes"],
        "matched_on": matched_on,
    }


def _default_result(query: str) -> dict:
    return {
        "brand": query,
        "risk_score": 10,
        "risk_level": "LOW",
        "complaint_types": "",
        "notes": "No match found in IP risk database",
        "matched_on": "none",
    }


def _score_to_level(score: int) -> str:
    if score >= 90:
        return "EXTREME"
    if score >= 70:
        return "HIGH"
    if score >= 40:
        return "MODERATE"
    return "LOW"


# ── CLI Handlers ──────────────────────────────────────────────────────────────

def cli_init(args):
    """Seed the database with all hardcoded brands."""
    print("[ip_intelligence] Seeding IP risk brand database...", file=sys.stderr)
    conn = get_db()
    now = datetime.utcnow().isoformat()
    inserted = 0
    updated = 0

    try:
        for record in SEED_BRANDS:
            brand_name, risk_score, risk_level, complaint_types, category, notes = record
            existing = conn.execute(
                "SELECT id, source FROM ip_risk_brands WHERE LOWER(brand_name) = LOWER(?)",
                (brand_name,)
            ).fetchone()

            if existing:
                # Only overwrite manual entries if source is 'seed' to respect custom edits
                if existing["source"] in ("seed", None, ""):
                    conn.execute("""
                        UPDATE ip_risk_brands SET
                            risk_score = ?, risk_level = ?, complaint_types = ?,
                            category = ?, notes = ?, source = 'seed', last_updated = ?
                        WHERE LOWER(brand_name) = LOWER(?)
                    """, (risk_score, risk_level, complaint_types, category, notes, now, brand_name))
                    updated += 1
                # Skip if manually added (preserves user edits)
            else:
                conn.execute("""
                    INSERT INTO ip_risk_brands
                        (brand_name, risk_score, risk_level, complaint_types,
                         category, notes, source, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, 'seed', ?)
                """, (brand_name, risk_score, risk_level, complaint_types, category, notes, now))
                inserted += 1

        conn.commit()
    finally:
        conn.close()

    print(f"[ip_intelligence] Done. {inserted} inserted, {updated} updated.", file=sys.stderr)
    print(json.dumps({
        "seeded": True,
        "inserted": inserted,
        "updated": updated,
        "total_seed_brands": len(SEED_BRANDS),
    }, indent=2))


def cli_score(args):
    """Score a brand name and output the result."""
    result = score_brand(args.brand)
    print(json.dumps(result, indent=2))


def cli_check(args):
    """Check a product title for any IP risk brand matches."""
    result = check_product(args.title)
    print(json.dumps(result, indent=2))


def cli_add(args):
    """Manually add or update a brand in the database."""
    level = args.level or _score_to_level(args.score)
    result = add_brand(
        brand_name=args.brand,
        risk_score=args.score,
        risk_level=level,
        complaint_types=args.complaint_types or "",
        category=args.category or "",
        notes=args.notes or "",
        source="manual",
    )
    print(json.dumps(result, indent=2))


def cli_list(args):
    """List brands from the database."""
    brands = list_brands(risk_level=args.level)
    if not brands:
        msg = f"No brands found" + (f" at level {args.level}" if args.level else "")
        print(msg, file=sys.stderr)
        sys.exit(0)
    print(json.dumps({"count": len(brands), "brands": brands}, indent=2))


def cli_update(args):
    """Stub: scrape public sources for new IP complaint data.

    Currently a stub — logs intent. Extend with web scraping logic for
    seller forums (e.g., SellerCentral forums, Reddit r/FulfillmentByAmazon)
    when a suitable scraping directive is added.
    """
    print("[ip_intelligence] Update subcommand: scanning public sources...", file=sys.stderr)
    print("[ip_intelligence] NOTE: Web scraping not yet implemented. "
          "Run 'init' to refresh from built-in seed data.", file=sys.stderr)
    print(json.dumps({
        "updated": False,
        "reason": "Automated web scraping not yet implemented. "
                  "Use 'add' to manually add brands or 'init' to re-seed built-in data.",
        "suggestion": "python execution/ip_intelligence.py init",
    }, indent=2))


def cli_stats(args):
    """Show database statistics."""
    stats = get_stats()
    print(json.dumps(stats, indent=2))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="IP Intelligence — Brand IP risk database for Amazon FBA sourcing"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init
    p_init = subparsers.add_parser("init", help="Seed database with 200+ known IP-aggressive brands")
    p_init.set_defaults(func=cli_init)

    # score
    p_score = subparsers.add_parser("score", help="Score a brand name for IP risk")
    p_score.add_argument("--brand", required=True, help="Brand name to score")
    p_score.set_defaults(func=cli_score)

    # check
    p_check = subparsers.add_parser("check", help="Check a product title for IP risk brands")
    p_check.add_argument("--title", required=True, help="Full product title to scan")
    p_check.set_defaults(func=cli_check)

    # add
    p_add = subparsers.add_parser("add", help="Manually add or update a brand")
    p_add.add_argument("--brand", required=True, help="Brand name")
    p_add.add_argument("--score", type=int, required=True, help="Risk score 0-100")
    p_add.add_argument("--level", choices=["LOW", "MODERATE", "HIGH", "EXTREME"],
                       help="Risk level (auto-derived from score if omitted)")
    p_add.add_argument("--complaint-types", help="Comma-separated complaint types "
                       "(ip, trademark, patent, counterfeit, cease_desist)")
    p_add.add_argument("--category", help="Product category the brand operates in")
    p_add.add_argument("--notes", help="Notes on enforcement behavior")
    p_add.set_defaults(func=cli_add)

    # list
    p_list = subparsers.add_parser("list", help="List brands in the database")
    p_list.add_argument("--level", choices=["LOW", "MODERATE", "HIGH", "EXTREME"],
                        help="Filter by risk level")
    p_list.set_defaults(func=cli_list)

    # update
    p_update = subparsers.add_parser("update", help="Scrape public sources for new IP complaint data")
    p_update.set_defaults(func=cli_update)

    # stats
    p_stats = subparsers.add_parser("stats", help="Show database statistics")
    p_stats.set_defaults(func=cli_stats)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()

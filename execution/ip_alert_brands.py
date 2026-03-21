from __future__ import annotations
"""
IP Alert Brand Database
Brands known to file IP complaints against 3P sellers, even for genuine product.
Source: Amazon seller forums, FBA communities, legal filings (as of 2026).
Update this list as new reports come in.
"""

# Severity levels: "HIGH" = confirmed complaints, "MEDIUM" = reported/suspected, "LOW" = caution
IP_ALERT_BRANDS: dict[str, dict] = {
    # HIGH — confirmed, documented complaint history
    "oakley": {"severity": "HIGH", "reason": "Files aggressive IP complaints against all 3P resellers", "source": "Amazon forum reports"},
    "crocs": {"severity": "HIGH", "reason": "Brand gated + files complaints against unauthorized resellers", "source": "FBA communities"},
    "patpat": {"severity": "HIGH", "reason": "Direct-to-consumer brand, files complaints against all resellers", "source": "r/FulfillmentByAmazon"},
    "lego": {"severity": "HIGH", "reason": "Strict MAP enforcement + IP complaints for misrepresentation", "source": "Seller community reports"},
    "apple": {"severity": "HIGH", "reason": "Brand gated, requires direct authorization", "source": "Amazon policy"},
    "beats": {"severity": "HIGH", "reason": "Apple brand, same IP enforcement", "source": "Amazon policy"},
    "disney": {"severity": "HIGH", "reason": "Strict licensing, complaints against unauthorized merch", "source": "FBA communities"},
    "hasbro": {"severity": "HIGH", "reason": "Brand protection program, complaints on unauthorized listings", "source": "Seller reports"},
    "funko": {"severity": "HIGH", "reason": "Very aggressive IP enforcement, even on genuine product", "source": "r/FulfillmentByAmazon multiple threads"},
    "jibbitz": {"severity": "HIGH", "reason": "Crocs subsidiary, same enforcement", "source": "FBA communities"},
    "fjallraven": {"severity": "HIGH", "reason": "Files complaints against all non-authorized Amazon sellers", "source": "FBA seller forum"},
    "rimowa": {"severity": "HIGH", "reason": "LVMH brand, aggressive IP enforcement", "source": "FBA communities"},
    "tiffany": {"severity": "HIGH", "reason": "LVMH brand, brand gated + complaints", "source": "Amazon policy"},
    "louboutin": {"severity": "HIGH", "reason": "Luxury brand gated, files all unauthorized complaints", "source": "Amazon policy"},
    "hermes": {"severity": "HIGH", "reason": "Luxury brand gated", "source": "Amazon policy"},
    "chanel": {"severity": "HIGH", "reason": "Luxury brand gated", "source": "Amazon policy"},
    "gucci": {"severity": "HIGH", "reason": "Luxury brand gated", "source": "Amazon policy"},
    "prada": {"severity": "HIGH", "reason": "Luxury brand gated", "source": "Amazon policy"},

    # MEDIUM — reported complaints, verify before buying
    "kylie cosmetics": {"severity": "MEDIUM", "reason": "Celebrity brand, reports of gating + complaints", "source": "FBA forums"},
    "skims": {"severity": "MEDIUM", "reason": "Kim K brand, aggressive brand protection", "source": "FBA forums"},
    "fenty beauty": {"severity": "MEDIUM", "reason": "Rihanna brand, reports of unauthorized seller complaints", "source": "FBA communities"},
    "rare beauty": {"severity": "MEDIUM", "reason": "Celebrity brand, reports of brand protection complaints", "source": "FBA communities"},
    "pattern beauty": {"severity": "MEDIUM", "reason": "Celebrity brand, reports of gating", "source": "FBA communities"},
    "tracee ellis ross": {"severity": "MEDIUM", "reason": "Same as Pattern Beauty", "source": "FBA communities"},
    "goop": {"severity": "MEDIUM", "reason": "Gwyneth Paltrow brand, reports of complaints", "source": "FBA seller reports"},
    "ollipop": {"severity": "MEDIUM", "reason": "DTC brand, reports of MAP enforcement + complaints", "source": "FBA communities"},
    "poppi": {"severity": "MEDIUM", "reason": "DTC brand, reports of complaints against resellers", "source": "FBA communities"},
    "liquid iv": {"severity": "MEDIUM", "reason": "Reports of IP complaints, Unilever brand now", "source": "FBA forums"},
    "athletic greens": {"severity": "MEDIUM", "reason": "AG1, DTC model, complaints against 3P resellers", "source": "FBA communities"},
    "ag1": {"severity": "MEDIUM", "reason": "Same as Athletic Greens", "source": "FBA communities"},
    "thrive causemetics": {"severity": "MEDIUM", "reason": "DTC brand, does not authorize 3P Amazon resellers", "source": "Brand website"},
    "saie beauty": {"severity": "MEDIUM", "reason": "DTC beauty brand, reports of complaints", "source": "FBA forums"},
    "ilia beauty": {"severity": "MEDIUM", "reason": "DTC beauty brand, reports of unauthorized reseller complaints", "source": "FBA communities"},
    "tatcha": {"severity": "MEDIUM", "reason": "Unilever brand, reports of complaint filings", "source": "FBA communities"},
    "drunk elephant": {"severity": "MEDIUM", "reason": "Shiseido brand, reports of IP enforcement", "source": "FBA forums"},
    "sunday riley": {"severity": "MEDIUM", "reason": "Luxury skincare, reports of complaints against resellers", "source": "FBA communities"},
    "noble panacea": {"severity": "MEDIUM", "reason": "Luxury skincare, DTC model", "source": "Brand website"},
    "dermalogica": {"severity": "MEDIUM", "reason": "Professional skincare, authorized reseller program only", "source": "Brand policy"},
    "obagi": {"severity": "MEDIUM", "reason": "Medical skincare, prescription lines only via authorized channels", "source": "Brand policy"},
    "supergoop": {"severity": "MEDIUM", "reason": "DTC SPF brand, reports of reseller complaints", "source": "FBA communities"},
    "tower 28": {"severity": "MEDIUM", "reason": "DTC beauty, reports of complaints", "source": "FBA communities"},
    "merit beauty": {"severity": "MEDIUM", "reason": "DTC clean beauty, reports of complaints", "source": "FBA communities"},

    # LOW — caution/watch, not confirmed
    "huda beauty": {"severity": "LOW", "reason": "Celebrity brand, monitor for complaints", "source": "Community reports"},
    "morphe": {"severity": "LOW", "reason": "Reports of varying IP enforcement", "source": "FBA communities"},
    "charlotte tilbury": {"severity": "LOW", "reason": "Luxury beauty, reports of MAP issues", "source": "FBA forums"},
    "elemis": {"severity": "LOW", "reason": "Luxury skincare, caution with reselling", "source": "FBA communities"},
    "la mer": {"severity": "LOW", "reason": "LVMH/Estee Lauder luxury, monitor", "source": "FBA communities"},
    "la prairie": {"severity": "LOW", "reason": "Ultra-luxury skincare, caution", "source": "FBA communities"},
    "sisley paris": {"severity": "LOW", "reason": "Luxury skincare, limited authorization", "source": "Brand policy"},
}


def is_ip_risk(brand_name: str) -> tuple[bool, str]:
    """
    Check if a brand has known IP complaint history.
    Returns (is_risk: bool, severity: str) where severity is 'HIGH', 'MEDIUM', 'LOW', or ''
    """
    if not brand_name:
        return False, ""
    normalized = brand_name.lower().strip()
    # Direct match
    if normalized in IP_ALERT_BRANDS:
        entry = IP_ALERT_BRANDS[normalized]
        return True, entry["severity"]
    # Partial match (brand name appears in key)
    for key, entry in IP_ALERT_BRANDS.items():
        if key in normalized or normalized in key:
            if abs(len(key) - len(normalized)) < 5:  # Avoid false positives on very different lengths
                return True, entry["severity"]
    return False, ""


def get_ip_alert_details(brand_name: str) -> dict | None:
    """Get full IP alert details for a brand, or None if not in database."""
    if not brand_name:
        return None
    normalized = brand_name.lower().strip()
    if normalized in IP_ALERT_BRANDS:
        return {**IP_ALERT_BRANDS[normalized], "brand": brand_name}
    for key, entry in IP_ALERT_BRANDS.items():
        if key in normalized or normalized in key:
            if abs(len(key) - len(normalized)) < 5:
                return {**entry, "brand": brand_name}
    return None


def get_all_ip_alert_brands(min_severity: str = "LOW") -> list[dict]:
    """Get all brands at or above a severity level."""
    severity_order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    min_level = severity_order.get(min_severity, 0)
    return [
        {"brand": k, **v}
        for k, v in IP_ALERT_BRANDS.items()
        if severity_order.get(v["severity"], 0) >= min_level
    ]


if __name__ == "__main__":
    # Test
    test_brands = ["Funko", "Crayola", "Oakley", "Apple", "Generic Brand", "Drunk Elephant"]
    for brand in test_brands:
        is_risk, severity = is_ip_risk(brand)
        print(f"{brand}: {'WARNING ' + severity if is_risk else 'OK'}")

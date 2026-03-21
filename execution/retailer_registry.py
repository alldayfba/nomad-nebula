#!/usr/bin/env python3
"""
Script: retailer_registry.py
Purpose: Master retailer database (300+ retailers) with smart category routing.
         Tier 1 = custom CSS selectors in retailer_configs.py (15 retailers).
         Tier 2 = generic JSON-LD fallback (85 retailers).
         Any retailer URL works out of the box via the generic scraper —
         the registry enables searching by name and applying correct cashback.

Key functions:
    get_retailer(domain_or_name) → retailer dict
    get_retailers_by_category(category) → list
    get_search_url(retailer, query) → formatted URL
    get_all_retailers(tier=None, enabled=True) → filtered list
    get_clearance_urls(category=None) → list of clearance URLs
    get_retailers_for_product(query_or_category, max_retailers=15) → ranked list
"""

from urllib.parse import quote_plus, urlparse

# ── 100-Retailer Registry ────────────────────────────────────────────────────

RETAILERS = [
    # ── Tier 1: Custom CSS selectors (15 retailers) ──────────────────────────
    {"key": "walmart", "name": "Walmart", "domain": "walmart.com", "search_url": "https://www.walmart.com/search?q={query}", "clearance_url": "https://www.walmart.com/browse/clearance", "cashback_percent": 3.0, "gift_card_discount": 0.0, "tier": 1, "categories": ["Grocery", "Seasonal", "Health", "Beauty", "Home", "Toys"], "request_delay": 2.0, "enabled": True},
    {"key": "target", "name": "Target", "domain": "target.com", "search_url": "https://www.target.com/s?searchTerm={query}", "clearance_url": "https://www.target.com/c/clearance", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 1, "categories": ["Grocery", "Beauty", "Seasonal", "Home", "Toys", "Kids"], "request_delay": 2.5, "enabled": True},
    {"key": "homedepot", "name": "Home Depot", "domain": "homedepot.com", "search_url": "https://www.homedepot.com/s/{query}", "clearance_url": "https://www.homedepot.com/b/Savings-Center/N-5yc1vZc2It", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 1, "categories": ["Home", "Tools", "Seasonal"], "request_delay": 2.0, "enabled": True},
    {"key": "cvs", "name": "CVS", "domain": "cvs.com", "search_url": "https://www.cvs.com/search?searchTerm={query}", "clearance_url": "https://www.cvs.com/shop/sales-and-special-offers", "cashback_percent": 3.0, "gift_card_discount": 0.0, "tier": 1, "categories": ["Health", "Beauty"], "request_delay": 3.0, "enabled": True},
    {"key": "walgreens", "name": "Walgreens", "domain": "walgreens.com", "search_url": "https://www.walgreens.com/search/results.jsp?Ntt={query}", "clearance_url": "https://www.walgreens.com/store/c/sale/N-355128", "cashback_percent": 3.0, "gift_card_discount": 0.0, "tier": 1, "categories": ["Health", "Beauty"], "request_delay": 3.0, "enabled": True},
    {"key": "costco", "name": "Costco", "domain": "costco.com", "search_url": "https://www.costco.com/CatalogSearch?dept=All&keyword={query}", "clearance_url": None, "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 1, "categories": ["Grocery", "Health", "Bulk"], "request_delay": 2.5, "enabled": True},
    {"key": "bjs", "name": "BJ's", "domain": "bjs.com", "search_url": "https://www.bjs.com/search/{query}", "clearance_url": None, "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 1, "categories": ["Grocery", "Health", "Bulk"], "request_delay": 2.5, "enabled": True},
    {"key": "samsclub", "name": "Sam's Club", "domain": "samsclub.com", "search_url": "https://www.samsclub.com/s/{query}", "clearance_url": "https://www.samsclub.com/c/instant-savings", "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 1, "categories": ["Grocery", "Health", "Bulk"], "request_delay": 2.5, "enabled": True},
    {"key": "kohls", "name": "Kohl's", "domain": "kohls.com", "search_url": "https://www.kohls.com/search.jsp?search={query}", "clearance_url": "https://www.kohls.com/sale-event/clearance.jsp", "cashback_percent": 4.0, "gift_card_discount": 0.0, "tier": 1, "categories": ["Apparel", "Beauty", "Home"], "request_delay": 2.5, "enabled": True},
    {"key": "bestbuy", "name": "Best Buy", "domain": "bestbuy.com", "search_url": "https://www.bestbuy.com/site/searchpage.jsp?st={query}", "clearance_url": "https://www.bestbuy.com/site/misc/clearance/pcmcat142300050026.c", "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 1, "categories": ["Electronics"], "request_delay": 2.0, "enabled": True},
    {"key": "lowes", "name": "Lowe's", "domain": "lowes.com", "search_url": "https://www.lowes.com/search?searchTerm={query}", "clearance_url": "https://www.lowes.com/l/Clearance/4294937087", "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 1, "categories": ["Home", "Tools", "Seasonal"], "request_delay": 2.0, "enabled": True},
    {"key": "macys", "name": "Macy's", "domain": "macys.com", "search_url": "https://www.macys.com/shop/featured/{query}", "clearance_url": "https://www.macys.com/shop/sale/clearance", "cashback_percent": 2.5, "gift_card_discount": 0.0, "tier": 1, "categories": ["Apparel", "Beauty", "Home"], "request_delay": 2.5, "enabled": True},
    {"key": "ulta", "name": "Ulta Beauty", "domain": "ulta.com", "search_url": "https://www.ulta.com/search?search={query}", "clearance_url": "https://www.ulta.com/promotion/sale", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 1, "categories": ["Beauty"], "request_delay": 2.5, "enabled": True},
    {"key": "dickssportinggoods", "name": "Dick's Sporting Goods", "domain": "dickssportinggoods.com", "search_url": "https://www.dickssportinggoods.com/s/{query}", "clearance_url": "https://www.dickssportinggoods.com/c/clearance", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 1, "categories": ["Sports & Outdoors"], "request_delay": 2.5, "enabled": True},
    {"key": "kroger", "name": "Kroger", "domain": "kroger.com", "search_url": "https://www.kroger.com/search?query={query}", "clearance_url": None, "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 1, "categories": ["Grocery"], "request_delay": 3.0, "enabled": True},

    # ── Tier 2: Generic + JSON-LD (85 retailers) ─────────────────────────────
    {"key": "nordstrom", "name": "Nordstrom", "domain": "nordstrom.com", "search_url": "https://www.nordstrom.com/sr?keyword={query}", "clearance_url": "https://www.nordstrom.com/browse/sale", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Apparel", "Beauty"], "request_delay": 3.0, "enabled": True},
    {"key": "tjmaxx", "name": "TJ Maxx", "domain": "tjmaxx.com", "search_url": "https://tjmaxx.tjx.com/store/search?q={query}", "clearance_url": "https://tjmaxx.tjx.com/store/shop/clearance", "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Apparel", "Home"], "request_delay": 3.0, "enabled": True},
    {"key": "marshalls", "name": "Marshalls", "domain": "marshalls.com", "search_url": "https://www.marshalls.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Apparel", "Home"], "request_delay": 3.0, "enabled": True},
    {"key": "wayfair", "name": "Wayfair", "domain": "wayfair.com", "search_url": "https://www.wayfair.com/keyword.php?keyword={query}", "clearance_url": "https://www.wayfair.com/daily-sales", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Home"], "request_delay": 3.0, "enabled": True},
    {"key": "overstock", "name": "Overstock", "domain": "overstock.com", "search_url": "https://www.overstock.com/search?keywords={query}", "clearance_url": "https://www.overstock.com/clearance", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Home"], "request_delay": 3.0, "enabled": True},
    {"key": "biglots", "name": "Big Lots", "domain": "biglots.com", "search_url": "https://www.biglots.com/search/?q={query}", "clearance_url": "https://www.biglots.com/c/clearance", "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Home", "Seasonal"], "request_delay": 3.0, "enabled": True},
    {"key": "dollargeneral", "name": "Dollar General", "domain": "dollargeneral.com", "search_url": "https://www.dollargeneral.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery", "Home"], "request_delay": 3.0, "enabled": True},
    {"key": "familydollar", "name": "Family Dollar", "domain": "familydollar.com", "search_url": "https://www.familydollar.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery", "Home"], "request_delay": 3.0, "enabled": True},
    {"key": "staples", "name": "Staples", "domain": "staples.com", "search_url": "https://www.staples.com/search?query={query}", "clearance_url": "https://www.staples.com/deals", "cashback_percent": 3.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Office"], "request_delay": 3.0, "enabled": True},
    {"key": "officedepot", "name": "Office Depot", "domain": "officedepot.com", "search_url": "https://www.officedepot.com/catalog/search?q={query}", "clearance_url": None, "cashback_percent": 3.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Office"], "request_delay": 3.0, "enabled": True},
    {"key": "gamestop", "name": "GameStop", "domain": "gamestop.com", "search_url": "https://www.gamestop.com/search/?q={query}", "clearance_url": "https://www.gamestop.com/deals", "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Electronics", "Toys"], "request_delay": 3.0, "enabled": True},
    {"key": "academy", "name": "Academy Sports", "domain": "academy.com", "search_url": "https://www.academy.com/shop/browse?Ntt={query}", "clearance_url": "https://www.academy.com/shop/browse/clearance", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Sports & Outdoors"], "request_delay": 3.0, "enabled": True},
    {"key": "petco", "name": "Petco", "domain": "petco.com", "search_url": "https://www.petco.com/shop/s/{query}", "clearance_url": "https://www.petco.com/shop/en/petcostore/category/sale", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Pets"], "request_delay": 3.0, "enabled": True},
    {"key": "petsmart", "name": "PetSmart", "domain": "petsmart.com", "search_url": "https://www.petsmart.com/search?q={query}", "clearance_url": "https://www.petsmart.com/sale/", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Pets"], "request_delay": 3.0, "enabled": True},
    {"key": "vitaminshoppe", "name": "Vitamin Shoppe", "domain": "vitaminshoppe.com", "search_url": "https://www.vitaminshoppe.com/search?search={query}", "clearance_url": "https://www.vitaminshoppe.com/c/sale", "cashback_percent": 3.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Health"], "request_delay": 3.0, "enabled": True},
    {"key": "vitacost", "name": "Vitacost", "domain": "vitacost.com", "search_url": "https://www.vitacost.com/search?q={query}", "clearance_url": "https://www.vitacost.com/clearance-closeout", "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Health", "Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "gnc", "name": "GNC", "domain": "gnc.com", "search_url": "https://www.gnc.com/search?q={query}", "clearance_url": "https://www.gnc.com/sale/", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Health"], "request_delay": 3.0, "enabled": True},
    {"key": "newegg", "name": "Newegg", "domain": "newegg.com", "search_url": "https://www.newegg.com/p/pl?d={query}", "clearance_url": "https://www.newegg.com/promotions", "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Electronics"], "request_delay": 3.0, "enabled": True},
    {"key": "bhphoto", "name": "B&H Photo", "domain": "bhphotovideo.com", "search_url": "https://www.bhphotovideo.com/c/search?q={query}", "clearance_url": "https://www.bhphotovideo.com/c/browse/deals-savings/ci/18897", "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Electronics"], "request_delay": 3.0, "enabled": True},
    {"key": "zoro", "name": "Zoro", "domain": "zoro.com", "search_url": "https://www.zoro.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Tools", "Industrial"], "request_delay": 3.0, "enabled": True},
    {"key": "sierra", "name": "Sierra", "domain": "sierra.com", "search_url": "https://www.sierra.com/s~{query}/", "clearance_url": "https://www.sierra.com/clearance~1/", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Sports & Outdoors"], "request_delay": 3.0, "enabled": True},
    {"key": "fivebelow", "name": "Five Below", "domain": "fivebelow.com", "search_url": "https://www.fivebelow.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Toys", "Seasonal"], "request_delay": 3.0, "enabled": True},
    {"key": "menards", "name": "Menards", "domain": "menards.com", "search_url": "https://www.menards.com/main/search.html?search={query}", "clearance_url": "https://www.menards.com/main/c-19283.htm", "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Home", "Tools"], "request_delay": 3.0, "enabled": True},
    {"key": "riteaid", "name": "Rite Aid", "domain": "riteaid.com", "search_url": "https://www.riteaid.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Health", "Beauty"], "request_delay": 3.0, "enabled": True},
    {"key": "meijer", "name": "Meijer", "domain": "meijer.com", "search_url": "https://www.meijer.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "albertsons", "name": "Albertsons", "domain": "albertsons.com", "search_url": "https://www.albertsons.com/shop/search-results.html?searchTerm={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "safeway", "name": "Safeway", "domain": "safeway.com", "search_url": "https://www.safeway.com/shop/search-results.html?searchTerm={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "publix", "name": "Publix", "domain": "publix.com", "search_url": "https://www.publix.com/search?query={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "gianteagle", "name": "Giant Eagle", "domain": "gianteagle.com", "search_url": "https://www.gianteagle.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "hyvee", "name": "Hy-Vee", "domain": "hy-vee.com", "search_url": "https://www.hy-vee.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "foodlion", "name": "Food Lion", "domain": "foodlion.com", "search_url": "https://www.foodlion.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "burlington", "name": "Burlington", "domain": "burlington.com", "search_url": "https://www.burlington.com/search?q={query}", "clearance_url": "https://www.burlington.com/clearance", "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Apparel"], "request_delay": 3.0, "enabled": True},
    {"key": "dsw", "name": "DSW", "domain": "dsw.com", "search_url": "https://www.dsw.com/search/{query}/", "clearance_url": "https://www.dsw.com/clearance/", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Footwear"], "request_delay": 3.0, "enabled": True},
    {"key": "shoecarnival", "name": "Shoe Carnival", "domain": "shoecarnival.com", "search_url": "https://www.shoecarnival.com/search?q={query}", "clearance_url": "https://www.shoecarnival.com/clearance/", "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Footwear"], "request_delay": 3.0, "enabled": True},
    {"key": "famousfootwear", "name": "Famous Footwear", "domain": "famousfootwear.com", "search_url": "https://www.famousfootwear.com/search?q={query}", "clearance_url": "https://www.famousfootwear.com/sale", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Footwear"], "request_delay": 3.0, "enabled": True},
    {"key": "rei", "name": "REI", "domain": "rei.com", "search_url": "https://www.rei.com/search?q={query}", "clearance_url": "https://www.rei.com/c/outlet", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Sports & Outdoors"], "request_delay": 3.0, "enabled": True},
    {"key": "cabelas", "name": "Cabela's", "domain": "cabelas.com", "search_url": "https://www.cabelas.com/shop/en/search?q={query}", "clearance_url": "https://www.cabelas.com/shop/en/bargain-cave", "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Sports & Outdoors"], "request_delay": 3.0, "enabled": True},
    {"key": "basspro", "name": "Bass Pro Shops", "domain": "basspro.com", "search_url": "https://www.basspro.com/shop/en/search?q={query}", "clearance_url": "https://www.basspro.com/shop/en/bargain-cave", "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Sports & Outdoors"], "request_delay": 3.0, "enabled": True},
    {"key": "harborfreight", "name": "Harbor Freight", "domain": "harborfreight.com", "search_url": "https://www.harborfreight.com/search?q={query}", "clearance_url": "https://www.harborfreight.com/clearance.html", "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Tools"], "request_delay": 3.0, "enabled": True},
    {"key": "tractorsupply", "name": "Tractor Supply", "domain": "tractorsupply.com", "search_url": "https://www.tractorsupply.com/search/{query}", "clearance_url": "https://www.tractorsupply.com/tsc/collection/clearance", "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Outdoors", "Farm", "Pets"], "request_delay": 3.0, "enabled": True},
    {"key": "ruralking", "name": "Rural King", "domain": "ruralking.com", "search_url": "https://www.ruralking.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Outdoors", "Farm"], "request_delay": 3.0, "enabled": True},
    {"key": "athome", "name": "At Home", "domain": "athome.com", "search_url": "https://www.athome.com/search?q={query}", "clearance_url": "https://www.athome.com/clearance/", "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Home"], "request_delay": 3.0, "enabled": True},
    {"key": "worldmarket", "name": "World Market", "domain": "worldmarket.com", "search_url": "https://www.worldmarket.com/search?q={query}", "clearance_url": "https://www.worldmarket.com/category/sale.do", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Home", "Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "ikea", "name": "IKEA", "domain": "ikea.com", "search_url": "https://www.ikea.com/us/en/search/?q={query}", "clearance_url": "https://www.ikea.com/us/en/offers/", "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Home"], "request_delay": 3.0, "enabled": True},
    {"key": "crateandbarrel", "name": "Crate & Barrel", "domain": "crateandbarrel.com", "search_url": "https://www.crateandbarrel.com/search?query={query}", "clearance_url": "https://www.crateandbarrel.com/sale/clearance", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Home"], "request_delay": 3.0, "enabled": True},
    {"key": "potterybarn", "name": "Pottery Barn", "domain": "potterybarn.com", "search_url": "https://www.potterybarn.com/search/results.html?words={query}", "clearance_url": "https://www.potterybarn.com/shop/sale/", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Home"], "request_delay": 3.0, "enabled": True},
    {"key": "westelm", "name": "West Elm", "domain": "westelm.com", "search_url": "https://www.westelm.com/search/results.html?words={query}", "clearance_url": "https://www.westelm.com/shop/sale/", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Home"], "request_delay": 3.0, "enabled": True},
    {"key": "williamssonoma", "name": "Williams Sonoma", "domain": "williams-sonoma.com", "search_url": "https://www.williams-sonoma.com/search/results.html?words={query}", "clearance_url": "https://www.williams-sonoma.com/shop/sale/", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Kitchen"], "request_delay": 3.0, "enabled": True},
    {"key": "surlatable", "name": "Sur La Table", "domain": "surlatable.com", "search_url": "https://www.surlatable.com/search?q={query}", "clearance_url": "https://www.surlatable.com/sale/", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Kitchen"], "request_delay": 3.0, "enabled": True},
    {"key": "carters", "name": "Carter's", "domain": "carters.com", "search_url": "https://www.carters.com/search?q={query}", "clearance_url": "https://www.carters.com/c/clearance", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Kids"], "request_delay": 3.0, "enabled": True},
    {"key": "oshkosh", "name": "OshKosh B'gosh", "domain": "oshkosh.com", "search_url": "https://www.oshkosh.com/search?q={query}", "clearance_url": "https://www.oshkosh.com/c/clearance", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Kids"], "request_delay": 3.0, "enabled": True},
    {"key": "oldnavy", "name": "Old Navy", "domain": "oldnavy.gap.com", "search_url": "https://oldnavy.gap.com/browse/search?searchText={query}", "clearance_url": "https://oldnavy.gap.com/browse/category.do?cid=1125700", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Apparel"], "request_delay": 3.0, "enabled": True},
    {"key": "gap", "name": "Gap", "domain": "gap.com", "search_url": "https://www.gap.com/browse/search?searchText={query}", "clearance_url": "https://www.gap.com/browse/category.do?cid=1124172", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Apparel"], "request_delay": 3.0, "enabled": True},
    {"key": "bananarepublic", "name": "Banana Republic", "domain": "bananarepublic.gap.com", "search_url": "https://bananarepublic.gap.com/browse/search?searchText={query}", "clearance_url": "https://bananarepublic.gap.com/browse/category.do?cid=1150419", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Apparel"], "request_delay": 3.0, "enabled": True},
    {"key": "jcpenney", "name": "JCPenney", "domain": "jcpenney.com", "search_url": "https://www.jcpenney.com/s/{query}", "clearance_url": "https://www.jcpenney.com/g/clearance", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Apparel", "Home"], "request_delay": 3.0, "enabled": True},
    {"key": "belk", "name": "Belk", "domain": "belk.com", "search_url": "https://www.belk.com/search?q={query}", "clearance_url": "https://www.belk.com/clearance/", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Apparel"], "request_delay": 3.0, "enabled": True},
    {"key": "ae", "name": "American Eagle", "domain": "ae.com", "search_url": "https://www.ae.com/us/en/search/{query}", "clearance_url": "https://www.ae.com/us/en/c/clearance", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Apparel"], "request_delay": 3.0, "enabled": True},
    {"key": "urbanoutfitters", "name": "Urban Outfitters", "domain": "urbanoutfitters.com", "search_url": "https://www.urbanoutfitters.com/search?q={query}", "clearance_url": "https://www.urbanoutfitters.com/sale", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Apparel"], "request_delay": 3.0, "enabled": True},
    {"key": "journeys", "name": "Journeys", "domain": "journeys.com", "search_url": "https://www.journeys.com/search?q={query}", "clearance_url": "https://www.journeys.com/sale", "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Footwear"], "request_delay": 3.0, "enabled": True},
    {"key": "pacsun", "name": "PacSun", "domain": "pacsun.com", "search_url": "https://www.pacsun.com/search?q={query}", "clearance_url": "https://www.pacsun.com/sale/", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Apparel"], "request_delay": 3.0, "enabled": True},
    {"key": "michaels", "name": "Michaels", "domain": "michaels.com", "search_url": "https://www.michaels.com/search?q={query}", "clearance_url": "https://www.michaels.com/sale-and-clearance", "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Crafts"], "request_delay": 3.0, "enabled": True},
    {"key": "hobbylobby", "name": "Hobby Lobby", "domain": "hobbylobby.com", "search_url": "https://www.hobbylobby.com/search/?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Crafts"], "request_delay": 3.0, "enabled": True},
    {"key": "joann", "name": "Joann", "domain": "joann.com", "search_url": "https://www.joann.com/search?q={query}", "clearance_url": "https://www.joann.com/clearance/", "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Crafts"], "request_delay": 3.0, "enabled": True},
    {"key": "partycity", "name": "Party City", "domain": "partycity.com", "search_url": "https://www.partycity.com/search?q={query}", "clearance_url": "https://www.partycity.com/sale", "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Seasonal", "Party"], "request_delay": 3.0, "enabled": True},
    {"key": "heb", "name": "HEB", "domain": "heb.com", "search_url": "https://www.heb.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "big5", "name": "Big 5 Sporting Goods", "domain": "big5sportinggoods.com", "search_url": "https://www.big5sportinggoods.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Sports & Outdoors"], "request_delay": 3.0, "enabled": True},
    {"key": "fredmeyer", "name": "Fred Meyer", "domain": "fredmeyer.com", "search_url": "https://www.fredmeyer.com/search?query={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "pcrichard", "name": "P.C. Richard", "domain": "pcrichard.com", "search_url": "https://www.pcrichard.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Electronics"], "request_delay": 3.0, "enabled": True},
    {"key": "microcenter", "name": "Micro Center", "domain": "microcenter.com", "search_url": "https://www.microcenter.com/search/search_results.aspx?N=&Ntt={query}", "clearance_url": "https://www.microcenter.com/search/search_results.aspx?N=4294966842", "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Electronics"], "request_delay": 3.0, "enabled": True},
    {"key": "fleetfarm", "name": "Fleet Farm", "domain": "fleetfarm.com", "search_url": "https://www.fleetfarm.com/search?q={query}", "clearance_url": "https://www.fleetfarm.com/catalog/clearance", "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Farm", "Outdoors", "Seasonal", "Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "farmandfleet", "name": "Farm & Fleet", "domain": "farmandfleet.com", "search_url": "https://www.farmandfleet.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Farm", "Outdoors"], "request_delay": 3.0, "enabled": True},
    {"key": "bfrg", "name": "Blain's Farm & Fleet", "domain": "bfrg.com", "search_url": "https://www.bfrg.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Farm", "Outdoors"], "request_delay": 3.0, "enabled": True},
    {"key": "oceanstatejoblot", "name": "Ocean State Job Lot", "domain": "oceanstatejoblot.com", "search_url": "https://www.oceanstatejoblot.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Closeouts"], "request_delay": 3.0, "enabled": True},
    {"key": "icuracao", "name": "Curacao", "domain": "icuracao.com", "search_url": "https://www.icuracao.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Electronics", "Home"], "request_delay": 3.0, "enabled": True},
    {"key": "shoprite", "name": "ShopRite", "domain": "shoprite.com", "search_url": "https://www.shoprite.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "stopandshop", "name": "Stop & Shop", "domain": "stopandshop.com", "search_url": "https://www.stopandshop.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "pricechopper", "name": "Price Chopper", "domain": "pricechopper.com", "search_url": "https://www.pricechopper.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "sprouts", "name": "Sprouts", "domain": "sprouts.com", "search_url": "https://www.sprouts.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery", "Health"], "request_delay": 3.0, "enabled": True},
    {"key": "lollicup", "name": "Lollicup", "domain": "lollicupstore.com", "search_url": "https://www.lollicupstore.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Kitchen", "Industrial", "Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "webstaurantstore", "name": "WebstaurantStore", "domain": "webstaurantstore.com", "search_url": "https://www.webstaurantstore.com/search/{query}.html", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Kitchen", "Industrial"], "request_delay": 3.0, "enabled": True},

    # ── Tier 2 Expansion: 200+ additional retailers ────────────────────────────

    # ── Grocery & Specialty Food ───────────────────────────────────────────────
    {"key": "aldi", "name": "Aldi", "domain": "aldi.us", "search_url": "https://www.aldi.us/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "traderjoes", "name": "Trader Joe's", "domain": "traderjoes.com", "search_url": "https://www.traderjoes.com/home/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "wholefoodsmarket", "name": "Whole Foods Market", "domain": "wholefoodsmarket.com", "search_url": "https://www.wholefoodsmarket.com/search?text={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery", "Health"], "request_delay": 3.0, "enabled": True},
    {"key": "thrive", "name": "Thrive Market", "domain": "thrivemarket.com", "search_url": "https://thrivemarket.com/search?search={query}", "clearance_url": None, "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery", "Health"], "request_delay": 3.0, "enabled": True},
    {"key": "iherb", "name": "iHerb", "domain": "iherb.com", "search_url": "https://www.iherb.com/search?kw={query}", "clearance_url": "https://www.iherb.com/c/clearance", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Health", "Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "wegmans", "name": "Wegmans", "domain": "wegmans.com", "search_url": "https://www.wegmans.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "winco", "name": "WinCo Foods", "domain": "wincofoods.com", "search_url": "https://www.wincofoods.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "harristeeter", "name": "Harris Teeter", "domain": "harristeeter.com", "search_url": "https://www.harristeeter.com/search?query={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "pigglywiggly", "name": "Piggly Wiggly", "domain": "pigglywiggly.com", "search_url": "https://www.pigglywiggly.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "winn-dixie", "name": "Winn-Dixie", "domain": "winndixie.com", "search_url": "https://www.winndixie.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "savemart", "name": "Save Mart", "domain": "savemart.com", "search_url": "https://www.savemart.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "hannaford", "name": "Hannaford", "domain": "hannaford.com", "search_url": "https://www.hannaford.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "foodcity", "name": "Food City", "domain": "foodcity.com", "search_url": "https://www.foodcity.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "smartandfinal", "name": "Smart & Final", "domain": "smartandfinal.com", "search_url": "https://www.smartandfinal.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery", "Bulk"], "request_delay": 3.0, "enabled": True},
    {"key": "instacart", "name": "Instacart", "domain": "instacart.com", "search_url": "https://www.instacart.com/store/search/{query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "boxed", "name": "Boxed", "domain": "boxed.com", "search_url": "https://www.boxed.com/search/{query}", "clearance_url": None, "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery", "Bulk"], "request_delay": 3.0, "enabled": True},

    # ── Beauty & Personal Care ─────────────────────────────────────────────────
    {"key": "maccosmetics", "name": "MAC Cosmetics", "domain": "maccosmetics.com", "search_url": "https://www.maccosmetics.com/search?query={query}", "clearance_url": "https://www.maccosmetics.com/sale", "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Beauty"], "request_delay": 3.0, "enabled": True},
    {"key": "fentybeauty", "name": "Fenty Beauty", "domain": "fentybeauty.com", "search_url": "https://www.fentybeauty.com/search?q={query}", "clearance_url": "https://www.fentybeauty.com/sale", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Beauty"], "request_delay": 3.0, "enabled": True},
    {"key": "jonesroadbeauty", "name": "Jones Road Beauty", "domain": "jonesroadbeauty.com", "search_url": "https://www.jonesroadbeauty.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Beauty"], "request_delay": 3.0, "enabled": True},
    {"key": "stylevana", "name": "Stylevana", "domain": "stylevana.com", "search_url": "https://www.stylevana.com/en_US/search?query={query}", "clearance_url": "https://www.stylevana.com/en_US/sale.html", "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Beauty", "K-Beauty"], "request_delay": 3.0, "enabled": True},
    {"key": "sephora", "name": "Sephora", "domain": "sephora.com", "search_url": "https://www.sephora.com/search?keyword={query}", "clearance_url": "https://www.sephora.com/sale", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Beauty"], "request_delay": 3.0, "enabled": True},
    {"key": "sallybeauty", "name": "Sally Beauty", "domain": "sallybeauty.com", "search_url": "https://www.sallybeauty.com/search?q={query}", "clearance_url": "https://www.sallybeauty.com/sale/", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Beauty"], "request_delay": 3.0, "enabled": True},
    {"key": "dermstore", "name": "Dermstore", "domain": "dermstore.com", "search_url": "https://www.dermstore.com/search?q={query}", "clearance_url": "https://www.dermstore.com/sale.list", "cashback_percent": 3.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Beauty", "Health"], "request_delay": 3.0, "enabled": True},
    {"key": "beautylish", "name": "Beautylish", "domain": "beautylish.com", "search_url": "https://www.beautylish.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Beauty"], "request_delay": 3.0, "enabled": True},
    {"key": "colourpop", "name": "ColourPop", "domain": "colourpop.com", "search_url": "https://colourpop.com/search?q={query}", "clearance_url": "https://colourpop.com/collections/sale", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Beauty"], "request_delay": 3.0, "enabled": True},
    {"key": "elfcosmetics", "name": "e.l.f. Cosmetics", "domain": "elfcosmetics.com", "search_url": "https://www.elfcosmetics.com/search?q={query}", "clearance_url": "https://www.elfcosmetics.com/sale/", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Beauty"], "request_delay": 3.0, "enabled": True},
    {"key": "bathandbodyworks", "name": "Bath & Body Works", "domain": "bathandbodyworks.com", "search_url": "https://www.bathandbodyworks.com/s?q={query}", "clearance_url": "https://www.bathandbodyworks.com/c/sale", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Beauty", "Home"], "request_delay": 3.0, "enabled": True},
    {"key": "theordinary", "name": "The Ordinary", "domain": "theordinary.com", "search_url": "https://theordinary.com/en-us/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Beauty"], "request_delay": 3.0, "enabled": True},
    {"key": "lookfantastic", "name": "Lookfantastic", "domain": "lookfantastic.com", "search_url": "https://www.lookfantastic.com/search?q={query}", "clearance_url": "https://www.lookfantastic.com/offers/sale.list", "cashback_percent": 3.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Beauty"], "request_delay": 3.0, "enabled": True},
    {"key": "fragrancenet", "name": "FragranceNet", "domain": "fragrancenet.com", "search_url": "https://www.fragrancenet.com/search?q={query}", "clearance_url": None, "cashback_percent": 3.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Beauty"], "request_delay": 3.0, "enabled": True},
    {"key": "loccitane", "name": "L'Occitane", "domain": "loccitane.com", "search_url": "https://www.loccitane.com/en-us/search?q={query}", "clearance_url": "https://www.loccitane.com/en-us/sale", "cashback_percent": 3.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Beauty"], "request_delay": 3.0, "enabled": True},

    # ── Electronics & Tech ─────────────────────────────────────────────────────
    {"key": "adorama", "name": "Adorama", "domain": "adorama.com", "search_url": "https://www.adorama.com/l/?searchinfo={query}", "clearance_url": "https://www.adorama.com/l/deals", "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Electronics"], "request_delay": 3.0, "enabled": True},
    {"key": "monoprice", "name": "Monoprice", "domain": "monoprice.com", "search_url": "https://www.monoprice.com/search?q={query}", "clearance_url": "https://www.monoprice.com/pages/clearance", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Electronics"], "request_delay": 3.0, "enabled": True},
    {"key": "tigerdirect", "name": "TigerDirect", "domain": "tigerdirect.com", "search_url": "https://www.tigerdirect.com/applications/SearchTools/search.asp?keywords={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Electronics"], "request_delay": 3.0, "enabled": True},
    {"key": "dell", "name": "Dell", "domain": "dell.com", "search_url": "https://www.dell.com/en-us/search/{query}", "clearance_url": "https://www.dell.com/en-us/shop/deals/cp/deals", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Electronics"], "request_delay": 3.0, "enabled": True},
    {"key": "hp", "name": "HP", "domain": "hp.com", "search_url": "https://www.hp.com/us-en/search?q={query}", "clearance_url": "https://www.hp.com/us-en/shop/slp/deals", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Electronics"], "request_delay": 3.0, "enabled": True},
    {"key": "lenovo", "name": "Lenovo", "domain": "lenovo.com", "search_url": "https://www.lenovo.com/us/en/search?q={query}", "clearance_url": "https://www.lenovo.com/us/en/d/deals", "cashback_percent": 3.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Electronics"], "request_delay": 3.0, "enabled": True},
    {"key": "cdw", "name": "CDW", "domain": "cdw.com", "search_url": "https://www.cdw.com/search/?key={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Electronics", "Office"], "request_delay": 3.0, "enabled": True},
    {"key": "bhphoto2", "name": "Abt Electronics", "domain": "abt.com", "search_url": "https://www.abt.com/resources/search?q={query}", "clearance_url": "https://www.abt.com/clearance", "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Electronics", "Home"], "request_delay": 3.0, "enabled": True},

    # ── Sports, Outdoors & Fitness ─────────────────────────────────────────────
    {"key": "backcountry", "name": "Backcountry", "domain": "backcountry.com", "search_url": "https://www.backcountry.com/search?q={query}", "clearance_url": "https://www.backcountry.com/sale", "cashback_percent": 3.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Sports & Outdoors"], "request_delay": 3.0, "enabled": True},
    {"key": "moosejaw", "name": "Moosejaw", "domain": "moosejaw.com", "search_url": "https://www.moosejaw.com/search?q={query}", "clearance_url": "https://www.moosejaw.com/content/sale", "cashback_percent": 3.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Sports & Outdoors"], "request_delay": 3.0, "enabled": True},
    {"key": "ems", "name": "Eastern Mountain Sports", "domain": "ems.com", "search_url": "https://www.ems.com/search?q={query}", "clearance_url": "https://www.ems.com/sale/", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Sports & Outdoors"], "request_delay": 3.0, "enabled": True},
    {"key": "scheels", "name": "Scheels", "domain": "scheels.com", "search_url": "https://www.scheels.com/search?q={query}", "clearance_url": "https://www.scheels.com/sale/", "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Sports & Outdoors"], "request_delay": 3.0, "enabled": True},
    {"key": "runningwarehouse", "name": "Running Warehouse", "domain": "runningwarehouse.com", "search_url": "https://www.runningwarehouse.com/searchresults.html?search={query}", "clearance_url": "https://www.runningwarehouse.com/sale.html", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Sports & Outdoors", "Footwear"], "request_delay": 3.0, "enabled": True},
    {"key": "roguefitness", "name": "Rogue Fitness", "domain": "roguefit.com", "search_url": "https://www.roguefitness.com/search?q={query}", "clearance_url": "https://www.roguefitness.com/deals", "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Sports & Outdoors"], "request_delay": 3.0, "enabled": True},
    {"key": "sportsmanswarehouse", "name": "Sportsman's Warehouse", "domain": "sportsmans.com", "search_url": "https://www.sportsmans.com/search?q={query}", "clearance_url": "https://www.sportsmans.com/sale", "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Sports & Outdoors"], "request_delay": 3.0, "enabled": True},
    {"key": "tacklewarehouse", "name": "Tackle Warehouse", "domain": "tacklewarehouse.com", "search_url": "https://www.tacklewarehouse.com/search?q={query}", "clearance_url": "https://www.tacklewarehouse.com/closeouts.html", "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Sports & Outdoors"], "request_delay": 3.0, "enabled": True},
    {"key": "soccercom", "name": "Soccer.com", "domain": "soccer.com", "search_url": "https://www.soccer.com/search?q={query}", "clearance_url": "https://www.soccer.com/sale", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Sports & Outdoors"], "request_delay": 3.0, "enabled": True},
    {"key": "dickssportinggoods2", "name": "Golf Galaxy", "domain": "golfgalaxy.com", "search_url": "https://www.golfgalaxy.com/s/{query}", "clearance_url": "https://www.golfgalaxy.com/c/clearance", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Sports & Outdoors"], "request_delay": 3.0, "enabled": True},

    # ── Pet Supplies ───────────────────────────────────────────────────────────
    {"key": "petedge", "name": "PetEdge", "domain": "petedge.com", "search_url": "https://www.petedge.com/search?q={query}", "clearance_url": "https://www.petedge.com/sale/", "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Pets", "Professional"], "request_delay": 3.0, "enabled": True},
    {"key": "chewy", "name": "Chewy", "domain": "chewy.com", "search_url": "https://www.chewy.com/s?query={query}", "clearance_url": "https://www.chewy.com/b/deals-702", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Pets"], "request_delay": 3.0, "enabled": True},
    {"key": "entirelypets", "name": "EntirelyPets", "domain": "entirelypets.com", "search_url": "https://www.entirelypets.com/search?q={query}", "clearance_url": "https://www.entirelypets.com/sale.html", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Pets"], "request_delay": 3.0, "enabled": True},
    {"key": "petflow", "name": "PetFlow", "domain": "petflow.com", "search_url": "https://www.petflow.com/search?q={query}", "clearance_url": None, "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Pets"], "request_delay": 3.0, "enabled": True},
    {"key": "petmountain", "name": "Pet Mountain", "domain": "petmountain.com", "search_url": "https://www.petmountain.com/search?q={query}", "clearance_url": "https://www.petmountain.com/sale/", "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Pets"], "request_delay": 3.0, "enabled": True},
    {"key": "1800petmeds", "name": "1-800-PetMeds", "domain": "1800petmeds.com", "search_url": "https://www.1800petmeds.com/search?q={query}", "clearance_url": None, "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Pets", "Health"], "request_delay": 3.0, "enabled": True},

    # ── Home & Garden ──────────────────────────────────────────────────────────
    {"key": "bedbathandbeyond", "name": "Bed Bath & Beyond", "domain": "bedbathandbeyond.com", "search_url": "https://www.bedbathandbeyond.com/s/{query}", "clearance_url": "https://www.bedbathandbeyond.com/c/clearance", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Home"], "request_delay": 3.0, "enabled": True},
    {"key": "pier1", "name": "Pier 1", "domain": "pier1.com", "search_url": "https://www.pier1.com/search?q={query}", "clearance_url": "https://www.pier1.com/sale/", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Home"], "request_delay": 3.0, "enabled": True},
    {"key": "zgallerie", "name": "Z Gallerie", "domain": "zgallerie.com", "search_url": "https://www.zgallerie.com/search?q={query}", "clearance_url": "https://www.zgallerie.com/sale/", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Home"], "request_delay": 3.0, "enabled": True},
    {"key": "hayneedle", "name": "Hayneedle", "domain": "hayneedle.com", "search_url": "https://www.hayneedle.com/search?q={query}", "clearance_url": None, "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Home"], "request_delay": 3.0, "enabled": True},
    {"key": "restorationhardware", "name": "Restoration Hardware", "domain": "rh.com", "search_url": "https://rh.com/search/results.jsp?query={query}", "clearance_url": "https://rh.com/catalog/category/products.jsp?sale=true", "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Home"], "request_delay": 3.0, "enabled": True},
    {"key": "houzz", "name": "Houzz", "domain": "houzz.com", "search_url": "https://www.houzz.com/products/q/{query}", "clearance_url": "https://www.houzz.com/shop-houzz", "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Home"], "request_delay": 3.0, "enabled": True},
    {"key": "acehardware", "name": "Ace Hardware", "domain": "acehardware.com", "search_url": "https://www.acehardware.com/search?query={query}", "clearance_url": "https://www.acehardware.com/departments/sale", "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Home", "Tools"], "request_delay": 3.0, "enabled": True},
    {"key": "truevalue", "name": "True Value", "domain": "truevalue.com", "search_url": "https://www.truevalue.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Home", "Tools"], "request_delay": 3.0, "enabled": True},
    {"key": "build", "name": "Build.com", "domain": "build.com", "search_url": "https://www.build.com/search?term={query}", "clearance_url": "https://www.build.com/deals", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Home"], "request_delay": 3.0, "enabled": True},
    {"key": "christmastreeshops", "name": "Christmas Tree Shops", "domain": "christmastreeshops.com", "search_url": "https://www.christmastreeshops.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Home", "Seasonal"], "request_delay": 3.0, "enabled": True},
    {"key": "tuesdaymorning", "name": "Tuesday Morning", "domain": "tuesdaymorning.com", "search_url": "https://www.tuesdaymorning.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Home", "Closeouts"], "request_delay": 3.0, "enabled": True},
    {"key": "kirklands", "name": "Kirkland's", "domain": "kirklands.com", "search_url": "https://www.kirklands.com/search?q={query}", "clearance_url": "https://www.kirklands.com/category/Sale/pc/2647.uts", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Home"], "request_delay": 3.0, "enabled": True},

    # ── Apparel & Fashion ──────────────────────────────────────────────────────
    {"key": "asos", "name": "ASOS", "domain": "asos.com", "search_url": "https://www.asos.com/us/search/?q={query}", "clearance_url": "https://www.asos.com/us/sale/", "cashback_percent": 3.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Apparel"], "request_delay": 3.0, "enabled": True},
    {"key": "shein", "name": "SHEIN", "domain": "shein.com", "search_url": "https://us.shein.com/pdsearch/{query}", "clearance_url": "https://us.shein.com/sale.html", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Apparel"], "request_delay": 3.0, "enabled": True},
    {"key": "hm", "name": "H&M", "domain": "hm.com", "search_url": "https://www2.hm.com/en_us/search-results.html?q={query}", "clearance_url": "https://www2.hm.com/en_us/sale.html", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Apparel"], "request_delay": 3.0, "enabled": True},
    {"key": "zara", "name": "Zara", "domain": "zara.com", "search_url": "https://www.zara.com/us/en/search?searchTerm={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Apparel"], "request_delay": 3.0, "enabled": True},
    {"key": "express", "name": "Express", "domain": "express.com", "search_url": "https://www.express.com/search?q={query}", "clearance_url": "https://www.express.com/clothing/clearance/", "cashback_percent": 3.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Apparel"], "request_delay": 3.0, "enabled": True},
    {"key": "forever21", "name": "Forever 21", "domain": "forever21.com", "search_url": "https://www.forever21.com/us/search/{query}", "clearance_url": "https://www.forever21.com/us/shop/sale/", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Apparel"], "request_delay": 3.0, "enabled": True},
    {"key": "abercrombie", "name": "Abercrombie & Fitch", "domain": "abercrombie.com", "search_url": "https://www.abercrombie.com/shop/us/search?searchTerm={query}", "clearance_url": "https://www.abercrombie.com/shop/us/clearance", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Apparel"], "request_delay": 3.0, "enabled": True},
    {"key": "hollister", "name": "Hollister", "domain": "hollisterco.com", "search_url": "https://www.hollisterco.com/shop/us/search?searchTerm={query}", "clearance_url": "https://www.hollisterco.com/shop/us/clearance", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Apparel"], "request_delay": 3.0, "enabled": True},
    {"key": "torrid", "name": "Torrid", "domain": "torrid.com", "search_url": "https://www.torrid.com/search?q={query}", "clearance_url": "https://www.torrid.com/clearance/", "cashback_percent": 3.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Apparel"], "request_delay": 3.0, "enabled": True},
    {"key": "lanebryant", "name": "Lane Bryant", "domain": "lanebryant.com", "search_url": "https://www.lanebryant.com/search?q={query}", "clearance_url": "https://www.lanebryant.com/clearance/", "cashback_percent": 3.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Apparel"], "request_delay": 3.0, "enabled": True},
    {"key": "hottopic", "name": "Hot Topic", "domain": "hottopic.com", "search_url": "https://www.hottopic.com/search?q={query}", "clearance_url": "https://www.hottopic.com/sale/clearance/", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Apparel", "Toys"], "request_delay": 3.0, "enabled": True},
    {"key": "boxlunch", "name": "BoxLunch", "domain": "boxlunch.com", "search_url": "https://www.boxlunch.com/search?q={query}", "clearance_url": "https://www.boxlunch.com/sale/clearance/", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Apparel", "Toys"], "request_delay": 3.0, "enabled": True},
    {"key": "anthropologie", "name": "Anthropologie", "domain": "anthropologie.com", "search_url": "https://www.anthropologie.com/search?q={query}", "clearance_url": "https://www.anthropologie.com/sale", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Apparel", "Home"], "request_delay": 3.0, "enabled": True},
    {"key": "freepeople", "name": "Free People", "domain": "freepeople.com", "search_url": "https://www.freepeople.com/search/?q={query}", "clearance_url": "https://www.freepeople.com/sale/", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Apparel"], "request_delay": 3.0, "enabled": True},
    {"key": "uniqlo", "name": "Uniqlo", "domain": "uniqlo.com", "search_url": "https://www.uniqlo.com/us/en/search?q={query}", "clearance_url": "https://www.uniqlo.com/us/en/sale", "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Apparel"], "request_delay": 3.0, "enabled": True},
    {"key": "lululemon", "name": "Lululemon", "domain": "lululemon.com", "search_url": "https://shop.lululemon.com/search?Ntt={query}", "clearance_url": "https://shop.lululemon.com/c/sale", "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Apparel", "Sports & Outdoors"], "request_delay": 3.0, "enabled": True},

    # ── Footwear ───────────────────────────────────────────────────────────────
    {"key": "footlocker", "name": "Foot Locker", "domain": "footlocker.com", "search_url": "https://www.footlocker.com/search?query={query}", "clearance_url": "https://www.footlocker.com/category/sale.html", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Footwear"], "request_delay": 3.0, "enabled": True},
    {"key": "finishline", "name": "Finish Line", "domain": "finishline.com", "search_url": "https://www.finishline.com/store/browse?Ntt={query}", "clearance_url": "https://www.finishline.com/store/sale", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Footwear"], "request_delay": 3.0, "enabled": True},
    {"key": "zappos", "name": "Zappos", "domain": "zappos.com", "search_url": "https://www.zappos.com/search?term={query}", "clearance_url": "https://www.zappos.com/sale", "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Footwear", "Apparel"], "request_delay": 3.0, "enabled": True},
    {"key": "6pm", "name": "6pm", "domain": "6pm.com", "search_url": "https://www.6pm.com/search?term={query}", "clearance_url": None, "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Footwear", "Apparel"], "request_delay": 3.0, "enabled": True},
    {"key": "shoebacca", "name": "Shoebacca", "domain": "shoebacca.com", "search_url": "https://www.shoebacca.com/search?q={query}", "clearance_url": "https://www.shoebacca.com/clearance/", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Footwear"], "request_delay": 3.0, "enabled": True},
    {"key": "newbalance", "name": "New Balance", "domain": "newbalance.com", "search_url": "https://www.newbalance.com/search?q={query}", "clearance_url": "https://www.newbalance.com/sale/", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Footwear"], "request_delay": 3.0, "enabled": True},
    {"key": "skechers", "name": "Skechers", "domain": "skechers.com", "search_url": "https://www.skechers.com/search?q={query}", "clearance_url": "https://www.skechers.com/sale/", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Footwear"], "request_delay": 3.0, "enabled": True},

    # ── Toys & Games ───────────────────────────────────────────────────────────
    {"key": "jellycat", "name": "Jellycat", "domain": "jellycat.com", "search_url": "https://www.jellycat.com/us/search/?q={query}", "clearance_url": "https://www.jellycat.com/us/sale/", "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Toys", "Kids"], "request_delay": 3.0, "enabled": True},
    {"key": "entertainmentearth", "name": "Entertainment Earth", "domain": "entertainmentearth.com", "search_url": "https://www.entertainmentearth.com/s/?query1={query}", "clearance_url": "https://www.entertainmentearth.com/s/sale-clearance", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Toys"], "request_delay": 3.0, "enabled": True},
    {"key": "toywiz", "name": "ToyWiz", "domain": "toywiz.com", "search_url": "https://www.toywiz.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Toys"], "request_delay": 3.0, "enabled": True},
    {"key": "toysuniverse", "name": "Fat Brain Toys", "domain": "fatbraintoys.com", "search_url": "https://www.fatbraintoys.com/search?q={query}", "clearance_url": "https://www.fatbraintoys.com/sale/", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Toys", "Kids"], "request_delay": 3.0, "enabled": True},
    {"key": "hasbropulse", "name": "Hasbro Pulse", "domain": "hasbropulse.com", "search_url": "https://hasbropulse.com/search?q={query}", "clearance_url": "https://hasbropulse.com/collections/sale", "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Toys"], "request_delay": 3.0, "enabled": True},
    {"key": "barnesandnoble", "name": "Barnes & Noble", "domain": "barnesandnoble.com", "search_url": "https://www.barnesandnoble.com/s/{query}", "clearance_url": "https://www.barnesandnoble.com/b/bargain-books/_/N-2bkv", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Toys", "Kids", "Office"], "request_delay": 3.0, "enabled": True},

    # ── Baby & Kids ────────────────────────────────────────────────────────────
    {"key": "buybuybaby", "name": "buybuy BABY", "domain": "buybuybaby.com", "search_url": "https://www.buybuybaby.com/s/{query}", "clearance_url": None, "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Kids"], "request_delay": 3.0, "enabled": True},
    {"key": "childrensplace", "name": "The Children's Place", "domain": "childrensplace.com", "search_url": "https://www.childrensplace.com/us/search/{query}", "clearance_url": "https://www.childrensplace.com/us/c/clearance", "cashback_percent": 3.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Kids", "Apparel"], "request_delay": 3.0, "enabled": True},
    {"key": "gymboree", "name": "Gymboree", "domain": "gymboree.com", "search_url": "https://www.gymboree.com/us/search/{query}", "clearance_url": "https://www.gymboree.com/us/c/clearance", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Kids", "Apparel"], "request_delay": 3.0, "enabled": True},
    {"key": "primarydotcom", "name": "Primary", "domain": "primary.com", "search_url": "https://www.primary.com/search?q={query}", "clearance_url": "https://www.primary.com/shop/sale", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Kids", "Apparel"], "request_delay": 3.0, "enabled": True},

    # ── Office & School ────────────────────────────────────────────────────────
    {"key": "quill", "name": "Quill", "domain": "quill.com", "search_url": "https://www.quill.com/search?q={query}", "clearance_url": "https://www.quill.com/deals/", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Office"], "request_delay": 3.0, "enabled": True},
    {"key": "bulkofficesupply", "name": "Bulk Office Supply", "domain": "bulkofficesupply.com", "search_url": "https://www.bulkofficesupply.com/search?q={query}", "clearance_url": None, "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Office"], "request_delay": 3.0, "enabled": True},
    {"key": "schoolspecialty", "name": "School Specialty", "domain": "schoolspecialty.com", "search_url": "https://www.schoolspecialty.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Office", "Kids"], "request_delay": 3.0, "enabled": True},

    # ── Automotive ─────────────────────────────────────────────────────────────
    {"key": "autozone", "name": "AutoZone", "domain": "autozone.com", "search_url": "https://www.autozone.com/searchresults?searchText={query}", "clearance_url": None, "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Automotive"], "request_delay": 3.0, "enabled": True},
    {"key": "oreillyauto", "name": "O'Reilly Auto Parts", "domain": "oreillyauto.com", "search_url": "https://www.oreillyauto.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Automotive"], "request_delay": 3.0, "enabled": True},
    {"key": "advanceautoparts", "name": "Advance Auto Parts", "domain": "advanceautoparts.com", "search_url": "https://shop.advanceautoparts.com/search/{query}", "clearance_url": None, "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Automotive"], "request_delay": 3.0, "enabled": True},
    {"key": "rockauto", "name": "RockAuto", "domain": "rockauto.com", "search_url": "https://www.rockauto.com/en/partsearch/?partnum={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Automotive"], "request_delay": 3.0, "enabled": True},
    {"key": "pepboys", "name": "Pep Boys", "domain": "pepboys.com", "search_url": "https://www.pepboys.com/search?q={query}", "clearance_url": None, "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Automotive"], "request_delay": 3.0, "enabled": True},

    # ── Closeouts & Discount ───────────────────────────────────────────────────
    {"key": "ollie", "name": "Ollie's", "domain": "ollies.us", "search_url": "https://www.ollies.us/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Closeouts"], "request_delay": 3.0, "enabled": True},
    {"key": "dollartree", "name": "Dollar Tree", "domain": "dollartree.com", "search_url": "https://www.dollartree.com/searchresults?Ntt={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Closeouts", "Seasonal"], "request_delay": 3.0, "enabled": True},
    {"key": "99cents", "name": "99 Cents Only", "domain": "99only.com", "search_url": "https://www.99only.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Closeouts", "Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "bargaintown", "name": "Bargain Hunt", "domain": "bargainhunt.com", "search_url": "https://www.bargainhunt.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Closeouts"], "request_delay": 3.0, "enabled": True},
    {"key": "rossstores", "name": "Ross Stores", "domain": "rossstores.com", "search_url": "https://www.rossstores.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Closeouts", "Apparel"], "request_delay": 3.0, "enabled": True},
    {"key": "grfrg", "name": "Gabe's", "domain": "gabrielbrothers.com", "search_url": "https://www.gabrielbrothers.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Closeouts", "Apparel"], "request_delay": 3.0, "enabled": True},
    {"key": "grfrg2", "name": "Bealls Outlet", "domain": "beallsoutlet.com", "search_url": "https://www.beallsoutlet.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Closeouts", "Apparel"], "request_delay": 3.0, "enabled": True},
    {"key": "nordstromrack", "name": "Nordstrom Rack", "domain": "nordstromrack.com", "search_url": "https://www.nordstromrack.com/search?q={query}", "clearance_url": "https://www.nordstromrack.com/clearance", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Closeouts", "Apparel", "Beauty"], "request_delay": 3.0, "enabled": True},
    {"key": "saksoff5th", "name": "Saks Off 5th", "domain": "saksoff5th.com", "search_url": "https://www.saksoff5th.com/search?q={query}", "clearance_url": "https://www.saksoff5th.com/c/clearance", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Closeouts", "Apparel", "Beauty"], "request_delay": 3.0, "enabled": True},
    {"key": "lastcall", "name": "Neiman Marcus Last Call", "domain": "lastcall.com", "search_url": "https://www.lastcall.com/search?q={query}", "clearance_url": None, "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Closeouts", "Apparel"], "request_delay": 3.0, "enabled": True},

    # ── Specialty & Niche ──────────────────────────────────────────────────────
    {"key": "containerstore", "name": "The Container Store", "domain": "containerstore.com", "search_url": "https://www.containerstore.com/search?q={query}", "clearance_url": "https://www.containerstore.com/sale", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Home"], "request_delay": 3.0, "enabled": True},
    {"key": "cracker_barrel", "name": "Cracker Barrel", "domain": "crackerbarrel.com", "search_url": "https://www.crackerbarrel.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Home", "Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "yankeecandle", "name": "Yankee Candle", "domain": "yankeecandle.com", "search_url": "https://www.yankeecandle.com/search?q={query}", "clearance_url": "https://www.yankeecandle.com/sale/", "cashback_percent": 3.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Home"], "request_delay": 3.0, "enabled": True},
    {"key": "brookstone", "name": "Brookstone", "domain": "brookstone.com", "search_url": "https://www.brookstone.com/search?q={query}", "clearance_url": None, "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Electronics", "Home"], "request_delay": 3.0, "enabled": True},
    {"key": "sharperimage", "name": "Sharper Image", "domain": "sharperimage.com", "search_url": "https://www.sharperimage.com/search?q={query}", "clearance_url": "https://www.sharperimage.com/sale/", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Electronics", "Home"], "request_delay": 3.0, "enabled": True},
    {"key": "spencers", "name": "Spencer's", "domain": "spencersonline.com", "search_url": "https://www.spencersonline.com/search/{query}", "clearance_url": "https://www.spencersonline.com/sale/", "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Seasonal", "Toys"], "request_delay": 3.0, "enabled": True},
    {"key": "spirithalloween", "name": "Spirit Halloween", "domain": "spirithalloween.com", "search_url": "https://www.spirithalloween.com/search?q={query}", "clearance_url": "https://www.spirithalloween.com/sale/", "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Seasonal"], "request_delay": 3.0, "enabled": True},
    {"key": "orientaltrading", "name": "Oriental Trading", "domain": "orientaltrading.com", "search_url": "https://www.orientaltrading.com/search?keywords={query}", "clearance_url": "https://www.orientaltrading.com/sale-a1-551278.fltr", "cashback_percent": 3.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Seasonal", "Party", "Crafts"], "request_delay": 3.0, "enabled": True},
    {"key": "dollskill", "name": "Dolls Kill", "domain": "dollskill.com", "search_url": "https://www.dollskill.com/search?q={query}", "clearance_url": "https://www.dollskill.com/sale.html", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Apparel"], "request_delay": 3.0, "enabled": True},
    {"key": "gamestop2", "name": "ThinkGeek", "domain": "thinkgeek.com", "search_url": "https://www.thinkgeek.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Toys", "Electronics"], "request_delay": 3.0, "enabled": True},
    {"key": "musiciansfriend", "name": "Musician's Friend", "domain": "musiciansfriend.com", "search_url": "https://www.musiciansfriend.com/search?query={query}", "clearance_url": "https://www.musiciansfriend.com/deals", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Electronics"], "request_delay": 3.0, "enabled": True},
    {"key": "guitarcenter", "name": "Guitar Center", "domain": "guitarcenter.com", "search_url": "https://www.guitarcenter.com/search?Ntt={query}", "clearance_url": "https://www.guitarcenter.com/sale", "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Electronics"], "request_delay": 3.0, "enabled": True},
    {"key": "midwayusa", "name": "MidwayUSA", "domain": "midwayusa.com", "search_url": "https://www.midwayusa.com/s?search={query}", "clearance_url": "https://www.midwayusa.com/clearance", "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Sports & Outdoors"], "request_delay": 3.0, "enabled": True},

    # ── Industrial & Safety ────────────────────────────────────────────────────
    {"key": "uline", "name": "Uline", "domain": "uline.com", "search_url": "https://www.uline.com/BL/Search?keywords={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Industrial"], "request_delay": 3.0, "enabled": True},
    {"key": "grainger", "name": "Grainger", "domain": "grainger.com", "search_url": "https://www.grainger.com/search?searchQuery={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Industrial", "Tools"], "request_delay": 3.0, "enabled": True},
    {"key": "mscdirect", "name": "MSC Industrial", "domain": "mscdirect.com", "search_url": "https://www.mscdirect.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Industrial", "Tools"], "request_delay": 3.0, "enabled": True},
    {"key": "globalindustrial", "name": "Global Industrial", "domain": "globalindustrial.com", "search_url": "https://www.globalindustrial.com/g/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Industrial"], "request_delay": 3.0, "enabled": True},

    # ── Pharmacy & Medical ─────────────────────────────────────────────────────
    {"key": "fsa_store", "name": "FSA Store", "domain": "fsastore.com", "search_url": "https://fsastore.com/search?q={query}", "clearance_url": None, "cashback_percent": 1.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Health"], "request_delay": 3.0, "enabled": True},
    {"key": "healthwarehouse", "name": "HealthWarehouse", "domain": "healthwarehouse.com", "search_url": "https://www.healthwarehouse.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Health"], "request_delay": 3.0, "enabled": True},
    {"key": "swansonvitamins", "name": "Swanson Vitamins", "domain": "swansonvitamins.com", "search_url": "https://www.swansonvitamins.com/ncat1/Search?kw={query}", "clearance_url": "https://www.swansonvitamins.com/ncat1/Sale", "cashback_percent": 3.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Health"], "request_delay": 3.0, "enabled": True},
    {"key": "pureformulas", "name": "PureFormulas", "domain": "pureformulas.com", "search_url": "https://www.pureformulas.com/search?q={query}", "clearance_url": "https://www.pureformulas.com/sale", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Health"], "request_delay": 3.0, "enabled": True},
    {"key": "luckyv", "name": "Lucky Vitamin", "domain": "luckyvitamin.com", "search_url": "https://www.luckyvitamin.com/search?q={query}", "clearance_url": "https://www.luckyvitamin.com/clearance", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Health", "Grocery"], "request_delay": 3.0, "enabled": True},

    # ── Convenience & Gas Station Retailers ────────────────────────────────────
    {"key": "sevenneleven", "name": "7-Eleven", "domain": "7-eleven.com", "search_url": "https://www.7-eleven.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery"], "request_delay": 3.0, "enabled": True},
    {"key": "wawa", "name": "Wawa", "domain": "wawa.com", "search_url": "https://www.wawa.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Grocery"], "request_delay": 3.0, "enabled": True},

    # ── Garden & Nursery ───────────────────────────────────────────────────────
    {"key": "gardeners", "name": "Gardener's Supply", "domain": "gardeners.com", "search_url": "https://www.gardeners.com/search?q={query}", "clearance_url": "https://www.gardeners.com/sale", "cashback_percent": 2.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Home", "Outdoors"], "request_delay": 3.0, "enabled": True},

    # ── Warehouse Clubs & Wholesale ────────────────────────────────────────────
    {"key": "restaurantdepot", "name": "Restaurant Depot", "domain": "restaurantdepot.com", "search_url": "https://www.restaurantdepot.com/search?q={query}", "clearance_url": None, "cashback_percent": 0.0, "gift_card_discount": 0.0, "tier": 2, "categories": ["Bulk", "Kitchen"], "request_delay": 3.0, "enabled": True},
]

# ── Indexes (built once at import time) ──────────────────────────────────────

_BY_KEY = {r["key"]: r for r in RETAILERS}
_BY_DOMAIN = {}
for _r in RETAILERS:
    _BY_DOMAIN[_r["domain"]] = _r
    # Also index without TLD for fuzzy matching
    _base = _r["domain"].split(".")[0]
    _BY_DOMAIN[_base] = _r

_BY_NAME_LOWER = {r["name"].lower(): r for r in RETAILERS}


# ── Category Keywords for Auto-Detection ─────────────────────────────────────

CATEGORY_KEYWORDS = {
    "Grocery": [
        "food", "snack", "candy", "chocolate", "cereal", "coffee", "tea", "sauce",
        "spice", "pasta", "rice", "organic", "gluten", "protein bar", "granola",
        "cookie", "cracker", "chip", "popcorn", "nut", "dried fruit", "honey",
        "syrup", "jam", "jelly", "peanut butter", "reeses", "oreo", "hershey",
        "m&m", "skittles", "gummy", "sour patch", "ketchup", "mustard", "mayo",
        "ranch", "salad dressing", "soup", "broth", "canned", "tuna",
        "easter candy", "halloween candy", "christmas candy", "valentine candy",
    ],
    "Health": [
        "vitamin", "supplement", "medicine", "first aid", "bandage", "thermometer",
        "blood pressure", "collagen", "probiotic", "omega", "melatonin", "zinc",
        "magnesium", "ashwagandha", "turmeric", "elderberry", "biotin", "iron",
        "calcium", "fish oil", "multivitamin", "protein powder", "whey", "creatine",
        "bcaa", "pre workout", "post workout", "electrolyte", "pedialyte",
        "tylenol", "advil", "ibuprofen", "allergy", "cold flu", "cough",
    ],
    "Beauty": [
        "makeup", "cosmetic", "skincare", "moisturizer", "shampoo", "conditioner",
        "hair", "nail", "lipstick", "foundation", "mascara", "perfume", "cologne",
        "serum", "toner", "cleanser", "sunscreen", "spf", "lotion", "body wash",
        "deodorant", "razor", "eyeshadow", "blush", "concealer", "primer",
        "setting spray", "curling iron", "flat iron", "hair dryer", "brush",
    ],
    "Sports & Outdoors": [
        "running", "fitness", "gym", "yoga", "hiking", "camping", "fishing",
        "hunting", "bike", "golf", "tennis", "basketball", "football", "soccer",
        "baseball", "swimming", "kayak", "canoe", "climbing", "skateboard",
        "surfing", "snowboard", "ski", "weights", "dumbbell", "kettlebell",
        "resistance band", "treadmill", "elliptical", "exercise",
    ],
    "Seasonal": [
        "easter", "christmas", "halloween", "valentine", "thanksgiving",
        "4th of july", "memorial day", "back to school", "spring", "summer",
        "fall", "winter", "holiday", "stocking stuffer", "advent", "pumpkin",
        "santa", "bunny", "egg hunt", "firework", "patriotic", "harvest",
    ],
    "Electronics": [
        "laptop", "phone", "tablet", "headphone", "speaker", "camera", "tv",
        "monitor", "keyboard", "mouse", "usb", "charger", "cable", "battery",
        "bluetooth", "wireless", "smart home", "alexa", "echo", "roku", "fire stick",
        "gaming", "xbox", "playstation", "nintendo", "switch", "controller",
        "printer", "scanner", "router", "modem", "hard drive", "ssd", "ram",
    ],
    "Home": [
        "furniture", "lamp", "rug", "curtain", "pillow", "towel", "sheet",
        "mattress", "shelf", "organizer", "storage", "decor", "candle", "vase",
        "frame", "mirror", "clock", "basket", "bin", "hanger", "hook",
        "cleaning", "vacuum", "mop", "broom", "sponge", "trash", "laundry",
    ],
    "Pets": [
        "dog", "cat", "pet", "puppy", "kitten", "fish", "bird", "reptile",
        "aquarium", "leash", "collar", "kibble", "treat", "chew", "toy",
        "litter", "cage", "crate", "bed", "bowl", "feeder", "grooming",
    ],
    "Toys": [
        "toy", "lego", "puzzle", "game", "doll", "action figure", "nerf",
        "playset", "board game", "card game", "stuffed animal", "plush",
        "hot wheels", "barbie", "transformers", "pokemon", "minecraft",
        "play-doh", "slime", "craft kit", "building blocks", "rc car",
    ],
    "Tools": [
        "drill", "saw", "wrench", "hammer", "screwdriver", "dewalt", "milwaukee",
        "makita", "ryobi", "bosch", "craftsman", "stanley", "socket", "plier",
        "tape measure", "level", "clamp", "sander", "grinder", "router",
        "compressor", "nail gun", "paint sprayer", "ladder", "work light",
    ],
    "Apparel": [
        "shirt", "pants", "jeans", "dress", "jacket", "coat", "sweater",
        "hoodie", "shorts", "skirt", "underwear", "socks", "belt", "hat",
        "scarf", "gloves", "tie", "suit", "blazer", "leggings", "swimsuit",
    ],
    "Footwear": [
        "shoe", "boot", "sneaker", "sandal", "slipper", "heel", "flat",
        "loafer", "oxford", "running shoe", "hiking boot", "work boot",
        "nike", "adidas", "new balance", "puma", "reebok", "skechers",
    ],
    "Office": [
        "pen", "pencil", "notebook", "binder", "folder", "paper", "envelope",
        "stapler", "tape", "scissors", "marker", "highlighter", "whiteboard",
        "desk", "chair", "filing cabinet", "planner", "calendar", "ink",
    ],
    "Crafts": [
        "yarn", "fabric", "sewing", "knitting", "crochet", "embroidery",
        "paint", "canvas", "brush", "glue", "ribbon", "beads", "stickers",
        "scrapbook", "stamp", "die cut", "cricut", "silhouette",
    ],
    "Automotive": [
        "car", "truck", "auto", "vehicle", "motor oil", "brake", "filter",
        "wiper", "battery", "spark plug", "headlight", "taillight", "bumper",
        "tire", "wheel", "floor mat", "seat cover", "dash cam", "car wash",
        "detailing", "wax", "polish", "obd", "torque wrench", "jack",
    ],
    "Kids": [
        "baby", "toddler", "infant", "newborn", "onesie", "diaper", "wipes",
        "stroller", "car seat", "high chair", "crib", "pacifier", "bottle",
        "sippy cup", "bib", "teether", "nursery", "children",
    ],
    "Kitchen": [
        "cookware", "bakeware", "knife", "cutting board", "blender", "mixer",
        "instant pot", "air fryer", "toaster", "coffee maker", "espresso",
        "pan", "pot", "skillet", "wok", "spatula", "whisk", "tongs",
    ],
    "Bulk": [
        "bulk", "wholesale", "case", "pallet", "multi-pack", "variety pack",
        "club pack", "value pack", "family size", "economy", "warehouse",
    ],
}

# ── Category → Retailer Mapping ──────────────────────────────────────────────

CATEGORY_RETAILERS = {
    "Grocery": ["walmart", "target", "costco", "bjs", "samsclub", "kroger", "meijer",
                 "albertsons", "safeway", "publix", "heb", "foodlion", "fredmeyer",
                 "shoprite", "stopandshop", "pricechopper", "sprouts", "worldmarket",
                 "dollargeneral", "familydollar", "aldi", "traderjoes", "wholefoodsmarket",
                 "thrive", "wegmans", "winco", "harristeeter", "winn-dixie", "hannaford",
                 "smartandfinal", "instacart", "boxed", "sevenneleven", "wawa"],
    "Health": ["cvs", "walgreens", "vitaminshoppe", "vitacost", "gnc", "walmart", "target",
               "costco", "bjs", "riteaid", "sprouts", "kroger", "iherb", "wholefoodsmarket",
               "thrive", "swansonvitamins", "pureformulas", "luckyv", "fsa_store",
               "healthwarehouse", "1800petmeds", "dermstore"],
    "Beauty": ["ulta", "target", "cvs", "walgreens", "macys", "nordstrom", "kohls",
               "walmart", "belk", "jcpenney", "sephora", "sallybeauty", "dermstore",
               "bathandbodyworks", "colourpop", "elfcosmetics", "lookfantastic",
               "fragrancenet", "loccitane", "beautylish", "theordinary",
               "nordstromrack", "saksoff5th"],
    "Sports & Outdoors": ["dickssportinggoods", "academy", "rei", "cabelas", "basspro",
                          "sierra", "big5", "walmart", "target", "backcountry", "moosejaw",
                          "ems", "scheels", "roguefitness", "sportsmanswarehouse",
                          "runningwarehouse", "tacklewarehouse", "soccercom",
                          "dickssportinggoods2", "midwayusa", "lululemon"],
    "Seasonal": ["walmart", "target", "kohls", "biglots", "fivebelow", "partycity",
                 "dollargeneral", "familydollar", "oceanstatejoblot", "cvs", "walgreens",
                 "spirithalloween", "orientaltrading", "spencers", "christmastreeshops",
                 "dollartree"],
    "Electronics": ["bestbuy", "newegg", "bhphoto", "gamestop", "microcenter",
                    "pcrichard", "walmart", "target", "staples", "officedepot",
                    "adorama", "monoprice", "tigerdirect", "dell", "hp", "lenovo",
                    "cdw", "bhphoto2", "brookstone", "sharperimage", "musiciansfriend",
                    "guitarcenter"],
    "Home": ["homedepot", "lowes", "wayfair", "overstock", "athome", "ikea",
             "crateandbarrel", "potterybarn", "westelm", "williamssonoma",
             "menards", "walmart", "target", "biglots", "worldmarket",
             "bedbathandbeyond", "pier1", "zgallerie", "hayneedle", "houzz",
             "acehardware", "truevalue", "build", "containerstore", "kirklands",
             "restorationhardware", "bathandbodyworks", "yankeecandle",
             "anthropologie", "christmastreeshops", "tuesdaymorning", "gardeners"],
    "Pets": ["petco", "petsmart", "tractorsupply", "walmart", "target", "costco",
             "chewy", "entirelypets", "petflow", "petmountain", "1800petmeds"],
    "Apparel": ["kohls", "macys", "nordstrom", "tjmaxx", "marshalls", "jcpenney",
                "oldnavy", "gap", "bananarepublic", "ae", "urbanoutfitters",
                "burlington", "belk", "pacsun", "asos", "shein", "hm", "zara",
                "express", "forever21", "abercrombie", "hollister", "torrid",
                "lanebryant", "hottopic", "boxlunch", "anthropologie", "freepeople",
                "uniqlo", "lululemon", "dollskill", "zappos", "nordstromrack",
                "saksoff5th", "rossstores"],
    "Footwear": ["dsw", "shoecarnival", "famousfootwear", "journeys",
                 "dickssportinggoods", "nordstrom", "kohls", "macys",
                 "footlocker", "finishline", "zappos", "6pm", "shoebacca",
                 "newbalance", "skechers", "runningwarehouse"],
    "Toys": ["walmart", "target", "fivebelow", "gamestop", "costco", "biglots",
             "kohls", "macys", "entertainmentearth", "toywiz", "toysuniverse",
             "hasbropulse", "barnesandnoble", "hottopic", "boxlunch", "spencers"],
    "Tools": ["homedepot", "lowes", "harborfreight", "menards", "zoro",
              "tractorsupply", "farmandfleet", "ruralking", "acehardware",
              "truevalue", "grainger", "mscdirect"],
    "Office": ["staples", "officedepot", "walmart", "target", "quill",
               "bulkofficesupply", "schoolspecialty", "cdw", "barnesandnoble"],
    "Crafts": ["michaels", "hobbylobby", "joann", "walmart", "orientaltrading"],
    "Kids": ["carters", "oshkosh", "target", "walmart", "kohls", "jcpenney",
             "oldnavy", "buybuybaby", "childrensplace", "gymboree", "primarydotcom",
             "toysuniverse", "barnesandnoble", "schoolspecialty"],
    "Kitchen": ["williamssonoma", "surlatable", "crateandbarrel", "walmart",
                "target", "costco", "webstaurantstore", "restaurantdepot"],
    "Bulk": ["costco", "bjs", "samsclub", "walmart", "smartandfinal", "boxed",
             "restaurantdepot"],
    "Farm": ["tractorsupply", "ruralking", "farmandfleet", "bfrg"],
    "Outdoors": ["rei", "cabelas", "basspro", "dickssportinggoods", "academy",
                 "tractorsupply", "sierra", "backcountry", "moosejaw", "ems",
                 "sportsmanswarehouse", "gardeners"],
    "Industrial": ["zoro", "webstaurantstore", "homedepot", "lowes", "uline",
                   "grainger", "mscdirect", "globalindustrial"],
    "Closeouts": ["biglots", "oceanstatejoblot", "fivebelow", "dollargeneral",
                  "ollie", "dollartree", "99cents", "bargaintown", "rossstores",
                  "grfrg", "grfrg2", "nordstromrack", "saksoff5th", "lastcall",
                  "tuesdaymorning"],
    "Party": ["partycity", "walmart", "target", "fivebelow", "orientaltrading",
              "spencers", "spirithalloween"],
    "Automotive": ["autozone", "oreillyauto", "advanceautoparts", "rockauto",
                   "pepboys"],
}


# ── Lookup Functions ─────────────────────────────────────────────────────────

def get_retailer(domain_or_name):
    """Look up a retailer by domain, key, or display name.

    Args:
        domain_or_name: e.g. "walmart.com", "walmart", or "Walmart"

    Returns:
        Retailer dict or None.
    """
    if not domain_or_name:
        return None
    q = domain_or_name.strip().lower()

    # Strip protocol and www
    if "://" in q:
        q = urlparse(q).netloc.lower()
    q = q.replace("www.", "")

    # Try exact key
    if q in _BY_KEY:
        return _BY_KEY[q]

    # Try domain
    if q in _BY_DOMAIN:
        return _BY_DOMAIN[q]

    # Try name
    if q in _BY_NAME_LOWER:
        return _BY_NAME_LOWER[q]

    # Fuzzy: check if query is substring of any domain or name
    for r in RETAILERS:
        if q in r["domain"] or q in r["name"].lower() or q in r["key"]:
            return r

    return None


def get_retailers_by_category(category):
    """Get all retailers that serve a given category.

    Args:
        category: e.g. "Grocery", "Health", "Beauty"

    Returns:
        List of retailer dicts, Tier 1 first, then Tier 2 sorted by cashback.
    """
    cat_keys = CATEGORY_RETAILERS.get(category, [])
    results = [_BY_KEY[k] for k in cat_keys if k in _BY_KEY and _BY_KEY[k].get("enabled", True)]
    # Sort: Tier 1 first, then by cashback descending
    results.sort(key=lambda r: (-1 if r["tier"] == 1 else 0, -r.get("cashback_percent", 0)))
    return results


def get_search_url(retailer, query):
    """Build a search URL for a retailer and query string.

    Args:
        retailer: Retailer dict (from get_retailer or RETAILERS list).
        query: Search query string.

    Returns:
        Formatted search URL string, or None if no search_url template.
    """
    template = retailer.get("search_url")
    if not template:
        return None
    return template.format(query=quote_plus(query))


def get_all_retailers(tier=None, enabled=True):
    """Get all retailers, optionally filtered by tier and enabled status.

    Args:
        tier: 1 or 2 to filter, None for all.
        enabled: If True, only return enabled retailers.

    Returns:
        List of retailer dicts.
    """
    results = RETAILERS
    if tier is not None:
        results = [r for r in results if r["tier"] == tier]
    if enabled:
        results = [r for r in results if r.get("enabled", True)]
    return results


def get_clearance_urls(category=None):
    """Get clearance/deals URLs for retailers.

    Args:
        category: If specified, only return retailers in that category.

    Returns:
        List of (retailer_dict, clearance_url) tuples.
    """
    if category:
        retailers = get_retailers_by_category(category)
    else:
        retailers = get_all_retailers(enabled=True)

    return [
        (r, r["clearance_url"])
        for r in retailers
        if r.get("clearance_url")
    ]


def detect_category(query):
    """Auto-detect product category from a search query.

    Args:
        query: Search term like "reeses easter eggs" or "protein powder"

    Returns:
        List of matching category names, ranked by keyword match count.
    """
    if not query:
        return []
    query_lower = query.lower()
    scores = {}

    for category, keywords in CATEGORY_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw in query_lower:
                # Longer keyword matches = higher score
                score += len(kw.split())
        if score > 0:
            scores[category] = score

    # Sort by score descending
    ranked = sorted(scores.keys(), key=lambda c: scores[c], reverse=True)
    return ranked


def get_retailers_for_product(query_or_category, max_retailers=15):
    """THE KEY FUNCTION: auto-detect category from query, return ranked retailers.

    This is the smart routing engine. It does NOT search all 100 retailers —
    it picks the right 5-15 based on what the product is.

    Args:
        query_or_category: A search term ("reeses easter eggs") or category name ("Grocery").
        max_retailers: Max retailers to return (default: 15).

    Returns:
        List of retailer dicts, ranked by relevance (Tier 1 first, then Tier 2 by cashback).
    """
    # Check if it's a known category name first
    if query_or_category in CATEGORY_RETAILERS:
        categories = [query_or_category]
    else:
        categories = detect_category(query_or_category)

    if not categories:
        # Fallback: return top Tier 1 retailers
        return get_all_retailers(tier=1, enabled=True)[:max_retailers]

    # Collect retailers from all detected categories (dedup, preserve order)
    seen_keys = set()
    ranked = []

    for cat in categories:
        cat_retailers = get_retailers_by_category(cat)
        for r in cat_retailers:
            if r["key"] not in seen_keys:
                seen_keys.add(r["key"])
                ranked.append(r)

    # Sort: Tier 1 first, then by cashback descending
    ranked.sort(key=lambda r: (-1 if r["tier"] == 1 else 0, -r.get("cashback_percent", 0)))

    return ranked[:max_retailers]


def get_cashback_map():
    """Build a name → cashback_percent dict for all retailers.

    Compatible with calculate_fba_profitability.RETAILER_CASHBACK_ESTIMATES format.
    """
    return {r["name"]: r["cashback_percent"] for r in RETAILERS if r.get("cashback_percent", 0) > 0}


# ── CLI Test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    all_r = get_all_retailers()
    print(f"Total retailers: {len(all_r)}")
    print(f"Tier 1: {len(get_all_retailers(tier=1))}")
    print(f"Tier 2: {len(get_all_retailers(tier=2))}")

    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        print(f"\nSmart routing for: '{query}'")
        categories = detect_category(query)
        print(f"Detected categories: {categories}")
        retailers = get_retailers_for_product(query)
        print(f"Retailers ({len(retailers)}):")
        for r in retailers:
            tier_label = "T1" if r["tier"] == 1 else "T2"
            print(f"  [{tier_label}] {r['name']:25s} | {r['cashback_percent']}% cashback | {', '.join(r['categories'])}")
    else:
        print("\nUsage: python retailer_registry.py <search query>")
        print("Example: python retailer_registry.py reeses easter eggs")
        print("Example: python retailer_registry.py protein powder")
        print("Example: python retailer_registry.py dewalt drill")

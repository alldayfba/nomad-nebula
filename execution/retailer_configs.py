#!/usr/bin/env python3
"""
Script: retailer_configs.py
Purpose: Per-retailer CSS selector configurations for product data extraction.
         Maps URL domain → CSS selectors for scraping product pages and category pages.
Inputs:  URL string
Outputs: (retailer_key, config_dict) tuple
"""

from urllib.parse import urlparse


RETAILER_CONFIGS = {
    "walmart.com": {
        "name": "Walmart",
        "product_page": {
            "title": 'h1[itemprop="name"], h1#main-title, h1.lh-copy',
            "price": 'span[itemprop="price"], span.inline-flex [aria-hidden="true"], span.price-characteristic',
            "sale_price": 'span.was-price, div.price-old span',
            "upc": 'meta[itemprop="gtin13"], meta[itemprop="gtin12"]',
            "image": 'img[data-testid="hero-image"], img.prod-hero-image, div.relative img',
            "category": 'nav[aria-label="breadcrumb"] a, ol.breadcrumb-list a',
        },
        "category_page": {
            "product_cards": 'div[data-item-id], div.mb0, div[data-testid="list-view"]',
            "card_link": 'a[link-identifier], a.absolute, a[href*="/ip/"]',
            "card_price": 'div[data-automation-id="product-price"] span.f2, span.w_iUH7',
            "card_title": 'span[data-automation-id="product-title"], span.lh-title',
        },
        "pagination": {
            "next_button": 'a[aria-label="Next Page"], nav[aria-label="pagination"] a:last-child',
            "max_pages": 5,
        },
        "request_delay": 2.0,
    },
    "target.com": {
        "name": "Target",
        "product_page": {
            "title": 'h1[data-test="product-title"], h1.Heading, h1',
            "price": 'span[data-test="product-price"], div[data-test="product-price"]',
            "sale_price": 'span[data-test="product-regular-price"], span.h-text-grayDark',
            "upc": None,
            "image": 'div[data-test="image-gallery"] img, img[data-test="product-image"]',
            "category": 'div[data-test="breadcrumb"] a, nav[aria-label="Breadcrumb"] a',
        },
        "category_page": {
            "product_cards": 'div[data-test="@web/site-top-of-funnel/ProductCardWrapper"], div[data-test="product-grid"] > div, div[data-test="@web/ProductCard"]',
            "card_link": 'a[data-test="@web/ProductCard/title"], a[data-test="product-title"], a[href*="/p/"]',
            "card_price": 'span[data-test="current-price"] span',
            "card_title": 'a[data-test="@web/ProductCard/title"], a[data-test="product-title"]',
        },
        "pagination": {
            "next_button": 'button[data-test="next"], a[aria-label="next"]',
            "max_pages": 5,
        },
        "request_delay": 2.5,
    },
    "homedepot.com": {
        "name": "Home Depot",
        "product_page": {
            "title": 'h1.product-title__title, h1.sui-text-primary, h1',
            "price": 'div.price-format__main-price span, span[itemprop="price"]',
            "sale_price": 'div.price-format__was-price span',
            "upc": None,
            "image": 'img.mediagallery__mainimage, img.stretchy, div[data-testid="media-gallery"] img',
            "category": 'nav.breadcrumb a, nav[aria-label="Breadcrumb"] a',
        },
        "category_page": {
            "product_cards": 'div.browse-search__pod, div[data-component="product-pod"], div.plp-pod',
            "card_link": 'a.product-pod--ie-fix, a[href*="/p/"]',
            "card_price": 'div.price-format__main-price span, span.price-format__main-price',
            "card_title": 'span.product-pod__title-default, a.product-pod__title',
        },
        "pagination": {
            "next_button": 'a.hd-pagination__link[aria-label="Next"], nav[aria-label="Pagination"] a:last-child',
            "max_pages": 5,
        },
        "request_delay": 2.0,
    },
    "cvs.com": {
        "name": "CVS",
        "product_page": {
            "title": 'h1.product-name, h1[data-testid="product-title"], h1',
            "price": 'span[data-testid="regular-price"], span.css-1jp1776, div.price span',
            "sale_price": 'span[data-testid="sale-price"], span.sale-price',
            "upc": None,
            "image": 'img.product-hero-image, img[data-testid="product-image"], div.product-image img',
            "category": 'nav[aria-label="breadcrumb"] a, nav.breadcrumb a',
        },
        "category_page": {
            "product_cards": 'div.product-card, div[data-testid="product-card"], li.product-card',
            "card_link": 'a.product-card__link, a[href*="/shop/"]',
            "card_price": 'span.product-card__price, div.product-price span',
            "card_title": 'span.product-card__title, a.product-name',
        },
        "pagination": {
            "next_button": 'a[aria-label="Next"], button[aria-label="Next Page"]',
            "max_pages": 3,
        },
        "request_delay": 3.0,
    },
    "walgreens.com": {
        "name": "Walgreens",
        "product_page": {
            "title": 'h1.product__title, h1#productTitle, h1',
            "price": 'span.product__price, span[class*="Price"], div.product-price span',
            "sale_price": 'span.product__price--sale, span.was-price',
            "upc": None,
            "image": 'img.product__image, img#productImg, div.product-image img',
            "category": 'nav.breadcrumb a, ol.breadcrumb a',
        },
        "category_page": {
            "product_cards": 'div.product-card, li.product-card, div[data-testid="product-card"]',
            "card_link": 'a.product-card__link, a[href*="/store/"]',
            "card_price": 'span.product-card__price, div.product-price',
            "card_title": 'span.product-card__title, h2.product-card__title',
        },
        "pagination": {
            "next_button": 'a[aria-label="Next"], button.next-page',
            "max_pages": 3,
        },
        "request_delay": 3.0,
    },
    "costco.com": {
        "name": "Costco",
        "product_page": {
            "title": 'h1[automation-id="productName"], h1.product-title, h1',
            "price": 'div.price, span.value, div[automation-id="productPrice"]',
            "sale_price": 'div.you-pay span, span.discount-price',
            "upc": None,
            "image": 'img.product-image, img[automation-id="productImageMain"]',
            "category": 'ul.breadcrumb a, nav[aria-label="breadcrumb"] a',
        },
        "category_page": {
            "product_cards": 'div.product-tile, div.product, div[automation-id="productList"] > div',
            "card_link": 'a.product-tile-link, a[automation-id="productDescriptionLink"]',
            "card_price": 'div.price, span.value',
            "card_title": 'span.description, a.product-tile-link span',
        },
        "pagination": {
            "next_button": 'a[rel="next"], button[aria-label="Next"]',
            "max_pages": 3,
        },
        "request_delay": 2.5,
    },
    "bjs.com": {
        "name": "BJ's",
        "product_page": {
            "title": 'h1.product-title, h1[data-testid="product-title"], h1',
            "price": 'span.price, div.price span, span[data-testid="price"]',
            "sale_price": 'span.sale-price, span.was-price, div.instant-savings span',
            "upc": None,
            "image": 'img.product-image, div.product-image img, img[data-testid="product-image"]',
            "category": 'nav.breadcrumb a, ul.breadcrumbs a',
        },
        "category_page": {
            "product_cards": 'div.product-tile, div.product-card, div[data-testid="product-tile"]',
            "card_link": 'a.product-link, a[href*="/product/"]',
            "card_price": 'span.price, div.product-price span',
            "card_title": 'h2.product-title, span.product-title, a.product-link',
        },
        "pagination": {
            "next_button": 'a[aria-label="Next"], button[aria-label="Next Page"]',
            "max_pages": 3,
        },
        "request_delay": 2.5,
    },
    "samsclub.com": {
        "name": "Sam's Club",
        "product_page": {
            "title": 'h1.sc-product-title, h1[data-testid="product-title"], h1',
            "price": 'span.Price-group, span[data-testid="price"], div.Price span',
            "sale_price": 'span.Price-group--instant-savings, span.was-price',
            "upc": None,
            "image": 'img.sc-product-image, img[data-testid="product-image"], div.product-image img',
            "category": 'nav.breadcrumb a, ol.breadcrumb a',
        },
        "category_page": {
            "product_cards": 'div.sc-product-card, div[data-testid="product-card"], div.sc-plp-cards-card',
            "card_link": 'a.sc-product-card-link, a[href*="/ip/"], a[href*="/product/"]',
            "card_price": 'span.Price-group, span[data-testid="price"]',
            "card_title": 'span.sc-product-card-title, h2[data-testid="product-title"]',
        },
        "pagination": {
            "next_button": 'a[aria-label="Next Page"], button[aria-label="Next"]',
            "max_pages": 3,
        },
        "request_delay": 2.5,
    },
    "kohls.com": {
        "name": "Kohl's",
        "product_page": {
            "title": 'h1.pdp-product-title, h1[data-testid="product-title"], h1.title',
            "price": 'span.sale-price, span[data-testid="current-price"], div.price-block span.sale',
            "sale_price": 'span.original-price, span[data-testid="original-price"], div.price-block span.original',
            "upc": None,
            "image": 'img.pdp-image, img[data-testid="product-image"], div.product-image img',
            "category": 'nav.breadcrumb a, ul.breadcrumbs a',
        },
        "category_page": {
            "product_cards": 'div.products-container li.product, ul.products_list li, div[data-testid="product-card"]',
            "card_link": 'a.thumbnail-link, a[data-testid="product-link"], a[href*="/product/"]',
            "card_price": 'span.sale-price, span.prod_price_amount, div.price-wrap span.sale',
            "card_title": 'span.prod_nameBlock, h2.prod-title, a.prod-title-text',
        },
        "pagination": {
            "next_button": 'a[aria-label="Next"], a.page-next, li.next a',
            "max_pages": 5,
        },
        "request_delay": 2.5,
    },
    "bestbuy.com": {
        "name": "Best Buy",
        "product_page": {
            "title": 'h1.heading, h1[data-testid="product-title"], div.sku-title h1',
            "price": 'div.priceView-hero-price span[aria-hidden="true"], span[data-testid="customer-price"] span',
            "sale_price": 'div.pricing-price__regular-price span, span.pricing-price__was-price',
            "upc": None,
            "image": 'img.primary-image, img[data-testid="product-image"], div.shop-media-gallery img',
            "category": 'nav.breadcrumb a, ol.breadcrumb-list a',
        },
        "category_page": {
            "product_cards": 'li.sku-item, div.sku-item, ol.sku-item-list > li',
            "card_link": 'a.image-link, h4.sku-title a, a[href*="/site/"]',
            "card_price": 'div.priceView-hero-price span[aria-hidden="true"], span.priceView-customer-price span',
            "card_title": 'h4.sku-title a, h4.sku-header a',
        },
        "pagination": {
            "next_button": 'a.sku-list-page-next, a[aria-label="Next Page"]',
            "max_pages": 5,
        },
        "request_delay": 2.0,
    },
    "lowes.com": {
        "name": "Lowe's",
        "product_page": {
            "title": 'h1.pdp-header, h1[data-selector="pdp-product-title"], h1',
            "price": 'span.aPrice, span[data-selector="price"], div.art-price-wrapper span',
            "sale_price": 'span.aPrice--was, span[data-selector="was-price"]',
            "upc": None,
            "image": 'img.pdp-image, img[data-selector="product-image"], div.met-product-image img',
            "category": 'nav.breadcrumb a, ol.breadcrumbs a',
        },
        "category_page": {
            "product_cards": 'div.plp-card, div[data-selector="product-card"], li.plp-grid__item',
            "card_link": 'a[data-selector="product-image-link"], a[href*="/pd/"], a.product-link',
            "card_price": 'span.aPrice, span[data-selector="price"]',
            "card_title": 'a[data-selector="product-title"], h3.product-title a, span.product-title',
        },
        "pagination": {
            "next_button": 'a[aria-label="Next Page"], a.pagination-next',
            "max_pages": 5,
        },
        "request_delay": 2.0,
    },
    "macys.com": {
        "name": "Macy's",
        "product_page": {
            "title": 'h1.pdp-title, h1[data-auto="product-name"], div.product-title h1',
            "price": 'span.lowest-sale-price, span[data-auto="price-sale"], div.price span.sale',
            "sale_price": 'span.regular-price, span[data-auto="price-regular"], div.price span.original',
            "upc": None,
            "image": 'img.pdp-image, img[data-auto="product-image"], picture.main-image img',
            "category": 'nav.breadcrumb a, ul.bread-crumb a',
        },
        "category_page": {
            "product_cards": 'div.productThumbnail, li.cell, div[data-auto="product-thumbnail"]',
            "card_link": 'a.productDescLink, a[data-auto="product-link"], a[href*="/shop/product/"]',
            "card_price": 'span.lowest-sale-price, div.prices span.sale',
            "card_title": 'div.productDescription a, a.productDescLink, span[data-auto="product-name"]',
        },
        "pagination": {
            "next_button": 'a[aria-label="Next"], li.next-page a',
            "max_pages": 5,
        },
        "request_delay": 2.5,
    },
    "ulta.com": {
        "name": "Ulta Beauty",
        "product_page": {
            "title": 'h1.ProductMainSection__productName, h1[data-testid="product-title"], h1.product-title',
            "price": 'span.ProductMainSection__productPrice, span[data-testid="product-price"], div.product-price span',
            "sale_price": 'span.ProductMainSection__originalPrice, span.product-original-price',
            "upc": None,
            "image": 'img.ProductMainSection__image, img[data-testid="product-image"], div.product-image img',
            "category": 'nav.breadcrumb a, div.Breadcrumb a',
        },
        "category_page": {
            "product_cards": 'div.ProductCard, div[data-testid="product-card"], li.ProductCard',
            "card_link": 'a.ProductCard__link, a[data-testid="product-link"], a[href*="/ulta/"]',
            "card_price": 'span.ProductCard__price, span[data-testid="product-price"]',
            "card_title": 'span.ProductCard__product, h3.ProductCard__title',
        },
        "pagination": {
            "next_button": 'a[aria-label="Next"], button.next-page',
            "max_pages": 5,
        },
        "request_delay": 2.5,
    },
    "dickssportinggoods.com": {
        "name": "Dick's Sporting Goods",
        "product_page": {
            "title": 'h1.product-title, h1[data-testid="product-name"], h1',
            "price": 'span.product-price, span[data-testid="product-price"], div.price-column span',
            "sale_price": 'span.product-was-price, span[data-testid="was-price"]',
            "upc": None,
            "image": 'img.product-image, img[data-testid="product-image"], div.product-gallery img',
            "category": 'nav.breadcrumb a, ul.breadcrumbs a',
        },
        "category_page": {
            "product_cards": 'div.product-card, div[data-testid="product-card"], div.rs-product-card',
            "card_link": 'a.product-card-link, a[data-testid="product-link"], a[href*="/p/"]',
            "card_price": 'span.product-card-price, span[data-testid="price"]',
            "card_title": 'div.product-card-title, a.product-card-title, span[data-testid="product-name"]',
        },
        "pagination": {
            "next_button": 'a[aria-label="Next Page"], button.next-page',
            "max_pages": 5,
        },
        "request_delay": 2.5,
    },
    "kroger.com": {
        "name": "Kroger",
        "product_page": {
            "title": 'h1.ProductDetails-header, h1[data-testid="product-title"], h1',
            "price": 'span.kds-Price, span[data-testid="product-price"], mark.kds-Price-promotional',
            "sale_price": 'span.kds-Price-original, span[data-testid="original-price"]',
            "upc": None,
            "image": 'img.ProductImages-image, img[data-testid="product-image"], div.ProductImages img',
            "category": 'nav.breadcrumb a, ol.Breadcrumbs a',
        },
        "category_page": {
            "product_cards": 'div.ProductCard, div[data-testid="product-card"], div.AutoGrid-cell',
            "card_link": 'a.ProductCard-link, a[data-testid="product-link"], a[href*="/p/"]',
            "card_price": 'span.kds-Price, span[data-testid="product-price"], mark.kds-Price-promotional',
            "card_title": 'span.ProductCard-title, h3.ProductCard-heading',
        },
        "pagination": {
            "next_button": 'a[aria-label="Next Page"], button[data-testid="next-page"]',
            "max_pages": 3,
        },
        "request_delay": 3.0,
    },
}

# Generic fallback for unknown retailers — attempts common e-commerce patterns
GENERIC_CONFIG = {
    "name": "Generic",
    "product_page": {
        "title": 'h1, [itemprop="name"], .product-title, .product-name',
        "price": '[itemprop="price"], .price, .product-price, .current-price',
        "sale_price": '.sale-price, .was-price, .original-price, .price--compare',
        "upc": '[itemprop="gtin13"], [itemprop="gtin12"], [itemprop="sku"]',
        "image": '[itemprop="image"], .product-image img, .product-gallery img',
        "category": 'nav.breadcrumb a, .breadcrumbs a, nav[aria-label="breadcrumb"] a',
    },
    "category_page": {
        "product_cards": '.product-card, .product-grid-item, .product-tile, .product-item',
        "card_link": 'a',
        "card_price": '.price, .product-price, .current-price',
        "card_title": '.product-title, .product-name, h2, h3',
    },
    "pagination": {
        "next_button": 'a[rel="next"], .pagination .next a, a[aria-label="Next"]',
        "max_pages": 3,
    },
    "request_delay": 3.0,
}


def get_retailer_config(url: str) -> tuple:
    """Return (retailer_key, config) for a URL. Falls back to generic."""
    domain = urlparse(url).netloc.replace("www.", "").lower()
    for key, config in RETAILER_CONFIGS.items():
        if key in domain:
            return key, config
    return "generic", GENERIC_CONFIG


def detect_page_type(url: str) -> str:
    """Heuristic: is this a product page or a category/search page?"""
    url_lower = url.lower()
    # Product page indicators
    product_indicators = ["/ip/", "/dp/", "/p/", "/product/", "/pdp/", "-p-",
                          "/item/", "/products/", "productid=", "skuid="]
    if any(ind in url_lower for ind in product_indicators):
        return "product"
    # Search/category indicators
    search_indicators = ["/search", "/browse", "/category", "/c/", "/b/",
                         "/s?", "q=", "query=", "keyword=", "/clearance",
                         "/sale", "/deals", "/rollback", "/shop/", "/catalog"]
    if any(ind in url_lower for ind in search_indicators):
        return "category"
    # Default to category (safer — will attempt to find product cards)
    return "category"

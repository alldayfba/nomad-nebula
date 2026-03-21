import asyncio
import functools
import itertools
import re
from typing import Callable
from playwright.async_api import async_playwright
import requests
from bs4 import BeautifulSoup


async def scrape_email_from_website(session: requests.Session, url: str) -> str:
    """Try to find an email address from a business website."""
    if not url or url == "N/A":
        return "N/A"
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        resp = session.get(url, headers=headers, timeout=4)
        text = resp.text
        emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
        blocked_exts = {"png", "jpg", "jpeg", "gif", "svg", "webp", "css", "js", "woff"}
        blocked_words = {"example", "domain", "sentry", "schema", "placeholder"}
        for email in emails:
            ext = email.split(".")[-1].lower()
            low = email.lower()
            if ext not in blocked_exts and not any(w in low for w in blocked_words):
                return email
    except Exception:
        pass
    return "N/A"


async def scrape_google_maps(query: str, location: str, max_results: int = 20, fetch_emails: bool = True):
    """Scrape Google Maps for B2B leads."""
    search_term = f"{query} in {location}"
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            java_script_enabled=True,
        )
        page = await context.new_page()

        try:
            encoded = requests.utils.quote(search_term)
            url = f"https://www.google.com/maps/search/{encoded}"
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2500)

            # Scroll results panel to load more listings
            for _ in range(4):
                try:
                    await page.locator('div[role="feed"]').evaluate("el => el.scrollBy(0, 2500)")
                except Exception:
                    pass
                await page.wait_for_timeout(1000)

            # Gather listing URLs from the sidebar
            listing_links = await page.locator('a[href*="/maps/place/"]').all()
            hrefs = []
            seen = set()
            for link in listing_links:
                href = await link.get_attribute("href")
                if href and href not in seen:
                    seen.add(href)
                    hrefs.append(href)
                if len(hrefs) >= max_results:
                    break

            # Visit each listing page
            for href in itertools.islice(hrefs, max_results):
                detail_page = None
                try:
                    detail_page = await context.new_page()
                    await detail_page.goto(href, wait_until="domcontentloaded", timeout=15000)
                    await detail_page.wait_for_timeout(1500)

                    soup = BeautifulSoup(await detail_page.content(), "html.parser")

                    # Business name
                    name_el = soup.select_one('h1.DUwDvf, h1[class*="fontHeadlineLarge"]')
                    name = name_el.get_text(strip=True) if name_el else "N/A"

                    # Rating
                    rating = "N/A"
                    for sel in ['span.ceNzKf', 'div.F7nice span[aria-hidden="true"]', 'span[aria-label*="stars"]']:
                        el = soup.select_one(sel)
                        if el:
                            rating = el.get_text(strip=True)
                            break

                    # Address
                    address = "N/A"
                    for btn in soup.select('button[data-item-id="address"], button[aria-label*="ddress"]'):
                        txt = btn.get_text(strip=True)
                        if txt:
                            address = txt
                            break

                    # Phone — extract from data-item-id or aria-label (not button text, which is "Send to phone")
                    phone = "N/A"
                    for btn in soup.select('button[data-item-id*="phone"]'):
                        data_id = btn.get("data-item-id", "")
                        # data-item-id is like "phone:tel:+13125551234"
                        if "tel:" in data_id:
                            phone = data_id.split("tel:")[-1].strip()
                            break
                        aria = btn.get("aria-label", "")
                        if aria:
                            # aria-label is like "Phone: (312) 555-1234"
                            phone_match = re.search(r'[\d\(\)\-\+\s\.]{7,}', aria)
                            if phone_match:
                                phone = phone_match.group(0).strip()
                                break
                    if phone == "N/A":
                        for btn in soup.select('button[aria-label*="hone"]'):
                            aria = btn.get("aria-label", "")
                            if aria:
                                phone_match = re.search(r'[\d\(\)\-\+\s\.]{7,}', aria)
                                if phone_match:
                                    phone = phone_match.group(0).strip()
                                    break

                    # Website
                    website = "N/A"
                    for sel in ['a[data-item-id="authority"]', 'a[aria-label*="ebsite"]']:
                        el = soup.select_one(sel)
                        if el:
                            website = el.get("href", "N/A")
                            break

                    # Category
                    category = "N/A"
                    cat_el = soup.select_one('button.DkEaL')
                    if cat_el:
                        category = cat_el.get_text(strip=True)

                    # Owner — best effort
                    owner = "N/A"
                    page_text = soup.get_text()
                    m = re.search(r"Owner[:\s]+([A-Z][a-z]+ [A-Z][a-z]+)", page_text)
                    if m:
                        owner = m.group(1)

                    if name and name != "N/A":
                        results.append({
                            "business_name": name,
                            "owner_name": owner,
                            "category": category,
                            "phone": phone,
                            "email": "pending",   # filled after loop
                            "website": website,
                            "address": address,
                            "rating": rating,
                            "maps_url": href,
                        })

                except Exception as e:
                    print(f"[listing error] {e}")
                finally:
                    if detail_page:
                        await detail_page.close()

        except Exception as e:
            print(f"[maps error] {e}")
        finally:
            await browser.close()

    # Email scraping (sync, outside browser context)
    if fetch_emails:
        session = requests.Session()
        for lead in results:
            fn: Callable[[], str] = functools.partial(_fetch_email_sync, session, lead["website"])
            lead["email"] = await asyncio.to_thread(fn)
    else:
        for lead in results:
            lead["email"] = "N/A"

    return results


def _fetch_email_sync(session: requests.Session, url: str) -> str:
    """Thread-safe sync email fetch."""
    if not url or url == "N/A":
        return "N/A"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = session.get(url, headers=headers, timeout=4)
        emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", resp.text)
        blocked_exts = {"png", "jpg", "jpeg", "gif", "svg", "webp", "css", "js", "woff"}
        blocked_words = {"example", "domain", "sentry", "schema", "placeholder"}
        for email in emails:
            ext = email.split(".")[-1].lower()
            if ext not in blocked_exts and not any(w in email.lower() for w in blocked_words):
                return email
    except Exception:
        pass
    return "N/A"


def run_scraper(query: str, location: str, max_results: int = 20, fetch_emails: bool = True):
    """Synchronous wrapper for the async scraper."""
    return asyncio.run(scrape_google_maps(query, location, max_results, fetch_emails))

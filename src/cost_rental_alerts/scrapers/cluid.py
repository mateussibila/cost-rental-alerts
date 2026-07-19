"""Scrape Clúid Housing cost-rental property pages."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from cost_rental_alerts.addresses import compose_address
from cost_rental_alerts.locations import normalize_location
from cost_rental_alerts.models import Listing
from cost_rental_alerts.scrapers.common import bedrooms_range, fetch, parse_bed_count, parse_price

CLUID_URL = "https://www.cluid.ie/cost-rental/"


def _slug_from_url(url: str) -> str:
    return urlparse(url).path.rstrip("/").split("/")[-1]


def _status_from_detail(text: str) -> str:
    lowered = text.lower()
    if re.search(r"applications?\s+(are\s+)?(now\s+)?closed|closed for applications", lowered):
        return "closed"
    if re.search(r"applications?\s+(are\s+)?open|apply now|register your interest", lowered):
        # Clúid FAQ pages always mention register-your-interest; require stronger open signal.
        if re.search(r"applications?\s+(are\s+)?open|apply now|applications open", lowered):
            return "open"
    if "coming soon" in lowered or "opening soon" in lowered:
        return "coming_soon"
    return "closed"


def _index_properties(html: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[tuple[str, str]] = []
    seen: set[str] = set()
    for a in soup.select('a[href*="/property/"]'):
        name = a.get_text(" ", strip=True).strip()
        href = urljoin(CLUID_URL, a.get("href", ""))
        if not name or len(name) < 3 or href in seen:
            continue
        if "/property/" not in href:
            continue
        seen.add(href)
        items.append((name, href))
    return items


def scrape_cluid() -> list[Listing]:
    html = fetch(CLUID_URL)
    listings: list[Listing] = []
    for title, url in _index_properties(html):
        listing = Listing(
            id=f"cluid:{_slug_from_url(url)}",
            source="cluid",
            title=title,
            location="",
            url=url,
            status="unknown",
            category="rent",
        )
        try:
            detail = fetch(url)
            text = BeautifulSoup(detail, "html.parser").get_text(" ", strip=True)
            listing.status = _status_from_detail(text)
            listing.price_from = parse_price(text)
            counts = [
                n
                for n in (parse_bed_count(m.group(0)) for m in re.finditer(r"\d+\s*[- ]?bed", text, re.I))
                if n is not None
            ]
            listing.bedrooms = bedrooms_range(counts)
            listing.address = compose_address(title, "", page_html=detail)
            listing.location = normalize_location(listing.address or title)
        except Exception:
            listing.status = "unknown"
        listings.append(listing)
    return listings

"""Scrape Oaklee cost-rental availability."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from cost_rental_alerts.addresses import compose_address
from cost_rental_alerts.locations import normalize_location
from cost_rental_alerts.models import Listing
from cost_rental_alerts.scrapers.common import bedrooms_range, fetch, parse_bed_count, parse_price

OAKLEE_URL = "https://oaklee.ie/become-a-resident/cost-rental-housing"


def _slug_from_url(url: str) -> str:
    return urlparse(url).path.rstrip("/").split("/")[-1]


def scrape_oaklee() -> list[Listing]:
    html = fetch(OAKLEE_URL)
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    soup = BeautifulSoup(html, "html.parser")

    # Explicit empty state on the marketing page.
    if re.search(r"currently no Cost Rental homes available", text, re.I):
        return []

    listings: list[Listing] = []
    seen: set[str] = set()

    for a in soup.select("a[href]"):
        href = urljoin(OAKLEE_URL, a.get("href", ""))
        label = a.get_text(" ", strip=True)
        blob = f"{label} {href}".lower()
        if not any(token in blob for token in ("sidings", "keyholder", "cost-rental", "cost rental")):
            continue
        if "how-to-apply" in href or href.rstrip("/").endswith("cost-rental-housing"):
            continue
        if href in seen:
            continue
        seen.add(href)

        title = label.strip() or _slug_from_url(href).replace("-", " ").title()
        title = re.sub(r"^\s*View\s+", "", title, flags=re.I).strip() or "Oaklee Cost Rental"
        listing = Listing(
            id=f"oaklee:{_slug_from_url(href)}",
            source="oaklee",
            title=title,
            location="",
            url=href,
            status="open",
            category="rent",
        )
        try:
            if "oaklee.ie" in href or "oakleehousing.ie" in href:
                detail = fetch(href)
                detail_text = BeautifulSoup(detail, "html.parser").get_text(" ", strip=True)
                if re.search(r"applications?\s+closed|currently no Cost Rental", detail_text, re.I):
                    listing.status = "closed"
                listing.price_from = parse_price(detail_text)
                counts = [
                    n
                    for n in (
                        parse_bed_count(m.group(0))
                        for m in re.finditer(r"\d+\s*[- ]?bed", detail_text, re.I)
                    )
                    if n is not None
                ]
                listing.bedrooms = bedrooms_range(counts)
                listing.address = compose_address(title, "", page_html=detail)
                listing.location = normalize_location(listing.address or title)
        except Exception:
            pass
        listings.append(listing)

    return listings

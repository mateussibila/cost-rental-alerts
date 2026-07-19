"""Scrape Respond Housing cost-rental listings."""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from cost_rental_alerts.addresses import compose_address
from cost_rental_alerts.locations import normalize_location
from cost_rental_alerts.models import Listing
from cost_rental_alerts.scrapers.common import (
    bedrooms_range,
    fetch,
    parse_bed_count,
    parse_price,
)

RESPOND_URL = "https://www.respond.ie/cost-rental/"
TZ = ZoneInfo("Europe/Dublin")

_SECTION_STATUS = {
    "current listings": "open",
    "coming soon": "coming_soon",
    "closed listings": "closed",
}


def _slug_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    return path.split("/")[-1]


def _parse_close_at(text: str) -> str | None:
    """Parse 'Closing Date 27/07/26 @11am' or 'Closing Date 27/07/2026'."""
    match = re.search(
        r"Closing Date\s*(\d{1,2})/(\d{1,2})/(\d{2,4})",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    day, month, year = match.groups()
    year_int = int(year)
    if year_int < 100:
        year_int += 2000
    try:
        return date_iso(year_int, int(month), int(day))
    except ValueError:
        return None


def date_iso(year: int, month: int, day: int) -> str:
    return datetime(year, month, day, tzinfo=TZ).date().isoformat()


def _min_rent(text: str) -> float | None:
    prices: list[float] = []
    for match in re.finditer(
        r"(?:monthly rent|rent(?:\s+of)?|is:)\s*:?\s*€\s*([0-9][0-9,]*)",
        text,
        re.IGNORECASE,
    ):
        prices.append(float(match.group(1).replace(",", "")))
    if not prices:
        for match in re.finditer(r"€\s*([0-9][0-9,]{2,})", text):
            value = float(match.group(1).replace(",", ""))
            if 500 <= value <= 5000:
                prices.append(value)
    return min(prices) if prices else None


def _bedrooms_from_text(text: str) -> str | None:
    counts: list[int] = []
    for match in re.finditer(
        r"(\d+)\s*[x×]\s*(\d+)\s*bedroom",
        text,
        re.IGNORECASE,
    ):
        counts.append(int(match.group(2)))
    for match in re.finditer(r"(\d+)\s*[- ]?bed", text, re.IGNORECASE):
        counts.append(int(match.group(1)))
    for match in re.finditer(
        r"\b(one|two|three|four)\s*[- ]?bed",
        text,
        re.IGNORECASE,
    ):
        counts.append({"one": 1, "two": 2, "three": 3, "four": 4}[match.group(1).lower()])
    if not counts:
        bed = parse_bed_count(text)
        return f"{bed} bed" if bed is not None else None
    return bedrooms_range(counts)


def _noise_title(title: str) -> bool:
    lowered = title.strip().lower()
    if not lowered or len(lowered) < 3 or len(lowered) > 100:
        return True
    if re.match(r"step\s*\d", lowered):
        return True
    return any(
        token in lowered
        for token in (
            "thank you",
            "eligib",
            "how do i",
            "what do i",
            "document",
            "overview",
            "find out more",
        )
    )


def _index_listings(html: str) -> list[tuple[str, str, str]]:
    """Return (title, url, status) from the cost-rental index."""
    soup = BeautifulSoup(html, "html.parser")
    section: str | None = None
    found: list[tuple[str, str, str]] = []
    seen_urls: set[str] = set()

    for el in soup.find_all(["h2", "h3"]):
        text = el.get_text(" ", strip=True).strip()
        lowered = text.lower()
        if lowered in _SECTION_STATUS:
            section = lowered
            continue
        if section is None or el.name != "h3" or _noise_title(text):
            continue

        link = el.find_next("a", href=re.compile(r"/properties/"))
        if not link:
            continue
        # Avoid associating a title with a link that belongs to a later section.
        between = el.find_all_next(["h2", "h3", "a"], limit=12)
        href = None
        for node in between:
            if node.name in {"h2", "h3"} and node.get_text(" ", strip=True).strip().lower() in _SECTION_STATUS:
                break
            if node.name == "a" and "/properties/" in (node.get("href") or ""):
                href = urljoin(RESPOND_URL, node["href"])
                break
        if not href or href in seen_urls:
            continue
        seen_urls.add(href)
        found.append((text, href, _SECTION_STATUS[section]))

    return found


def _enrich(listing: Listing) -> None:
    try:
        html = fetch(listing.url)
    except Exception:
        return
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    close_at = _parse_close_at(text)
    if close_at:
        listing.applications_close_at = close_at
    price = _min_rent(text) or parse_price(text)
    if price is not None:
        listing.price_from = price
    beds = _bedrooms_from_text(text)
    if beds:
        listing.bedrooms = beds
    listing.address = compose_address(
        listing.title,
        listing.location,
        page_html=html,
    )
    if listing.status == "open" and close_at:
        try:
            if datetime.fromisoformat(close_at).date() < datetime.now(TZ).date():
                listing.status = "closed"
        except ValueError:
            pass


def scrape_respond() -> list[Listing]:
    html = fetch(RESPOND_URL)
    listings: list[Listing] = []
    for title, url, status in _index_listings(html):
        location = ""
        if "," in title:
            location = normalize_location(title.split(",", 1)[1].strip())
        listing = Listing(
            id=f"respond:{_slug_from_url(url)}",
            source="respond",
            title=title,
            location=location,
            url=url,
            status=status,
            category="rent",
        )
        listings.append(listing)

    for listing in listings:
        _enrich(listing)
    return listings

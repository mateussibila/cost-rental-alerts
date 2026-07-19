"""Scrape Circle VHA cost-rental scheme pages."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from cost_rental_alerts.addresses import compose_address
from cost_rental_alerts.locations import normalize_location
from cost_rental_alerts.models import Listing
from cost_rental_alerts.scrapers.common import bedrooms_range, fetch, parse_bed_count, parse_price

CIRCLE_URL = "https://circlevha.ie/cost-rental/"
TZ = ZoneInfo("Europe/Dublin")

_MONTH = (
    r"(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)"
)


def _slug_from_url(url: str) -> str:
    return urlparse(url).path.rstrip("/").split("/")[-1]


def _parse_close_at(text: str) -> str | None:
    match = re.search(
        rf"Applications?\s+closed\s+at\s+[^.]{{0,40}}?\b(\d{{1,2}})(?:st|nd|rd|th)?"
        rf"\s+{_MONTH}\s+(\d{{4}})",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    day, month_name, year = match.groups()
    try:
        month = __import__("datetime").datetime.strptime(month_name[:3], "%b").month
        return f"{int(year)}-{month:02d}-{int(day):02d}"
    except ValueError:
        return None


def _status_from_detail(text: str, close_at: str | None) -> str:
    lowered = text.lower()
    if close_at or re.search(r"applications?\s+closed", lowered):
        return "closed"
    if re.search(r"applications?\s+(are\s+)?open|apply now|register now", lowered):
        return "open"
    if "coming soon" in lowered:
        return "coming_soon"
    return "closed"


def _index_schemes(html: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[tuple[str, str]] = []
    seen: set[str] = set()

    for a in soup.select('a[href*="/cost-rental/"]'):
        href = urljoin(CIRCLE_URL, a.get("href", ""))
        path = urlparse(href).path.rstrip("/")
        if path.endswith("/cost-rental") or path == "/cost-rental":
            continue
        if href in seen:
            continue
        # Prefer nearby heading text over "Find out more here".
        name = a.get_text(" ", strip=True).strip()
        if not name or name.lower().startswith("find out more"):
            heading = a.find_previous(["h2", "h3", "h4"])
            name = heading.get_text(" ", strip=True) if heading else _slug_from_url(href).replace("-", " ").title()
        if "," in name:
            # "Lanestown View, Donabate" -> keep full
            pass
        seen.add(href)
        items.append((name, href))

    # Also catch scheme names listed as headings with known detail paths.
    for h in soup.select("h2, h3"):
        name = h.get_text(" ", strip=True).strip()
        if not name or len(name) < 5:
            continue
        link = h.find_next("a", href=re.compile(r"/cost-rental/[^/]+"))
        if not link:
            continue
        href = urljoin(CIRCLE_URL, link["href"])
        if href.rstrip("/").endswith("/cost-rental") or href in seen:
            continue
        if name.lower().startswith(("one-bed", "two-bed", "three-bed", "four-bed", "register")):
            continue
        seen.add(href)
        items.append((name, href))

    return items


def scrape_circle() -> list[Listing]:
    html = fetch(CIRCLE_URL)
    listings: list[Listing] = []
    for title, url in _index_schemes(html):
        listing = Listing(
            id=f"circle:{_slug_from_url(url)}",
            source="circle",
            title=title.split(",")[0].strip(),
            location=normalize_location(title.split(",", 1)[1].strip()) if "," in title else "",
            url=url,
            status="unknown",
            category="rent",
        )
        if "," in title:
            listing.title = title
        try:
            detail = fetch(url)
            text = BeautifulSoup(detail, "html.parser").get_text(" ", strip=True)
            close_at = _parse_close_at(text)
            listing.applications_close_at = close_at
            listing.status = _status_from_detail(text, close_at)
            listing.price_from = parse_price(text)
            counts = [
                n
                for n in (parse_bed_count(m.group(0)) for m in re.finditer(r"\d+\s*[- ]?bed", text, re.I))
                if n is not None
            ]
            listing.bedrooms = bedrooms_range(counts)
            listing.address = compose_address(listing.title, listing.location, page_html=detail)
            if not listing.location:
                listing.location = normalize_location(listing.address or listing.title)
        except Exception:
            listing.status = "unknown"
        listings.append(listing)
    return listings

import re
from datetime import date, datetime, timedelta
from typing import Dict, List, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from cost_rental_alerts.addresses import compose_address
from cost_rental_alerts.models import Listing
from cost_rental_alerts.scrapers.common import (
    fetch,
    normalize_bedrooms,
    normalize_status,
    parse_listed_date,
    parse_price,
    parse_quantity,
)

BASE_URL = "https://affordablehomes.ie"
RENT_URL = f"{BASE_URL}/rent/"
CALENDAR_URL = f"{BASE_URL}/rent/calendar/"

CalendarEventDate = date | Tuple[int, int]


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _date_from_month_day(month: int, day: int, year: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _iso_from_month_day(month: int, day: int, year: int) -> str | None:
    parsed = _date_from_month_day(month, day, year)
    return parsed.isoformat() if parsed else None


def _calendar_year(article) -> int | None:
    section = article.find_parent("section", class_="calendar")
    if not section:
        return None

    label = section.get("aria-labelledby", "")
    match = re.search(r"\byear-(\d{4})\b", label)
    if match:
        return int(match.group(1))

    heading = section.select_one("h3.year")
    if heading:
        match = re.search(r"\b(\d{4})\b", heading.get_text(" ", strip=True))
        if match:
            return int(match.group(1))

    return None


def _calendar_events(html: str) -> Dict[str, Dict[str, CalendarEventDate]]:
    """Map slug -> calendar open/close events, preserving year when present."""
    soup = BeautifulSoup(html, "html.parser")
    events: Dict[str, Dict[str, CalendarEventDate]] = {}

    for article in soup.select("article.calendar"):
        day_el = article.select_one("h4 span")
        month_el = article.select_one("h4 span.fwb")
        if not day_el or not month_el:
            continue
        try:
            day = int(day_el.get_text(strip=True))
            month_name = month_el.get_text(strip=True)
            month = datetime.strptime(month_name, "%b").month
        except ValueError:
            continue
        year = _calendar_year(article)

        for block in article.select("div.open, div.close"):
            classes = block.get("class", [])
            if "open" in classes:
                event_type = "opened"
            elif "close" in classes:
                event_type = "closed"
            else:
                continue

            for link in block.select('a[href^="/rent/"]'):
                href = link.get("href", "")
                slug_match = re.search(r"/rent/([^/]+)/", href)
                if not slug_match:
                    continue
                slug = slug_match.group(1)
                event_date: CalendarEventDate
                if year is None:
                    event_date = (month, day)
                else:
                    parsed = _date_from_month_day(month, day, year)
                    if parsed is None:
                        continue
                    event_date = parsed

                bucket = events.setdefault(slug, {})
                existing = bucket.get(event_type)
                if isinstance(existing, date) and not isinstance(event_date, date):
                    continue
                bucket[event_type] = event_date

    return events


def _calendar_event_to_date(
    event: CalendarEventDate | None,
    anchor_year: int | None,
) -> date | None:
    if event is None:
        return None
    if isinstance(event, date):
        return event
    if anchor_year is None:
        return None
    return _date_from_month_day(event[0], event[1], anchor_year)


def _resolve_explicit_calendar_dates(
    opened_event: CalendarEventDate | None,
    closed_event: CalendarEventDate | None,
) -> Tuple[str | None, str | None] | None:
    if not isinstance(opened_event, date) and not isinstance(closed_event, date):
        return None

    anchor_year = None
    if isinstance(opened_event, date):
        anchor_year = opened_event.year
    elif isinstance(closed_event, date):
        anchor_year = closed_event.year

    opened = _calendar_event_to_date(opened_event, anchor_year)
    closed = _calendar_event_to_date(closed_event, anchor_year)
    if opened and closed and closed < opened and not isinstance(closed_event, date):
        closed = _date_from_month_day(closed.month, closed.day, opened.year + 1)

    return (
        opened.isoformat() if opened else None,
        closed.isoformat() if closed else None,
    )


def _resolve_calendar_dates(
    opened_event: CalendarEventDate | None,
    closed_event: CalendarEventDate | None,
    listing: Listing,
    today: date,
) -> Tuple[str | None, str | None]:
    """
    Pick plausible years for month/day calendar events.

    The AH calendar has no year; using the current year for every June event
    turns past rounds (e.g. listed 2025) into false "opening soon" alerts.
    """
    explicit_dates = _resolve_explicit_calendar_dates(opened_event, closed_event)
    if explicit_dates is not None:
        return explicit_dates

    opened_md = opened_event if isinstance(opened_event, tuple) else None
    closed_md = closed_event if isinstance(closed_event, tuple) else None
    listed = _parse_iso_date(listing.listed_at)
    listed_year = listed.year if listed else None

    def pair_for_year(year: int) -> Tuple[date | None, date | None]:
        opened = (
            _date_from_month_day(opened_md[0], opened_md[1], year) if opened_md else None
        )
        closed = (
            _date_from_month_day(closed_md[0], closed_md[1], year) if closed_md else None
        )
        return opened, closed

    if listing.status == "open":
        for year in range(today.year, today.year - 4, -1):
            opened, closed = pair_for_year(year)
            if opened and opened <= today and (closed is None or closed >= today):
                return (
                    opened.isoformat(),
                    closed.isoformat() if closed else None,
                )
        year = listed_year or today.year
        opened, closed = pair_for_year(year)
        return (
            opened.isoformat() if opened else None,
            closed.isoformat() if closed else None,
        )

    for year in range(today.year, today.year - 4, -1):
        opened, closed = pair_for_year(year)
        if closed and closed < today:
            return (
                opened.isoformat() if opened else None,
                closed.isoformat(),
            )

    opened, closed = pair_for_year(today.year)
    if (
        opened
        and opened > today
        and listed
        and listed >= today - timedelta(days=90)
        and listed_year is not None
        and listed_year >= today.year - 1
    ):
        return (
            opened.isoformat(),
            closed.isoformat() if closed else None,
        )

    return None, None


def _parse_listing_page(html: str) -> List[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    listings: List[Listing] = []

    for article in soup.select("article.property"):
        classes = article.get("class", [])
        status = "open" if "open" in classes else "closed" if "closed" in classes else "unknown"

        title_link = article.select_one("h3 a")
        if not title_link:
            continue

        slug = title_link.get("href", "").strip("/")
        title = title_link.get_text(strip=True)
        url = urljoin(RENT_URL, slug + "/")

        price_el = article.select_one("p.price")
        price = parse_price(price_el.get_text()) if price_el else None

        status_el = article.select_one("p.status")
        if status_el:
            status = normalize_status(status_el.get_text())

        location_el = article.select_one("p.location span")
        location = location_el.get_text(strip=True) if location_el else ""

        listed_el = article.select_one("p.date")
        listed_at = (
            parse_listed_date(listed_el.get_text())
            if listed_el
            else None
        )

        listings.append(
            Listing(
                id=f"affordablehomes:{slug}",
                source="affordablehomes",
                title=title,
                location=location,
                url=url,
                status=status,
                category="rent",
                price_from=price,
                listed_at=listed_at,
            )
        )

    return listings


def _detail_field(soup: BeautifulSoup, label: str) -> str | None:
    for h3 in soup.select("h3.fwu"):
        if h3.get_text(strip=True) == label:
            sibling = h3.find_next_sibling("p")
            if sibling:
                return sibling.get_text(strip=True)
    return None


def _parse_portal_dates(html: str) -> Tuple[str | None, str | None]:
    """Parse explicit portal window text, e.g. '... 20th June 2024 up to ... 27th June 2024'."""
    match = re.search(
        r"Portal open for applications from.*?"
        r"(\d{1,2})(?:st|nd|rd|th)?\s+(\w+)\s+(\d{4}).*?"
        r"(?:up to|until).*?"
        r"(\d{1,2})(?:st|nd|rd|th)?\s+(\w+)\s+(\d{4})",
        html,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None, None
    open_day, open_month, open_year, close_day, close_month, close_year = match.groups()
    try:
        open_at = f"{open_year}-{datetime.strptime(open_month[:3], '%b').month:02d}-{int(open_day):02d}"
        close_at = (
            f"{close_year}-{datetime.strptime(close_month[:3], '%b').month:02d}-{int(close_day):02d}"
        )
        return open_at, close_at
    except ValueError:
        return None, None


def _parse_detail(
    html: str,
) -> tuple[str | None, int | None, str | None, str | None, str | None]:
    """Return (bedrooms, quantity, open_at, close_at, detail location)."""
    soup = BeautifulSoup(html, "html.parser")

    bedrooms = None
    raw_beds = _detail_field(soup, "Bedrooms")
    if raw_beds:
        bedrooms = normalize_bedrooms(raw_beds)

    quantity = None
    raw_qty = _detail_field(soup, "Availability")
    if raw_qty:
        quantity = parse_quantity(raw_qty)

    detail_location = _detail_field(soup, "Location")

    portal_open, portal_close = _parse_portal_dates(html)
    if portal_open or portal_close:
        return bedrooms, quantity, portal_open, portal_close, detail_location

    close_match = re.search(
        r"Applications Close:.*?(\d{1,2})\s+(\w+)\s+(\d{4})",
        html,
        re.IGNORECASE | re.DOTALL,
    )
    close_at = None
    if close_match:
        day, month_name, year = close_match.groups()
        try:
            month = datetime.strptime(month_name[:3], "%b").month
            close_at = f"{year}-{month:02d}-{int(day):02d}"
        except ValueError:
            pass

    return bedrooms, quantity, None, close_at, detail_location


def _enrich_listings(listings: List[Listing]) -> None:
    for listing in listings:
        try:
            detail_html = fetch(listing.url)
            bedrooms, quantity, open_at, close_at, detail_location = _parse_detail(
                detail_html
            )
            listing.bedrooms = bedrooms
            listing.quantity = quantity
            listing.address = compose_address(
                listing.title,
                listing.location,
                detail_location=detail_location,
                page_html=detail_html,
            )
            if open_at:
                listing.applications_open_at = open_at
            if close_at:
                listing.applications_close_at = close_at
        except Exception:
            continue


def _total_pages(html: str) -> int:
    match = re.search(r"Showing \d+ to \d+ of (\d+)", html)
    if not match:
        return 1
    total = int(match.group(1))
    return max(1, (total + 11) // 12)


def scrape_affordablehomes() -> List[Listing]:
    first_html = fetch(RENT_URL)
    pages = _total_pages(first_html)
    listings: List[Listing] = []
    seen_ids = set()

    for page in range(1, pages + 1):
        html = first_html if page == 1 else fetch(f"{RENT_URL}?page={page}")
        for listing in _parse_listing_page(html):
            if listing.id not in seen_ids:
                seen_ids.add(listing.id)
                listings.append(listing)

    try:
        calendar_html = fetch(CALENDAR_URL)
        events = _calendar_events(calendar_html)
    except Exception:
        events = {}

    today = datetime.now().date()
    for listing in listings:
        slug = listing.id.split(":", 1)[1]
        if slug not in events:
            continue
        opened = events[slug].get("opened")
        closed = events[slug].get("closed")
        open_at, close_at = _resolve_calendar_dates(opened, closed, listing, today)
        if open_at:
            listing.applications_open_at = open_at
        if close_at:
            listing.applications_close_at = close_at

    _enrich_listings(listings)
    return listings

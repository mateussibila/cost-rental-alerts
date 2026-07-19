"""Minimal CHI monitor — detect any future Cost Rental listings."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from cost_rental_alerts.models import Listing
from cost_rental_alerts.scrapers.common import fetch

CHI_URLS = (
    "https://www.cooperativehousing.ie/",
    "https://www.cooperativehousing.ie/about",
    "https://www.cooperativehousing.ie/news",
)


def _slug_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    return path.split("/")[-1] or "home"


def scrape_chi() -> list[Listing]:
    """
    CHI currently focuses on social-rented and owner-occupier homes.

    This monitor only returns listings when a page clearly advertises Cost Rental
    applications, so we notice if CHI ever launches that tenure.
    """
    listings: list[Listing] = []
    seen: set[str] = set()

    for page_url in CHI_URLS:
        try:
            html = fetch(page_url)
        except Exception:
            continue
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)
        if not re.search(r"cost\s*[- ]?\s*rental", text, re.I):
            continue

        for a in soup.select("a[href]"):
            href = urljoin(page_url, a.get("href", ""))
            label = a.get_text(" ", strip=True)
            blob = f"{label} {href}".lower()
            if "cost" not in blob or "rental" not in blob:
                continue
            if href in seen:
                continue
            # Ignore pure policy/about mentions without an apply path.
            if not re.search(r"apply|scheme|home|property|development", blob):
                continue
            seen.add(href)
            listings.append(
                Listing(
                    id=f"chi:{_slug_from_url(href)}",
                    source="chi",
                    title=label or "CHI Cost Rental",
                    location="",
                    url=href,
                    status="open",
                    category="rent",
                )
            )

        # If the phrase appears with open/apply language but no link, keep a sentinel open row
        # pointing at the page so ops/hub can investigate.
        if not listings and re.search(
            r"cost\s*[- ]?\s*rental.{0,80}(apply|applications?\s+open|now open)",
            text,
            re.I | re.S,
        ):
            listings.append(
                Listing(
                    id=f"chi:monitor:{_slug_from_url(page_url)}",
                    source="chi",
                    title="CHI Cost Rental (monitor hit)",
                    location="",
                    url=page_url,
                    status="open",
                    category="rent",
                )
            )

    return listings

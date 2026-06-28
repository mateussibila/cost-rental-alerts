#!/usr/bin/env python3
import argparse
import os
import sys
import traceback
from dataclasses import dataclass, field

from cost_rental_alerts.db import connect, get_meta, init_db, mark_notified, set_meta, upsert_listings
from cost_rental_alerts.diff import find_closing_soon, find_news, find_opening_soon
from cost_rental_alerts.export_csv import resolve_export_status
from cost_rental_alerts.models import Listing
from cost_rental_alerts.notify import (
    email_configured,
    format_message,
    format_test_message,
    format_whatsapp_message,
    send_email,
    send_whatsapp,
)
from cost_rental_alerts.schemes import enrich_cross_source_open_dates
from cost_rental_alerts.scrapers import scrape_affordablehomes, scrape_lda, scrape_tuath


def normalize_listing_statuses(listings: list[Listing]) -> None:
    for listing in listings:
        listing.status = resolve_export_status(
            listing.status,
            listing.applications_open_at,
        )


@dataclass
class SourceResult:
    name: str
    label: str
    ok: bool
    count: int = 0
    error: str | None = None
    open_samples: list[Listing] = field(default_factory=list)


def scrape_sources() -> tuple[list[Listing], list[SourceResult]]:
    listings: list[Listing] = []
    results: list[SourceResult] = []

    for name, label, scraper in [
        ("affordablehomes", "affordablehomes.ie", scrape_affordablehomes),
        ("lda", "lda.ie", scrape_lda),
        ("tuath", "tuathhousing.ie", scrape_tuath),
    ]:
        try:
            found = scraper()
            open_samples = [item for item in found if item.status == "open"][:3]
            print(f"[{name}] {len(found)} listings")
            listings.extend(found)
            results.append(
                SourceResult(
                    name=name,
                    label=label,
                    ok=True,
                    count=len(found),
                    open_samples=open_samples,
                )
            )
        except Exception as exc:
            print(f"[{name}] ERROR: {exc}", file=sys.stderr)
            traceback.print_exc()
            results.append(
                SourceResult(name=name, label=label, ok=False, error=str(exc))
            )

    if all(not result.ok for result in results):
        raise RuntimeError("All scrapers failed")

    return listings, results


def scrape_all() -> list[Listing]:
    listings, _ = scrape_sources()
    return listings


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily cost rental scrape and alert")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape and print message without sending WhatsApp",
    )
    parser.add_argument(
        "--scrape-only",
        action="store_true",
        help="Only scrape and update database, no notification",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Send a connection test report to WhatsApp (does not affect daily alerts)",
    )
    args = parser.parse_args()

    conn = connect()
    init_db(conn)

    listings, source_results = scrape_sources()
    enrich_cross_source_open_dates(listings)
    normalize_listing_statuses(listings)
    upsert_listings(conn, listings)

    if args.scrape_only:
        print(f"Scrape complete. {len(listings)} listings upserted.")
        return 0

    if args.test:
        whatsapp_ok = bool(
            os.environ.get("CALLMEBOT_PHONE", "").strip()
            and os.environ.get("CALLMEBOT_APIKEY", "").strip()
        )
        message = format_test_message(
            source_results=source_results,
            total_scraped=len(listings),
            whatsapp_configured=whatsapp_ok,
        )
        send_whatsapp(message, dry_run=args.dry_run)
        send_email(message, dry_run=args.dry_run)
        print(message)
        return 0

    news = find_news(conn)
    closing_soon = find_closing_soon(conn)
    opening_soon = find_opening_soon(conn)

    # First WhatsApp run: avoid flooding with every currently-open scheme.
    bootstrap = get_meta(conn, "bootstrap_done") is None
    if bootstrap:
        message = (
            f"🏠 Cost Rental Alert — first run\n\n"
            f"✅ Database created with {len(listings)} schemes monitored.\n"
            f"From tomorrow you'll receive daily updates only."
        )
        whatsapp_message = message
    else:
        message = format_message(
            news,
            total_scraped=len(listings),
            closing_soon=closing_soon,
            opening_soon=opening_soon,
        )
        whatsapp_message = format_whatsapp_message(
            news,
            total_scraped=len(listings),
            closing_soon=closing_soon,
            opening_soon=opening_soon,
        )

    sent_whatsapp = send_whatsapp(whatsapp_message, dry_run=args.dry_run)
    sent_email = send_email(message, dry_run=args.dry_run)
    sent = sent_whatsapp or sent_email

    if sent:
        if bootstrap:
            set_meta(conn, "bootstrap_done", "1")
        else:
            for item in news:
                mark_notified(conn, item.listing_id, item.notification_type)

    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

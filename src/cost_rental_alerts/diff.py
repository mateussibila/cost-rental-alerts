from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List

import sqlite3

from cost_rental_alerts.db import TZ, today_iso, was_notified


@dataclass
class NewsItem:
    listing_id: str
    title: str
    location: str
    url: str
    status: str
    price_from: float | None
    notification_type: str  # new_open | opened_today | apply_now | opening_soon
    bedrooms: str | None = None
    applications_close_at: str | None = None
    applications_open_at: str | None = None
    source: str = ""
    scheme_key: str = ""


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _is_today(ts: str | None) -> bool:
    if not ts:
        return False
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        return dt.astimezone(TZ).date().isoformat() == today_iso()
    except ValueError:
        return False


def _news_item_from_row(row: sqlite3.Row, notification_type: str) -> NewsItem:
    return NewsItem(
        listing_id=row["id"],
        title=row["title"],
        location=row["location"] or "",
        url=row["url"],
        status=row["status"],
        price_from=row["price_from"],
        bedrooms=row["bedrooms"],
        notification_type=notification_type,
        applications_close_at=row["applications_close_at"],
        applications_open_at=row["applications_open_at"],
        source=row["source"],
        scheme_key=row["scheme_key"] or row["id"],
    )


def find_news(conn: sqlite3.Connection, opening_soon_days: int = 14) -> List[NewsItem]:
    today = date.fromisoformat(today_iso())
    soon_end = today + timedelta(days=opening_soon_days)
    items: List[NewsItem] = []
    seen_keys = set()

    rows = conn.execute(
        """
        SELECT * FROM listings
        WHERE category = 'rent'
        ORDER BY title
        """
    ).fetchall()

    for row in rows:
        first_seen_today = _is_today(row["first_seen_at"])
        status_changed_today = _is_today(row["status_changed_at"])
        is_open = row["status"] == "open"

        if is_open and (first_seen_today or (status_changed_today and not first_seen_today)):
            key = (row["id"], "new_open")
            if key not in seen_keys:
                seen_keys.add(key)
                items.append(
                    _news_item_from_row(
                        row,
                        "opened_today" if status_changed_today and not first_seen_today else "new_open",
                    )
                )

        open_at = _parse_date(row["applications_open_at"])
        if (
            row["status"] != "open"
            and open_at
            and today < open_at <= soon_end
            and not was_notified(conn, row["id"], "opening_soon")
        ):
            key = (row["id"], "opening_soon")
            if key not in seen_keys:
                seen_keys.add(key)
                items.append(_news_item_from_row(row, "opening_soon"))

    return items


def _is_new_application_today(row: sqlite3.Row) -> bool:
    if row["status"] != "open":
        return False
    first_seen_today = _is_today(row["first_seen_at"])
    status_changed_today = _is_today(row["status_changed_at"])
    return first_seen_today or (status_changed_today and not first_seen_today)


def find_apply_now(conn: sqlite3.Connection) -> List[NewsItem]:
    """All open listings for the daily Apply now digest."""
    items: List[NewsItem] = []

    rows = conn.execute(
        """
        SELECT * FROM listings
        WHERE category = 'rent'
          AND status = 'open'
        ORDER BY applications_close_at, title
        """
    ).fetchall()

    for row in rows:
        if _is_new_application_today(row):
            first_seen_today = _is_today(row["first_seen_at"])
            status_changed_today = _is_today(row["status_changed_at"])
            ntype = (
                "opened_today"
                if status_changed_today and not first_seen_today
                else "new_open"
            )
        else:
            ntype = "apply_now"
        items.append(_news_item_from_row(row, ntype))

    return items


def find_opening_soon(conn: sqlite3.Connection, opening_soon_days: int = 14) -> List[NewsItem]:
    """Daily digest of upcoming openings, including already-notified listings."""
    today = date.fromisoformat(today_iso())
    soon_end = today + timedelta(days=opening_soon_days)
    items: List[NewsItem] = []

    rows = conn.execute(
        """
        SELECT * FROM listings
        WHERE category = 'rent'
          AND status != 'open'
          AND applications_open_at IS NOT NULL
        ORDER BY applications_open_at, title
        """
    ).fetchall()

    for row in rows:
        open_at = _parse_date(row["applications_open_at"])
        if open_at and today < open_at <= soon_end:
            items.append(_news_item_from_row(row, "opening_soon"))

    return items

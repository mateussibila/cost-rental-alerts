import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

from cost_rental_alerts.models import Listing
from cost_rental_alerts.paths import DATA_DIR
from cost_rental_alerts.schemes import compute_scheme_key

TZ = ZoneInfo("Europe/Dublin")
DB_PATH = DATA_DIR / "listings.db"


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def today_iso() -> str:
    return datetime.now(TZ).date().isoformat()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS listings (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            location TEXT,
            url TEXT NOT NULL,
            status TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'rent',
            price_from REAL,
            bedrooms TEXT,
            quantity INTEGER,
            income_min REAL,
            income_max REAL,
            applications_open_at TEXT,
            applications_close_at TEXT,
            listed_at TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            status_changed_at TEXT,
            scheme_key TEXT
        );

        CREATE TABLE IF NOT EXISTS notifications_sent (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id TEXT NOT NULL,
            notification_type TEXT NOT NULL,
            sent_at TEXT NOT NULL,
            UNIQUE(listing_id, notification_type)
        );

        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    conn.commit()
    _migrate_schema(conn)


def _migrate_schema(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(listings)")}
    if "scheme_key" not in columns:
        conn.execute("ALTER TABLE listings ADD COLUMN scheme_key TEXT")
    if "quantity" not in columns:
        conn.execute("ALTER TABLE listings ADD COLUMN quantity INTEGER")
    if "income_min" not in columns:
        conn.execute("ALTER TABLE listings ADD COLUMN income_min REAL")
    if "income_max" not in columns:
        conn.execute("ALTER TABLE listings ADD COLUMN income_max REAL")
    if "address" not in columns:
        conn.execute("ALTER TABLE listings ADD COLUMN address TEXT")
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO meta (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )
    conn.commit()


def get_listing(conn: sqlite3.Connection, listing_id: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()


def listing_from_row(row: sqlite3.Row) -> Listing:
    return Listing(
        id=row["id"],
        source=row["source"],
        title=row["title"],
        location=row["location"] or "",
        url=row["url"],
        status=row["status"],
        category=row["category"],
        price_from=row["price_from"],
        bedrooms=row["bedrooms"],
        quantity=row["quantity"],
        income_min=row["income_min"],
        income_max=row["income_max"],
        applications_open_at=row["applications_open_at"],
        applications_close_at=row["applications_close_at"],
        listed_at=row["listed_at"],
        scheme_key=row["scheme_key"],
        address=row["address"],
    )


def persist_listing_closed(conn: sqlite3.Connection, listing: Listing) -> None:
    ts = now_iso()
    existing = get_listing(conn, listing.id)
    if existing is None:
        return
    status_changed_at = existing["status_changed_at"]
    if existing["status"] != listing.status:
        status_changed_at = ts
    conn.execute(
        """
        UPDATE listings SET
            status = ?,
            applications_close_at = COALESCE(?, applications_close_at),
            status_changed_at = ?
        WHERE id = ?
        """,
        (
            listing.status,
            listing.applications_close_at,
            status_changed_at,
            listing.id,
        ),
    )


def _resolve_scheme_key(listing: Listing, existing: Optional[sqlite3.Row] = None) -> str:
    open_at = listing.applications_open_at
    listed_at = listing.listed_at
    if existing is not None:
        open_at = open_at or existing["applications_open_at"]
        listed_at = listed_at or existing["listed_at"]
    return compute_scheme_key(
        listing.title,
        open_at,
        listed_at,
        listing.id,
    )


def upsert_listings(conn: sqlite3.Connection, listings: Iterable[Listing]) -> None:
    ts = now_iso()
    for listing in listings:
        existing = get_listing(conn, listing.id)
        scheme_key = _resolve_scheme_key(listing, existing)
        listing.scheme_key = scheme_key

        if existing is None:
            conn.execute(
                """
                INSERT INTO listings (
                    id, source, title, location, url, status, category,
                    price_from, bedrooms, quantity, income_min, income_max,
                    applications_open_at, applications_close_at,
                    listed_at, first_seen_at, last_seen_at, status_changed_at,
                    scheme_key, address
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    listing.id,
                    listing.source,
                    listing.title,
                    listing.location,
                    listing.url,
                    listing.status,
                    listing.category,
                    listing.price_from,
                    listing.bedrooms,
                    listing.quantity,
                    listing.income_min,
                    listing.income_max,
                    listing.applications_open_at,
                    listing.applications_close_at,
                    listing.listed_at,
                    ts,
                    ts,
                    ts,
                    scheme_key,
                    listing.address,
                ),
            )
            continue

        status_changed_at = existing["status_changed_at"]
        if existing["status"] != listing.status:
            status_changed_at = ts

        conn.execute(
            """
            UPDATE listings SET
                source = ?, title = ?, location = ?, url = ?, status = ?, category = ?,
                price_from = ?,
                bedrooms = ?,
                quantity = ?,
                income_min = ?,
                income_max = ?,
                applications_open_at = CASE
                    WHEN ? IS NOT NULL THEN ?
                    WHEN ? != 'open' THEN NULL
                    ELSE applications_open_at
                END,
                applications_close_at = CASE
                    WHEN ? = 'lda' THEN ?
                    WHEN ? IS NOT NULL THEN ?
                    WHEN ? != 'open' THEN NULL
                    ELSE applications_close_at
                END,
                listed_at = COALESCE(?, listed_at),
                address = COALESCE(?, address),
                last_seen_at = ?,
                status_changed_at = ?,
                scheme_key = ?
            WHERE id = ?
            """,
            (
                listing.source,
                listing.title,
                listing.location,
                listing.url,
                listing.status,
                listing.category,
                listing.price_from,
                listing.bedrooms,
                listing.quantity,
                listing.income_min,
                listing.income_max,
                listing.applications_open_at,
                listing.applications_open_at,
                listing.status,
                listing.source,
                listing.applications_close_at,
                listing.applications_close_at,
                listing.applications_close_at,
                listing.status,
                listing.listed_at,
                listing.address,
                ts,
                status_changed_at,
                scheme_key,
                listing.id,
            ),
        )
    conn.commit()


def was_notified(conn: sqlite3.Connection, listing_id: str, notification_type: str) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM notifications_sent
        WHERE listing_id = ? AND notification_type = ?
        """,
        (listing_id, notification_type),
    ).fetchone()
    return row is not None


def mark_notified(
    conn: sqlite3.Connection, listing_id: str, notification_type: str
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO notifications_sent (listing_id, notification_type, sent_at)
        VALUES (?, ?, ?)
        """,
        (listing_id, notification_type, now_iso()),
    )
    conn.commit()

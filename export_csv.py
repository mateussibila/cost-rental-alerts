#!/usr/bin/env python3
"""Export listings.db to listings-export.csv."""

import csv
import sqlite3
from datetime import datetime
from pathlib import Path

from locations import format_city_neighborhood

DB_PATH = Path(__file__).parent / "listings.db"
OUT_PATH = Path(__file__).parent / "listings-export.csv"


def fmt_date(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        return datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return iso


def fmt_price(price: float | None) -> str:
    if price is None:
        return ""
    if float(price) == int(price):
        return str(int(price))
    s = f"{float(price):.2f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def fmt_beds(bedrooms: str | None) -> str:
    if not bedrooms:
        return ""
    return bedrooms.removesuffix(" bed").strip()


def export_csv() -> int:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """
        SELECT title, location, address, price_from, quantity, bedrooms, status,
               income_min, income_max,
               listed_at, applications_open_at, applications_close_at, source, url
        FROM listings WHERE category = 'rent'
        ORDER BY lower(title), source
        """
    ).fetchall()

    with OUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "name",
                "location",
                "address",
                "price",
                "quantity",
                "beds",
                "is_open",
                "income_min",
                "income_max",
                "listed_at",
                "open_on",
                "close_on",
                "source",
                "link",
            ]
        )
        for (
            title,
            location,
            address,
            price,
            quantity,
            bedrooms,
            status,
            income_min,
            income_max,
            listed,
            open_,
            close,
            source,
            url,
        ) in rows:
            writer.writerow(
                [
                    title,
                    format_city_neighborhood(title, location or ""),
                    address or "",
                    fmt_price(price),
                    quantity if quantity is not None else "",
                    fmt_beds(bedrooms),
                    "TRUE" if status == "open" else "FALSE",
                    fmt_price(income_min),
                    fmt_price(income_max),
                    fmt_date(listed),
                    fmt_date(open_),
                    fmt_date(close),
                    source,
                    url or "",
                ]
            )

    return len(rows)


if __name__ == "__main__":
    count = export_csv()
    print(f"Wrote {count} rows to {OUT_PATH}")

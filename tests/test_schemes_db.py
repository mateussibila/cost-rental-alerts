import sqlite3
import unittest

from cost_rental_alerts.db import init_db, listing_from_row, upsert_listings
from cost_rental_alerts.models import Listing
from cost_rental_alerts.schemes import apply_affordablehomes_closed_overrides_to_db


class AffordableHomesDbOverrideTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)

    def test_db_override_closes_stale_open_tuath_when_scrape_fails(self):
        stale_tuath = Listing(
            id="tuath:folkstown-park-2",
            source="tuath",
            title="Folkstown Park",
            location="Dublin",
            url="https://example.test/tuath",
            status="open",
            category="rent",
            applications_open_at="2026-06-04",
        )
        upsert_listings(self.conn, [stale_tuath])

        scraped_ah = [
            Listing(
                id="affordablehomes:folkstownpark1",
                source="affordablehomes",
                title="Folkstown Park",
                location="Dublin",
                url="https://example.test/ah",
                status="closed",
                category="rent",
                applications_open_at="2026-06-04",
                applications_close_at="2026-06-22",
            )
        ]

        closed = apply_affordablehomes_closed_overrides_to_db(self.conn, scraped_ah)

        self.assertEqual(closed, 1)
        row = self.conn.execute(
            "SELECT status, applications_close_at FROM listings WHERE id = ?",
            (stale_tuath.id,),
        ).fetchone()
        self.assertEqual(row["status"], "closed")
        self.assertEqual(row["applications_close_at"], "2026-06-22")

        listing = listing_from_row(
            self.conn.execute(
                "SELECT * FROM listings WHERE id = ?", (stale_tuath.id,)
            ).fetchone()
        )
        self.assertEqual(listing.status, "closed")


if __name__ == "__main__":
    unittest.main()

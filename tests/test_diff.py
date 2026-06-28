import sqlite3
import unittest

from cost_rental_alerts import diff
from cost_rental_alerts.db import init_db


class DiffDigestTests(unittest.TestCase):
    def setUp(self):
        self._original_today_iso = diff.today_iso
        diff.today_iso = lambda: "2026-06-10"

        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)

    def tearDown(self):
        diff.today_iso = self._original_today_iso
        self.conn.close()

    def _insert_listing(
        self,
        listing_id: str,
        *,
        status: str,
        open_at: str | None = None,
        close_at: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO listings (
                id, source, title, location, url, status, category,
                price_from, bedrooms, applications_open_at, applications_close_at,
                first_seen_at, last_seen_at, status_changed_at, scheme_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                listing_id,
                "affordablehomes",
                listing_id.title(),
                "Dublin",
                f"https://example.com/{listing_id}",
                status,
                "rent",
                1326,
                "1-2 bed",
                open_at,
                close_at,
                "2026-06-01T08:00:00+01:00",
                "2026-06-10T08:00:00+01:00",
                "2026-06-01T08:00:00+01:00",
                listing_id,
            ),
        )
        self.conn.commit()

    def test_opening_soon_digest_repeats_already_notified_items(self):
        self._insert_listing(
            "opening-soon",
            status="closed",
            open_at="2026-06-12",
        )
        self.conn.execute(
            """
            INSERT INTO notifications_sent (listing_id, notification_type, sent_at)
            VALUES (?, ?, ?)
            """,
            ("opening-soon", "opening_soon", "2026-06-09T08:00:00+01:00"),
        )
        self.conn.commit()

        news = diff.find_news(self.conn)
        digest = diff.find_opening_soon(self.conn)

        self.assertEqual([], [item.listing_id for item in news])
        self.assertEqual(["opening-soon"], [item.listing_id for item in digest])

    def test_apply_now_includes_all_open_and_marks_new_today(self):
        self._insert_listing(
            "new-today",
            status="open",
            close_at="2026-06-17",
        )
        self.conn.execute(
            """
            UPDATE listings
            SET first_seen_at = ?, status_changed_at = ?
            WHERE id = ?
            """,
            ("2026-06-10T08:00:00+01:00", "2026-06-10T08:00:00+01:00", "new-today"),
        )
        self._insert_listing(
            "existing",
            status="open",
            close_at="2026-06-20",
        )
        self.conn.commit()

        apply_now = diff.find_apply_now(self.conn)

        self.assertEqual(
            {item.listing_id: item.notification_type for item in apply_now},
            {"new-today": "new_open", "existing": "apply_now"},
        )


if __name__ == "__main__":
    unittest.main()

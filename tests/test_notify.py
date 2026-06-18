import unittest
from datetime import date

from cost_rental_alerts import notify
from cost_rental_alerts.diff import NewsItem


def _item(
    listing_id: str,
    title: str,
    *,
    notification_type: str,
    status: str,
    open_at: str | None = None,
    close_at: str | None = None,
) -> NewsItem:
    return NewsItem(
        listing_id=listing_id,
        title=title,
        location="Dublin",
        url=f"https://example.com/{listing_id}",
        status=status,
        price_from=1326,
        bedrooms="1-2 bed",
        notification_type=notification_type,
        applications_open_at=open_at,
        applications_close_at=close_at,
        source="affordablehomes",
        scheme_key=listing_id,
    )


class NotifyMessageTests(unittest.TestCase):
    def setUp(self):
        self._original_today = notify._today
        notify._today = lambda: date(2026, 6, 10)

    def tearDown(self):
        notify._today = self._original_today

    def test_no_news_message_includes_digest_sections(self):
        message = notify.format_message([], total_scraped=176)

        self.assertNotIn("No updates today", message)
        self.assertIn("🆕 NO NEW APPLICATIONS", message)
        self.assertIn("⏳ CLOSING SOON: none", message)
        self.assertIn("📅 OPENING SOON: none", message)

    def test_no_new_message_lists_closing_and_opening_soon(self):
        closing = [
            _item(
                "closing",
                "Closing Scheme",
                notification_type="closing_soon",
                status="open",
                close_at="2026-06-12",
            )
        ]
        opening = [
            _item(
                "opening",
                "Opening Scheme",
                notification_type="opening_soon",
                status="closed",
                open_at="2026-06-20",
            )
        ]

        message = notify.format_message(
            [],
            total_scraped=176,
            closing_soon=closing,
            opening_soon=opening,
        )

        self.assertIn("🆕 NO NEW APPLICATIONS", message)
        self.assertIn("⏳ CLOSING SOON (1):", message)
        self.assertIn("Closing Scheme", message)
        self.assertIn("Closes in 2 days", message)
        self.assertIn("📅 OPENING SOON (1):", message)
        self.assertIn("Opening Scheme", message)
        self.assertIn("Opens: 20/06/26", message)

    def test_new_application_is_not_repeated_in_closing_soon(self):
        lancaster = _item(
            "lancastergate3",
            "Lancaster Gate",
            notification_type="new_open",
            status="open",
            close_at="2026-06-17",
        )

        message = notify.format_message(
            [lancaster],
            total_scraped=180,
            closing_soon=[
                lancaster,
                _item(
                    "folkstown",
                    "Folkstown Park",
                    notification_type="closing_soon",
                    status="open",
                    close_at="2026-06-14",
                ),
            ],
        )

        self.assertIn("📢 NEW APPLICATIONS (1):", message)
        self.assertIn("⏳ CLOSING SOON (1):", message)
        self.assertEqual(message.count("Lancaster Gate"), 1)
        self.assertIn("Folkstown Park", message)


if __name__ == "__main__":
    unittest.main()

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
    location: str = "Dublin",
    open_at: str | None = None,
    close_at: str | None = None,
    price: float = 1326,
    bedrooms: str = "2 bed",
) -> NewsItem:
    return NewsItem(
        listing_id=listing_id,
        title=title,
        location=location,
        url=f"https://example.com/{listing_id}",
        status=status,
        price_from=price,
        bedrooms=bedrooms,
        notification_type=notification_type,
        applications_open_at=open_at,
        applications_close_at=close_at,
        source="affordablehomes",
        scheme_key=listing_id,
    )


class NotifyMessageTests(unittest.TestCase):
    def setUp(self):
        self._original_today = notify._today
        notify._today = lambda: date(2026, 6, 28)

    def tearDown(self):
        notify._today = self._original_today

    def test_whatsapp_message_template(self):
        message = notify.format_whatsapp_message(
            [
                _item(
                    "rath-rua",
                    "Rath Rua",
                    notification_type="new_open",
                    status="open",
                    location="Laois - Portlaoise",
                    close_at="2026-06-23",
                    price=1105,
                    bedrooms="2 bed",
                ),
                _item(
                    "cookstown",
                    "Cookstown Gateway",
                    notification_type="apply_now",
                    status="open",
                    location="Dublin 24",
                    close_at="2026-06-17",
                    price=1574,
                    bedrooms="2 bed",
                ),
            ],
            [
                _item(
                    "future",
                    "Future Scheme",
                    notification_type="opening_soon",
                    status="closed",
                    location="Cork City, Co. Cork",
                    open_at="2026-07-05",
                    price=1595,
                    bedrooms="2 bed",
                )
            ],
        )

        self.assertIn("🏠 Cost Rental — 28/06", message)
        self.assertIn("Scheme Hub:", message)
        self.assertIn("🟢 Apply now:", message)
        self.assertIn("🔥 Laois — Rath Rua", message)
        self.assertIn("Dublin — Cookstown Gateway", message)
        self.assertNotIn("🔥 Dublin — Cookstown Gateway", message)
        self.assertIn("🛏️ 2 | 💰 €1,105", message)
        self.assertIn("closes 23/06", message)
        self.assertIn("🔵 Opening soon:", message)
        self.assertIn("Cork — Future Scheme", message)
        self.assertIn("opens 05/07", message)
        self.assertNotIn("none", message.lower())
        self.assertNotIn("https://example.com", message)

    def test_email_message_includes_links_and_details(self):
        message = notify.format_message(
            [
                _item(
                    "rath-rua",
                    "Rath Rua",
                    notification_type="new_open",
                    status="open",
                    location="Laois - Portlaoise",
                    close_at="2026-06-23",
                    price=1105,
                )
            ],
            [],
        )

        self.assertIn("🏠 Cost Rental — 28/06/2026", message)
        self.assertIn("Scheme Hub:", message)
        self.assertIn("🟢 Apply now (1):", message)
        self.assertIn("🔥 Rath Rua — Laois - Portlaoise", message)
        self.assertIn("💰 from €1,105/mo", message)
        self.assertIn("Closes: 23/06/2026", message)
        self.assertIn("https://example.com/rath-rua", message)
        self.assertNotIn("🔵 Opening soon", message)

    def test_empty_sections_are_omitted(self):
        message = notify.format_whatsapp_message([], [])

        self.assertIn("Scheme Hub:", message)
        self.assertNotIn("Apply now", message)
        self.assertNotIn("Opening soon", message)

    def test_short_whatsapp_message_is_not_split(self):
        message = "🏠 Cost Rental — 28/06\n\nScheme Hub: https://example.com"

        chunks = notify._split_whatsapp_message(message, max_chars=500)

        self.assertEqual(chunks, [message])

    def test_long_whatsapp_message_is_split_into_numbered_parts(self):
        blocks = ["🏠 Cost Rental — 28/06", "Scheme Hub: https://example.com"]
        for index in range(1, 12):
            blocks.append(
                "\n".join(
                    [
                        f"Scheme {index} — Dublin",
                        "🛏️ 2 | 💰 €1,200",
                        f"closes 0{index}/07",
                    ]
                )
            )
        message = "\n\n".join(blocks)

        chunks = notify._split_whatsapp_message(message, max_chars=360)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 360 for chunk in chunks))


if __name__ == "__main__":
    unittest.main()

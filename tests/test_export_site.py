import unittest
from datetime import date

from cost_rental_alerts.export_site import (
    apply_now_schemes,
    build_schemes,
    closing_soon_schemes,
    opening_soon_schemes,
)


class ExportSiteTests(unittest.TestCase):
    def test_build_schemes_groups_duplicate_sources(self):
        rows = [
            {
                "name": "Folkstown Park",
                "location": "Dublin - Balbriggan",
                "address": "Folkstown Park, Balbriggan",
                "price": "1150",
                "quantity": "40",
                "beds": "1-3",
                "status": "open",
                "income_min": "",
                "income_max": "",
                "listed_at": "03/06/2026",
                "open_on": "04/06/2026",
                "close_on": "",
                "source": "affordablehomes",
                "link": "https://example.test/affordablehomes",
            },
            {
                "name": "Folkstown Park",
                "location": "Dublin - Balbriggan",
                "address": "Folkstown Park, Balbriggan",
                "price": "1150",
                "quantity": "40",
                "beds": "1-3",
                "status": "open",
                "income_min": "",
                "income_max": "",
                "listed_at": "",
                "open_on": "04/06/2026",
                "close_on": "",
                "source": "tuath",
                "link": "https://example.test/tuath",
            },
        ]

        schemes = build_schemes(rows)

        self.assertEqual(len(schemes), 1)
        self.assertEqual(schemes[0].name, "Folkstown Park")
        self.assertEqual(
            [(source.source, source.link) for source in schemes[0].sources],
            [
                ("affordablehomes", "https://example.test/affordablehomes"),
                ("tuath", "https://example.test/tuath"),
            ],
        )

    def test_sections_split_apply_opening_and_closing_soon(self):
        rows = [
            {
                "name": "Closing Soon",
                "location": "Dublin",
                "address": "",
                "price": "",
                "quantity": "",
                "beds": "",
                "status": "open",
                "income_min": "",
                "income_max": "",
                "listed_at": "",
                "open_on": "10/06/2026",
                "close_on": "20/06/2026",
                "source": "lda",
                "link": "https://example.test/closing",
            },
            {
                "name": "Opening Soon",
                "location": "Cork",
                "address": "",
                "price": "",
                "quantity": "",
                "beds": "",
                "status": "opening soon",
                "income_min": "",
                "income_max": "",
                "listed_at": "",
                "open_on": "25/06/2026",
                "close_on": "",
                "source": "affordablehomes",
                "link": "https://example.test/opening",
            },
            {
                "name": "Closed",
                "location": "Galway",
                "address": "",
                "price": "",
                "quantity": "",
                "beds": "",
                "status": "closed",
                "income_min": "",
                "income_max": "",
                "listed_at": "",
                "open_on": "",
                "close_on": "",
                "source": "tuath",
                "link": "https://example.test/closed",
            },
        ]

        schemes = build_schemes(rows)

        self.assertEqual([scheme.name for scheme in apply_now_schemes(schemes)], ["Closing Soon"])
        self.assertEqual([scheme.name for scheme in opening_soon_schemes(schemes)], ["Opening Soon"])
        self.assertEqual(
            [scheme.name for scheme in closing_soon_schemes(schemes, today=date(2026, 6, 13))],
            ["Closing Soon"],
        )


if __name__ == "__main__":
    unittest.main()

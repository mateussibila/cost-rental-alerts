import unittest
from datetime import date

from cost_rental_alerts.export_csv import resolve_export_status
from cost_rental_alerts.models import Listing
from cost_rental_alerts.schemes import apply_affordablehomes_closed_overrides
from cost_rental_alerts.scrapers.tuath import (
    _apply_closed_inference,
    _detail_applications_closed,
    _parse_close_at,
)


class TuathParserTests(unittest.TestCase):
    DETAIL_HTML = """
    <p>Application closing date is Monday, 22 June at 12:00PM.</p>
    <h2>Applications are now closed – visit our Cost Rental landing page.</h2>
    """

    def test_parse_close_at_uses_current_year_not_forced_future(self):
        close_at = _parse_close_at(self.DETAIL_HTML)
        self.assertEqual(close_at, "2026-06-22")

    def test_detail_page_closed_text_detected(self):
        self.assertTrue(_detail_applications_closed(self.DETAIL_HTML))

    def test_past_close_date_marks_listing_closed(self):
        listing = Listing(
            id="tuath:test",
            source="tuath",
            title="Test",
            location="Dublin",
            url="https://example.test",
            status="open",
            category="rent",
            applications_close_at="2026-06-22",
        )
        _apply_closed_inference(listing, self.DETAIL_HTML, listing.applications_close_at)
        self.assertEqual(listing.status, "closed")


class ExportStatusTests(unittest.TestCase):
    def test_past_close_date_exports_as_closed(self):
        status = resolve_export_status(
            "open",
            "2026-06-04",
            "2026-06-22",
            today=date(2026, 6, 28),
        )
        self.assertEqual(status, "closed")


class AffordableHomesOverrideTests(unittest.TestCase):
    def test_closed_affordablehomes_overrides_open_tuath_same_phase(self):
        listings = [
            Listing(
                id="affordablehomes:folkstown",
                source="affordablehomes",
                title="Folkstown Park",
                location="Dublin",
                url="https://example.test/ah",
                status="closed",
                category="rent",
                applications_open_at="2026-06-04",
                applications_close_at="2026-06-22",
            ),
            Listing(
                id="tuath:folkstown",
                source="tuath",
                title="Folkstown Park",
                location="Dublin",
                url="https://example.test/tuath",
                status="open",
                category="rent",
                applications_open_at="2026-06-04",
            ),
        ]

        apply_affordablehomes_closed_overrides(listings)

        self.assertEqual(listings[1].status, "closed")
        self.assertEqual(listings[1].applications_close_at, "2026-06-22")

    def test_closed_affordablehomes_overrides_open_tuath_with_one_day_open_drift(self):
        listings = [
            Listing(
                id="affordablehomes:folkstown",
                source="affordablehomes",
                title="Folkstown Park",
                location="Dublin",
                url="https://example.test/ah",
                status="closed",
                category="rent",
                applications_open_at="2026-06-03",
                applications_close_at="2026-06-22",
            ),
            Listing(
                id="tuath:folkstown",
                source="tuath",
                title="Folkstown Park",
                location="Dublin",
                url="https://example.test/tuath",
                status="open",
                category="rent",
                applications_open_at="2026-06-04",
            ),
        ]

        apply_affordablehomes_closed_overrides(listings)

        self.assertEqual(listings[1].status, "closed")
        self.assertEqual(listings[1].applications_close_at, "2026-06-22")

    def test_closed_affordablehomes_does_not_override_different_phase(self):
        listings = [
            Listing(
                id="affordablehomes:folkstown-old",
                source="affordablehomes",
                title="Folkstown Park",
                location="Dublin",
                url="https://example.test/ah-old",
                status="closed",
                category="rent",
                applications_open_at="2026-03-20",
                applications_close_at="2026-03-27",
            ),
            Listing(
                id="tuath:folkstown",
                source="tuath",
                title="Folkstown Park",
                location="Dublin",
                url="https://example.test/tuath",
                status="open",
                category="rent",
                applications_open_at="2026-06-04",
            ),
        ]

        apply_affordablehomes_closed_overrides(listings)

        self.assertEqual(listings[1].status, "open")


if __name__ == "__main__":
    unittest.main()

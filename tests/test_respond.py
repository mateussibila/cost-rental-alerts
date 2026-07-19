import unittest

from cost_rental_alerts.models import Listing
from cost_rental_alerts.schemes import same_scheme_phase
from cost_rental_alerts.scrapers.respond import _index_listings, _parse_close_at


class RespondParserTests(unittest.TestCase):
    INDEX_HTML = """
    <h2>Current Listings</h2>
    <h3>Airton Road</h3>
    <a href="https://www.respond.ie/properties/airton-road-2/">View</a>
    <h3>Westfield, Leixlip</h3>
    <a href="https://www.respond.ie/properties/westfield/">View</a>
    <h3>The Granary, Swords</h3>
    <a href="https://www.respond.ie/properties/mooretown-swords/">View</a>
    <h3>Step 1</h3>
    <a href="https://www.respond.ie/properties/pipers-square/">View</a>
    <h2>Closed Listings</h2>
    <h3>Pipers Square</h3>
    <a href="https://www.respond.ie/properties/pipers-square/">View</a>
    """

    def test_index_keeps_current_and_closed_without_step_noise(self):
        items = _index_listings(self.INDEX_HTML)
        by_url = {url: (title, status) for title, url, status in items}
        self.assertEqual(by_url["https://www.respond.ie/properties/westfield/"][1], "open")
        self.assertEqual(
            by_url["https://www.respond.ie/properties/mooretown-swords/"][0],
            "The Granary, Swords",
        )
        self.assertEqual(by_url["https://www.respond.ie/properties/pipers-square/"][1], "closed")
        self.assertNotIn("Step 1", [title for title, _, _ in items])

    def test_parse_close_at(self):
        self.assertEqual(
            _parse_close_at("Closing Date 27/07/26 @11am Apply Now"),
            "2026-07-27",
        )


class StrictPhaseMatchTests(unittest.TestCase):
    def _listing(self, **kwargs):
        base = dict(
            id="x",
            source="lda",
            title="Woodside Rise",
            location="Dublin",
            url="https://example.test",
            status="open",
            category="rent",
            price_from=1257.0,
            applications_open_at="2026-07-13",
            applications_close_at="2026-07-20",
        )
        base.update(kwargs)
        return Listing(**base)

    def test_same_name_price_and_close_matches(self):
        left = self._listing(source="affordablehomes")
        right = self._listing(source="tuath", applications_open_at=None)
        self.assertTrue(same_scheme_phase(left, right))

    def test_missing_price_does_not_match(self):
        left = self._listing(source="affordablehomes")
        right = self._listing(source="respond", price_from=None)
        self.assertFalse(same_scheme_phase(left, right))

    def test_different_close_and_open_does_not_match(self):
        left = self._listing(source="affordablehomes")
        right = self._listing(
            source="respond",
            applications_open_at="2026-01-01",
            applications_close_at="2026-01-10",
        )
        self.assertFalse(same_scheme_phase(left, right))


if __name__ == "__main__":
    unittest.main()

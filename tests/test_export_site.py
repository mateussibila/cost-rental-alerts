import unittest
from unittest.mock import patch

from cost_rental_alerts.export_site import (
    BUTTONDOWN_SUBSCRIBE_URL,
    HUB_LOGO_URL,
    SUBSCRIBE_DISMISS_STORAGE_KEY,
    SUBSCRIBE_HERO_URL,
    VIEW_MODE_STORAGE_KEY,
    apply_now_schemes,
    build_schemes,
    enrich_scheme_sources,
    opening_soon_schemes,
    render_html,
    report_issue_href,
    sort_source_links,
    SourceLink,
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

    def test_sections_split_apply_and_opening_soon(self):
        rows = [
            {
                "name": "Apply Now",
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
                "link": "https://example.test/apply",
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

        self.assertEqual([scheme.name for scheme in apply_now_schemes(schemes)], ["Apply Now"])
        self.assertEqual([scheme.name for scheme in opening_soon_schemes(schemes)], ["Opening Soon"])

    def test_enrich_scheme_sources_adds_alternate_links_by_name(self):
        rows = [
            {
                "name": "Mountneil",
                "location": "Waterford - Carrickperish",
                "address": "",
                "price": "1219",
                "quantity": "1",
                "beds": "3",
                "status": "open",
                "income_min": "",
                "income_max": "",
                "listed_at": "",
                "open_on": "04/06/2026",
                "close_on": "11/06/2026",
                "source": "tuath",
                "link": "https://example.test/tuath/mountneil",
            },
            {
                "name": "Mountneil",
                "location": "Wexford - Carrickperish",
                "address": "",
                "price": "1219",
                "quantity": "1",
                "beds": "3",
                "status": "open",
                "income_min": "",
                "income_max": "",
                "listed_at": "",
                "open_on": "04/06/2026",
                "close_on": "11/06/2026",
                "source": "affordablehomes",
                "link": "https://example.test/affordablehomes/mountneil1",
            },
        ]

        schemes = build_schemes(rows)
        enrich_scheme_sources(schemes, rows)

        self.assertEqual(len(schemes), 2)
        self.assertEqual(
            [(source.source, source.link) for source in sort_source_links(schemes[0].sources)],
            [
                ("affordablehomes", "https://example.test/affordablehomes/mountneil1"),
                ("tuath", "https://example.test/tuath/mountneil"),
            ],
        )

    def test_enrich_scheme_sources_skips_closed_phase_links(self):
        rows = [
            {
                "name": "Kilcarbery Grange",
                "location": "Dublin - D22 Clondalkin",
                "address": "",
                "price": "1264",
                "quantity": "2",
                "beds": "2",
                "status": "open",
                "income_min": "",
                "income_max": "",
                "listed_at": "",
                "open_on": "23/06/2026",
                "close_on": "30/06/2026",
                "source": "affordablehomes",
                "link": "https://example.test/kilcarberygrange2",
            },
            {
                "name": "Kilcarbery Grange",
                "location": "Dublin - Clondalkin",
                "address": "",
                "price": "1295",
                "quantity": "1",
                "beds": "1",
                "status": "closed",
                "income_min": "",
                "income_max": "",
                "listed_at": "",
                "open_on": "09/04/2026",
                "close_on": "16/04/2026",
                "source": "affordablehomes",
                "link": "https://example.test/kilcarberygrange1",
            },
            {
                "name": "Kilcarbery Grange",
                "location": "Dublin - Clondalkin",
                "address": "",
                "price": "1295",
                "quantity": "1",
                "beds": "1",
                "status": "closed",
                "income_min": "",
                "income_max": "",
                "listed_at": "",
                "open_on": "17/10/2025",
                "close_on": "24/10/2025",
                "source": "affordablehomes",
                "link": "https://example.test/kilcarberygrange",
            },
        ]

        schemes = build_schemes(rows)
        enrich_scheme_sources(schemes, rows)

        self.assertEqual(
            [(source.source, source.link) for source in schemes[0].sources],
            [("affordablehomes", "https://example.test/kilcarberygrange2")],
        )

    def test_build_schemes_keeps_one_link_per_source(self):
        rows = [
            {
                "name": "Kilcarbery Grange",
                "location": "Dublin - D22 Clondalkin",
                "address": "",
                "price": "1264",
                "quantity": "2",
                "beds": "2",
                "status": "open",
                "income_min": "",
                "income_max": "",
                "listed_at": "",
                "open_on": "23/06/2026",
                "close_on": "30/06/2026",
                "source": "affordablehomes",
                "link": "https://example.test/kilcarberygrange2",
            },
            {
                "name": "Kilcarbery Grange",
                "location": "Dublin - D22 Clondalkin",
                "address": "",
                "price": "1295",
                "quantity": "1",
                "beds": "1",
                "status": "open",
                "income_min": "",
                "income_max": "",
                "listed_at": "",
                "open_on": "01/07/2026",
                "close_on": "08/07/2026",
                "source": "affordablehomes",
                "link": "https://example.test/kilcarberygrange3",
            },
        ]

        schemes = build_schemes(rows)

        self.assertEqual(len(schemes), 2)
        self.assertEqual(
            [(source.source, source.link) for source in schemes[0].sources],
            [("affordablehomes", "https://example.test/kilcarberygrange2")],
        )
        self.assertEqual(
            [(source.source, source.link) for source in schemes[1].sources],
            [("affordablehomes", "https://example.test/kilcarberygrange3")],
        )

    def test_report_issue_href_uses_default_ops_email(self):
        with patch.dict("os.environ", {}, clear=True):
            href = report_issue_href()

        self.assertIn("mailto:costrentalhub@gmail.com", href)

    def test_report_issue_href_prefills_scheme_name(self):
        with patch.dict("os.environ", {}, clear=True):
            href = report_issue_href(scheme_name="Kilcarbery Grange")

        self.assertIn("Kilcarbery%20Grange", href)

    def test_mobile_card_details_use_compact_grid(self):
        html = render_html([])

        self.assertIn(
            ".details {\n        grid-template-columns: repeat(6, minmax(0, 1fr));",
            html,
        )
        self.assertIn(".detail:nth-child(1),", html)
        self.assertIn(".detail:nth-child(3),", html)
        self.assertNotIn(
            ".scheme-grid,\n      .details {\n        grid-template-columns: 1fr;",
            html,
        )

    def test_mobile_hub_actions_use_three_columns(self):
        html = render_html([])

        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr));", html)
        self.assertIn(".summary-card {\n        padding: 16px;", html)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr));", html)
        self.assertIn(".hub-action--primary {\n        grid-column: 1 / -1;", html)
        self.assertIn('class="hub-actions"', html)

    def test_hub_actions_replace_toolbar(self):
        html = render_html([])

        self.assertNotIn('class="toolbar"', html)
        self.assertNotIn("scheme-search", html)
        self.assertNotIn("<footer>", html)
        self.assertIn("data-open-about", html)
        self.assertIn("data-open-cost-rental", html)
        self.assertIn("What is cost rental?", html)
        self.assertIn("About Ireland Cost Rental Hub", html)

    def test_hero_source_text_uses_portals_tooltip(self):
        html = render_html([])

        self.assertIn("Updated daily from cost rental portals", html)
        self.assertNotIn(
            "Updated daily from affordablehomes.ie, LDA, and Tuath Housing",
            html,
        )
        self.assertIn("Affordable Homes Ireland", html)
        self.assertIn("LDA", html)
        self.assertIn("Tuath Housing", html)
        self.assertIn("Clúid", html)
        self.assertIn("Respond", html)
        self.assertIn("Circle VHA", html)
        self.assertIn("Co-operative Housing Ireland", html)
        self.assertIn("Oaklee", html)
        self.assertIn("Ó Cualann", html)
        self.assertIn("Fold Ireland", html)
        self.assertNotIn("scrape", html.lower())

    def test_subscribe_modal_and_hub_actions(self):
        html = render_html([])

        self.assertIn('data-open-subscribe data-i18n="action.email"', html)
        self.assertIn("Get cost rental alerts", html)
        self.assertIn(BUTTONDOWN_SUBSCRIBE_URL, html)
        self.assertIn('name="embed" value="1"', html)
        self.assertIn("subscribe-consent", html)
        self.assertIn("Affordable Homes Ireland", html)
        self.assertIn("subscribe-not-now", html)
        self.assertIn(SUBSCRIBE_DISMISS_STORAGE_KEY, html)
        self.assertIn("data-open-subscribe", html)
        self.assertIn(SUBSCRIBE_HERO_URL, html)
        self.assertIn("Help improve this", html)
        self.assertIn("Free service — some gaps", html)
        self.assertIn("Get free daily alerts for schemes", html)
        self.assertIn("lang-toggle", html)
        self.assertIn('data-lang="pt"', html)
        self.assertIn("LANGUAGE_STORAGE_KEY", html)

    def test_hero_shows_logo(self):
        html = render_html([])

        self.assertIn('class="hero-logo"', html)
        self.assertIn(HUB_LOGO_URL, html)
        self.assertIn('class="hero-brand"', html)

    def test_desktop_view_toggle_defaults_to_table(self):
        html = render_html([])

        self.assertIn('data-view="table"', html)
        self.assertIn('class="view-toggle"', html)
        self.assertIn('data-view-mode="table"', html)
        self.assertIn('data-view-mode="cards"', html)
        self.assertIn(VIEW_MODE_STORAGE_KEY, html)
        self.assertIn(
            '.scheme-section:not([data-view="cards"]) .scheme-table-wrap',
            html,
        )


if __name__ == "__main__":
    unittest.main()

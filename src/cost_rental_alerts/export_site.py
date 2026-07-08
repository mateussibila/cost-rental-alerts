#!/usr/bin/env python3
"""Generate a static GitHub Pages dashboard from the scheme CSV export."""

from __future__ import annotations

import csv
import os
import re
import shutil
import urllib.parse
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from cost_rental_alerts.hub_i18n import LANGUAGE_STORAGE_KEY, TRANSLATIONS, translations_json
from cost_rental_alerts.notify import report_issue_email, scheme_hub_url
from cost_rental_alerts.paths import DATA_DIR, REPO_ROOT

TZ = ZoneInfo("Europe/Dublin")
SOURCE_LINK_PRIORITY = {"affordablehomes": 0, "lda": 1, "tuath": 2}
DEFAULT_REPORT_ISSUE_REPO = "costrentalhub/cost-rental-alerts"

CSV_PATH = DATA_DIR / "listings-export.csv"
SITE_DIR = REPO_ROOT / "site"
INDEX_PATH = SITE_DIR / "index.html"
HUB_LOGO_PATH = REPO_ROOT / "assets" / "cr-house-logo.png"
HUB_LOGO_SITE_PATH = SITE_DIR / "assets" / "cr-house-logo.png"
HUB_LOGO_URL = "assets/cr-house-logo.png"
SUBSCRIBE_HERO_PATH = REPO_ROOT / "assets" / "email-modal-hero.jpg"
SUBSCRIBE_HERO_SITE_PATH = SITE_DIR / "assets" / "email-modal-hero.jpg"
SUBSCRIBE_HERO_URL = "assets/email-modal-hero.jpg"


@dataclass
class SourceLink:
    source: str
    link: str


@dataclass
class Scheme:
    name: str
    location: str
    address: str
    price: str
    quantity: str
    beds: str
    status: str
    income_min: str
    income_max: str
    listed_at: str
    open_on: str
    close_on: str
    sources: list[SourceLink] = field(default_factory=list)

    @property
    def search_text(self) -> str:
        values = [
            self.name,
            self.location,
            self.address,
            self.status,
            self.price,
            self.quantity,
            self.beds,
            self.open_on,
            self.close_on,
            " ".join(source.source for source in self.sources),
        ]
        return " ".join(value for value in values if value).lower()


def parse_csv_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def date_sort_value(value: str) -> tuple[int, date]:
    parsed = parse_csv_date(value)
    if parsed is None:
        return (1, date.max)
    return (0, parsed)


def normalize_key(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().casefold())


def row_score(row: dict[str, str]) -> tuple[int, int]:
    source_priority = {"affordablehomes": 3, "lda": 2, "tuath": 1}
    filled_fields = sum(1 for value in row.values() if value)
    return filled_fields, source_priority.get(normalize_key(row.get("source")), 0)


def scheme_key(row: dict[str, str]) -> tuple[str, str, str, str, str]:
    return (
        normalize_key(row.get("name")),
        normalize_key(row.get("location")),
        normalize_key(row.get("status")),
        normalize_key(row.get("open_on")),
        normalize_key(row.get("close_on")),
    )


def load_rows(csv_path: Path = CSV_PATH) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _best_link_per_source(
    rows: Iterable[dict[str, str]],
) -> dict[str, SourceLink]:
    """Keep one active link per source, preferring the fullest row."""
    best: dict[str, tuple[tuple[int, int], SourceLink]] = {}
    for row in rows:
        status = normalize_key(row.get("status"))
        if status not in {"open", "opening soon"}:
            continue
        source = row.get("source", "").strip()
        link = row.get("link", "").strip()
        if not source or not link:
            continue
        src_key = normalize_key(source)
        score = row_score(row)
        existing = best.get(src_key)
        if existing is None or score > existing[0]:
            best[src_key] = (score, SourceLink(source=source, link=link))
    return {src_key: link for src_key, (_, link) in best.items()}


def active_links_by_name(rows: Iterable[dict[str, str]]) -> dict[str, dict[str, SourceLink]]:
    """Map scheme name -> source -> best active link."""
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        name = normalize_key(row.get("name"))
        if not name:
            continue
        grouped.setdefault(name, []).append(row)

    return {
        name: _best_link_per_source(name_rows)
        for name, name_rows in grouped.items()
    }


def build_schemes(rows: Iterable[dict[str, str]]) -> list[Scheme]:
    grouped: dict[tuple[str, str, str, str, str], list[dict[str, str]]] = {}
    for row in rows:
        if normalize_key(row.get("status")) in {"open", "opening soon"}:
            grouped.setdefault(scheme_key(row), []).append(row)

    schemes: list[Scheme] = []
    for group_rows in grouped.values():
        best = max(group_rows, key=row_score)
        links_by_source = _best_link_per_source(group_rows)
        sources = sort_source_links(links_by_source.values())

        schemes.append(
            Scheme(
                name=best.get("name", "").strip(),
                location=best.get("location", "").strip(),
                address=best.get("address", "").strip(),
                price=best.get("price", "").strip(),
                quantity=best.get("quantity", "").strip(),
                beds=best.get("beds", "").strip(),
                status=best.get("status", "").strip(),
                income_min=best.get("income_min", "").strip(),
                income_max=best.get("income_max", "").strip(),
                listed_at=best.get("listed_at", "").strip(),
                open_on=best.get("open_on", "").strip(),
                close_on=best.get("close_on", "").strip(),
                sources=sources,
            )
        )

    return sorted(
        schemes,
        key=lambda scheme: (
            normalize_key(scheme.status) != "open",
            date_sort_value(scheme.close_on),
            date_sort_value(scheme.open_on),
            normalize_key(scheme.name),
        ),
    )


def apply_now_schemes(schemes: Iterable[Scheme]) -> list[Scheme]:
    return sorted(
        [scheme for scheme in schemes if normalize_key(scheme.status) == "open"],
        key=lambda scheme: (date_sort_value(scheme.close_on), normalize_key(scheme.name)),
    )


def opening_soon_schemes(schemes: Iterable[Scheme]) -> list[Scheme]:
    return sorted(
        [scheme for scheme in schemes if normalize_key(scheme.status) == "opening soon"],
        key=lambda scheme: (date_sort_value(scheme.open_on), normalize_key(scheme.name)),
    )


def enrich_scheme_sources(schemes: list[Scheme], rows: Iterable[dict[str, str]]) -> None:
    """Add cross-source links when the same scheme name is active on another source."""
    by_name = active_links_by_name(rows)

    for scheme in schemes:
        extras = by_name.get(normalize_key(scheme.name), {})
        seen_sources = {normalize_key(item.source) for item in scheme.sources}
        for link in sort_source_links(extras.values()):
            src_key = normalize_key(link.source)
            if src_key in seen_sources:
                continue
            scheme.sources.append(link)
            seen_sources.add(src_key)


def sort_source_links(sources: Iterable[SourceLink]) -> list[SourceLink]:
    return sorted(
        list(sources),
        key=lambda item: SOURCE_LINK_PRIORITY.get(normalize_key(item.source), 9),
    )


def report_issue_href(*, scheme_name: str = "", page_url: str = "") -> str:
    scheme_line = scheme_name.strip() or ""
    page_line = page_url.strip() or scheme_hub_url()
    email = report_issue_email()
    if email:
        subject = urllib.parse.quote(f"{HUB_TITLE} — issue report")
        body = urllib.parse.quote(
            f"Scheme name: {scheme_line}\n"
            "What is wrong (broken link, wrong dates, etc.):\n\n"
            f"Page URL: {page_line}\n"
        )
        return f"mailto:{email}?subject={subject}&body={body}"

    repo = os.environ.get("REPORT_ISSUE_REPO", DEFAULT_REPORT_ISSUE_REPO).strip()
    params = urllib.parse.urlencode(
        {
            "title": f"{HUB_TITLE} issue",
            "body": (
                f"**Scheme name:** {scheme_line}\n"
                "**What is wrong:** \n"
                f"**Page URL:** {page_line}\n"
            ),
        }
    )
    return f"https://github.com/{repo}/issues/new?{params}"


def fmt_count(count: int, singular: str, plural: str | None = None) -> str:
    return f"{count} {singular if count == 1 else (plural or singular + 's')}"


def render_money(value: str) -> str:
    if value:
        return escape(f"EUR {value}")
    return '<span data-i18n="value.tbc">TBC</span>'


def money(value: str) -> str:
    return f"EUR {value}" if value else "TBC"


def income_range_html(scheme: Scheme) -> str:
    if scheme.income_min and scheme.income_max:
        return escape(f"EUR {scheme.income_min} - EUR {scheme.income_max}")
    if scheme.income_min:
        return (
            f'<span data-i18n="value.income_from">From EUR</span> '
            f"{escape(scheme.income_min)}"
        )
    if scheme.income_max:
        return (
            f'<span data-i18n="value.income_up_to">Up to EUR</span> '
            f"{escape(scheme.income_max)}"
        )
    return '<span data-i18n="value.not_listed">Not listed</span>'


def income_range(scheme: Scheme) -> str:
    if scheme.income_min and scheme.income_max:
        return f"EUR {scheme.income_min} - EUR {scheme.income_max}"
    if scheme.income_min:
        return f"From EUR {scheme.income_min}"
    if scheme.income_max:
        return f"Up to EUR {scheme.income_max}"
    return "Not listed"


def render_source_links(scheme: Scheme) -> str:
    links = []
    for source in sort_source_links(scheme.sources):
        label = escape(source.source or "Source")
        if source.link:
            links.append(
                f'<a class="source-link" href="{escape(source.link, quote=True)}" '
                f'target="_blank" rel="noopener noreferrer">{label}</a>'
            )
        else:
            links.append(f'<span class="source-link source-link--muted">{label}</span>')
    return "\n".join(links)


HUB_TITLE = "Ireland Cost Rental Hub"
BUTTONDOWN_USERNAME = "costrentalhub"
BUTTONDOWN_SUBSCRIBE_URL = (
    f"https://buttondown.com/api/emails/embed-subscribe/{BUTTONDOWN_USERNAME}"
)
NEWSLETTER_TITLE = "Ireland Cost Rental Alerts"
SUBSCRIBE_DISMISS_STORAGE_KEY = "crh_email_alerts_dismissed"
VIEW_MODE_STORAGE_KEY = "crh_scheme_view"


def status_i18n_key(status: str) -> str:
    normalized = normalize_key(status)
    if normalized == "open":
        return "status.open"
    if normalized == "opening soon":
        return "status.opening_soon"
    return ""


def render_status_badge(status: str) -> str:
    i18n_key = status_i18n_key(status)
    i18n_attr = f' data-i18n="{i18n_key}"' if i18n_key else ""
    return (
        f'<span class="badge badge--{escape(normalize_key(status).replace(" ", "-"))}"'
        f'{i18n_attr}>{escape(status.title())}</span>'
    )


def render_detail(label_key: str, value_html: str) -> str:
    label = TRANSLATIONS[label_key]["en"]
    return (
        '<div class="detail">'
        f'<dt data-i18n="{escape(label_key, quote=True)}">{escape(label)}</dt>'
        f"<dd>{value_html}</dd>"
        "</div>"
    )


def render_text_value(value: str, *, default_key: str = "not_listed") -> str:
    if value:
        return escape(value)
    default = TRANSLATIONS[f"value.{default_key}"]["en"]
    return (
        f'<span data-i18n="value.{default_key}">{escape(default)}</span>'
    )


TEST_PHASE_NOTE = (
    "This app is in test phase. If you find inconsistencies, please use the Report "
    "button and we will work on fixing the problem."
)
SOURCE_PORTALS_NOTE = (
    "Data comes from Affordable Homes Ireland, LDA and Tuath Housing. Other "
    "cost-rental providers, including Clúid, Respond, Circle VHA, Co-operative "
    "Housing Ireland, Oaklee, Ó Cualann and Fold Ireland, usually publish their "
    "schemes through Affordable Homes Ireland, so they are covered there rather "
    "than listed separately."
)


def render_scheme_card(scheme: Scheme, *, extra_badges: Iterable[str] = ()) -> str:
    badges = [scheme.status, *extra_badges]
    badge_html = "".join(render_status_badge(badge) for badge in badges if badge)
    details = [
        render_detail("detail.location", render_text_value(scheme.location)),
        render_detail("detail.price", render_money(scheme.price)),
        render_detail(
            "detail.homes",
            render_text_value(scheme.quantity, default_key="tbc") if not scheme.quantity else escape(scheme.quantity),
        ),
        render_detail(
            "detail.beds",
            render_text_value(scheme.beds, default_key="tbc") if not scheme.beds else escape(scheme.beds),
        ),
        render_detail("detail.income", income_range_html(scheme)),
        render_detail("detail.opens", render_text_value(scheme.open_on)),
        render_detail("detail.closes", render_text_value(scheme.close_on)),
    ]
    scheme_name = scheme.name or TRANSLATIONS["value.unnamed"]["en"]
    name_html = (
        f'<span data-i18n="value.unnamed">{escape(scheme_name)}</span>'
        if not scheme.name
        else escape(scheme.name)
    )
    address = (
        f'<p class="address">{escape(scheme.address)}</p>' if scheme.address else ""
    )
    return f"""
<article class="scheme-card" data-search="{escape(scheme.search_text, quote=True)}">
  <div class="scheme-card__header">
    <div>
      <h3>{name_html}</h3>
      {address}
    </div>
    <div class="badges">{badge_html}</div>
  </div>
  <dl class="details">
    {''.join(details)}
  </dl>
  <div class="scheme-card__footer">
    <div class="source-links">
      {render_source_links(scheme)}
    </div>
    <a class="scheme-report" data-i18n="report" href="{escape(report_issue_href(scheme_name=scheme.name), quote=True)}">Report</a>
  </div>
</article>
""".strip()


def render_scheme_table_row(scheme: Scheme) -> str:
    if scheme.name:
        name_cell = f"<strong>{escape(scheme.name)}</strong>"
    else:
        name_cell = (
            f'<strong><span data-i18n="value.unnamed">'
            f'{escape(TRANSLATIONS["value.unnamed"]["en"])}</span></strong>'
        )
    if scheme.address:
        name_cell += f'<span class="table-scheme__address">{escape(scheme.address)}</span>'
    return f"""
<tr class="scheme-row" data-search="{escape(scheme.search_text, quote=True)}">
  <td class="table-scheme">{name_cell}</td>
  <td>{render_text_value(scheme.location)}</td>
  <td>{render_money(scheme.price)}</td>
  <td>{render_text_value(scheme.beds, default_key="tbc") if not scheme.beds else escape(scheme.beds)}</td>
  <td>{render_text_value(scheme.quantity, default_key="tbc") if not scheme.quantity else escape(scheme.quantity)}</td>
  <td>{income_range_html(scheme)}</td>
  <td>{render_text_value(scheme.open_on)}</td>
  <td>{render_text_value(scheme.close_on)}</td>
  <td class="table-links">{render_source_links(scheme)}</td>
  <td class="table-report">
    <a class="scheme-report" data-i18n="report" href="{escape(report_issue_href(scheme_name=scheme.name), quote=True)}">Report</a>
  </td>
</tr>
""".strip()


def render_scheme_table(
    schemes: list[Scheme],
    *,
    empty_key: str,
) -> str:
    if not schemes:
        empty = TRANSLATIONS[empty_key]["en"]
        return f'<p class="empty-state" data-i18n="{escape(empty_key, quote=True)}">{escape(empty)}</p>'
    rows = "\n".join(render_scheme_table_row(scheme) for scheme in schemes)
    return f"""
<div class="scheme-table-panel">
  <table class="scheme-table">
    <thead>
      <tr>
        <th scope="col" data-i18n="table.scheme">Scheme</th>
        <th scope="col" data-i18n="table.location">📍 Location</th>
        <th scope="col" data-i18n="table.price">💰 Price</th>
        <th scope="col" data-i18n="table.beds">🛏️ Beds</th>
        <th scope="col" data-i18n="table.homes">🏠 Homes</th>
        <th scope="col" data-i18n="table.income">💶 Income</th>
        <th scope="col" data-i18n="table.opens">📅 Opens</th>
        <th scope="col" data-i18n="table.closes">⏰ Closes</th>
        <th scope="col" data-i18n="table.apply_now">Apply now</th>
        <th scope="col"><span class="sr-only" data-i18n="report">Report</span></th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
</div>
""".strip()


def render_hub_actions(*, issue_href: str) -> str:
    return f"""
<nav class="hub-actions" data-i18n-aria="action.hub_actions" aria-label="Hub actions">
  <button type="button" class="hub-action hub-action--primary" data-open-subscribe data-i18n="action.email">
    Email
  </button>
  <a class="hub-action" data-i18n="action.report" href="{escape(issue_href, quote=True)}">Report</a>
  <button type="button" class="hub-action" data-open-about data-i18n="action.about">About</button>
  <button type="button" class="hub-action" data-open-cost-rental data-i18n="action.cost_rental">Cost rental</button>
</nav>
""".strip()


def render_about_modal(*, issue_href: str) -> str:
    contact_email = escape(report_issue_email())
    issue_link = escape(issue_href, quote=True)
    return f"""
<div class="about-modal hub-modal" id="about-modal" aria-hidden="true">
  <div class="about-modal__backdrop" data-close-about></div>
  <div
    class="about-modal__panel"
    role="dialog"
    aria-modal="true"
    aria-labelledby="about-modal-title"
  >
    <button type="button" class="about-modal__close" data-close-about data-i18n-aria="modal.close" aria-label="Close">
      &times;
    </button>
    <h2 id="about-modal-title" data-i18n="about.title">About {escape(HUB_TITLE)}</h2>
    <div class="about-modal__body">
      <p class="about-modal__lede" data-i18n="about.lede">
        A daily dashboard for cost rental housing in Ireland. See what you can apply for
        today and what is opening soon, without checking each portal separately.
      </p>
      <section class="about-modal__section">
        <h3 data-i18n="about.how.title">How it works</h3>
        <p data-i18n="about.how.body">
          We check affordablehomes.ie, LDA and Tuath Housing every morning, merge the
          results, and publish updates here and by email.
        </p>
      </section>
      <section class="about-modal__section">
        <h3 data-i18n="about.sources.title">Data sources</h3>
        <p data-i18n="tip.sources">{escape(SOURCE_PORTALS_NOTE)}</p>
      </section>
      <section class="about-modal__section">
        <h3 data-i18n="about.email.title">Email alerts</h3>
        <p>
          <span data-i18n="about.email.body">Get one morning email with apply-now and opening-soon schemes.</span>
          <button type="button" class="about-modal__inline-link" data-open-subscribe data-i18n="about.email.link">
            Open email signup
          </button>.
        </p>
      </section>
      <section class="about-modal__section">
        <h3 data-i18n="about.test.title">Test phase</h3>
        <p data-i18n="about.test.body">{escape(TEST_PHASE_NOTE)}</p>
      </section>
      <section class="about-modal__section">
        <h3 data-i18n="about.limits.title">Free service — some gaps</h3>
        <p data-i18n="about.limits.body">
          This hub is free to use. We read public portals automatically each morning,
          not by hand. Some details — like exact rent, income limits, or dates — may be
          missing when a portal does not show them clearly or changes layout. Always
          confirm on the official scheme page before you apply. Use Report if you spot a
          gap.
        </p>
      </section>
      <section class="about-modal__section">
        <h3 data-i18n="about.help.title">Help improve this</h3>
        <ul class="about-modal__list">
          <li data-i18n="about.help.scheme">Wrong details on a scheme? Use <strong>Report</strong> on that scheme&apos;s card.</li>
          <li>
            <span data-i18n="about.help.other">Another problem?</span>
            <a href="{issue_link}" data-i18n="about.help.report">Send a report</a>.
          </li>
          <li>
            <span data-i18n="about.help.contribute">Want to contribute?</span>
            <a href="mailto:{contact_email}">{contact_email}</a>.
          </li>
        </ul>
      </section>
    </div>
    <button type="button" class="about-modal__done" data-close-about data-i18n="modal.close">Close</button>
  </div>
</div>
""".strip()


def render_cost_rental_modal() -> str:
    return f"""
<div class="cost-rental-modal hub-modal" id="cost-rental-modal" aria-hidden="true">
  <div class="cost-rental-modal__backdrop" data-close-cost-rental></div>
  <div
    class="cost-rental-modal__panel"
    role="dialog"
    aria-modal="true"
    aria-labelledby="cost-rental-modal-title"
  >
    <button type="button" class="cost-rental-modal__close" data-close-cost-rental data-i18n-aria="modal.close" aria-label="Close">
      &times;
    </button>
    <h2 id="cost-rental-modal-title" data-i18n="cost_rental.title">What is cost rental?</h2>
    <div class="cost-rental-modal__body">
      <p class="cost-rental-modal__lede" data-i18n="cost_rental.lede">
        Cost rental is a form of affordable housing in Ireland where rent is set below
        market rates and linked to your household income.
      </p>
      <section class="cost-rental-modal__section">
        <h3 data-i18n="cost_rental.who.title">Who provides it</h3>
        <p data-i18n="cost_rental.who.body">
          Schemes are run by approved Irish housing bodies and public agencies, including
          Clúid, LDA and Tuath Housing. Many others publish through Affordable Homes Ireland.
        </p>
      </section>
      <section class="cost-rental-modal__section">
        <h3 data-i18n="cost_rental.diff.title">How it differs</h3>
        <p data-i18n="cost_rental.diff.body">
          Unlike HAP or the Rental Accommodation Scheme, cost rental is a tenancy in a
          new affordable home — not a subsidy for a home you find yourself. It is also
          different from traditional social housing queues, though eligibility can overlap.
        </p>
      </section>
      <section class="cost-rental-modal__section">
        <h3 data-i18n="cost_rental.apply.title">How to apply</h3>
        <p data-i18n="cost_rental.apply.body">
          When a scheme is open, apply through the provider&apos;s portal — affordablehomes.ie,
          LDA or Tuath Housing. This hub shows what is open now and opening soon so you
          do not miss a window.
        </p>
      </section>
    </div>
    <button type="button" class="cost-rental-modal__done" data-close-cost-rental data-i18n="modal.close">Close</button>
  </div>
</div>
""".strip()


def render_subscribe_modal() -> str:
    subscribe_url = escape(BUTTONDOWN_SUBSCRIBE_URL, quote=True)
    return f"""
<div class="subscribe-modal hub-modal" id="subscribe-modal" aria-hidden="true">
  <div class="subscribe-modal__backdrop" data-close-subscribe></div>
  <div
    class="subscribe-modal__panel"
    role="dialog"
    aria-modal="true"
    aria-labelledby="subscribe-modal-title"
  >
    <button type="button" class="subscribe-modal__close" data-close-subscribe data-i18n-aria="modal.close" aria-label="Close">
      &times;
    </button>
    <h2 id="subscribe-modal-title" data-i18n="subscribe.title">Get cost rental alerts</h2>
    <div class="subscribe-modal__hero">
      <img
        class="subscribe-modal__hero-image"
        src="{escape(SUBSCRIBE_HERO_URL, quote=True)}"
        alt=""
        width="930"
        height="291"
        loading="lazy"
      >
    </div>
    <div class="subscribe-modal__lede">
      <p class="subscribe-modal__lede-line" data-i18n="subscribe.lede_line1">
        Get free daily alerts for schemes you can apply for now, plus those opening soon.
      </p>
      <p class="subscribe-modal__lede-line">
        <span data-i18n="subscribe.lede_line2">
          We check affordablehomes.ie, LDA, and Tuath Housing for you.
        </span>{render_info_tip("tip.sources")}
      </p>
    </div>
    <form
      id="subscribe-form"
      class="subscribe-form"
      action="{subscribe_url}"
      method="post"
      novalidate
    >
      <input type="hidden" name="embed" value="1">
      <label class="subscribe-form__field" for="subscribe-email" data-i18n="subscribe.email">Email</label>
      <input
        class="subscribe-form__input"
        id="subscribe-email"
        type="email"
        name="email"
        autocomplete="email"
        placeholder="you@example.com"
        required
      >
      <label class="subscribe-form__consent" for="subscribe-consent">
        <input id="subscribe-consent" type="checkbox" name="consent" required>
        <span data-i18n="subscribe.consent">
          I agree to receive daily {escape(NEWSLETTER_TITLE)} emails. You can unsubscribe at any time.
        </span>
      </label>
      <p class="subscribe-form__note" data-i18n="subscribe.note">
        Double opt-in: we will send a confirmation email — click the link to finish subscribing.
      </p>
      <div class="subscribe-form__actions">
        <button class="subscribe-form__submit" type="submit" data-i18n="subscribe.submit">Subscribe</button>
        <button class="subscribe-form__dismiss" type="button" id="subscribe-not-now" data-i18n="subscribe.not_now">Not now</button>
      </div>
      <p class="subscribe-form__error" id="subscribe-error" hidden></p>
    </form>
    <div class="subscribe-success" id="subscribe-success" hidden>
      <p data-i18n="subscribe.success"><strong>Almost there.</strong> Check your inbox and confirm your subscription.</p>
      <button type="button" class="subscribe-form__submit" data-close-subscribe data-i18n="modal.close">Close</button>
    </div>
  </div>
</div>
""".strip()


def render_info_tip(key: str) -> str:
    text = TRANSLATIONS[key]["en"]
    return (
        '<span class="info-tip" tabindex="0" role="button" data-i18n-aria="tip.section_info" '
        'aria-label="Section information">'
        '<span class="info-tip__icon" aria-hidden="true">i</span>'
        f'<span class="info-tip__popup" data-i18n="{escape(key, quote=True)}">{escape(text)}</span>'
        "</span>"
    )


def render_lang_toggle() -> str:
    return """
<div class="lang-toggle" role="group" data-i18n-aria="lang.label" aria-label="Language">
  <button
    type="button"
    class="lang-toggle__btn is-active"
    data-lang="en"
    data-i18n-title="lang.en"
    aria-pressed="true"
    title="English"
  >🇮🇪</button>
  <button
    type="button"
    class="lang-toggle__btn"
    data-lang="pt"
    data-i18n-title="lang.pt"
    aria-pressed="false"
    title="Portuguese"
  >🇧🇷</button>
</div>
""".strip()


def render_view_toggle() -> str:
    return """
<div class="view-toggle" role="group" data-i18n-aria="view.layout" aria-label="Layout">
  <button
    type="button"
    class="view-toggle__btn is-active"
    data-view-mode="table"
    aria-pressed="true"
    data-i18n="view.table"
  >Table</button>
  <button
    type="button"
    class="view-toggle__btn"
    data-view-mode="cards"
    aria-pressed="false"
    data-i18n="view.cards"
  >Cards</button>
</div>
""".strip()


def render_section(
    section_id: str,
    title_key: str,
    tip_key: str,
    schemes: list[Scheme],
    *,
    empty_key: str,
    extra_badges: Iterable[str] = (),
) -> str:
    cards = "\n".join(
        render_scheme_card(scheme, extra_badges=extra_badges) for scheme in schemes
    )
    table = render_scheme_table(schemes, empty_key=empty_key)
    if not schemes:
        empty = TRANSLATIONS[empty_key]["en"]
        cards = f'<p class="empty-state" data-i18n="{escape(empty_key, quote=True)}">{escape(empty)}</p>'
    title = TRANSLATIONS[title_key]["en"]
    scheme_count = len(schemes)
    count_label = fmt_count(scheme_count, TRANSLATIONS["count.scheme"]["en"], TRANSLATIONS["count.schemes"]["en"])
    return f"""
<section
  class="scheme-section"
  id="{escape(section_id, quote=True)}"
  data-section="{escape(section_id, quote=True)}"
  data-view="table"
>
  <div class="section-heading">
    <div>
      <p class="eyebrow" data-scheme-count="{scheme_count}">{escape(count_label)}</p>
      <h2 class="section-title"><span data-i18n="{escape(title_key, quote=True)}">{escape(title)}</span>{render_info_tip(tip_key)}</h2>
    </div>
    {render_view_toggle()}
  </div>
  <div class="scheme-grid scheme-grid--cards">
    {cards}
  </div>
  <div class="scheme-table-wrap">
    {table}
  </div>
</section>
""".strip()


def render_html(
    schemes: list[Scheme],
    *,
    generated_at: datetime | None = None,
) -> str:
    generated = generated_at or datetime.now(TZ)
    apply_now = apply_now_schemes(schemes)
    opening_soon = opening_soon_schemes(schemes)
    generated_label = generated.strftime("%d %b %Y %H:%M %Z")
    issue_href = report_issue_href()

    return f"""<!doctype html>
<html lang="en" id="hub-root">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <title>{escape(HUB_TITLE)}</title>
  <link rel="icon" href="{escape(HUB_LOGO_URL, quote=True)}" type="image/png">
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f7fb;
      --panel: #ffffff;
      --text: #102033;
      --muted: #607083;
      --line: #dce4ef;
      --brand: #1456f0;
      --brand-dark: #0e3fb3;
      --green: #087f5b;
      --amber: #b76e00;
      --red: #c92a2a;
      --shadow: 0 18px 55px rgba(16, 32, 51, 0.10);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: radial-gradient(circle at top left, #dbeafe 0, transparent 35rem), var(--bg);
      color: var(--text);
      line-height: 1.5;
    }}
    a {{ color: inherit; }}
    .page {{
      width: min(1180px, calc(100% - 32px));
      margin: 0 auto;
      padding: 40px 0 64px;
    }}
    .hero {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 32px;
      align-items: end;
      margin-bottom: 28px;
    }}
    .hero h1 {{
      margin: 0;
      font-size: clamp(2rem, 6vw, 4rem);
      line-height: 0.95;
      letter-spacing: -0.05em;
    }}
    .hero-brand {{
      display: flex;
      align-items: center;
      gap: clamp(12px, 2vw, 18px);
      margin-bottom: 10px;
    }}
    .hero-logo {{
      width: clamp(52px, 8vw, 72px);
      height: clamp(52px, 8vw, 72px);
      flex-shrink: 0;
    }}
    .hero p {{
      margin: 0;
      max-width: 720px;
      color: var(--muted);
      font-size: 1.05rem;
    }}
    .updated {{
      padding: 14px 16px;
      border: 1px solid var(--line);
      border-radius: 18px;
      background: rgba(255, 255, 255, 0.72);
      color: var(--muted);
      white-space: nowrap;
      box-shadow: var(--shadow);
    }}
    .hero-meta {{
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 10px;
    }}
    .lang-toggle {{
      display: inline-flex;
      padding: 4px;
      border: 1px solid #e8eef5;
      border-radius: 14px;
      background: rgba(255, 255, 255, 0.78);
      box-shadow: 0 8px 24px rgba(16, 32, 51, 0.05);
    }}
    .lang-toggle__btn {{
      min-width: 44px;
      min-height: 40px;
      padding: 0 10px;
      border: 0;
      border-radius: 10px;
      background: transparent;
      font-size: 1.2rem;
      line-height: 1;
      cursor: pointer;
    }}
    .lang-toggle__btn.is-active {{
      background: #eef4ff;
      box-shadow: inset 0 0 0 1px #c7d8f8;
    }}
    .lang-toggle__btn:hover:not(.is-active) {{
      background: #f8fafc;
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
      margin: 30px 0;
    }}
    .summary-card {{
      padding: 22px;
      border-radius: 24px;
      background: var(--panel);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
    }}
    .summary-card span {{
      display: block;
      color: var(--muted);
      font-size: 0.92rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .summary-card strong {{
      display: block;
      margin-top: 8px;
      font-size: 2.7rem;
      line-height: 1;
    }}
    .summary-card--apply strong {{ color: var(--green); }}
    .summary-card--opening strong {{ color: var(--brand); }}
    .hub-actions {{
      margin: 26px 0;
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .hub-action {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 44px;
      padding: 0 16px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--text);
      text-decoration: none;
      font: inherit;
      font-weight: 700;
      font-size: 0.92rem;
      cursor: pointer;
      box-shadow: var(--shadow);
    }}
    .hub-action:hover {{
      border-color: #cbd5e1;
    }}
    .hub-action--primary {{
      background: var(--brand);
      border-color: var(--brand);
      color: #fff;
    }}
    .hub-action--primary:hover {{
      background: var(--brand-dark);
      border-color: var(--brand-dark);
      color: #fff;
    }}
    .scheme-section {{
      margin-top: 34px;
      scroll-margin-top: 100px;
    }}
    .section-heading {{
      margin-bottom: 16px;
    }}
    .view-toggle {{
      display: none;
      padding: 4px;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: var(--panel);
      box-shadow: var(--shadow);
      flex-shrink: 0;
    }}
    .view-toggle__btn {{
      min-height: 36px;
      padding: 0 14px;
      border: 0;
      border-radius: 10px;
      background: transparent;
      color: var(--muted);
      font: inherit;
      font-size: 0.84rem;
      font-weight: 700;
      cursor: pointer;
    }}
    .view-toggle__btn.is-active {{
      background: var(--text);
      color: #fff;
    }}
    .view-toggle__btn:hover:not(.is-active) {{
      color: var(--text);
    }}
    .section-title {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      margin: 0;
      font-size: clamp(1.65rem, 3vw, 2.45rem);
      letter-spacing: -0.03em;
    }}
    .info-tip {{
      position: relative;
      display: inline-flex;
      align-items: center;
      flex-shrink: 0;
    }}
    .info-tip__icon {{
      width: 18px;
      height: 18px;
      border-radius: 50%;
      border: 1.5px solid var(--muted);
      color: var(--muted);
      font-size: 0.72rem;
      font-weight: 800;
      font-style: italic;
      font-family: Georgia, "Times New Roman", serif;
      line-height: 1;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      cursor: help;
      user-select: none;
    }}
    .info-tip:hover .info-tip__icon,
    .info-tip:focus-visible .info-tip__icon {{
      color: var(--brand-dark);
      border-color: var(--brand);
    }}
    .info-tip__popup {{
      display: none;
      position: absolute;
      left: 50%;
      top: calc(100% + 10px);
      transform: translateX(-50%);
      width: min(340px, 78vw);
      padding: 12px 14px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--muted);
      font-size: 0.88rem;
      font-weight: 500;
      line-height: 1.45;
      letter-spacing: normal;
      text-transform: none;
      box-shadow: var(--shadow);
      z-index: 20;
    }}
    .info-tip__popup::before {{
      content: "";
      position: absolute;
      left: 50%;
      top: -6px;
      width: 10px;
      height: 10px;
      background: var(--panel);
      border-left: 1px solid var(--line);
      border-top: 1px solid var(--line);
      transform: translateX(-50%) rotate(45deg);
    }}
    .info-tip:hover .info-tip__popup,
    .info-tip:focus-within .info-tip__popup {{
      display: block;
    }}
    .eyebrow {{
      margin-bottom: 4px !important;
      color: var(--brand) !important;
      font-size: 0.82rem;
      font-weight: 800;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }}
    .scheme-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 16px;
    }}
    .scheme-table-wrap {{
      display: none;
    }}
    .scheme-table-panel {{
      overflow-x: auto;
      border-radius: 24px;
      border: 1px solid var(--line);
      background: var(--panel);
      box-shadow: var(--shadow);
    }}
    .scheme-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.92rem;
    }}
    .scheme-table thead {{
      background: #f8fafc;
      border-bottom: 1px solid var(--line);
    }}
    .scheme-table th {{
      padding: 14px 12px;
      text-align: left;
      color: var(--muted);
      font-size: 0.72rem;
      font-weight: 800;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      white-space: nowrap;
    }}
    .scheme-table td {{
      padding: 14px 12px;
      border-top: 1px solid #eef2f7;
      vertical-align: top;
    }}
    .scheme-table th:nth-child(3),
    .scheme-table th:nth-child(4),
    .scheme-table th:nth-child(5),
    .scheme-table th:nth-child(6),
    .scheme-table th:nth-child(7),
    .scheme-table th:nth-child(8),
    .scheme-table td:nth-child(3),
    .scheme-table td:nth-child(4),
    .scheme-table td:nth-child(5),
    .scheme-table td:nth-child(6),
    .scheme-table td:nth-child(7),
    .scheme-table td:nth-child(8) {{
      text-align: center;
    }}
    .scheme-table tbody tr:hover {{
      background: #fafcff;
    }}
    .scheme-row[hidden] {{ display: none; }}
    .table-scheme {{
      min-width: 180px;
    }}
    .table-scheme strong {{
      display: block;
      font-size: 0.98rem;
      line-height: 1.25;
    }}
    .table-scheme__address {{
      display: block;
      margin-top: 4px;
      color: var(--muted);
      font-size: 0.82rem;
      line-height: 1.35;
      max-width: 240px;
    }}
    .table-links .source-link {{
      min-height: 32px;
      padding: 0 10px;
      font-size: 0.82rem;
      border-radius: 10px;
    }}
    .table-report {{
      white-space: nowrap;
    }}
    .sr-only {{
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }}
    @media (min-width: 960px) {{
      .section-heading {{
        display: flex;
        align-items: flex-end;
        justify-content: space-between;
        gap: 16px;
      }}
      .view-toggle {{
        display: inline-flex;
      }}
      .scheme-section:not([data-view="cards"]) .scheme-grid--cards {{
        display: none;
      }}
      .scheme-section:not([data-view="cards"]) .scheme-table-wrap {{
        display: block;
      }}
      .scheme-section[data-view="cards"] .scheme-grid--cards {{
        display: grid;
      }}
      .scheme-section[data-view="cards"] .scheme-table-wrap {{
        display: none;
      }}
    }}
    .scheme-card {{
      display: flex;
      min-height: 100%;
      flex-direction: column;
      gap: 16px;
      padding: 20px;
      border-radius: 24px;
      background: var(--panel);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
    }}
    .scheme-card[hidden] {{ display: none; }}
    .scheme-card__header {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-start;
    }}
    .scheme-card h3 {{
      margin: 0;
      font-size: 1.22rem;
      line-height: 1.2;
      letter-spacing: -0.02em;
    }}
    .address {{
      margin: 8px 0 0;
      color: var(--muted);
      font-size: 0.95rem;
    }}
    .badges {{
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 6px;
      flex-shrink: 0;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 5px 9px;
      font-size: 0.76rem;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      background: #e7f5ff;
      color: var(--brand-dark);
    }}
    .badge--open {{ background: #d3f9d8; color: var(--green); }}
    .badge--opening-soon {{ background: #fff3bf; color: var(--amber); }}
    .details {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      margin: 0;
    }}
    .detail {{
      padding: 10px;
      border-radius: 14px;
      background: #f8fafc;
      border: 1px solid #eef2f7;
    }}
    .detail dt {{
      margin: 0 0 3px;
      color: var(--muted);
      font-size: 0.76rem;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .detail dd {{
      margin: 0;
      font-weight: 750;
    }}
    .source-links {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .scheme-card__footer {{
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 12px;
      margin-top: auto;
    }}
    .scheme-report {{
      flex-shrink: 0;
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      padding: 0 10px;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: #fff;
      color: var(--muted);
      text-decoration: none;
      font-size: 0.78rem;
      font-weight: 700;
    }}
    .scheme-report:hover {{
      color: var(--text);
      border-color: #cbd5e1;
    }}
    .source-link {{
      display: inline-flex;
      align-items: center;
      min-height: 40px;
      padding: 0 12px;
      border-radius: 13px;
      background: var(--brand);
      color: #fff;
      text-decoration: none;
      font-weight: 750;
    }}
    .source-link--muted {{
      background: #e9eef6;
      color: var(--muted);
    }}
    .empty-state {{
      grid-column: 1 / -1;
      margin: 0;
      padding: 24px;
      border: 1px dashed var(--line);
      border-radius: 22px;
      color: var(--muted);
      background: rgba(255, 255, 255, 0.6);
    }}
    body.hub-modal-open {{
      overflow: hidden;
    }}
    .hub-modal {{
      display: none;
      position: fixed;
      inset: 0;
      z-index: 100;
      place-items: center;
      padding: 20px;
    }}
    .hub-modal.is-open {{
      display: grid;
    }}
    .hub-modal__backdrop,
    .subscribe-modal__backdrop,
    .about-modal__backdrop,
    .cost-rental-modal__backdrop {{
      position: absolute;
      inset: 0;
      z-index: 0;
      background: rgba(16, 32, 51, 0.45);
      backdrop-filter: blur(4px);
    }}
    .subscribe-modal__panel,
    .about-modal__panel,
    .cost-rental-modal__panel {{
      position: relative;
      z-index: 1;
      width: min(520px, 100%);
      max-height: min(88vh, 760px);
      padding: 28px 24px 24px;
      border-radius: 24px;
      border: 1px solid var(--line);
      background: var(--panel);
      box-shadow: var(--shadow);
      overflow: auto;
    }}
    .subscribe-modal__close,
    .about-modal__close,
    .cost-rental-modal__close {{
      position: absolute;
      top: 12px;
      right: 12px;
      width: 36px;
      height: 36px;
      border: 0;
      border-radius: 12px;
      background: #f8fafc;
      color: var(--muted);
      font-size: 1.4rem;
      line-height: 1;
      cursor: pointer;
    }}
    .subscribe-modal__close:hover,
    .about-modal__close:hover,
    .cost-rental-modal__close:hover {{
      color: var(--text);
      background: #eef2f7;
    }}
    .subscribe-modal__panel h2,
    .about-modal__panel h2,
    .cost-rental-modal__panel h2 {{
      margin: 0 0 10px;
      font-size: 1.45rem;
      letter-spacing: -0.02em;
    }}
    .about-modal__lede,
    .cost-rental-modal__lede {{
      margin: 0;
      color: var(--muted);
      font-size: 0.95rem;
      line-height: 1.5;
    }}
    .about-modal__body,
    .cost-rental-modal__body {{
      display: grid;
      gap: 18px;
    }}
    .subscribe-modal__hero {{
      margin: 0 0 16px;
      width: 100%;
      aspect-ratio: 16 / 5;
      border-radius: 16px;
      overflow: hidden;
      border: 1px solid var(--line);
      background: linear-gradient(135deg, #e7f0ff 0%, #f8fafc 55%, #eef6ff 100%);
    }}
    .subscribe-modal__hero-image {{
      display: block;
      width: 100%;
      height: 100%;
      object-fit: cover;
      object-position: center;
    }}
    .subscribe-modal__lede {{
      margin: 0 0 18px;
      color: var(--muted);
      font-size: 0.95rem;
    }}
    .subscribe-modal__lede-line {{
      margin: 0;
      line-height: 1.45;
    }}
    .subscribe-modal__lede-line + .subscribe-modal__lede-line {{
      margin-top: 8px;
    }}
    .subscribe-modal__lede .info-tip {{
      vertical-align: middle;
      margin-left: 2px;
    }}
    .subscribe-modal__lede .info-tip__popup {{
      width: min(300px, 82vw);
    }}
    .about-modal__section,
    .cost-rental-modal__section {{
      margin: 0;
    }}
    .about-modal__section h3,
    .cost-rental-modal__section h3 {{
      margin: 0 0 8px;
      font-size: 0.88rem;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--muted);
    }}
    .about-modal__section p,
    .cost-rental-modal__section p {{
      margin: 0;
      color: var(--text);
      font-size: 0.92rem;
      line-height: 1.5;
    }}
    .about-modal__list {{
      margin: 0;
      padding-left: 1.1rem;
      color: var(--text);
      font-size: 0.92rem;
      line-height: 1.55;
    }}
    .about-modal__list li + li {{
      margin-top: 8px;
    }}
    .about-modal__list a,
    .about-modal__inline-link {{
      color: var(--brand-dark);
      font-weight: 700;
    }}
    .about-modal__inline-link {{
      border: 0;
      padding: 0;
      background: none;
      font: inherit;
      text-decoration: underline;
      cursor: pointer;
    }}
    .about-modal__done,
    .cost-rental-modal__done {{
      margin-top: 22px;
      min-height: 44px;
      padding: 0 16px;
      border: 0;
      border-radius: 14px;
      background: var(--brand);
      color: #fff;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }}
    .about-modal__done:hover,
    .cost-rental-modal__done:hover {{
      background: var(--brand-dark);
    }}
    .subscribe-form__field {{
      display: block;
      margin-bottom: 6px;
      font-size: 0.82rem;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--muted);
    }}
    .subscribe-form__input {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px 14px;
      font: inherit;
      color: var(--text);
      background: #fff;
      margin-bottom: 14px;
    }}
    .subscribe-form__consent {{
      display: flex;
      gap: 10px;
      align-items: flex-start;
      margin-bottom: 10px;
      color: var(--text);
      font-size: 0.9rem;
      line-height: 1.4;
      cursor: pointer;
    }}
    .subscribe-form__consent input {{
      margin-top: 3px;
      flex-shrink: 0;
    }}
    .subscribe-form__note {{
      margin: 0 0 16px;
      color: var(--muted);
      font-size: 0.84rem;
    }}
    .subscribe-form__actions {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .subscribe-form__submit,
    .subscribe-form__dismiss {{
      min-height: 44px;
      padding: 0 16px;
      border-radius: 14px;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }}
    .subscribe-form__submit {{
      border: 0;
      background: var(--brand);
      color: #fff;
    }}
    .subscribe-form__submit:hover {{
      background: var(--brand-dark);
    }}
    .subscribe-form__submit:disabled {{
      opacity: 0.65;
      cursor: not-allowed;
    }}
    .subscribe-form__dismiss {{
      border: 1px solid var(--line);
      background: #fff;
      color: var(--muted);
    }}
    .subscribe-form__error {{
      margin: 12px 0 0;
      color: var(--red);
      font-size: 0.88rem;
      font-weight: 600;
    }}
    .subscribe-success p {{
      margin: 0 0 16px;
      color: var(--text);
      line-height: 1.45;
    }}
    @media (max-width: 820px) {{
      .hero,
      .section-heading {{
        grid-template-columns: 1fr;
      }}
      .updated {{ white-space: normal; }}
      .summary {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 10px;
      }}
      .summary-card {{
        padding: 16px;
        border-radius: 20px;
      }}
      .summary-card span {{
        font-size: 0.74rem;
        letter-spacing: 0.06em;
      }}
      .summary-card strong {{
        font-size: 2.2rem;
      }}
      .hub-actions {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      .hub-action--primary {{
        grid-column: 1 / -1;
      }}
      .hub-action {{
        width: 100%;
      }}
    }}
    @media (max-width: 460px) {{
      .page {{
        width: min(100% - 20px, 1180px);
        padding-top: 24px;
      }}
      .scheme-grid {{
        grid-template-columns: 1fr;
      }}
      .details {{
        grid-template-columns: repeat(6, minmax(0, 1fr));
        gap: 8px;
      }}
      .detail {{
        min-width: 0;
        padding: 9px;
      }}
      .detail:nth-child(1),
      .detail:nth-child(2),
      .detail:nth-child(6),
      .detail:nth-child(7) {{
        grid-column: span 3;
      }}
      .detail:nth-child(3),
      .detail:nth-child(4),
      .detail:nth-child(5) {{
        grid-column: span 2;
      }}
      .detail dt {{
        font-size: 0.62rem;
        letter-spacing: 0.06em;
      }}
      .detail dd {{
        font-size: 0.94rem;
        overflow-wrap: anywhere;
      }}
      .scheme-card__header {{
        flex-direction: column;
      }}
      .badges {{
        align-items: flex-start;
        flex-direction: row;
        flex-wrap: wrap;
      }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <header class="hero">
      <div>
        <div class="hero-brand">
          <img
            class="hero-logo"
            src="{escape(HUB_LOGO_URL, quote=True)}"
            alt=""
            width="72"
            height="72"
          >
          <h1 data-i18n="hub.title">{escape(HUB_TITLE)}</h1>
        </div>
        <p>
          <span data-i18n="hero.tagline">Cost rental schemes in Ireland — apply now and opening soon. Updated daily from cost rental portals</span>
          {render_info_tip("tip.sources")}
        </p>
      </div>
      <div class="hero-meta">
        {render_lang_toggle()}
        <div class="updated" id="updated-label" data-timestamp="{escape(generated_label, quote=True)}">
          <span data-i18n="hero.updated">Updated</span> {escape(generated_label)}
        </div>
      </div>
    </header>

    <section class="summary" data-i18n-aria="summary.label" aria-label="Scheme summary">
      <div class="summary-card summary-card--apply"><span data-i18n="summary.apply_now">🟢 Apply now</span><strong>{len(apply_now)}</strong></div>
      <div class="summary-card summary-card--opening"><span data-i18n="summary.opening_soon">🔵 Opening soon</span><strong>{len(opening_soon)}</strong></div>
    </section>

    {render_hub_actions(issue_href=issue_href)}

    {render_section(
        "apply-now",
        "section.apply_now.title",
        "section.apply_now.tip",
        apply_now,
        empty_key="section.apply_now.empty",
    )}

    {render_section(
        "opening-soon",
        "section.opening_soon.title",
        "section.opening_soon.tip",
        opening_soon,
        empty_key="section.opening_soon.empty",
    )}

  </main>

  {render_subscribe_modal()}
  {render_about_modal(issue_href=issue_href)}
  {render_cost_rental_modal()}

  <script>
    const I18N = {translations_json()};
    const LANGUAGE_STORAGE_KEY = {escape(LANGUAGE_STORAGE_KEY)!r};
    const SUBSCRIBE_DISMISS_KEY = {escape(SUBSCRIBE_DISMISS_STORAGE_KEY)!r};
    const VIEW_MODE_STORAGE_KEY = {escape(VIEW_MODE_STORAGE_KEY)!r};
    const DESKTOP_LAYOUT = window.matchMedia("(min-width: 960px)");
    const subscribeModal = document.getElementById("subscribe-modal");
    const subscribeForm = document.getElementById("subscribe-form");
    const subscribeSuccess = document.getElementById("subscribe-success");
    const subscribeError = document.getElementById("subscribe-error");
    const subscribeNotNow = document.getElementById("subscribe-not-now");
    const aboutModal = document.getElementById("about-modal");
    const costRentalModal = document.getElementById("cost-rental-modal");
    const hubModals = [subscribeModal, aboutModal, costRentalModal].filter(Boolean);

    function isModalOpen(modal) {{
      return Boolean(modal && modal.classList.contains("is-open"));
    }}

    function openModal(modal) {{
      if (!modal) return;
      hubModals.forEach((item) => {{
        if (item !== modal) closeModal(item);
      }});
      modal.classList.add("is-open");
      modal.setAttribute("aria-hidden", "false");
      document.body.classList.add("hub-modal-open");
      const focusTarget = modal.querySelector(
        "input, button:not(.subscribe-modal__close):not(.about-modal__close):not(.cost-rental-modal__close), [href]"
      );
      if (focusTarget && focusTarget.focus) focusTarget.focus();
    }}

    function closeModal(modal) {{
      if (!modal) return;
      modal.classList.remove("is-open");
      modal.setAttribute("aria-hidden", "true");
      if (!hubModals.some(isModalOpen)) {{
        document.body.classList.remove("hub-modal-open");
      }}
    }}

    function openSubscribeModal() {{
      openModal(subscribeModal);
    }}

    function closeSubscribeModal() {{
      closeModal(subscribeModal);
    }}

    function openAboutModal() {{
      openModal(aboutModal);
    }}

    function closeAboutModal() {{
      closeModal(aboutModal);
    }}

    function openCostRentalModal() {{
      openModal(costRentalModal);
    }}

    function closeCostRentalModal() {{
      closeModal(costRentalModal);
    }}

    function dismissSubscribePrompt() {{
      try {{
        localStorage.setItem(SUBSCRIBE_DISMISS_KEY, "1");
      }} catch (error) {{
        // Ignore private browsing storage errors.
      }}
      closeSubscribeModal();
    }}

    document.querySelectorAll("[data-open-subscribe]").forEach((button) => {{
      button.addEventListener("click", (event) => {{
        event.preventDefault();
        closeAboutModal();
        closeCostRentalModal();
        openSubscribeModal();
      }});
    }});

    document.querySelectorAll("[data-open-about]").forEach((button) => {{
      button.addEventListener("click", (event) => {{
        event.preventDefault();
        openAboutModal();
      }});
    }});

    document.querySelectorAll("[data-open-cost-rental]").forEach((button) => {{
      button.addEventListener("click", (event) => {{
        event.preventDefault();
        openCostRentalModal();
      }});
    }});

    document.querySelectorAll("[data-close-subscribe]").forEach((button) => {{
      button.addEventListener("click", closeSubscribeModal);
    }});

    document.querySelectorAll("[data-close-about]").forEach((button) => {{
      button.addEventListener("click", closeAboutModal);
    }});

    document.querySelectorAll("[data-close-cost-rental]").forEach((button) => {{
      button.addEventListener("click", closeCostRentalModal);
    }});

    if (subscribeNotNow) {{
      subscribeNotNow.addEventListener("click", dismissSubscribePrompt);
    }}

    if (subscribeForm) {{
      subscribeForm.addEventListener("submit", async (event) => {{
        event.preventDefault();
        if (subscribeError) {{
          subscribeError.hidden = true;
          subscribeError.textContent = "";
        }}

        if (!subscribeForm.reportValidity()) {{
          return;
        }}

        const submitButton = subscribeForm.querySelector('button[type="submit"]');
        const email = new FormData(subscribeForm).get("email");
        if (submitButton) submitButton.disabled = true;

        try {{
          await fetch(subscribeForm.action, {{
            method: "POST",
            body: new URLSearchParams({{ email: String(email || ""), embed: "1" }}),
            mode: "no-cors",
          }});
          subscribeForm.hidden = true;
          if (subscribeSuccess) subscribeSuccess.hidden = false;
          try {{
            localStorage.setItem(SUBSCRIBE_DISMISS_KEY, "1");
          }} catch (storageError) {{
            // Ignore private browsing storage errors.
          }}
        }} catch (error) {{
          if (subscribeError) {{
            subscribeError.hidden = false;
            subscribeError.textContent = t("subscribe.error", document.documentElement.lang === "pt" ? "pt" : "en");
          }}
          if (submitButton) submitButton.disabled = false;
        }}
      }});
    }}

    document.addEventListener("keydown", (event) => {{
      if (event.key === "Escape") {{
        if (isModalOpen(subscribeModal)) closeSubscribeModal();
        if (isModalOpen(aboutModal)) closeAboutModal();
        if (isModalOpen(costRentalModal)) closeCostRentalModal();
      }}
    }});

    function applyViewMode(mode) {{
      document.querySelectorAll(".scheme-section").forEach((section) => {{
        section.dataset.view = mode;
        const toggle = section.querySelector(".view-toggle");
        if (!toggle) return;
        toggle.querySelectorAll(".view-toggle__btn").forEach((button) => {{
          const active = button.dataset.viewMode === mode;
          button.classList.toggle("is-active", active);
          button.setAttribute("aria-pressed", active ? "true" : "false");
        }});
      }});
      if (DESKTOP_LAYOUT.matches) {{
        try {{
          localStorage.setItem(VIEW_MODE_STORAGE_KEY, mode);
        }} catch (error) {{
          // Ignore private browsing storage errors.
        }}
      }}
    }}

    function initViewToggles() {{
      let mode = "table";
      try {{
        const stored = localStorage.getItem(VIEW_MODE_STORAGE_KEY);
        if (stored === "table" || stored === "cards") {{
          mode = stored;
        }}
      }} catch (error) {{
        // Ignore private browsing storage errors.
      }}
      applyViewMode(mode);

      document.querySelectorAll(".view-toggle").forEach((toggle) => {{
        toggle.addEventListener("click", (event) => {{
          const button = event.target.closest(".view-toggle__btn");
          if (!button) return;
          applyViewMode(button.dataset.viewMode);
        }});
      }});
    }}

    initViewToggles();

    function t(key, lang) {{
      return I18N[key]?.[lang] ?? I18N[key]?.en ?? "";
    }}

    function formatSchemeCount(count, lang) {{
      const label = count === 1 ? t("count.scheme", lang) : t("count.schemes", lang);
      return `${{count}} ${{label}}`;
    }}

    function applyLanguage(lang) {{
      const language = lang === "pt" ? "pt" : "en";
      document.documentElement.lang = language;
      document.querySelectorAll("[data-i18n]").forEach((element) => {{
        const key = element.dataset.i18n;
        const value = t(key, language);
        if (value) element.textContent = value;
      }});
      document.querySelectorAll("[data-i18n-aria]").forEach((element) => {{
        const key = element.dataset.i18nAria;
        const value = t(key, language);
        if (value) element.setAttribute("aria-label", value);
      }});
      document.querySelectorAll("[data-i18n-title]").forEach((element) => {{
        const key = element.dataset.i18nTitle;
        const value = t(key, language);
        if (value) element.setAttribute("title", value);
      }});
      document.querySelectorAll("[data-scheme-count]").forEach((element) => {{
        const count = Number.parseInt(element.dataset.schemeCount || "0", 10);
        element.textContent = formatSchemeCount(count, language);
      }});
      const updatedLabel = document.getElementById("updated-label");
      if (updatedLabel) {{
        const timestamp = updatedLabel.dataset.timestamp || "";
        updatedLabel.textContent = `${{t("hero.updated", language)}} ${{timestamp}}`.trim();
      }}
      document.querySelectorAll("[data-lang]").forEach((button) => {{
        const active = button.dataset.lang === language;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", active ? "true" : "false");
      }});
      try {{
        localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
      }} catch (error) {{
        // Ignore private browsing storage errors.
      }}
    }}

    function initLanguageToggle() {{
      let language = "en";
      try {{
        const stored = localStorage.getItem(LANGUAGE_STORAGE_KEY);
        if (stored === "en" || stored === "pt") language = stored;
      }} catch (error) {{
        // Ignore private browsing storage errors.
      }}
      applyLanguage(language);
      document.querySelectorAll("[data-lang]").forEach((button) => {{
        button.addEventListener("click", () => {{
          applyLanguage(button.dataset.lang);
        }});
      }});
    }}

    initLanguageToggle();
  </script>
</body>
</html>
"""


def export_site(
    *,
    csv_path: Path = CSV_PATH,
    out_path: Path = INDEX_PATH,
    generated_at: datetime | None = None,
) -> Path:
    rows = load_rows(csv_path)
    schemes = build_schemes(rows)
    enrich_scheme_sources(schemes, rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if HUB_LOGO_PATH.exists():
        HUB_LOGO_SITE_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(HUB_LOGO_PATH, HUB_LOGO_SITE_PATH)
    if SUBSCRIBE_HERO_PATH.exists():
        SUBSCRIBE_HERO_SITE_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SUBSCRIBE_HERO_PATH, SUBSCRIBE_HERO_SITE_PATH)
    out_path.write_text(
        render_html(schemes, generated_at=generated_at),
        encoding="utf-8",
    )
    return out_path


if __name__ == "__main__":
    path = export_site()
    print(f"Wrote schemes dashboard to {path}")

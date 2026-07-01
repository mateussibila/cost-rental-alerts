#!/usr/bin/env python3
"""Generate a static GitHub Pages dashboard from the scheme CSV export."""

from __future__ import annotations

import csv
import os
import re
import urllib.parse
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from cost_rental_alerts.notify import report_issue_email, scheme_hub_url
from cost_rental_alerts.paths import DATA_DIR, REPO_ROOT

TZ = ZoneInfo("Europe/Dublin")
SOURCE_LINK_PRIORITY = {"affordablehomes": 0, "lda": 1, "tuath": 2}
DEFAULT_REPORT_ISSUE_REPO = "mateussibila/cost-rental-alerts"

CSV_PATH = DATA_DIR / "listings-export.csv"
SITE_DIR = REPO_ROOT / "site"
INDEX_PATH = SITE_DIR / "index.html"


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


def money(value: str) -> str:
    return f"EUR {value}" if value else "TBC"


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


def render_detail(label: str, value: str) -> str:
    return (
        '<div class="detail">'
        f'<dt>{escape(label)}</dt>'
        f'<dd>{escape(value or "Not listed")}</dd>'
        "</div>"
    )


TEST_PHASE_NOTE = (
    "This app is in test phase. If you find inconsistencies, please use the Report "
    "button and we will work on fixing the problem."
)


def render_scheme_card(scheme: Scheme, *, extra_badges: Iterable[str] = ()) -> str:
    badges = [scheme.status, *extra_badges]
    badge_html = "".join(
        f'<span class="badge badge--{escape(normalize_key(badge).replace(" ", "-"))}">'
        f"{escape(badge.title())}</span>"
        for badge in badges
        if badge
    )
    details = [
        render_detail("📍 Location", scheme.location),
        render_detail("💰 Price from", money(scheme.price)),
        render_detail("🏠 Homes", scheme.quantity or "TBC"),
        render_detail("🛏️ Bedrooms", scheme.beds or "TBC"),
        render_detail("💶 Income", income_range(scheme)),
        render_detail("📅 Opens", scheme.open_on or "Not listed"),
        render_detail("⏰ Closes", scheme.close_on or "Not listed"),
    ]
    address = (
        f'<p class="address">{escape(scheme.address)}</p>' if scheme.address else ""
    )
    return f"""
<article class="scheme-card" data-search="{escape(scheme.search_text, quote=True)}">
  <div class="scheme-card__header">
    <div>
      <h3>{escape(scheme.name or "Unnamed scheme")}</h3>
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
    <a class="scheme-report" href="{escape(report_issue_href(scheme_name=scheme.name), quote=True)}">Report</a>
  </div>
</article>
""".strip()


def render_scheme_table_row(scheme: Scheme) -> str:
    name_cell = f'<strong>{escape(scheme.name or "Unnamed scheme")}</strong>'
    if scheme.address:
        name_cell += f'<span class="table-scheme__address">{escape(scheme.address)}</span>'
    return f"""
<tr class="scheme-row" data-search="{escape(scheme.search_text, quote=True)}">
  <td class="table-scheme">{name_cell}</td>
  <td>{escape(scheme.location or "Not listed")}</td>
  <td>{escape(money(scheme.price))}</td>
  <td>{escape(scheme.beds or "TBC")}</td>
  <td>{escape(scheme.quantity or "TBC")}</td>
  <td>{escape(income_range(scheme))}</td>
  <td>{escape(scheme.open_on or "Not listed")}</td>
  <td>{escape(scheme.close_on or "Not listed")}</td>
  <td class="table-links">{render_source_links(scheme)}</td>
  <td class="table-report">
    <a class="scheme-report" href="{escape(report_issue_href(scheme_name=scheme.name), quote=True)}">Report</a>
  </td>
</tr>
""".strip()


def render_scheme_table(
    schemes: list[Scheme],
    *,
    empty_message: str,
) -> str:
    if not schemes:
        return f'<p class="empty-state">{escape(empty_message)}</p>'
    rows = "\n".join(render_scheme_table_row(scheme) for scheme in schemes)
    return f"""
<div class="scheme-table-panel">
  <table class="scheme-table">
    <thead>
      <tr>
        <th scope="col">Scheme</th>
        <th scope="col">📍 Location</th>
        <th scope="col">💰 Price</th>
        <th scope="col">🛏️ Beds</th>
        <th scope="col">🏠 Homes</th>
        <th scope="col">💶 Income</th>
        <th scope="col">📅 Opens</th>
        <th scope="col">⏰ Closes</th>
        <th scope="col">Links</th>
        <th scope="col"><span class="sr-only">Report</span></th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
</div>
""".strip()


def render_info_tip(text: str) -> str:
    return (
        '<span class="info-tip" tabindex="0" role="button" aria-label="Section information">'
        '<span class="info-tip__icon" aria-hidden="true">i</span>'
        f'<span class="info-tip__popup">{escape(text)}</span>'
        "</span>"
    )


def render_section(
    section_id: str,
    title: str,
    info_tip: str,
    schemes: list[Scheme],
    *,
    empty_message: str,
    extra_badges: Iterable[str] = (),
) -> str:
    cards = "\n".join(
        render_scheme_card(scheme, extra_badges=extra_badges) for scheme in schemes
    )
    table = render_scheme_table(schemes, empty_message=empty_message)
    if not schemes:
        cards = f'<p class="empty-state">{escape(empty_message)}</p>'
    return f"""
<section class="scheme-section" id="{escape(section_id, quote=True)}" data-section="{escape(section_id, quote=True)}">
  <div class="section-heading">
    <div>
      <p class="eyebrow">{escape(fmt_count(len(schemes), "scheme"))}</p>
      <h2 class="section-title">{escape(title)}{render_info_tip(info_tip)}</h2>
    </div>
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
    issue_href = escape(report_issue_href(), quote=True)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <title>{escape(HUB_TITLE)}</title>
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
      margin: 0 0 10px;
      font-size: clamp(2rem, 6vw, 4rem);
      line-height: 0.95;
      letter-spacing: -0.05em;
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
    .toolbar {{
      margin: 26px 0;
      padding: 12px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      background: rgba(245, 247, 251, 0.86);
      backdrop-filter: blur(12px);
      border: 1px solid var(--line);
      border-radius: 22px;
    }}
    .search {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 13px 15px;
      font: inherit;
      color: var(--text);
      background: var(--panel);
    }}
    .quick-links {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}
    .quick-links a {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 48px;
      padding: 0 14px;
      border-radius: 15px;
      background: var(--text);
      color: #fff;
      text-decoration: none;
      font-weight: 700;
      font-size: 0.92rem;
    }}
    .quick-links a.report-link {{
      background: #fff;
      color: var(--text);
      border: 1px solid var(--line);
    }}
    .scheme-section {{
      margin-top: 34px;
      scroll-margin-top: 100px;
    }}
    .section-heading {{
      margin-bottom: 16px;
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
      .scheme-grid--cards {{
        display: none;
      }}
      .scheme-table-wrap {{
        display: block;
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
    .no-results {{
      display: none;
      margin-top: 20px;
      padding: 18px;
      border-radius: 18px;
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--muted);
    }}
    .no-results.is-visible {{ display: block; }}
    footer {{
      margin-top: 48px;
      display: flex;
      justify-content: flex-end;
    }}
    .footer-link {{
      display: inline-flex;
      align-items: center;
      min-height: 42px;
      padding: 0 14px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--muted);
      text-decoration: none;
      font-weight: 700;
      font-size: 0.92rem;
    }}
    @media (max-width: 820px) {{
      .hero,
      .toolbar,
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
      .quick-links {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        justify-content: stretch;
      }}
      .quick-links a {{
        width: 100%;
      }}
      .quick-links a.report-link {{
        grid-column: 1 / -1;
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
        <h1>{escape(HUB_TITLE)}</h1>
        <p>Cost rental schemes in Ireland — apply now and opening soon. Updated daily from affordablehomes.ie, LDA, and Tuath Housing.</p>
      </div>
      <div class="updated">Updated {escape(generated_label)}</div>
    </header>

    <section class="summary" aria-label="Scheme summary">
      <div class="summary-card summary-card--apply"><span>🟢 Apply now</span><strong>{len(apply_now)}</strong></div>
      <div class="summary-card summary-card--opening"><span>🔵 Opening soon</span><strong>{len(opening_soon)}</strong></div>
    </section>

    <nav class="toolbar" aria-label="Dashboard tools">
      <input class="search" id="scheme-search" type="search" placeholder="Search by scheme, county, source, price, beds..." autocomplete="off">
      <div class="quick-links">
        <a href="#apply-now">🟢 Apply now</a>
        <a href="#opening-soon">🔵 Opening soon</a>
        <a class="report-link" href="{issue_href}">Report issue</a>
      </div>
    </nav>

    <p class="no-results" id="no-results">No active schemes match that search.</p>

    {render_section(
        "apply-now",
        "🟢 Apply now",
        (
            "Open application windows. Schemes with a close date are sorted first so the "
            "earliest deadlines are easiest to spot. "
            + TEST_PHASE_NOTE
        ),
        apply_now,
        empty_message="No schemes are open for applications right now.",
    )}

    {render_section(
        "opening-soon",
        "🔵 Opening soon",
        (
            "Not yet open for applications. Sorted by opening date, soonest first. "
            + TEST_PHASE_NOTE
        ),
        opening_soon,
        empty_message="No schemes are opening soon right now.",
    )}

    <footer>
      <a class="footer-link" href="{issue_href}">Report issue</a>
    </footer>
  </main>

  <script>
    const searchInput = document.getElementById("scheme-search");
    const noResults = document.getElementById("no-results");
    const searchableItems = Array.from(document.querySelectorAll(".scheme-card, .scheme-row"));

    function applySearch() {{
      const query = searchInput.value.trim().toLowerCase();
      let visible = 0;
      searchableItems.forEach((item) => {{
        const matches = !query || item.dataset.search.includes(query);
        item.hidden = !matches;
        if (matches) visible += 1;
      }});

      document.querySelectorAll(".scheme-section").forEach((section) => {{
        const sectionItems = Array.from(
          section.querySelectorAll(".scheme-card, .scheme-row")
        );
        const hasVisibleItems = sectionItems.some((item) => !item.hidden);
        const hasRealItems = sectionItems.length > 0;
        section.hidden = hasRealItems && !hasVisibleItems && query.length > 0;
      }});

      noResults.classList.toggle("is-visible", visible === 0 && query.length > 0);
    }}

    searchInput.addEventListener("input", applySearch);
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
    out_path.write_text(
        render_html(schemes, generated_at=generated_at),
        encoding="utf-8",
    )
    return out_path


if __name__ == "__main__":
    path = export_site()
    print(f"Wrote schemes dashboard to {path}")

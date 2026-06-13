#!/usr/bin/env python3
"""Generate a static GitHub Pages dashboard from the scheme CSV export."""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from cost_rental_alerts.paths import DATA_DIR, REPO_ROOT

TZ = ZoneInfo("Europe/Dublin")
CLOSING_SOON_DAYS = 14

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


def build_schemes(rows: Iterable[dict[str, str]]) -> list[Scheme]:
    grouped: dict[tuple[str, str, str, str, str], list[dict[str, str]]] = {}
    for row in rows:
        if normalize_key(row.get("status")) in {"open", "opening soon"}:
            grouped.setdefault(scheme_key(row), []).append(row)

    schemes: list[Scheme] = []
    for group_rows in grouped.values():
        best = max(group_rows, key=row_score)
        sources: list[SourceLink] = []
        seen_sources: set[tuple[str, str]] = set()
        for row in sorted(group_rows, key=lambda item: normalize_key(item.get("source"))):
            source = row.get("source", "").strip()
            link = row.get("link", "").strip()
            key = (source, link)
            if source and key not in seen_sources:
                sources.append(SourceLink(source=source, link=link))
                seen_sources.add(key)

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


def closing_soon_schemes(
    schemes: Iterable[Scheme],
    *,
    today: date | None = None,
    days: int = CLOSING_SOON_DAYS,
) -> list[Scheme]:
    ref = today or datetime.now(TZ).date()
    soon_end = ref + timedelta(days=days)
    return sorted(
        [
            scheme
            for scheme in schemes
            if normalize_key(scheme.status) == "open"
            and (close_date := parse_csv_date(scheme.close_on)) is not None
            and ref <= close_date <= soon_end
        ],
        key=lambda scheme: (date_sort_value(scheme.close_on), normalize_key(scheme.name)),
    )


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
    for source in scheme.sources:
        label = escape(source.source or "Source")
        if source.link:
            links.append(
                f'<a class="source-link" href="{escape(source.link, quote=True)}" '
                f'target="_blank" rel="noopener noreferrer">{label}</a>'
            )
        else:
            links.append(f'<span class="source-link source-link--muted">{label}</span>')
    return "\n".join(links)


def render_detail(label: str, value: str) -> str:
    return (
        '<div class="detail">'
        f'<dt>{escape(label)}</dt>'
        f'<dd>{escape(value or "Not listed")}</dd>'
        "</div>"
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
        render_detail("Location", scheme.location),
        render_detail("Price from", money(scheme.price)),
        render_detail("Homes", scheme.quantity or "TBC"),
        render_detail("Bedrooms", scheme.beds or "TBC"),
        render_detail("Income", income_range(scheme)),
        render_detail("Opens", scheme.open_on or "Not listed"),
        render_detail("Closes", scheme.close_on or "Not listed"),
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
  <div class="source-links">
    {render_source_links(scheme)}
  </div>
</article>
""".strip()


def render_section(
    section_id: str,
    title: str,
    description: str,
    schemes: list[Scheme],
    *,
    empty_message: str,
    extra_badges: Iterable[str] = (),
) -> str:
    cards = "\n".join(
        render_scheme_card(scheme, extra_badges=extra_badges) for scheme in schemes
    )
    if not cards:
        cards = f'<p class="empty-state">{escape(empty_message)}</p>'
    return f"""
<section class="scheme-section" id="{escape(section_id, quote=True)}" data-section="{escape(section_id, quote=True)}">
  <div class="section-heading">
    <div>
      <p class="eyebrow">{escape(fmt_count(len(schemes), "scheme"))}</p>
      <h2>{escape(title)}</h2>
    </div>
    <p>{escape(description)}</p>
  </div>
  <div class="scheme-grid">
    {cards}
  </div>
</section>
""".strip()


def render_html(
    schemes: list[Scheme],
    *,
    generated_at: datetime | None = None,
    today: date | None = None,
) -> str:
    generated = generated_at or datetime.now(TZ)
    ref = today or generated.date()
    apply_now = apply_now_schemes(schemes)
    opening_soon = opening_soon_schemes(schemes)
    closing_soon = closing_soon_schemes(schemes, today=ref)
    generated_label = generated.strftime("%d %b %Y %H:%M %Z")

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <title>Cost Rental Schemes</title>
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
      grid-template-columns: repeat(3, minmax(0, 1fr));
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
    .toolbar {{
      position: sticky;
      top: 0;
      z-index: 2;
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
    .scheme-section {{
      margin-top: 34px;
      scroll-margin-top: 100px;
    }}
    .section-heading {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(260px, 420px);
      gap: 20px;
      align-items: end;
      margin-bottom: 16px;
    }}
    .section-heading h2 {{
      margin: 0;
      font-size: clamp(1.65rem, 3vw, 2.45rem);
      letter-spacing: -0.03em;
    }}
    .section-heading p {{
      margin: 0;
      color: var(--muted);
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
    .badge--closing-soon {{ background: #ffe3e3; color: var(--red); }}
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
      margin-top: auto;
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
      color: var(--muted);
      font-size: 0.92rem;
    }}
    @media (max-width: 820px) {{
      .hero,
      .toolbar,
      .section-heading {{
        grid-template-columns: 1fr;
      }}
      .updated {{ white-space: normal; }}
      .summary {{ grid-template-columns: 1fr; }}
      .quick-links {{ justify-content: stretch; }}
      .quick-links a {{ flex: 1 1 150px; }}
    }}
    @media (max-width: 460px) {{
      .page {{
        width: min(100% - 20px, 1180px);
        padding-top: 24px;
      }}
      .scheme-grid,
      .details {{
        grid-template-columns: 1fr;
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
        <h1>Cost rental schemes</h1>
        <p>Private dashboard for active cost-rental opportunities in Ireland. Use the sections below to see schemes you can apply for now, schemes opening soon, and open schemes whose application windows are closing soon.</p>
      </div>
      <div class="updated">Updated {escape(generated_label)}</div>
    </header>

    <section class="summary" aria-label="Scheme summary">
      <div class="summary-card"><span>Apply now</span><strong>{len(apply_now)}</strong></div>
      <div class="summary-card"><span>Opening soon</span><strong>{len(opening_soon)}</strong></div>
      <div class="summary-card"><span>Closing soon</span><strong>{len(closing_soon)}</strong></div>
    </section>

    <nav class="toolbar" aria-label="Dashboard tools">
      <input class="search" id="scheme-search" type="search" placeholder="Search by scheme, county, source, price, beds..." autocomplete="off">
      <div class="quick-links">
        <a href="#apply-now">Apply now</a>
        <a href="#opening-soon">Opening soon</a>
        <a href="#closing-soon">Closing soon</a>
      </div>
    </nav>

    <p class="no-results" id="no-results">No active schemes match that search.</p>

    {render_section(
        "apply-now",
        "Apply now",
        "Open application windows. Schemes with a close date are sorted first so the earliest deadlines are easiest to spot.",
        apply_now,
        empty_message="No schemes are open for applications right now.",
    )}

    {render_section(
        "opening-soon",
        "Opening soon",
        "Schemes marked by the source data as opening soon.",
        opening_soon,
        empty_message="No schemes are marked as opening soon right now.",
    )}

    {render_section(
        "closing-soon",
        "Closing soon",
        f"Open schemes with an application close date in the next {CLOSING_SOON_DAYS} days.",
        closing_soon,
        empty_message="No open schemes are closing soon.",
        extra_badges=("closing soon",),
    )}

    <footer>
      Data comes from <code>data/listings-export.csv</code>. Links open the original source pages in a new tab.
    </footer>
  </main>

  <script>
    const searchInput = document.getElementById("scheme-search");
    const noResults = document.getElementById("no-results");
    const cards = Array.from(document.querySelectorAll(".scheme-card"));

    function applySearch() {{
      const query = searchInput.value.trim().toLowerCase();
      let visible = 0;
      cards.forEach((card) => {{
        const matches = !query || card.dataset.search.includes(query);
        card.hidden = !matches;
        if (matches) visible += 1;
      }});

      document.querySelectorAll(".scheme-section").forEach((section) => {{
        const sectionCards = Array.from(section.querySelectorAll(".scheme-card"));
        const hasVisibleCards = sectionCards.some((card) => !card.hidden);
        const hasRealCards = sectionCards.length > 0;
        section.hidden = hasRealCards && !hasVisibleCards && query.length > 0;
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
    schemes = build_schemes(load_rows(csv_path))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        render_html(schemes, generated_at=generated_at),
        encoding="utf-8",
    )
    return out_path


if __name__ == "__main__":
    path = export_site()
    print(f"Wrote schemes dashboard to {path}")

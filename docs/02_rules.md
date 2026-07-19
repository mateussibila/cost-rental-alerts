# Business rules

## Source priority

When the same scheme phase appears on multiple sources, **affordablehomes data wins** for the merged card/alert line.

| Priority | Source |
|---|---|
| 1 | affordablehomes |
| 2 | lda |
| 3 | tuath |
| 4 | respond |
| 5 | cluid |
| 6 | circle |
| 7 | oaklee |
| 8 | chi |

Secondary sources are kept whenever they are **not** a clear duplicate of AH. Prefer showing two entries over hiding an available scheme.

**Clear duplicate** (merge only when all of these hold):

- same / overlapping scheme name
- same price (both present; tolerance €1)
- matching `applications_open_at` **and/or** `applications_close_at`

If price or dates are missing on either side, keep both entries.

LDA/Tuath/Respond/etc. rows stay when AH does not clearly cover that phase. A stale AH closed entry does **not** block a new open round on another source unless name + price + dates match.

## Scheme identity (`scheme_key`)

A scheme phase is identified by **name + open date**:

- Same name + same open date across sources = one phase (deduped in alerts)
- Different open dates = separate entries (e.g. Parklands 2024 vs Parklands 2026)
- Fallback: `name|listing_id` when no open date exists

## Status values

| Value | Meaning |
|---|---|
| `open` | Applications currently open |
| `closed` | Not open |
| `opening soon` | Opens within the next 14 days, not yet open |

Derived in `export_csv.resolve_export_status()` from stored status + `applications_open_at`.

## Alert triggers (`diff.find_news`)

| Type | Condition |
|---|---|
| `new_open` / `opened_today` | `status = open` AND (first seen today OR status changed to open today) |
| `opening_soon` | `status != open` AND `applications_open_at` within next 14 days AND not yet notified |

Bootstrap: first WhatsApp/email send is a short setup message; no flood of all open schemes.

## Daily digest lists

Every non-bootstrap message includes:

- **Ireland Cost Rental Hub** link to the GitHub Pages dashboard
- **Apply now:** all open listings; first-time schemes prefixed with 🔥
- **Opening soon:** non-open listings with `applications_open_at` within 14 days

Empty sections are omitted. WhatsApp and email share the same structure; email adds URLs and fuller detail.

## Message formatting (`notify.py`)

- **Dedupe:** merge by `scheme_key`; prefer open status, then source priority
- **Apply now:** new today first, then sorted by `applications_close_at` ascending
- **Opening soon:** sorted by `applications_open_at` ascending
- **Email subject:** `Cost Rental — DD/MM/YYYY` (for iOS Shortcuts filter)

## Date inference (affordablehomes)

AH calendar events are parsed with their year when they appear inside a
`year-YYYY` calendar section. Events without an explicit year (for example the
top-level Upcoming section) fall back to year inference per listing using:

- `listed_at`
- current `status`
- whether the round already closed

Detail pages also parse explicit portal text: “Portal open for applications from … DATE … up to … DATE”.

**Guards:**

- `opening_soon` only when `status != 'open'`
- `db.py` clears stale open/close dates on closed listings when scraper returns no date

## Tuath / LDA date notes

- Tuath: closing dates like `Thursday, 11 June at 2PM` — year inferred from context
- LDA: bad dates (e.g. `30/03/2011`) corrected during scrape
- Bilingual counties normalised (e.g. `Co. na Gailimhe/Co. Galway` → `Co. Galway`)

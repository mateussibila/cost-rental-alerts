# Data model

## `Listing` dataclass (`models.py`)

| Field | Type | Notes |
|---|---|---|
| `id` | str | Unique per source listing |
| `source` | str | `affordablehomes` \| `lda` \| `tuath` \| `respond` \| `cluid` \| `circle` \| `oaklee` \| `chi` |
| `title` | str | Scheme name |
| `location` | str | Raw location from source |
| `url` | str | Apply / detail page |
| `status` | str | `open` \| `closed` \| `opening soon` |
| `category` | str | Always `rent` |
| `price_from` | float? | Monthly rent from |
| `bedrooms` | str? | e.g. `1-3 bed` |
| `quantity` | int? | Number of units |
| `income_min` / `income_max` | float? | LDA eligibility (when available) |
| `applications_open_at` | str? | ISO date `YYYY-MM-DD` |
| `applications_close_at` | str? | ISO date `YYYY-MM-DD` |
| `listed_at` | str? | ISO date |
| `scheme_key` | str? | Computed identity for dedupe |
| `address` | str? | Google Maps–compatible string |

## SQLite (`data/listings.db`)

### `listings`

Mirrors `Listing` fields plus:

| Field | Notes |
|---|---|
| `first_seen_at` | When first scraped |
| `last_seen_at` | Last scrape timestamp |
| `status_changed_at` | Updated when `status` changes |

### `notifications_sent`

Tracks which `(listing_id, notification_type)` pairs were already sent (`opening_soon`, etc.).

### `meta`

Key-value store. `bootstrap_done` prevents first-run alert flood.

## CSV export

Files: `data/listings-export.csv` (all), `data/listings-open.csv` (open only).

| Column | Source |
|---|---|
| `name` | `title` |
| `location` | derived via `format_city_neighborhood()` |
| `address` | `address` |
| `price` | `price_from` (formatted) |
| `quantity` | `quantity` |
| `beds` | `bedrooms` |
| `status` | `open` \| `closed` \| `opening soon` |
| `income_min` / `income_max` | income fields |
| `listed_at` / `open_on` / `close_on` | dates as `DD/MM/YYYY` |
| `source` | source name |
| `link` | `url` |

## Scheme snapshot

A point-in-time table of all schemes is kept at `data/schemes-snapshot.md` for quick reference (not auto-generated).

# Cost Rental Alerts — summary and backlog

## Project summary

Daily **cost rental** alerts for Ireland. The system scrapes three sources, stores everything in SQLite, detects changes, and sends **WhatsApp** messages (CallMeBot) for review before posting to Community Announcements.

| Piece | File / destination |
|---|---|
| Daily scrape | `run_daily.py` → affordablehomes.ie, lda.ie, tuathhousing.ie |
| Database | `listings.db` (~202 schemes, `category = rent`) |
| CSV export | `export_csv.py` → `listings-export.csv` |
| Alerts | `diff.py` + `notify.py` → CallMeBot |
| Automation | GitHub Actions `.github/workflows/daily-scrape.yml` (07:00 UTC) |

**CSV columns today:** `name`, `location` (derived), `address` (Google Maps), `price`, `quantity`, `beds`, `is_open`, `income_min`, `income_max`, `listed_at`, `open_on`, `close_on`, `source`, `link`.

**WhatsApp behaviour:**
- **First run with send:** short bootstrap message (“database created, updates only from tomorrow”).
- **Following days:** **updates only** — opened today, changed to open, or opening within 14 days. No news → `✅ No updates today.`
- **Dedupe:** same scheme on multiple sources → one entry (priority: affordablehomes > lda > tuath).

**Planned message format:** hub link (your site) at the top; per listing, short Maps link (`?q=lat,lng` or `address`) + Apply link.

---

# Future improvements

Improvement backlog.

---

## 1. Floor area per unit type

**Goal:** extract area (m²) for each available unit type / floor plan in a scheme.

**Context:** many schemes have 4–5 different configurations (e.g. 1-bed vs 2-bed, different layouts). Today we store aggregated `beds` and `quantity`; per-unit detail is missing.

**Possible approach:**
- Parse affordablehomes detail pages (and LDA where structured) for tables or blocks per unit type
- Model as sub-records or JSON in the DB, e.g.:
  ```json
  [
    { "beds": 1, "area_sqm": 52, "price": 1150 },
    { "beds": 2, "area_sqm": 68, "price": 1250 }
  ]
  ```
- Include in CSV / master spreadsheet as expanded rows or a structured column

**Challenges:** layout varies between schemes; some only mention area in PDF/brochure, not HTML.

---

## 2. Exact location and Maps link

**Status:** partial — `address` column in DB/CSV; AH `Location` + LDA maps link + Tuath normalised.

**Remaining:**
- `latitude`, `longitude` in DB (AH: `data-center` on `#map` in Location Map section)
- `maps_url` — `https://maps.google.com/?q=lat,lng` or fallback `?q={address}`
- Maps link in WhatsApp message (`📍` line before Apply)
- Hub site as first link in the message (preview + single entry point)

---

## 3. Master spreadsheet for users

**Goal:** provide users a public (or semi-public) data view — mirror of the database, similar to `listings-export.csv`.

**Base content (“Master” tab):**
- Faithful DB copy: `name`, `price`, `quantity`, `beds`, `listed_at`, `open_on`, `close_on`, `source`, `link`
- Future: floor area, address, coordinates (items 1 and 2)
- Auto-update after each daily scrape

**Interactive tab — “Distance to”:**
- Dropdown with preset destinations, e.g.:
  - Dublin City Centre
  - Heuston Station
  - Connolly Station
  - Dublin Airport
  - (other reference points)
- On selection, compute and show distance / estimated travel time by car or public transport
- Requires coordinates from item 2 + routing API (Google Distance Matrix, OSRM, etc.)

**Possible formats:**
- Google Sheets (Apps Script + CSV export from repo)
- Online Excel
- Simple web page with filters + CSV export (natural project evolution)

**Notes:**
- Master spreadsheet ≠ WhatsApp notifications — for browsing and comparison
- Consider update lag (1×/day) and unofficial-data disclaimer

---

## 4. Hub site + interactive map — **high priority**

**Goal:** public site as the main entry point (link at top of WhatsApp messages) + map with all filterable schemes.

**Why high priority:** location is a key decision factor; WhatsApp only alerts — the site is where people explore and compare.

### Homepage — 3 boxes at the top

Three clickable boxes, always visible above the fold. Each goes to the **same listings page** (`/listings` or `/schemes`), but with a **pre-applied status filter** via query string:

| Box | UI label | Filter | Suggested DB criteria |
|---|---|---|---|
| 1 | **Apply now** | `status=open` | `status = 'open'` |
| 2 | **Opening soon** | `status=soon` | `applications_open_at` within next 14 days and not yet open |
| 3 | **Recently closed** | `status=closed` | `status = 'closed'` and `applications_close_at` in last 30 days (or recent `status_changed_at`) |

**Example URLs:**
- `/listings?filter=open`
- `/listings?filter=soon`
- `/listings?filter=closed`

The listings page shows **all** schemes (table + optional map), with the active filter and ability to change/remove filters (price, beds, county, etc.). Homepage boxes can show an **updated count** (e.g. “Apply now · 5”).

**Homepage — rest:** WhatsApp link / how it works; last scrape timestamp; unofficial-data disclaimer.

### Listings page + map

**Features:**
- **Map:** pins for each open scheme (coordinates from item 2)
- **Pin popup:** name, price, beds, quantity, link, open/close dates
- **Filters / toggles:**
  - Price (min–max or bands)
  - Bedrooms (1, 2, 3, 1–3, etc.)
  - Region / county / radius from a point
  - Status: open only (default), opening soon, etc.
- Map updates when filters change — only pins matching criteria
- Side list synced with map (optional)

**Possible stack:**
- Static frontend (GitHub Pages / Cloudflare Pages) + JSON exported from DB after each scrape
- Google Maps JavaScript API (Maps + markers; eventually Places)
- Open-source alternative: Leaflet + OpenStreetMap (no API cost)

**Dependencies:** item 2 (coordinates) is **blocking** for an accurate map; item 1 (m²) is nice-to-have in the popup.

**Suggested MVP:**
1. Homepage with 3 boxes → `/listings?filter=…`
2. Export `listings.json` after each scrape (all statuses + lat/lng + `maps_url`)
3. Listings with URL-synced filters (open / soon / closed + price, beds, county)
4. Map with pins reflecting active filters

---

## 5. Historical price per m² by region chart

**Goal:** visualise price per square metre over time, aggregated by region.

**Context:** with DB history (multiple rounds of the same name, e.g. Airton Plaza) and area per unit type (item 1), we can compute €/m² and regional trends.

**Metric:**
```
price_per_m2 = price_from / area_sqm
```
- One entry per unit type when multiple floor plans exist
- Region: county, Dublin postal district, or geographic cluster

**Visualisation:**
- Time series per region (e.g. Dublin, Wicklow, Wexford)
- Box plot or bars to compare regions in the same period
- Optional: filter by beds (1-bed vs 2-bed have different €/m²)

**Data required:**
- Price history already partly in DB (`listed_at`, multiple slugs per scheme)
- Floor area (item 1) — without m², the chart is not possible
- Normalised region (derived from `location` or geocoding from item 2)

**Where it lives:** section of the webapp (item 4) or separate dashboard; can share the same API/JSON.

**Challenges:**
- Older schemes may lack m² in HTML
- Same development, different rounds with different unit types — aggregate carefully
- Define “region” consistently (county vs neighbourhood)

---

## 6. Minimum and maximum income — **done (LDA)**

**Status:** `income_min` / `income_max` in DB and CSV; parsed from LDA eligibility table.

**Remaining (optional):**
- Extract income limits from affordablehomes and Tuath
- `income_region` (Dublin vs elsewhere) when limits differ
- “My income: €X” filter in webapp (item 4)

---

## Suggested priorities

| Priority | Item | Reason |
|---|---|---|
| **High** | 2 (remainder) → 4 | `maps_url` + lat/lng + site (3 boxes + filterable listings) |
| Medium | WhatsApp + site | Hub at top of message; Maps + Apply per listing |
| Medium | 1 → 5 | m² unlocks €/m² and regional charts |
| Medium | 3 | Master spreadsheet — low effort, complements map |
| Low | 5 | Historical chart — needs data volume + m² |

---

*Last updated: 2026-06-06*

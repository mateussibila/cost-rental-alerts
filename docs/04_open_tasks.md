# Open tasks and backlog

## Current phase — solo testing

Hub is live at https://costrentalhub.github.io/ but **not yet promoted to the public**. One person testing alerts, data quality, and hub UX before wider use.

| Item | Status |
|---|---|
| Daily scrape + WhatsApp + email alerts | Running |
| Ireland Cost Rental Hub (Apply now / Opening soon) | Live |
| Ops email (`costrentalhub@gmail.com`) | Scrape failures + broken links |
| Per-scheme **Report** button (`mailto`) | In progress — local preview |
| Public launch | Not yet |

---

## Immediate (high priority)

| Item | Notes |
|---|---|
| **Solo testing** | Validate alerts, hub data, and link quality before public use |
| **Monitor emails + dates** | Confirm no stale Open rows, wrong close dates, or duplicate sections |
| **Fix iPhone automations** | Email → Shortcuts → Notes not reliable in background; Time of Day backup |

### iOS Shortcuts status

- Gmail linked in Mail app; email automation created
- Shortcut: `Get Text from Input` → `Append to Note` (Cost Rental)
- **Issue:** automation only ran after opening Mail — not on banner/background
- **Workarounds:** Background App Refresh → Mail ON; subject filter `Cost Rental Alert`; Time of Day 08:15 backup with CSV link

---

## Progress log

### 2026-06-06 — core pipeline

- Private repo + daily scrape + SQLite + GitHub Actions cron
- CSV daily export committed
- Address field + Tuath location fix (bilingual counties)
- WhatsApp (CallMeBot) + email (Gmail SMTP)

### 2026-06-06 — message ordering

- Applications Open → closes soonest first
- Opening Soon → opens soonest first

### 2026-06-06 — date accuracy fix (affordablehomes calendar)

AH calendar day/month-only dates were assumed as current year → false “opening soon” alerts. Fixed with year inference, detail-page parsing, and DB stale-date cleanup.

### 2026-06-06 — `status` column

`is_open` (TRUE/FALSE) → `status` (`open`, `closed`, `opening soon`).

### 2026-06-10 — project restructure

- Code → `src/cost_rental_alerts/`
- Data → `data/`
- Docs → `docs/00–04_*.md`

### 2026-06-28 — Ireland Cost Rental Hub + ops alerts

- Hub rebranded: Apply now / Opening soon, search, daily update timestamp
- Daily alert digest redesigned (Apply now + Opening soon; Closing Soon removed)
- Ops alerts: scrape failures + broken active links → `costrentalhub@gmail.com`
- Hub email routing: daily alerts from hub account; digest to personal Gmail
- Tuath scraper fixes (403 headers, closed inference, close-date year)
- Affordablehomes closed overrides for stale LDA/Tuath rows
- Hub links: one link per source; cross-source only (AH + LDA/Tuath)
- Email digest aligned with hub (`resolve_export_status` for past close dates)
- CI: `check_links --warn-only` after each scrape

---

## Backlog

### 1. Report issue modal (FormSubmit.co) — future, not essential now

Replace `mailto` with an in-hub modal:

- Checkboxes: broken link, wrong status, wrong dates, wrong details, missing scheme, stale listing, other
- Optional free-text details
- Submit via [FormSubmit.co](https://formsubmit.co) → `costrentalhub@gmail.com`
- Success message stays in hub (no user email app)

**Why later:** hub works for solo testing with `mailto` + per-scheme Report button. FormSubmit needs one-time email activation; modal UX is polish before public launch.

### 2. Floor area per unit type

Extract m² per unit type / floor plan. Model as JSON sub-records or expanded CSV rows.

### 3. Exact location and Maps link

Partial — `address` exists. Remaining: `latitude`, `longitude`, `maps_url`, Maps line in WhatsApp.

### 4. Master spreadsheet

Public data view mirroring DB + optional “Distance to” tab with routing API.

### 5. Hub map

Export `listings.json` after each scrape and add interactive map pins.

### 6. Historical price per m² by region

Needs floor area data (item 2) + coordinates (item 3).

### 7. Income limits — done for LDA

Optional: extract from AH/Tuath; income filter in hub.

---

## Suggested priorities

| Priority | Item |
|---|---|
| **High** | Solo testing — alerts + hub accuracy |
| **High** | Date / stale-status monitoring in production |
| Medium | FormSubmit modal (before public launch) |
| Medium | Coordinates + hub map |
| Medium | iPhone automations |
| Low | Floor area → €/m² charts |
| Low | Historical regional charts |

*Last updated: 2026-06-28*

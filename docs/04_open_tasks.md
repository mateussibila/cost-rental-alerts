# Open tasks and backlog

## Immediate (high priority)

| Item | Notes |
|---|---|
| **Fix iPhone automations** | Email → Shortcuts → Notes not reliable in background; finish trigger setup or add Time of Day backup |
| **Monitor emails + dates** | Watch daily alerts; confirm no false “Opening Soon” or wrong open/close dates |

### iOS Shortcuts status

- Gmail linked in Mail app; email automation created
- Shortcut: `Get Text from Input` → `Append to Note` (Cost Rental)
- **Issue:** automation only ran after opening Mail — not on banner/background
- **Cause:** Email trigger fires when Mail syncs, not on notification alone
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

---

## Backlog

### 1. Floor area per unit type

Extract m² per unit type / floor plan. Model as JSON sub-records or expanded CSV rows.

### 2. Exact location and Maps link

Partial — `address` exists. Remaining: `latitude`, `longitude`, `maps_url`, Maps line in WhatsApp, hub site link at top of message.

### 3. Master spreadsheet

Public data view mirroring DB + optional “Distance to” tab with routing API.

### 4. Hub site + interactive map (high priority)

Private GitHub Pages dashboard exists with Apply now / Opening soon / Closing soon sections. Remaining: export `listings.json` after each scrape and add interactive map pins.

### 5. Historical price per m² by region

Needs floor area data (item 1) + coordinates (item 2).

### 6. Income limits — done for LDA

Optional: extract from AH/Tuath; income filter in webapp.

---

## Suggested priorities

| Priority | Item |
|---|---|
| **High** | iPhone automations |
| **High** | Date monitoring in production |
| **High** | Coordinates + hub site |
| Medium | Maps link in WhatsApp |
| Medium | Floor area → €/m² charts |
| Low | Historical regional charts |

*Last updated: 2026-06-10*

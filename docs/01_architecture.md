# Architecture

## Pipeline

```
run_daily.py
  → scrape (affordablehomes, lda, tuath)
  → enrich_cross_source_open_dates()
  → normalize_listing_statuses()
  → upsert_listings() → data/listings.db
  → find_news() + daily digest lists → format_message()
  → send_whatsapp() + send_email()
```

After each GitHub Actions run, `export_csv.py` writes `data/listings-export.csv` and `data/listings-open.csv`.

## Project layout

```
cost-rental-alerts/
├── README.md
├── docs/                          # project documentation
├── src/cost_rental_alerts/        # Python package
│   ├── run_daily.py               # CLI entrypoint
│   ├── db.py                      # SQLite
│   ├── diff.py                    # detects news
│   ├── notify.py                  # message + WhatsApp / email
│   ├── export_csv.py              # CSV export
│   ├── schemes.py                 # scheme identity + dedupe
│   ├── addresses.py               # Google Maps addresses
│   ├── locations.py               # city-neighbourhood formatting
│   ├── models.py                  # Listing dataclass
│   └── scrapers/                  # affordablehomes, lda, tuath
├── data/                          # generated artefacts
│   ├── listings.db
│   ├── listings-export.csv
│   └── listings-open.csv
├── tests/
└── .github/workflows/daily-scrape.yml
```

## Modules

| Module | Role |
|---|---|
| `run_daily.py` | CLI: `--scrape-only`, `--dry-run`, `--test` |
| `scrapers/` | Fetch and parse listings from each source |
| `schemes.py` | `scheme_key` identity; AH-first merge; cross-source date enrichment |
| `db.py` | Schema, upsert, notification tracking, meta (`bootstrap_done`) |
| `diff.py` | `find_news()` plus daily opening soon digest list |
| `notify.py` | Format message, dedupe by scheme, sort, send WhatsApp/email |
| `export_csv.py` | Export DB to CSV with derived `status` and formatted dates |

## GitHub Actions

Workflow: `.github/workflows/daily-scrape.yml`

- Schedule: **07:00 UTC** (~08:00 Ireland)
- Manual trigger: Actions → Daily Cost Rental Scrape → Run workflow
- Commits `data/listings.db` and CSV files after each run

## Secrets

| Secret | Purpose |
|---|---|
| `CALLMEBOT_PHONE` | WhatsApp destination |
| `CALLMEBOT_APIKEY` | CallMeBot API key |
| `SMTP_USER` | Gmail address |
| `SMTP_PASSWORD` | Gmail App Password |
| `EMAIL_TO` | Alert recipient |

Optional: `SMTP_HOST`, `SMTP_PORT`, `EMAIL_FROM`.

## Local commands

```bash
pip install -r requirements.txt && pip install -e .

python -m cost_rental_alerts.run_daily --scrape-only
python -m cost_rental_alerts.run_daily --dry-run
python -m cost_rental_alerts.export_csv
```

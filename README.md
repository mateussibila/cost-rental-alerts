# Cost Rental Alerts

Daily scraper for affordable housing (cost rental) in Ireland.

**Sources:** [affordablehomes.ie](https://affordablehomes.ie/rent/), [LDA](https://lda.ie/affordable-homes/lda-cost-rental/), [Tuath Housing](https://tuathhousing.ie/cost-rental/)

**Output:** daily alert via **WhatsApp** (CallMeBot) and/or **email** (Gmail SMTP).

📖 Full docs: [docs/00_overview.md](docs/00_overview.md)

## Quick setup

### 1. CallMeBot (one-time)

1. Add `+34 644 31 95 65` to your phone contacts (name: CallMeBot)
2. Send on WhatsApp: `I allow callmebot to send me messages`
3. Save the `apikey` from the reply — do not commit it

### 2. GitHub Secrets

| Secret | Value |
|---|---|
| `CALLMEBOT_PHONE` | e.g. `+353871234567` |
| `CALLMEBOT_APIKEY` | From CallMeBot |
| `SMTP_USER` | Gmail address |
| `SMTP_PASSWORD` | Gmail [App Password](https://myaccount.google.com/apppasswords) |
| `EMAIL_TO` | Alert recipient |

### 3. Test locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

python -m cost_rental_alerts.run_daily --scrape-only
python -m cost_rental_alerts.run_daily --dry-run
```

### 4. GitHub Actions

Runs at **07:00 UTC** daily. Manual run: **Actions → Daily Cost Rental Scrape → Run workflow**.

## Data

- `data/listings.db` — SQLite (committed after each run)
- [listings-export.csv](data/listings-export.csv) — all schemes
- [listings-open.csv](data/listings-open.csv) — open only
- GitHub Pages dashboard — https://mateussibila.github.io/cost-rental-alerts/

The dashboard is generated from `data/listings-export.csv` and published by
GitHub Actions after each daily scrape. It is designed for private GitHub Pages
access and includes Apply now, Opening soon, and Closing soon sections.

## Structure

```
docs/                 # documentation
src/cost_rental_alerts/   # Python package
data/                 # database + CSV exports
tests/
```

See [docs/01_architecture.md](docs/01_architecture.md) for module details and [docs/04_open_tasks.md](docs/04_open_tasks.md) for backlog.

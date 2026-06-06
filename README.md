# Cost Rental Alerts

Daily scraper for affordable housing (cost rental) in Ireland.

**Sources:** [affordablehomes.ie](https://affordablehomes.ie/rent/), [LDA](https://lda.ie/affordable-homes/lda-cost-rental/), [Tuath Housing](https://tuathhousing.ie/cost-rental/)

**Output:** WhatsApp message (via CallMeBot) to your private number — you review and post to Community Announcements.

## Quick setup

### 1. CallMeBot (one-time)

1. Add `+34 644 31 95 65` to your phone contacts (name: CallMeBot)
2. Send on WhatsApp: `I allow callmebot to send me messages`
3. You receive a reply with your `apikey`
4. Save the apikey — do not commit it to the repo

### 2. GitHub repository (private)

```bash
cd cost-rental-alerts
git init
git add .
git commit -m "Initial cost rental alerts scraper"
gh repo create cost-rental-alerts --private --source=. --push
```

### 3. GitHub Secrets

In **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value |
|---|---|
| `CALLMEBOT_PHONE` | Your number with country code, e.g. `+353871234567` |
| `CALLMEBOT_APIKEY` | Apikey received from CallMeBot |

### 4. Test locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# First time: create the database only (recommended before automatic WhatsApp)
python run_daily.py --scrape-only

# Preview message without sending
python run_daily.py --dry-run

# Send to your WhatsApp (export secrets locally)
export CALLMEBOT_PHONE="+353..."
export CALLMEBOT_APIKEY="..."
python run_daily.py
```

### 5. GitHub Actions

The workflow runs automatically at **07:00 UTC** (~08:00 Ireland). You can also run it manually via **Actions → Daily Cost Rental Scrape → Run workflow**.

## Behaviour

- **With updates:** lists applications opened today + schemes opening in the next 14 days
- **No updates:** sends `✅ No updates today.`
- **Database:** `listings.db` (SQLite, committed to the repo after each run)

## Structure

```
run_daily.py          # entrypoint
scrapers/             # affordablehomes, lda, tuath
db.py                 # SQLite
diff.py               # detects updates
notify.py             # formats message + CallMeBot
.github/workflows/    # daily cron
```

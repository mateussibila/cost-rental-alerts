# Overview

Daily **cost rental** alerts for Ireland. The system scrapes three sources, stores everything in SQLite, detects changes, and sends **WhatsApp** (CallMeBot) and **email** (Gmail SMTP) for review before posting to Community Announcements.

## Sources

- [affordablehomes.ie](https://affordablehomes.ie/rent/)
- [LDA cost rental](https://lda.ie/affordable-homes/lda-cost-rental/)
- [Tuath Housing](https://tuathhousing.ie/cost-rental/)

## Output

| Piece | Location |
|---|---|
| Database | `data/listings.db` (~200 schemes, `category = rent`) |
| CSV (all) | `data/listings-export.csv` |
| CSV (open only) | `data/listings-open.csv` |
| Private dashboard | GitHub Pages — Apply now, Opening soon, Closing soon |
| Alerts | WhatsApp + email via `notify.py` |
| Automation | GitHub Actions — 07:00 UTC daily |

**CSV on GitHub:** [all schemes](https://github.com/mateussibila/cost-rental-alerts/blob/main/data/listings-export.csv) · [open only](https://github.com/mateussibila/cost-rental-alerts/blob/main/data/listings-open.csv)

**Dashboard:** https://mateussibila.github.io/cost-rental-alerts/

## User flow

1. Daily scrape runs on GitHub Actions
2. Alert arrives on WhatsApp and/or email
3. You review and manually post to Community Announcements

**Target flow:** email → iOS Shortcuts → Notes → paste to Community (see [04_open_tasks.md](04_open_tasks.md) for automation status).

## Alert behaviour

- **First run with send:** bootstrap message — database created, updates only from tomorrow
- **Following days:** daily digest — new applications, closing soon, and opening soon
- **No new applications:** message says `NO NEW APPLICATIONS` and still repeats any closing/opening soon sections
- **Sorting:** New Applications and Closing Soon → closes soonest first; Opening Soon → opens soonest first

## Links

- Repo: https://github.com/mateussibila/cost-rental-alerts
- Actions: https://github.com/mateussibila/cost-rental-alerts/actions

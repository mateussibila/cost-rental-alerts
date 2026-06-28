import os
import smtplib
import ssl
import time
import urllib.parse
from datetime import date, datetime
from email.message import EmailMessage
from typing import List
from zoneinfo import ZoneInfo

import requests

from cost_rental_alerts.diff import NewsItem
from cost_rental_alerts.locations import format_city_neighborhood

TZ = ZoneInfo("Europe/Dublin")
WHATSAPP_CHUNK_CHARS = int(os.environ.get("WHATSAPP_CHUNK_CHARS", "650"))
DEFAULT_SCHEME_HUB_URL = "https://mateussibila.github.io/cost-rental-alerts/"


def _today() -> date:
    return datetime.now(TZ).date()


def scheme_hub_url() -> str:
    return os.environ.get("SCHEME_HUB_URL", DEFAULT_SCHEME_HUB_URL).strip() or DEFAULT_SCHEME_HUB_URL


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _format_day_month(value: str | None) -> str | None:
    parsed = _parse_date(value)
    if not parsed:
        return None
    return parsed.strftime("%d/%m")


def _format_day_month_year(value: str | None) -> str | None:
    parsed = _parse_date(value)
    if not parsed:
        return None
    return parsed.strftime("%d/%m/%Y")


def _compact_price(price: float | None) -> str:
    if price is None:
        return ""
    if price == int(price):
        return f"€{int(price):,}"
    return f"€{price:,.2f}"


def _email_price(price: float | None) -> str:
    if price is None:
        return ""
    if price == int(price):
        return f"from €{int(price):,}/mo"
    return f"from €{price:,.2f}/mo"


def _compact_bedrooms(bedrooms: str | None) -> str:
    if not bedrooms:
        return ""
    return bedrooms.removesuffix(" bed").strip()


SOURCE_PRIORITY = {"affordablehomes": 0, "lda": 1, "tuath": 2}


def _pick_better_item(current: NewsItem, candidate: NewsItem) -> NewsItem:
    """Same scheme phase on multiple sources — prefer open, then affordablehomes."""
    if current.status == "open" and candidate.status != "open":
        return current
    if candidate.status == "open" and current.status != "open":
        return candidate
    if SOURCE_PRIORITY.get(candidate.source, 9) < SOURCE_PRIORITY.get(current.source, 9):
        return candidate
    return current


def _dedupe_news(items: List[NewsItem]) -> List[NewsItem]:
    """Merge only the same scheme phase (name + open date), not different phases."""
    best: dict[str, NewsItem] = {}
    for item in items:
        key = item.scheme_key or item.listing_id
        current = best.get(key)
        if current is None:
            best[key] = item
        else:
            best[key] = _pick_better_item(current, item)
    return list(best.values())


def _is_new_today(item: NewsItem) -> bool:
    return item.notification_type in ("new_open", "opened_today")


def _compact_city(item: NewsItem) -> str:
    location = (item.location or "").strip()
    if " - " in location:
        return location.split(" - ", 1)[0].strip()
    formatted = format_city_neighborhood(item.title, item.location)
    return formatted.split(" - ", 1)[0]


def _scheme_headline(item: NewsItem) -> str:
    return f"{_compact_city(item)} — {item.title}"


def _sort_apply_now(items: List[NewsItem]) -> List[NewsItem]:
    def key(item: NewsItem) -> tuple[int, tuple[int, date], str]:
        close_date = _parse_date(item.applications_close_at)
        return (
            0 if _is_new_today(item) else 1,
            (1, date.max) if close_date is None else (0, close_date),
            item.title.casefold(),
        )

    return sorted(items, key=key)


def _sort_by_open_date(items: List[NewsItem]) -> List[NewsItem]:
    def key(item: NewsItem) -> tuple[int, date, str]:
        open_date = _parse_date(item.applications_open_at)
        if open_date is None:
            return (1, date.max, item.title.casefold())
        return (0, open_date, item.title.casefold())

    return sorted(items, key=key)


def _message_header(*, include_year: bool) -> List[str]:
    today = datetime.now(TZ).strftime("%d/%m/%Y" if include_year else "%d/%m")
    return [
        f"🏠 Cost Rental — {today}",
        f"Scheme Hub: {scheme_hub_url()}",
        "",
    ]


def _whatsapp_item_lines(item: NewsItem, *, date_label: str, date_value: str | None) -> List[str]:
    prefix = "🔥 " if _is_new_today(item) else ""
    lines = [f"{prefix}{_scheme_headline(item)}"]
    details = []
    beds = _compact_bedrooms(item.bedrooms)
    if beds:
        details.append(f"🛏️ {beds}")
    price = _compact_price(item.price_from)
    if price:
        details.append(f"💰 {price}")
    if details:
        lines.append(" | ".join(details))
    day = _format_day_month(date_value)
    if day:
        lines.append(f"{date_label} {day}")
    return lines


def _email_item_lines(index: int, item: NewsItem, *, date_label: str, date_value: str | None) -> List[str]:
    prefix = "🔥 " if _is_new_today(item) else ""
    loc = item.location or item.title
    lines = [f"{index}. {prefix}{item.title} — {loc}"]
    details = []
    if item.bedrooms:
        details.append(f"🛏️ {item.bedrooms}")
    price = _email_price(item.price_from)
    if price:
        details.append(f"💰 {price}")
    if details:
        lines.append(f"   {' | '.join(details)}")
    day = _format_day_month_year(date_value)
    if day:
        lines.append(f"   {date_label}: {day}")
    lines.append(f"   {item.url}")
    lines.append("")
    return lines


def format_whatsapp_message(
    apply_now: List[NewsItem],
    opening_soon: List[NewsItem],
) -> str:
    apply_items = _sort_apply_now(_dedupe_news(apply_now))
    soon_items = _sort_by_open_date(_dedupe_news(opening_soon))
    lines = _message_header(include_year=False)

    if apply_items:
        lines.append("🟢 Apply now:")
        for item in apply_items:
            lines.extend(
                _whatsapp_item_lines(
                    item,
                    date_label="closes",
                    date_value=item.applications_close_at,
                )
            )
            lines.append("")

    if soon_items:
        lines.append("🔵 Opening soon:")
        for item in soon_items:
            lines.extend(
                _whatsapp_item_lines(
                    item,
                    date_label="opens",
                    date_value=item.applications_open_at,
                )
            )
            lines.append("")

    return "\n".join(lines).strip()


def format_message(
    apply_now: List[NewsItem],
    opening_soon: List[NewsItem],
) -> str:
    apply_items = _sort_apply_now(_dedupe_news(apply_now))
    soon_items = _sort_by_open_date(_dedupe_news(opening_soon))
    lines = _message_header(include_year=True)

    if apply_items:
        lines.append(f"🟢 Apply now ({len(apply_items)}):")
        lines.append("")
        for index, item in enumerate(apply_items, 1):
            lines.extend(
                _email_item_lines(
                    index,
                    item,
                    date_label="Closes",
                    date_value=item.applications_close_at,
                )
            )

    if soon_items:
        lines.append(f"🔵 Opening soon ({len(soon_items)}):")
        lines.append("")
        for index, item in enumerate(soon_items, 1):
            lines.extend(
                _email_item_lines(
                    index,
                    item,
                    date_label="Opens",
                    date_value=item.applications_open_at,
                )
            )

    return "\n".join(lines).strip()


def format_test_message(
    source_results,
    total_scraped: int,
    whatsapp_configured: bool,
) -> str:
    today = datetime.now(TZ).strftime("%d/%m/%Y")
    lines = [
        f"🧪 TEST — Cost Rental Alert — {today}",
        "",
        "Connection check:",
        "",
    ]

    for result in source_results:
        if result.ok:
            lines.append(f"✅ {result.label} — {result.count} schemes")
        else:
            lines.append(f"❌ {result.label} — ERROR")
            lines.append(f"   {result.error}")

    lines.append("")
    if whatsapp_configured:
        lines.append("✅ WhatsApp CallMeBot — credentials configured")
    else:
        lines.append("❌ WhatsApp CallMeBot — missing CALLMEBOT_PHONE / CALLMEBOT_APIKEY")

    samples: list = []
    for result in source_results:
        for item in result.open_samples:
            samples.append(item)
            if len(samples) >= 3:
                break
        if len(samples) >= 3:
            break

    if samples:
        lines.extend(["", f"📢 Sample open listings ({len(samples)}):"])
        for i, item in enumerate(samples, 1):
            price = _email_price(item.price_from)
            close = _format_day_month_year(item.applications_close_at)
            lines.append(f"{i}. {item.title} — {item.location or item.title}")
            if item.bedrooms or price:
                parts = []
                if item.bedrooms:
                    parts.append(f"🛏️ {item.bedrooms}")
                if price:
                    parts.append(f"💰 {price}")
                lines.append(f"   {' | '.join(parts)}")
            if close:
                lines.append(f"   Closes: {close}")
            lines.append(f"   {item.url}")
            lines.append("")

    lines.extend(
        [
            f"Total: {total_scraped} schemes monitored",
            "Tomorrow: normal alerts (new updates only).",
        ]
    )
    return "\n".join(lines).strip()


def email_configured() -> bool:
    return bool(
        os.environ.get("SMTP_USER", "").strip()
        and os.environ.get("SMTP_PASSWORD", "").strip()
        and os.environ.get("EMAIL_TO", "").strip()
    )


def email_subject(message: str) -> str:
    """Subject line for Mail app / Shortcuts (filter: 'Cost Rental Alert')."""
    first_line = message.split("\n", 1)[0].strip()
    if first_line.startswith("🏠"):
        return first_line.removeprefix("🏠 ").strip()
    return f"Cost Rental Alert — {datetime.now(TZ).strftime('%d/%m/%Y')}"


def send_email(message: str, dry_run: bool = False) -> bool:
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "").strip()
    to_addr = os.environ.get("EMAIL_TO", "").strip()
    from_addr = os.environ.get("EMAIL_FROM", "").strip() or user
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com").strip()
    port = int(os.environ.get("SMTP_PORT", "587"))

    if dry_run or not user or not password or not to_addr:
        print("--- Email (dry-run / missing credentials) ---")
        print(f"To: {to_addr or '(not set)'}")
        print(f"Subject: {email_subject(message)}")
        print(message)
        print("--- end ---")
        return False

    mail = EmailMessage()
    mail["Subject"] = email_subject(message)
    mail["From"] = from_addr
    mail["To"] = to_addr
    mail.set_content(message)

    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.starttls(context=context)
        smtp.login(user, password)
        smtp.send_message(mail)

    print(f"Email sent to {to_addr}.")
    return True


def _split_long_text(text: str, max_chars: int) -> List[str]:
    chunks: List[str] = []
    remaining = text
    while len(remaining) > max_chars:
        split_at = remaining.rfind("\n", 0, max_chars + 1)
        if split_at <= 0:
            split_at = remaining.rfind(" ", 0, max_chars + 1)
        if split_at <= 0:
            split_at = max_chars
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _split_blocks(blocks: List[str], max_chars: int) -> List[str]:
    chunks: List[str] = []
    current = ""

    for block in [block.strip() for block in blocks if block.strip()]:
        if len(block) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_text(block, max_chars))
            continue

        candidate = block if not current else f"{current}\n\n{block}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = block

    if current:
        chunks.append(current)
    return chunks


def _split_whatsapp_message(
    message: str,
    max_chars: int = WHATSAPP_CHUNK_CHARS,
) -> List[str]:
    """Split long CallMeBot messages into block-preserving WhatsApp parts."""
    if len(message) <= max_chars:
        return [message]

    header, separator, body = message.partition("\n\n")
    if not separator:
        return _split_long_text(message, max_chars)

    body_limit = max(200, max_chars - len(header) - 16)
    body_chunks = _split_blocks(body.split("\n\n"), body_limit)
    total = len(body_chunks)
    if total <= 1:
        return [message]

    return [
        f"{header} ({index}/{total})\n\n{chunk}"
        for index, chunk in enumerate(body_chunks, 1)
    ]


def send_whatsapp(message: str, dry_run: bool = False) -> bool:
    phone = os.environ.get("CALLMEBOT_PHONE", "").strip()
    apikey = os.environ.get("CALLMEBOT_APIKEY", "").strip()
    chunks = _split_whatsapp_message(message)

    if dry_run or not phone or not apikey:
        print("--- WhatsApp message (dry-run / missing credentials) ---")
        for index, chunk in enumerate(chunks, 1):
            if len(chunks) > 1:
                print(f"--- part {index}/{len(chunks)} ---")
            print(chunk)
        print("--- end ---")
        return False

    for index, chunk in enumerate(chunks, 1):
        url = (
            "https://api.callmebot.com/whatsapp.php?"
            f"phone={urllib.parse.quote(phone)}"
            f"&text={urllib.parse.quote(chunk)}"
            f"&apikey={urllib.parse.quote(apikey)}"
        )
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        if index < len(chunks):
            time.sleep(1)

    if len(chunks) == 1:
        print("WhatsApp message sent.")
    else:
        print(f"WhatsApp message sent in {len(chunks)} parts.")
    return True

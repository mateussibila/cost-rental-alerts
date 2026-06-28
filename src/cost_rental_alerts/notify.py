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


def _today() -> date:
    return datetime.now(TZ).date()


def _format_price(price: float | None, prefix: str = "from") -> str:
    if price is None:
        return ""
    if price == int(price):
        amount = f"€{int(price):,}/mo"
    else:
        amount = f"€{price:,.2f}/mo"
    return f"{prefix} {amount}" if prefix else amount


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _format_open_date_short(value: str | None) -> str:
    parsed = _parse_date(value)
    if not parsed:
        return ""
    return parsed.strftime("%d/%m/%y")


def _format_day_month(value: str | None) -> str:
    parsed = _parse_date(value)
    if not parsed:
        return "date TBC"
    return parsed.strftime("%d/%m")


def _closes_line(close_at: str | None) -> str:
    close_date = _parse_date(close_at)
    if not close_date:
        return "Closes in: not informed"
    delta = (close_date - _today()).days
    if delta < 0:
        return "Closes in: not informed"
    if delta == 0:
        return "Closes today"
    if delta == 1:
        return "Closes in 1 day"
    return f"Closes in {delta} days"


def _format_details_line(bedrooms: str | None, price: float | None) -> str:
    parts = []
    if bedrooms:
        parts.append(f"🛏️ {bedrooms}")
    price_text = _format_price(price)
    if price_text:
        parts.append(f"💰 {price_text}")
    return " | ".join(parts)


def _format_listing_block(
    index: int,
    title: str,
    location: str,
    url: str,
    bedrooms: str | None,
    price: float | None,
    *,
    extra_line: str | None = None,
) -> List[str]:
    loc = location or title
    lines = [f"{index}. {title} — {loc}"]
    details = _format_details_line(bedrooms, price)
    if details:
        lines.append(f"   {details}")
    if extra_line:
        lines.append(f"   {extra_line}")
    lines.append(f"   {url}")
    lines.append("")
    return lines


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


def _sort_by_close_date(items: List[NewsItem]) -> List[NewsItem]:
    """Soonest closing first; listings without a close date last."""

    def key(item: NewsItem) -> tuple[int, date]:
        close_date = _parse_date(item.applications_close_at)
        if close_date is None:
            return (1, date.max)
        return (0, close_date)

    return sorted(items, key=key)


def _sort_by_open_date(items: List[NewsItem]) -> List[NewsItem]:
    """Soonest opening first; listings without an open date last."""

    def key(item: NewsItem) -> tuple[int, date]:
        open_date = _parse_date(item.applications_open_at)
        if open_date is None:
            return (1, date.max)
        return (0, open_date)

    return sorted(items, key=key)


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


def _identity_keys(item: NewsItem) -> set[str]:
    return {key for key in (item.listing_id, item.scheme_key) if key}


def _exclude_items(
    items: List[NewsItem],
    excluded: List[NewsItem],
) -> List[NewsItem]:
    excluded_keys: set[str] = set()
    for item in excluded:
        excluded_keys.update(_identity_keys(item))
    return [item for item in items if _identity_keys(item).isdisjoint(excluded_keys)]


def _message_groups(
    news: List[NewsItem],
    closing_soon: List[NewsItem] | None = None,
    opening_soon: List[NewsItem] | None = None,
) -> tuple[List[NewsItem], List[NewsItem], List[NewsItem]]:
    news = _dedupe_news(news)
    opened = [n for n in news if n.notification_type in ("new_open", "opened_today")]
    soon_source = (
        opening_soon
        if opening_soon is not None
        else [n for n in news if n.notification_type == "opening_soon"]
    )
    soon = _exclude_items(_dedupe_news(soon_source), opened)
    closing = _exclude_items(_dedupe_news(closing_soon or []), opened)
    return opened, closing, soon


def _append_listing_section(
    lines: List[str],
    heading: str,
    items: List[NewsItem],
    *,
    sort_by: str,
) -> None:
    if sort_by == "close":
        sorted_items = _sort_by_close_date(items)
    elif sort_by == "open":
        sorted_items = _sort_by_open_date(items)
    else:
        sorted_items = items

    lines.append(f"{heading} ({len(sorted_items)}):")
    lines.append("")
    for i, item in enumerate(sorted_items, 1):
        if sort_by == "open":
            open_date = _format_open_date_short(item.applications_open_at)
            extra = f"Opens: {open_date}" if open_date else None
        else:
            extra = _closes_line(item.applications_close_at)

        lines.extend(
            _format_listing_block(
                i,
                item.title,
                item.location,
                item.url,
                item.bedrooms,
                item.price_from,
                extra_line=extra,
            )
        )


def format_message(
    news: List[NewsItem],
    total_scraped: int,
    *,
    closing_soon: List[NewsItem] | None = None,
    opening_soon: List[NewsItem] | None = None,
) -> str:
    today = datetime.now(TZ).strftime("%d/%m/%Y")
    lines = [f"🏠 Cost Rental Alert — {today}", ""]
    opened, closing, soon = _message_groups(news, closing_soon, opening_soon)

    if opened:
        _append_listing_section(
            lines,
            "📢 NEW APPLICATIONS",
            opened,
            sort_by="close",
        )
    else:
        lines.append("🆕 NO NEW APPLICATIONS")
        lines.append("")

    if closing:
        _append_listing_section(
            lines,
            "⏳ CLOSING SOON",
            closing,
            sort_by="close",
        )
    else:
        lines.append("⏳ CLOSING SOON: none")
        lines.append("")

    if soon:
        _append_listing_section(
            lines,
            "📅 OPENING SOON",
            soon,
            sort_by="open",
        )
    else:
        lines.append("📅 OPENING SOON: none")
        lines.append("")

    lines.append(f"({total_scraped} schemes monitored)")
    return "\n".join(lines).strip()


def _compact_city(item: NewsItem) -> str:
    formatted = format_city_neighborhood(item.title, item.location)
    return formatted.split(" - ", 1)[0]


def _compact_item_line(index: int, item: NewsItem, date_value: str | None) -> List[str]:
    return [
        f"{index}. {_format_day_month(date_value)} - {_compact_city(item)}, {item.title}",
        item.url,
    ]


def _append_compact_section(
    lines: List[str],
    heading: str,
    items: List[NewsItem],
    *,
    date_field: str,
    sort_by: str,
) -> None:
    if sort_by == "close":
        sorted_items = _sort_by_close_date(items)
    elif sort_by == "open":
        sorted_items = _sort_by_open_date(items)
    else:
        sorted_items = items

    lines.append(f"{heading}:")
    if not sorted_items:
        lines.append("none")
        lines.append("")
        return

    for i, item in enumerate(sorted_items, 1):
        date_value = (
            item.applications_open_at
            if date_field == "open"
            else item.applications_close_at
        )
        lines.extend(_compact_item_line(i, item, date_value))
    lines.append("")


def format_whatsapp_message(
    news: List[NewsItem],
    total_scraped: int,
    *,
    closing_soon: List[NewsItem] | None = None,
    opening_soon: List[NewsItem] | None = None,
) -> str:
    today = datetime.now(TZ).strftime("%d/%m")
    opened, closing, soon = _message_groups(news, closing_soon, opening_soon)
    lines = [f"🏠 Cost Rental — {today}", ""]

    _append_compact_section(
        lines,
        "🆕 New",
        opened,
        date_field="close",
        sort_by="close",
    )
    _append_compact_section(
        lines,
        "⏳ Closing soon",
        closing,
        date_field="close",
        sort_by="close",
    )
    _append_compact_section(
        lines,
        "📅 Opening soon",
        soon,
        date_field="open",
        sort_by="open",
    )

    lines.append(f"({total_scraped} monitored)")
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
            lines.extend(
                _format_listing_block(
                    i,
                    item.title,
                    item.location,
                    item.url,
                    item.bedrooms,
                    item.price_from,
                    extra_line=_closes_line(item.applications_close_at),
                )
            )

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

    # Reserve room for the repeated header and "(1/2)" marker in each part.
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

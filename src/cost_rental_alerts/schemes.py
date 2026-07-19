"""Logical scheme identity — distinguishes phases of the same development name."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from cost_rental_alerts.models import Listing

# Sources that may lag behind AH when their scrape fails (e.g. 403).
SECONDARY_SOURCES = frozenset(
    {"lda", "tuath", "respond", "cluid", "circle", "oaklee", "chi"}
)


def normalize_scheme_name(title: str) -> str:
    return " ".join(title.strip().lower().split())


def compute_scheme_key(
    title: str,
    applications_open_at: str | None,
    listed_at: str | None,
    listing_id: str,
) -> str:
    """
    Identify a scheme phase by name + open date.

    Same name + same open date across sources (e.g. Tuath + affordablehomes) = one phase.
    Different open dates or names (e.g. Parklands 2024 vs Parklands 2026) = separate entries.
    """
    name = normalize_scheme_name(title)
    open_date = applications_open_at or listed_at
    if open_date:
        return f"{name}|{open_date[:10]}"
    return f"{name}|{listing_id}"


def names_overlap(a: str, b: str) -> bool:
    na, nb = normalize_scheme_name(a), normalize_scheme_name(b)
    if na == nb:
        return True
    if na.split(",")[0].strip() == nb.split(",")[0].strip():
        return True
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    return longer.startswith(shorter + " ") or longer.startswith(shorter + ",")


def listing_scheme_key(listing: Listing) -> str:
    return compute_scheme_key(
        listing.title,
        listing.applications_open_at,
        listing.listed_at,
        listing.id,
    )


def _dates_within(
    left: str,
    right: str,
    *,
    max_days: int = 1,
) -> bool:
    left_day = left[:10]
    right_day = right[:10]
    if left_day == right_day:
        return True
    try:
        a = date.fromisoformat(left_day)
        b = date.fromisoformat(right_day)
    except ValueError:
        return False
    return abs((a - b).days) <= max_days


def prices_match(
    left: float | None,
    right: float | None,
    *,
    tolerance: float = 1.0,
) -> bool:
    """Require both prices; missing price means not a clear duplicate."""
    if left is None or right is None:
        return False
    return abs(float(left) - float(right)) <= tolerance


def dates_share_open_or_close(left: Listing, right: Listing) -> bool:
    """True when open dates match and/or close dates match."""
    open_match = False
    close_match = False
    if left.applications_open_at and right.applications_open_at:
        open_match = _dates_within(left.applications_open_at, right.applications_open_at)
    if left.applications_close_at and right.applications_close_at:
        close_match = _dates_within(left.applications_close_at, right.applications_close_at)
    return open_match or close_match


def same_scheme_phase(left: Listing, right: Listing) -> bool:
    """
    Clear duplicate across sources: same name, same price, and matching open and/or close.

    Prefer showing two entries when any of these signals is missing or disagrees.
    """
    if not names_overlap(left.title, right.title):
        return False
    if not prices_match(left.price_from, right.price_from):
        return False
    if not dates_share_open_or_close(left, right):
        return False
    return True


def matching_affordablehomes_closed(ah: Listing, other: Listing) -> bool:
    """True when a closed AH row should override a stale open secondary-source row."""
    if ah.source != "affordablehomes" or ah.status != "closed":
        return False
    if other.source not in SECONDARY_SOURCES or other.status != "open":
        return False
    if not names_overlap(ah.title, other.title):
        return False
    # Prefer strict phase match when both sides are well populated.
    if (
        ah.price_from is not None
        and other.price_from is not None
        and ah.applications_open_at
        and other.applications_open_at
    ):
        return same_scheme_phase(ah, other) or (
            prices_match(ah.price_from, other.price_from)
            and _dates_within(ah.applications_open_at, other.applications_open_at)
        )
    if ah.applications_open_at and other.applications_open_at:
        if not _dates_within(ah.applications_open_at, other.applications_open_at):
            return False
    if ah.price_from is not None and other.price_from is not None:
        if not prices_match(ah.price_from, other.price_from):
            return False
    return True


def apply_ah_closed_override(ah: Listing, listing: Listing) -> None:
    listing.status = "closed"
    if ah.applications_close_at and not listing.applications_close_at:
        listing.applications_close_at = ah.applications_close_at


def apply_affordablehomes_closed_overrides_to_targets(
    targets: list[Listing],
    ah_listings: list[Listing],
) -> list[Listing]:
    """Apply AH closed overrides. Returns targets that were changed."""
    ah_closed = [
        listing
        for listing in ah_listings
        if listing.source == "affordablehomes" and listing.status == "closed"
    ]
    changed: list[Listing] = []
    for listing in targets:
        if listing.source not in SECONDARY_SOURCES or listing.status != "open":
            continue
        for ah in ah_closed:
            if matching_affordablehomes_closed(ah, listing):
                apply_ah_closed_override(ah, listing)
                changed.append(listing)
                break
    return changed


def is_covered_by_affordablehomes(
    listing: Listing, ah_listings: list[Listing]
) -> bool:
    """True only when AH has a clear same-phase duplicate (name+price+dates)."""
    for ah in ah_listings:
        if same_scheme_phase(listing, ah):
            return True
    return False


def merge_listings_ah_first(listings: list[Listing]) -> list[Listing]:
    """
    Keep AH entries and add other sources unless they are a clear AH duplicate.

    Prefer duplicate cards over dropping a scheme that might still be available.
    """
    ah = [listing for listing in listings if listing.source == "affordablehomes"]
    merged = list(ah)
    for listing in listings:
        if listing.source == "affordablehomes":
            continue
        if not is_covered_by_affordablehomes(listing, ah):
            merged.append(listing)
    return merged


def apply_affordablehomes_closed_overrides(listings: list[Listing]) -> None:
    """When AH marks a scheme phase closed, override stale open secondary-source rows."""
    apply_affordablehomes_closed_overrides_to_targets(listings, listings)


def apply_affordablehomes_closed_overrides_to_db(
    conn,
    scraped: list[Listing],
) -> int:
    """
    Close stale open secondary-source rows already in the database.

    Used when a source scrape fails (e.g. Tuath 403 on GitHub Actions) but AH still
    reports the same phase as closed.
    """
    from cost_rental_alerts.db import listing_from_row, persist_listing_closed

    ah_listings = [listing for listing in scraped if listing.source == "affordablehomes"]
    if not ah_listings:
        return 0

    placeholders = ", ".join("?" for _ in SECONDARY_SOURCES)
    rows = conn.execute(
        f"""
        SELECT * FROM listings
        WHERE source IN ({placeholders})
          AND status = 'open'
          AND category = 'rent'
        """,
        tuple(sorted(SECONDARY_SOURCES)),
    ).fetchall()
    if not rows:
        return 0

    targets = [listing_from_row(row) for row in rows]
    changed = apply_affordablehomes_closed_overrides_to_targets(targets, ah_listings)
    for listing in changed:
        persist_listing_closed(conn, listing)
    if changed:
        conn.commit()
    return len(changed)


def enrich_cross_source_open_dates(listings: list[Listing]) -> None:
    """Copy applications_open_at from affordablehomes when another source lacks it."""
    open_dates_by_name: dict[str, list[str]] = defaultdict(list)

    for listing in listings:
        if listing.source != "affordablehomes" or not listing.applications_open_at:
            continue
        if listing.status == "open":
            open_dates_by_name[normalize_scheme_name(listing.title)].append(
                listing.applications_open_at
            )

    for listing in listings:
        if listing.applications_open_at or listing.status != "open":
            continue
        candidates = open_dates_by_name.get(normalize_scheme_name(listing.title), [])
        unique = sorted(set(candidates))
        if len(unique) == 1:
            listing.applications_open_at = unique[0]

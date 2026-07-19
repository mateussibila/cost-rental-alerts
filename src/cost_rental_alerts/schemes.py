"""Logical scheme identity — distinguishes phases of the same development name."""

from collections import defaultdict
from datetime import date

from cost_rental_alerts.models import Listing


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


def _open_dates_match(
    ah_open: str,
    other_open: str,
    *,
    max_days: int = 1,
) -> bool:
    ah_date = ah_open[:10]
    other_date = other_open[:10]
    if ah_date == other_date:
        return True
    try:
        ah_day = date.fromisoformat(ah_date)
        other_day = date.fromisoformat(other_date)
    except ValueError:
        return False
    return abs((ah_day - other_day).days) <= max_days


def matching_affordablehomes_closed(ah: Listing, other: Listing) -> bool:
    """True when a closed AH row should override a stale open LDA/Tuath row."""
    if ah.source != "affordablehomes" or ah.status != "closed":
        return False
    if other.source not in {"lda", "tuath"} or other.status != "open":
        return False
    if not names_overlap(ah.title, other.title):
        return False
    if ah.applications_open_at and other.applications_open_at:
        if not _open_dates_match(ah.applications_open_at, other.applications_open_at):
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
    ah_by_name: dict[str, list[Listing]] = defaultdict(list)
    for listing in ah_listings:
        if listing.source == "affordablehomes" and listing.status == "closed":
            ah_by_name[normalize_scheme_name(listing.title)].append(listing)

    changed: list[Listing] = []
    for listing in targets:
        if listing.source not in {"lda", "tuath"} or listing.status != "open":
            continue
        for ah in ah_by_name.get(normalize_scheme_name(listing.title), []):
            if matching_affordablehomes_closed(ah, listing):
                apply_ah_closed_override(ah, listing)
                changed.append(listing)
                break
    return changed


def is_covered_by_affordablehomes(
    listing: Listing, ah_listings: list[Listing]
) -> bool:
    """True when affordablehomes already has this scheme (AH data wins)."""
    sk = listing_scheme_key(listing)
    for ah in ah_listings:
        if listing_scheme_key(ah) == sk:
            return True

    for ah in ah_listings:
        if not names_overlap(ah.title, listing.title):
            continue
        # Stale AH closed entry does not cover a new open round on LDA/Tuath.
        if listing.status == "open" and ah.status != "open":
            continue
        return True

    return False


def merge_listings_ah_first(listings: list[Listing]) -> list[Listing]:
    """Keep all AH entries; add LDA/Tuath only when not already on AH."""
    ah = [listing for listing in listings if listing.source == "affordablehomes"]
    merged = list(ah)
    for listing in listings:
        if listing.source == "affordablehomes":
            continue
        if not is_covered_by_affordablehomes(listing, ah):
            merged.append(listing)
    return merged


def apply_affordablehomes_closed_overrides(listings: list[Listing]) -> None:
    """When AH marks a scheme phase closed, override stale open LDA/Tuath rows."""
    apply_affordablehomes_closed_overrides_to_targets(listings, listings)


def apply_affordablehomes_closed_overrides_to_db(
    conn,
    scraped: list[Listing],
) -> int:
    """
    Close stale open LDA/Tuath rows already in the database.

    Used when a source scrape fails (e.g. Tuath 403 on GitHub Actions) but AH still
    reports the same phase as closed.
    """
    from cost_rental_alerts.db import listing_from_row, persist_listing_closed

    ah_listings = [listing for listing in scraped if listing.source == "affordablehomes"]
    if not ah_listings:
        return 0

    rows = conn.execute(
        """
        SELECT * FROM listings
        WHERE source IN ('tuath', 'lda')
          AND status = 'open'
          AND category = 'rent'
        """
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

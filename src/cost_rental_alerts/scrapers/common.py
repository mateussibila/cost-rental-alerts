import re
from typing import Optional

import requests

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
BROWSER_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IE,en;q=0.9",
}
TIMEOUT = 30


def fetch(url: str, *, extra_headers: dict[str, str] | None = None) -> str:
    headers = dict(BROWSER_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    response = requests.get(
        url,
        headers=headers,
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.text


def parse_income_amount(text: str) -> Optional[float]:
    """Parse € amounts from eligibility tables, including European €66.000 format."""
    cleaned = text.strip().replace("€", "").strip()
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", cleaned):
        return float(cleaned.replace(".", ""))
    match = re.search(r"([0-9][0-9,]*)", cleaned)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def parse_price(text: str) -> Optional[float]:
    match = re.search(r"€\s*([0-9][0-9,]*)", text)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def normalize_status(text: str) -> str:
    lowered = text.strip().lower()
    if "open" in lowered or "apply now" in lowered:
        return "open"
    if "closed" in lowered:
        return "closed"
    if "soon" in lowered:
        return "coming_soon"
    return "unknown"


def parse_bed_count(text: str) -> Optional[int]:
    """e.g. '2 bedroom duplex', 'One-bedroom apartment', '1 bed maisonette' -> 2, 1, 1."""
    cleaned = text.strip()
    if "/" in cleaned:
        cleaned = cleaned.split("/", 1)[1].strip()
    word_map = {"one": 1, "two": 2, "three": 3, "four": 4}
    word_match = re.search(r"\b(one|two|three|four)\s*[- ]?\s*bed", cleaned, re.I)
    if word_match:
        return word_map[word_match.group(1).lower()]
    num_match = re.search(r"(\d+)\s*[- ]?\s*bed", cleaned, re.I)
    if num_match:
        return int(num_match.group(1))
    return None


def bedrooms_range(counts: list[int]) -> Optional[str]:
    if not counts:
        return None
    nums = sorted(set(counts))
    if len(nums) == 1:
        return f"{nums[0]} bed"
    return f"{nums[0]}-{nums[-1]} bed"


def normalize_bedrooms(text: str) -> str:
    """e.g. '1, 2 & 3 Bed' -> '1-3 bed', '3 Bed' -> '3 bed'."""
    cleaned = text.strip()
    if not cleaned:
        return ""
    match = re.search(r"(\d+(?:\s*,\s*\d+)*)\s*(?:&\s*(\d+))?\s*Bed", cleaned, re.I)
    if not match:
        return cleaned.lower().strip()
    nums = [int(n.strip()) for n in match.group(1).split(",")]
    if match.group(2):
        nums.append(int(match.group(2)))
    nums = sorted(set(nums))
    if len(nums) == 1:
        return f"{nums[0]} bed"
    return f"{nums[0]}-{nums[-1]} bed"


def parse_quantity(text: str) -> Optional[int]:
    """e.g. '40 Units' -> 40."""
    match = re.search(r"(\d+)\s+Units?\b", text.strip(), re.I)
    if not match:
        return None
    return int(match.group(1))


def parse_listed_date(text: str) -> Optional[str]:
    match = re.search(r"(\d{2})/(\d{2})/(\d{4})", text)
    if not match:
        return None
    day, month, year = match.groups()
    return f"{year}-{month}-{day}"

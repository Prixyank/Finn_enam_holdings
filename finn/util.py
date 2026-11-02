"""Small parsing helpers shared across the engine."""

from __future__ import annotations

import re
from datetime import date, datetime

from .config import USD_INR

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def num(x) -> float | None:
    """'1,234' -> 1234.0, '17%' -> 17.0, '' -> None."""
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).replace(",", "").replace("%", "").replace("₹", "").strip()
    if s in {"", "-", "—"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def volume(x) -> float | None:
    """'4.33M' -> 4_330_000, '605.96K' -> 605_960, '' -> None."""
    if x is None:
        return None
    s = str(x).strip().replace(",", "")
    if not s:
        return None
    mult = {"K": 1e3, "M": 1e6, "B": 1e9}.get(s[-1].upper())
    if mult:
        return float(s[:-1]) * mult
    try:
        return float(s)
    except ValueError:
        return None


def parse_day_month(s: str, year: int) -> date:
    """screener's '27 Oct' (no year) -> date."""
    d, m = s.strip().split()[:2]
    return date(year, MONTHS[m[:3].lower()], int(d))


def parse_date(s: str) -> date:
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d-%b-%Y", "%d-%b-%Y %H:%M:%S", "%a %b %d %Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unparsed date: {s!r}")


_AMOUNT = re.compile(
    r"(?P<cur>₹|rs\.?|inr|us\$|usd|\$)\s*(?P<val>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>lakh\s+crore|crores?|cr\b|million|mn\b|billion|bn\b)?",
    re.I,
)


def amounts_in_crore(text: str) -> list[float]:
    """Every money amount in a sentence, normalised to ₹ crore. Used to size a filing against market cap."""
    out = []
    for m in _AMOUNT.finditer(text or ""):
        val = float(m.group("val").replace(",", ""))
        cur = m.group("cur").lower()
        unit = (m.group("unit") or "").lower()
        if unit.startswith("lakh"):
            val *= 1e5
        elif unit.startswith(("million", "mn")):
            val /= 10
        elif unit.startswith(("billion", "bn")):
            val *= 100
        elif not unit:
            continue  # a bare price like '₹1,119' is a per-share number, not a deal size
        if cur in {"us$", "usd", "$"}:
            val *= USD_INR
        out.append(round(val, 2))
    return out


def pct(a: float | None, b: float | None) -> float | None:
    """Percent change from b to a."""
    if a is None or b in (None, 0):
        return None
    return round((a - b) / abs(b) * 100, 1)


def fy_quarter(label: str) -> str:
    """'Sep 2026' (quarter end) -> 'Q2FY27'."""
    m, y = label.split()
    mi, yi = MONTHS[m[:3].lower()], int(y)
    q = {6: 1, 9: 2, 12: 3, 3: 4}[mi]
    fy = yi + 1 if mi >= 4 else yi
    return f"Q{q}FY{fy % 100:02d}"


def quarter_index(q: str) -> int:
    """'Q3FY27' -> a sortable integer, one step per quarter."""
    m = re.fullmatch(r"Q([1-4])FY(\d{2})", q)
    if not m:
        raise ValueError(q)
    return int(m.group(2)) * 4 + int(m.group(1))

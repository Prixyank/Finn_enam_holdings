"""End-of-day rules: unusual volume and unusual price moves, against user thresholds.

The web app re-implements `scan` in JavaScript so thresholds can be moved live;
tests/test_parity.py runs both on the same bars and asserts identical output.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

from .config import Thresholds


@dataclass
class Bar:
    date: date
    close: float
    volume: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None


@dataclass
class Trigger:
    ticker: str
    date: str
    close: float
    move_pct: float | None
    vol: float | None
    avg_vol: float | None
    vol_ratio: float | None
    price_hit: bool
    volume_hit: bool
    lookback_used: int

    @property
    def kind(self) -> str:
        return "price+volume" if self.price_hit and self.volume_hit else "price" if self.price_hit else "volume"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["kind"] = self.kind
        return d


def evaluate_day(ticker: str, bars: list[Bar], i: int, th: Thresholds) -> Trigger | None:
    """Rules for bars[i] using only bars before it. `bars` must be sorted oldest→newest."""
    if i == 0:
        return None
    b, prev = bars[i], bars[i - 1]
    move = round((b.close - prev.close) / prev.close * 100, 2) if prev.close else None
    window = [x.volume for x in bars[max(0, i - th.volume_lookback):i] if x.volume]
    avg = sum(window) / len(window) if len(window) >= th.min_lookback else None
    ratio = round(b.volume / avg, 2) if (avg and b.volume) else None
    price_hit = move is not None and abs(move) >= th.price_move_pct
    volume_hit = ratio is not None and ratio >= th.volume_multiple
    if not (price_hit or volume_hit):
        return None
    return Trigger(ticker, b.date.isoformat(), b.close, move, b.volume, round(avg) if avg else None, ratio, price_hit, volume_hit, len(window))


def scan(ticker: str, bars: list[Bar], th: Thresholds, start: date, end: date) -> list[Trigger]:
    """All triggers for sessions in [start, end]."""
    bars = sorted(bars, key=lambda x: x.date)
    out = []
    for i, b in enumerate(bars):
        if start <= b.date <= end:
            t = evaluate_day(ticker, bars, i, th)
            if t:
                out.append(t)
    return out


def staleness(bars: list[Bar], as_of: date, max_gap_days: int = 4) -> str | None:
    """Data-health guard: a feed that silently stops updating is worse than no feed."""
    if not bars:
        return "no price data"
    last = max(b.date for b in bars)
    gap = (as_of - last).days
    return f"last bar {last.isoformat()} ({gap} days old)" if gap > max_gap_days else None

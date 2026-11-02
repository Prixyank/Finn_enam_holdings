"""End-of-day price & volume. Live: yfinance (.NS tickers). Snapshot: CSV rows as fetched."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from ..alerts import Bar
from ..util import num, parse_date, volume


def fetch_yfinance(symbols: list[str], period: str = "3mo") -> dict[str, list[Bar]]:
    import yfinance as yf  # optional dependency, only for live runs

    data = yf.download([f"{s}.NS" for s in symbols], period=period, interval="1d", group_by="ticker", auto_adjust=False, progress=False, threads=True)
    out: dict[str, list[Bar]] = {}
    for s in symbols:
        df = data[f"{s}.NS"].dropna(subset=["Close"])
        out[s] = [Bar(idx.date(), float(r["Close"]), float(r["Volume"]) if r["Volume"] == r["Volume"] else None,
                      float(r["Open"]), float(r["High"]), float(r["Low"])) for idx, r in df.iterrows()]
    return out


def load_snapshot_csv(paths: list[Path], through=None) -> dict[str, list[Bar]]:
    """Rows: ticker,Date,Price,Open,High,Low,Vol.,Change %. `through` drops bars after the EOD cut-off
    (the snapshot was taken intraday, so the current session's partial bar must not count as a close)."""
    out: dict[str, list[Bar]] = defaultdict(list)
    for p in paths:
        with open(p, newline="") as f:
            for r in csv.DictReader(f):
                d = parse_date(r["Date"])
                if through and d > through:
                    continue
                out[r["ticker"]].append(Bar(d, num(r["Price"]), volume(r.get("Vol.")), num(r.get("Open")), num(r.get("High")), num(r.get("Low"))))
    return {k: sorted(v, key=lambda b: b.date) for k, v in out.items()}

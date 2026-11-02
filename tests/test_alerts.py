from datetime import date, timedelta

from finn.alerts import Bar, evaluate_day, scan, staleness
from finn.config import Thresholds


def bars(closes, vols):
    d0 = date(2026, 10, 1)
    return [Bar(d0 + timedelta(days=i), c, v) for i, (c, v) in enumerate(zip(closes, vols))]


def test_volume_spike_uses_only_prior_sessions():
    b = bars([100] * 6 + [101], [10, 10, 10, 10, 10, 10, 25])
    t = evaluate_day("X", b, 6, Thresholds())
    assert t.volume_hit and not t.price_hit and t.vol_ratio == 2.5 and t.avg_vol == 10


def test_price_move_threshold_is_inclusive_and_signed():
    b = bars([100, 97], [None, None])
    t = evaluate_day("X", b, 1, Thresholds(price_move_pct=3.0))
    assert t.price_hit and t.move_pct == -3.0 and t.vol_ratio is None


def test_volume_rule_abstains_with_short_history():
    b = bars([100, 100, 100, 100], [10, 10, 10, 50])
    assert evaluate_day("X", b, 3, Thresholds()) is None  # 3 prior sessions < min_lookback 5


def test_thresholds_are_respected():
    b = bars([100] * 6 + [102], [10] * 6 + [19])
    assert scan("X", b, Thresholds(), b[0].date, b[-1].date) == []
    hits = scan("X", b, Thresholds(volume_multiple=1.5, price_move_pct=2.0), b[0].date, b[-1].date)
    assert len(hits) == 1 and hits[0].kind == "price+volume"


def test_real_eternal_post_results_volume():
    """22 Oct 2026, the session after Eternal's results: 85.5M shares vs ~22M normal."""
    from pathlib import Path

    from finn.sources.prices import load_snapshot_csv
    root = Path(__file__).resolve().parent.parent
    b = load_snapshot_csv(sorted((root / "data/raw/prices").glob("*.csv")), through=date(2026, 10, 26))["ETERNAL"]
    hits = {t.date: t for t in scan("ETERNAL", b, Thresholds(), date(2026, 10, 20), date(2026, 10, 26))}
    assert hits["2026-10-22"].volume_hit and hits["2026-10-22"].vol_ratio > 3.5
    assert hits["2026-10-23"].kind == "price+volume"


def test_intraday_bar_is_excluded_from_eod():
    from pathlib import Path

    from finn.sources.prices import load_snapshot_csv
    root = Path(__file__).resolve().parent.parent
    b = load_snapshot_csv(sorted((root / "data/raw/prices").glob("*.csv")), through=date(2026, 10, 26))
    assert all(x.date <= date(2026, 10, 26) for v in b.values() for x in v)
    assert len(b) == 15


def test_staleness_guard():
    assert staleness([Bar(date(2026, 10, 1), 1)], date(2026, 10, 26)).startswith("last bar 2026-10-01")
    assert staleness([Bar(date(2026, 10, 23), 1)], date(2026, 10, 26)) is None

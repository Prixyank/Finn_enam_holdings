"""The app re-runs the alert rules in JavaScript so thresholds move live. This proves the two
implementations agree on the real snapshot, at default and at loosened thresholds."""

import json
import shutil
import subprocess
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

from finn import alerts as A
from finn.config import Thresholds
from finn.sources.prices import load_snapshot_csv

ROOT = Path(__file__).resolve().parent.parent
EOD = date(2026, 10, 26)


def js_rules() -> str:
    html = (ROOT / "web" / "app.html").read_text()
    return html.split("// ==RULES==", 1)[1].split("// ==/RULES==", 1)[0].split("\n", 1)[1]


def py_triggers(bars, th):
    out = []
    for t, bs in bars.items():
        out += [x.to_dict() for x in A.scan(t, bs, th, EOD - timedelta(days=30), EOD)]
    return sorted((x["ticker"], x["date"], x["kind"], x["move_pct"], x["vol_ratio"]) for x in out)


def test_js_and_python_rules_agree():
    if not shutil.which("node"):
        return  # nothing to compare against without a JS runtime
    bars = load_snapshot_csv(sorted((ROOT / "data/raw/prices").glob("*.csv")), through=EOD)
    rows = {t: [[b.date.isoformat(), b.close, b.volume] for b in bs] for t, bs in bars.items()}
    for th in (Thresholds(), Thresholds(volume_multiple=1.5, price_move_pct=2.0)):
        script = js_rules() + f"""
const bars = {json.dumps(rows)}; const th = {json.dumps(asdict(th))};
let out = [];
for (const [t, b] of Object.entries(bars)) out.push(...scanBars(t, b, th, "{(EOD - timedelta(days=30)).isoformat()}", "{EOD.isoformat()}"));
console.log(JSON.stringify(out.map(x => [x.ticker, x.date, x.kind, x.move_pct, x.vol_ratio])));
"""
        js = sorted(tuple(x) for x in json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout))
        py = py_triggers(bars, th)
        assert [x[:3] for x in js] == [x[:3] for x in py], "rule hits differ"
        for a, b in zip(js, py):
            assert a[3] is None and b[3] is None or abs(a[3] - b[3]) < 0.011
            assert a[4] is None and b[4] is None or abs(a[4] - b[4]) < 0.011

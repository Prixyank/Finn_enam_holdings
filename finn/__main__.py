"""CLI.

  python -m finn build              replay the committed snapshot → web/data/finn.json + dist/
  python -m finn live               pull today's data from NSE/BSE, yfinance and screener, then build
  python -m finn notify [--dry-run] push what crossed your rules to Telegram / email, once per item
  python -m finn research SYMBOL    pull-side research on any NSE symbol screener covers (prints JSON)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone

from .build import load_snapshot, process, write_app
from .config import PORTFOLIO
from .llm import LLM, available

IST = timezone(timedelta(hours=5, minutes=30))


def cmd_build(_):
    now = datetime(2026, 10, 27, 12, 35, tzinfo=IST)
    payload = process(load_snapshot(date(2026, 10, 26)), now, date(2026, 10, 26))
    print(f"wrote {write_app(payload)}  ({len(payload['filings'])} filings, {len(payload['triggers'])} triggers)")


def _previous_close_day(now: datetime) -> date:
    d = now.date() if now.hour >= 16 else now.date() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def collect_live(now: datetime, days: int = 30) -> dict:
    from .sources import exchange, prices, screener

    eod = _previous_close_day(now)
    start = now.date() - timedelta(days=days)
    nse = exchange.NSE()
    companies = {}
    for t in PORTFOLIO:
        s = screener.parse(screener.fetch(t))
        anns = exchange.announcements(t, s.get("bse_code"), start, now.date(), nse)
        companies[t] = {
            "name": s["name"], "mcap_cr": float(s["top"].get("Market Cap", "0") or 0), "bse_code": s.get("bse_code"),
            "quarters": {"labels": s["quarters"]["labels"][-6:], "rows": {k.replace(" +", ""): v[-6:] for k, v in s["quarters"]["rows"].items()}},
            "announcements": [{**a, "date_iso": a["date"]} for a in anns],
        }
    return {"companies": companies, "research": {}, "bars": prices.fetch_yfinance(list(PORTFOLIO)), "promises": {}, "enrichment": {}, "sources": {"snapshot_taken": now.isoformat()}}, eod


def cmd_live(_):
    now = datetime.now(IST)
    raw, eod = collect_live(now)
    payload = process(raw, now, eod, LLM() if available() else None)
    print(f"wrote {write_app(payload)}")


def cmd_research(a):
    from .research import research
    from .sources import screener
    from .util import num

    s = screener.parse(screener.fetch(a.symbol.upper()))
    pl, bs, cf, ra = s["pl"], s["bs"], s["cf"], s["ratios"]
    n = 6

    def rows(tbl, keys):
        return {k: [num(v) for v in tbl["rows"].get(k, tbl["rows"].get(k + " +", []))[-n:]] for k in keys}

    years = [f"FY{l[-2:]}" for l in pl["labels"] if l.startswith("Mar")][-n:]
    c = {
        "name": s["name"], "about": "", "segments": None,
        "top": {"mcap_cr": num(s["top"].get("Market Cap")), "pe": num(s["top"].get("Stock P/E")), "roce": num(s["top"].get("ROCE")), "roe": num(s["top"].get("ROE"))},
        "years": years,
        "pl": rows(pl, ["Sales", "Expenses", "Operating Profit", "Other Income", "Interest", "Depreciation", "Profit before tax", "Net Profit", "Dividend Payout %"]),
        "bs": rows(bs, ["Equity Capital", "Reserves", "Borrowings", "Other Liabilities", "Fixed Assets", "CWIP", "Investments", "Other Assets"]),
        "cf": {"CFO": rows(cf, ["Cash from Operating Activity"])["Cash from Operating Activity"], "FCF": rows(cf, ["Free Cash Flow"])["Free Cash Flow"]},
        "ratios": rows(ra, ["Debtor Days", "Inventory Days", "Days Payable", "Working Capital Days", "ROCE %"]),
    }
    out = research(c)
    out["documents"] = {"transcripts": [x for x in s["concalls"] if x.get("transcript")][:4], "annual_reports": s["annual_reports"][:2]}
    if available() and out["documents"]["transcripts"]:
        from .sources.docs import chunk_transcript, fetch_pdf_text

        llm = LLM()
        statements = []
        for call in out["documents"]["transcripts"]:
            for ch in chunk_transcript(fetch_pdf_text(call["transcript"])):
                statements += [{**x, "call": call["date"]} for x in llm.extract_guidance(s["name"], call["date"], ch)]
        out["guidance_statements"] = statements
        out["llm_spend"] = llm.spend
    json.dump(out, sys.stdout, indent=1, ensure_ascii=False, default=str)


def cmd_notify(a):
    from . import notify
    from .build import ROOT

    payload = json.loads((ROOT / "web" / "data" / "finn.json").read_text())
    sent = notify.send(payload, dry_run=a.dry_run)
    for x in sent:
        print(("WOULD SEND " if a.dry_run else "SENT ") + f"{x['ticker']}: {x['title']} — {x['text']}")
    if not sent:
        print("nothing new")


def main():
    p = argparse.ArgumentParser(prog="finn")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build").set_defaults(fn=cmd_build)
    sub.add_parser("live").set_defaults(fn=cmd_live)
    n = sub.add_parser("notify")
    n.add_argument("--dry-run", action="store_true")
    n.set_defaults(fn=cmd_notify)
    r = sub.add_parser("research")
    r.add_argument("symbol")
    r.set_defaults(fn=cmd_research)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

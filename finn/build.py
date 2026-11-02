"""Raw data → app payload (web/data/finn.json), and the single-file app (dist/index.html).

`process()` is shared by snapshot replays and live runs: connectors only decide where raw data comes from.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path

from . import alerts as A
from .classify import classify_with_fallback, clean_title
from .config import PORTFOLIO, RESEARCH_SET, Thresholds
from .ledger import build_ledger
from .research import research
from .results import results_card
from .sources.prices import load_snapshot_csv
from .util import MONTHS, parse_day_month

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
LLM_OUT = ROOT / "data" / "llm"

_DATE_PATTERNS = [
    re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*,?\s+(\d{4})", re.I),
    re.compile(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2}),?\s+(\d{4})", re.I),
]


def find_event_date(text: str) -> date | None:
    for i, p in enumerate(_DATE_PATTERNS):
        m = p.search(text or "")
        if m:
            d, mon, y = (m.group(1), m.group(2), m.group(3)) if i == 0 else (m.group(2), m.group(1), m.group(3))
            return date(int(y), MONTHS[mon[:3].lower()], int(d))
    return None


def _fid(t: str, url: str) -> str:
    return hashlib.sha1(f"{t}|{url}".encode()).hexdigest()[:10]


def load_json(p: Path, default=None):
    return json.loads(p.read_text()) if p.exists() else default


def triage_filings(companies: dict, year: int, llm=None) -> list[dict]:
    filings = []
    for t, c in companies.items():
        if t.startswith("_"):
            continue
        for a in c.get("announcements", []):
            d = a.get("date_iso") or parse_day_month(a["date"], year).isoformat()
            tr = classify_with_fallback(a["title"], a.get("subtitle", ""), c.get("mcap_cr"), llm)
            filings.append({
                "id": _fid(t, a["url"]), "ticker": t, "date": d, "title": clean_title(a["title"]), "raw_title": a["title"],
                "subtitle": a.get("subtitle", ""), "url": a["url"], **asdict(tr),
            })
    return filings


def cluster(filings: list[dict]) -> list[dict]:
    """Same company, same day, same category → one card with the rest attached (an Eternal results day
    is five filings; the reader needs one)."""
    groups: dict[tuple, list[dict]] = {}
    for f in filings:
        if f["category"] == "results":
            key = (f["ticker"], f["date"], "results-" + ("notice" if f["subtype"] == "date set" else "out"))
        else:
            key = (f["ticker"], f["date"], f["category"] + f["id"])
        groups.setdefault(key, []).append(f)
    out = []
    for g in groups.values():
        g.sort(key=lambda x: -x["score"])
        lead = dict(g[0])
        lead["related"] = [{"title": x["title"], "url": x["url"], "subtype": x["subtype"]} for x in g[1:]]
        out.append(lead)
    return sorted(out, key=lambda x: (x["date"], x["score"]), reverse=True)


def upcoming(filings: list[dict], today: date) -> list[dict]:
    out = {}
    for f in filings:
        if f["category"] in {"results", "earnings_call"} and f["subtype"] in {"date set", "call / transcript", "meeting"}:
            d = find_event_date(f["subtitle"]) or find_event_date(f["raw_title"])
            if d and d >= today:
                what = "Results" if f["category"] == "results" else "Earnings call"
                key = (f["ticker"], what)
                if key not in out or d < date.fromisoformat(out[key]["date"]):
                    out[key] = {"ticker": f["ticker"], "date": d.isoformat(), "what": what, "url": f["url"]}
    return sorted(out.values(), key=lambda x: x["date"])


def process(raw: dict, now: datetime, eod: date, llm=None) -> dict:
    th = Thresholds()
    comp = raw["companies"]
    filings = cluster(triage_filings(comp, now.year, llm))

    one_liners = load_json(LLM_OUT / "one_liners.json", {})
    for f in filings:
        ol = one_liners.get(f["url"])
        if ol:
            f["so_what"] = ol["text"]
            f["so_what_by"] = ol.get("by")
        elif llm is not None and f["tier"] != "low":
            f["so_what"] = llm.one_liner(f["ticker"], f["title"], f["subtitle"])
            f["so_what_by"] = "tier-1 model"

    enrich = raw.get("enrichment", {})
    for f in filings:
        if f["category"] == "management_change":
            for k, e in enrich.items():
                if k.startswith("_") or e["ticker"] != f["ticker"]:
                    continue
                if e.get("effective") == f["date"] or e["incoming"].split()[-1].lower() in (f["subtitle"] + f["title"]).lower():
                    f["person"] = e
    # Automatic path for every other management change: names from the filing text (free), background
    # from a search-grounded model only for senior roles and only when a key is configured.
    from .enrich import enrich_filing
    for f in filings:
        if f["category"] == "management_change" and "person" not in f:
            e = enrich_filing(f, comp.get(f["ticker"], {}).get("name", f["ticker"]), llm)
            if e and (e.get("incoming") or e.get("outgoing")):
                f["person_auto"] = e

    # Results season: every portfolio company whose latest quarter is the one being reported now.
    season_q = max((c["quarters"]["labels"][-1] for t, c in comp.items() if not t.startswith("_")), key=lambda l: (int(l.split()[1]), MONTHS[l[:3].lower()]))
    results = {}
    for t, c in comp.items():
        if t.startswith("_"):
            continue
        card = results_card(c["quarters"], PORTFOLIO.get(t, {}).get("kind", "default"))
        if card:
            card["reported"] = c["quarters"]["labels"][-1] == season_q
            results[t] = card
    for f in filings:
        if f["category"] == "results" and f["subtype"] != "date set" and results.get(f["ticker"], {}).get("reported"):
            f["results_card"] = True

    bars = raw["bars"]
    triggers, health = [], {}
    for t, bs in bars.items():
        triggers += [x.to_dict() for x in A.scan(t, bs, th, eod - timedelta(days=30), eod)]
        st = A.staleness(bs, eod)
        if st:
            health[t] = st
    triggers.sort(key=lambda x: (x["date"], abs(x["move_pct"] or 0)), reverse=True)

    portfolio = []
    for t, meta in PORTFOLIO.items():
        c, bs = comp.get(t, {}), bars.get(t, [])
        last, prev = (bs[-1], bs[-2]) if len(bs) >= 2 else (None, None)
        portfolio.append({
            "ticker": t, "name": c.get("name", t), **meta, "mcap_cr": c.get("mcap_cr"),
            "close": last.close if last else None, "close_date": last.date.isoformat() if last else None,
            "chg": round((last.close - prev.close) / prev.close * 100, 2) if last and prev else None,
            "has_volume": any(b.volume for b in bs),
        })

    research_out = {}
    promises = raw.get("promises", {})
    bull_bear = load_json(LLM_OUT / "bull_bear.json", {})
    current_q = f"Q{((now.month - 4) % 12) // 3 + 1}FY{(now.year + (1 if now.month >= 4 else 0)) % 100:02d}"
    notes = raw.get("filing_notes", {})
    for t in RESEARCH_SET:
        c = raw["research"].get(t)
        if not c:
            continue
        r = research(c, notes.get(t))
        p = promises.get(t, {})
        r["ledger"] = build_ledger(p, current_q) if p.get("promises") else {"items": [], "note": p.get("note")}
        if not p.get("promises"):
            r["signals"].append({"id": "disclosure", "tone": "neg", "text": "No earnings calls — management's forward claims can't be tracked against delivery"})
        r["quarters"] = (comp.get(t) or c).get("quarters")
        r["bull_bear"] = bull_bear.get(t)
        research_out[t] = r

    def bar_rows(bs):
        return [[b.date.isoformat(), b.close, b.volume] for b in bs]

    tiers = {"rules": sum(1 for f in filings if f["via"] == "rules"), "llm": sum(1 for f in filings if f["via"] == "llm"), "none": sum(1 for f in filings if f["via"] == "none")}
    return {
        "generated_at": now.isoformat(), "eod": eod.isoformat(), "season_q": season_q, "current_q": current_q,
        "thresholds": asdict(th), "portfolio": portfolio, "filings": filings, "upcoming": upcoming(filings, now.date()),
        "results": results, "triggers": triggers, "bars": {t: bar_rows(b) for t, b in bars.items()}, "data_health": health,
        "research": research_out, "engine": {"triage": tiers, "llm_spend": getattr(llm, "spend", None)},
        "sources": raw.get("sources", {}), "validation": load_json(ROOT / "data" / "validation.json", []),
    }


def load_snapshot(eod: date) -> dict:
    comp = load_json(RAW / "screener" / "portfolio_2026-10-27.json")
    res = load_json(RAW / "screener" / "research_2026-10-27.json")
    for t, c in res.items():
        if t.startswith("_"):
            continue
        if "quarters" not in c and t in comp:
            c["quarters"] = comp[t]["quarters"]
    return {
        "companies": comp,
        "research": res,
        "bars": load_snapshot_csv(sorted((RAW / "prices").glob("*.csv")), through=eod),
        "promises": load_json(RAW / "transcripts" / "promises.json"),
        "enrichment": load_json(RAW / "enrichment.json", {}),
        "filing_notes": load_json(RAW / "filing_notes.json", {}),
        "sources": load_json(RAW / "sources.json", {}),
    }


def write_app(payload: dict) -> Path:
    web = ROOT / "web"
    (web / "data").mkdir(parents=True, exist_ok=True)
    (web / "data" / "finn.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    template = (web / "app.html").read_text()
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    body = template.replace("/*__FINN_DATA__*/null", blob)
    # Artifact host supplies the document skeleton; GitHub Pages / any static host needs a full document.
    (dist / "artifact.html").write_text(body)
    out = dist / "index.html"
    out.write_text('<!doctype html><html lang="en"><head><meta charset="utf-8">'
                   '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
                   '<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}'
                   'body{margin:0}[hidden]{display:none!important}img{max-width:100%}</style></head><body>'
                   + body + "</body></html>")
    return out

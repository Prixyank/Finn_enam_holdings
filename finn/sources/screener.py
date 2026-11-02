"""screener.in company page → quarterly results, annual statements, ratios, documents, announcements.

Works for any NSE symbol screener covers, which is what lets the pull side take a ticker we never picked.
"""

from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from .exchange import UA

SECTIONS = {"quarters": "quarters", "profit-loss": "pl", "balance-sheet": "bs", "cash-flow": "cf", "ratios": "ratios", "shareholding": "shareholding"}


def fetch(symbol: str, consolidated: bool = True) -> str:
    url = f"https://www.screener.in/company/{symbol}/{'consolidated/' if consolidated else ''}"
    r = requests.get(url, headers={**UA, "Accept": "text/html"}, timeout=20)
    if r.status_code == 404 and consolidated:
        return fetch(symbol, consolidated=False)
    r.raise_for_status()
    return r.text


def _label(td) -> str:
    return re.sub(r"\s*\+\s*$", "", td.get_text(" ", strip=True).replace("\xa0", " ")).strip()


def parse_table(section) -> dict | None:
    table = section.select_one("table.data-table") if section else None
    if table is None:
        return None
    labels = [th.get_text(strip=True) for th in table.select("thead th")][1:]
    rows = {}
    for tr in table.select("tbody tr"):
        tds = tr.find_all("td")
        if not tds:
            continue
        name = _label(tds[0])
        if not name or name.lower().startswith("raw pdf"):
            continue
        rows[name] = [td.get_text(strip=True) for td in tds[1:]]
    return {"labels": labels, "rows": rows}


def parse(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    out: dict = {"name": (soup.select_one("h1").get_text(strip=True) if soup.select_one("h1") else None)}
    m = re.search(r'data-company-id="(\d+)"', html)
    out["company_id"] = m.group(1) if m else None
    m = re.search(r"bseindia\.com/stock-share-price/[^\"]*/(\d{6})", html)
    out["bse_code"] = m.group(1) if m else None

    top = {}
    for li in soup.select("#top-ratios li"):
        name, val = li.select_one(".name"), li.select_one(".number")
        if name and val:
            top[name.get_text(strip=True)] = val.get_text(strip=True).replace(",", "")
    out["top"] = top

    for sec_id, key in SECTIONS.items():
        out[key] = parse_table(soup.select_one(f"section#{sec_id}"))

    docs = soup.select_one("section#documents")
    out["annual_reports"] = [{"label": a.get_text(" ", strip=True), "url": a["href"]} for a in (docs.select(".annual-reports a[href]") if docs else [])]
    calls = []
    for li in (docs.select(".concalls li") if docs else []):
        when = li.select_one("div")
        links = {a.get_text(strip=True).lower(): a["href"] for a in li.select("a[href]")}
        calls.append({"date": when.get_text(strip=True) if when else None, "transcript": links.get("transcript"), "ppt": links.get("ppt")})
    out["concalls"] = calls

    ann = []
    for a in soup.select("#company-announcements a[href], section#documents .announcements a[href]"):
        text = a.get_text(" ", strip=True)
        sub = a.find_next(class_=re.compile("smaller|ink-600"))
        ann.append({"title": text, "subtitle": sub.get_text(" ", strip=True) if sub else "", "url": a["href"]})
    out["announcements"] = ann
    return out

"""Corporate announcements from NSE (primary) with BSE as fallback."""

from __future__ import annotations

from datetime import date, datetime

import requests

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 Chrome/126 Safari/537.36",
      "Accept": "application/json, text/plain, */*", "Accept-Language": "en-IN,en;q=0.9"}


class NSE:
    """NSE's JSON API needs the cookies its homepage sets; one warm-up GET per session."""

    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({**UA, "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements"})
        self.s.get("https://www.nseindia.com", timeout=15)

    def announcements(self, symbol: str, start: date, end: date) -> list[dict]:
        r = self.s.get("https://www.nseindia.com/api/corporate-announcements", timeout=20,
                       params={"index": "equities", "symbol": symbol, "from_date": start.strftime("%d-%m-%Y"), "to_date": end.strftime("%d-%m-%Y")})
        r.raise_for_status()
        rows = r.json()
        rows = rows.get("data", rows) if isinstance(rows, dict) else rows
        return [{
            "ticker": symbol,
            "datetime": datetime.strptime(x["an_dt"], "%d-%b-%Y %H:%M:%S").isoformat(),
            "date": datetime.strptime(x["an_dt"], "%d-%b-%Y %H:%M:%S").date().isoformat(),
            "title": x.get("desc", ""),
            "subtitle": (x.get("attchmntText") or "").strip(),
            "url": x.get("attchmntFile"),
            "source": "NSE",
        } for x in rows]


def bse_announcements(scrip_code: str, ticker: str, start: date, end: date) -> list[dict]:
    r = requests.get("https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w", timeout=20,
                     headers={**UA, "Referer": "https://www.bseindia.com/", "Origin": "https://www.bseindia.com"},
                     params={"pageno": 1, "strCat": -1, "strPrevDate": start.strftime("%Y%m%d"), "strScrip": scrip_code,
                             "strSearch": "P", "strToDate": end.strftime("%Y%m%d"), "strType": "C", "subcategory": -1})
    r.raise_for_status()
    out = []
    for x in r.json().get("Table", []):
        dt = datetime.fromisoformat(x["NEWS_DT"].split(".")[0])
        out.append({"ticker": ticker, "datetime": dt.isoformat(), "date": dt.date().isoformat(),
                    "title": x.get("NEWSSUB") or x.get("HEADLINE", ""), "subtitle": (x.get("HEADLINE") or "").strip(),
                    "url": f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{x['ATTACHMENTNAME']}" if x.get("ATTACHMENTNAME") else None,
                    "source": "BSE"})
    return out


def announcements(symbol: str, bse_code: str | None, start: date, end: date, nse: NSE | None = None) -> list[dict]:
    try:
        return (nse or NSE()).announcements(symbol, start, end)
    except Exception:
        if not bse_code:
            raise
        return bse_announcements(bse_code, symbol, start, end)

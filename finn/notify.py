"""Push delivery: send what crossed the user's rules to Telegram and/or email, once.

Run after each refresh (`python -m finn notify`). A state file remembers what was already sent,
so a filing or a price breach interrupts you exactly once however often the job runs.

Channels are configured by environment variables:
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
  SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASSWORD, ALERT_EMAIL_TO
  FINN_APP_URL (optional link back to the app)
"""

from __future__ import annotations

import html
import json
import os
import smtplib
from datetime import date, timedelta
from email.message import EmailMessage
from pathlib import Path

import requests

STATE = Path(os.getenv("FINN_STATE", Path.home() / ".cache" / "finn" / "sent.json"))
CAT = {"management_change": "Management change", "results": "Results", "M&A": "M&A", "litigation": "Legal",
       "credit_rating": "Credit rating", "fund_raise": "Fund raise", "insider_trading": "Large-holder trade"}


def due_alerts(payload: dict, th: dict | None = None, lookback_days: int = 2) -> list[dict]:
    """Everything that crosses the rules: material filings in the last `lookback_days`, and EOD
    breaches on the latest session. Each gets a stable key for de-duplication."""
    th = th or payload["thresholds"]
    now = date.fromisoformat(payload["generated_at"][:10])
    since = (now - timedelta(days=lookback_days)).isoformat()
    out = []
    for f in payload["filings"]:
        if f["date"] >= since and f["score"] >= th["materiality_floor"] and f["category"] in th["alert_categories"]:
            out.append({"key": "f:" + f["id"], "kind": "filing", "ticker": f["ticker"], "date": f["date"],
                        "title": CAT.get(f["category"], f["category"]), "text": f.get("so_what") or f.get("subtitle") or f["title"],
                        "url": f["url"], "score": f["score"], "person": f.get("person")})
    for t in payload["triggers"]:
        if t["date"] == payload["eod"]:
            what = f"{'+' if (t['move_pct'] or 0) > 0 else ''}{t['move_pct']}%" + (f" on {t['vol_ratio']}× usual volume" if t["vol_ratio"] else "")
            out.append({"key": f"t:{t['ticker']}:{t['date']}", "kind": "move", "ticker": t["ticker"], "date": t["date"],
                        "title": "Unusual move", "text": f"Closed ₹{t['close']:,.2f} ({what})", "url": None, "score": 0})
    return sorted(out, key=lambda x: (x["kind"] != "filing", -x["score"]))


def load_state() -> set[str]:
    try:
        return set(json.loads(STATE.read_text()))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_state(sent: set[str]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(sorted(sent)[-2000:]))


def render_telegram(a: dict, app_url: str | None) -> str:
    lines = [f"<b>{html.escape(a['ticker'])}</b> · {html.escape(a['title'])}", html.escape(a["text"])]
    p = a.get("person")
    if p and p.get("background"):
        lines.append(f"<i>{html.escape(p['incoming'])}</i>: " + html.escape("; ".join(p["background"][-2:])))
    links = []
    if a.get("url"):
        links.append(f'<a href="{html.escape(a["url"])}">Filing</a>')
    if app_url:
        links.append(f'<a href="{html.escape(app_url)}">FINN</a>')
    if links:
        lines.append(" · ".join(links))
    return "\n".join(lines)


def render_email(alerts: list[dict], app_url: str | None) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = f"FINN: {len(alerts)} item{'s' if len(alerts) != 1 else ''} need you — " + ", ".join(dict.fromkeys(a["ticker"] for a in alerts))
    body = []
    for a in alerts:
        body.append(f"{a['ticker']} · {a['title']}\n{a['text']}" + (f"\n{a['url']}" if a.get("url") else ""))
    if app_url:
        body.append(f"Open FINN: {app_url}")
    msg.set_content("\n\n".join(body))
    return msg


def send(payload: dict, dry_run: bool = False) -> list[dict]:
    sent = load_state()
    new = [a for a in due_alerts(payload) if a["key"] not in sent]
    app_url = os.getenv("FINN_APP_URL")
    if dry_run or not new:
        return new
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if tok and chat:
        for a in new:
            requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=20,
                          json={"chat_id": chat, "text": render_telegram(a, app_url), "parse_mode": "HTML", "disable_web_page_preview": True}).raise_for_status()
    if os.getenv("SMTP_HOST") and os.getenv("ALERT_EMAIL_TO"):
        msg = render_email(new, app_url)
        msg["From"], msg["To"] = os.getenv("SMTP_USER", "finn@localhost"), os.environ["ALERT_EMAIL_TO"]
        with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", "587"))) as s:
            s.starttls()
            if os.getenv("SMTP_USER"):
                s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            s.send_message(msg)
    save_state(sent | {a["key"] for a in new})
    return new

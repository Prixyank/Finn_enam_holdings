"""Push alerts on the real snapshot: what would be sent, and that nothing is sent twice."""

import os
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from finn import notify
from finn.build import load_snapshot, process

IST = timezone(timedelta(hours=5, minutes=30))
PAYLOAD = process(load_snapshot(date(2026, 10, 26)), datetime(2026, 10, 27, 12, 35, tzinfo=IST), date(2026, 10, 26))


def test_due_alerts_on_snapshot():
    keys = {a["ticker"]: a for a in notify.due_alerts(PAYLOAD)}
    assert set(keys) == {"HDFCBANK", "POLYCAB"}  # CEO change today, +4% close; the 24-Oct Jio filing went out on an earlier run
    assert keys["HDFCBANK"]["kind"] == "filing" and keys["POLYCAB"]["kind"] == "move"


def test_render_is_escaped_and_carries_links():
    a = next(x for x in notify.due_alerts(PAYLOAD) if x["ticker"] == "HDFCBANK")
    t = notify.render_telegram(a, "https://example.test/finn")
    assert t.startswith("<b>HDFCBANK</b>") and 'href="https://www.bseindia.com' in t and "Anup Bagchi" in t
    m = notify.render_email(notify.due_alerts(PAYLOAD), None)
    assert m["Subject"].startswith("FINN: 2 items need you")


def test_sends_once():
    with tempfile.TemporaryDirectory() as d:
        notify.STATE = Path(d) / "sent.json"
        for k in ("TELEGRAM_BOT_TOKEN", "SMTP_HOST"):
            os.environ.pop(k, None)
        first = notify.send(PAYLOAD)          # no channels configured: records as handled
        again = notify.send(PAYLOAD)
        assert len(first) == 2 and again == []

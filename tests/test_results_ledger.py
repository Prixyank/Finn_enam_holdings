import json
from pathlib import Path

from finn.ledger import build_ledger, score
from finn.results import results_card
from finn.util import amounts_in_crore, fy_quarter, quarter_index

ROOT = Path(__file__).resolve().parent.parent
PORT = json.loads((ROOT / "data/raw/screener/portfolio_2026-10-27.json").read_text())
PROM = json.loads((ROOT / "data/raw/transcripts/promises.json").read_text())


def line(card, name):
    return next(l for l in card["lines"] if l["name"] == name)


def test_tcs_q2_card_math():
    c = results_card(PORT["TCS"]["quarters"])
    assert c["fq"] == "Q2FY27" and c["vs_q"] == "Jun 2026" and c["vs_y"] == "Sep 2025"
    rev = line(c, "Revenue")
    assert (rev["value"], rev["qoq"], rev["yoy"]) == (73188, 1.3, 11.2)
    assert line(c, "PAT")["yoy"] == 14.9
    assert c["margin"]["bps_yoy"] == -160


def test_bank_card_does_not_invent_ebitda_or_misflag_other_income():
    c = results_card(PORT["HDFCBANK"]["quarters"], "bank")
    assert line(c, "EBITDA")["value"] is None
    assert not any("Other income" in f for f in c["flags"])


def test_eternal_flags_treasury_income():
    c = results_card(PORT["ETERNAL"]["quarters"])
    assert any("Other income is 109% of PBT" in f for f in c["flags"])


def test_quarter_helpers():
    assert fy_quarter("Sep 2026") == "Q2FY27" and fy_quarter("Mar 2026") == "Q4FY26" and fy_quarter("Dec 2025") == "Q3FY26"
    assert quarter_index("Q3FY27") - quarter_index("Q4FY26") == 3


def test_amount_parsing():
    assert amounts_in_crore("allotted ₹7,816 crore NCDs") == [7816]
    assert amounts_in_crore("positive tax impact of about Rs. 130,000 million") == [13000]
    assert amounts_in_crore("issue price fixed at ₹1,119") == []
    assert amounts_in_crore("a US$7 million guarantee") == [61.6]
    assert amounts_in_crore("₹1 lakh crore of sales") == [100000]


def by_id(company):
    return {p["id"]: p for p in PROM[company]["promises"]}


def test_dixon_ledger_statuses():
    P = by_id("DIXON")
    assert score(P["D1"], "Q3FY27")["status"] == "missed" and score(P["D1"], "Q3FY27")["gap_pct"] == -17.5
    assert score(P["D3"], "Q3FY27")["status"] == "met"
    s5 = score(P["D5"], "Q3FY27")
    assert s5["status"] == "slipped" and s5["slip_q"] == 3 and "due this quarter" in s5["detail"]
    s8 = score(P["D8"], "Q3FY27")
    assert s8["status"] == "delivered late" and s8["slip_q"] == 3
    assert score(P["D10"], "Q3FY27")["status"] == "walked back"
    assert score(P["D12"], "Q3FY27")["status"] == "met"  # ₹1,058 cr vs ₹1,100 cr floor is inside the 5% grace
    assert score(P["D13"], "Q3FY27")["status"] == "missed"
    assert score(P["D14"], "Q3FY27")["status"] == "ahead"
    assert score(P["D16"], "Q3FY27")["status"] == "open"


def test_timeline_becomes_overdue_when_quarter_passes():
    assert "now overdue" in score(by_id("DIXON")["D7"], "Q4FY27")["detail"]


def test_dixon_pattern_line():
    L = build_ledger(PROM["DIXON"], "Q3FY27")
    assert L["headline"].startswith("5/8 hard numbers kept · 0/4 dates kept")
    assert L["pattern"].startswith("Delivers on the numbers it controls")


def test_tcs_ledger():
    L = build_ledger(PROM["TCS"], "Q3FY27")
    st = {i["id"]: i["status"] for i in L["items"]}
    assert st == {"T1": "met", "T2": "walked back", "T3": "marginal", "T4": "delivered", "T5": "marginal", "T6": "delivered", "T7": "met", "T8": "delivered"}
    assert len(L["calls"]) == 4 and L["pattern"].startswith("Keeps its few hard commitments")

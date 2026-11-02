"""Parser test against a small HTML fixture that mirrors screener.in's markup.
The fixture is hand-written (the build sandbox could not reach screener directly), so this
pins the parsing logic, not screener's live markup — see README 'What is and isn't verified'."""

from pathlib import Path

from finn.sources.screener import parse

FIX = Path(__file__).parent / "fixtures" / "screener_tcs.html"


def test_parse_quarters_and_documents():
    d = parse(FIX.read_text())
    assert d["company_id"] == "3365" and d["bse_code"] == "532540"
    assert d["quarters"]["labels"] == ["Jun 2026", "Sep 2026"]
    assert d["quarters"]["rows"]["Sales"] == ["72,275", "73,188"]
    assert "Raw PDF" not in d["quarters"]["rows"]
    assert d["top"]["Market Cap"] == "905444"
    assert d["concalls"][0]["transcript"].endswith(".pdf")
    assert d["annual_reports"][0]["label"].startswith("Financial Year 2026")

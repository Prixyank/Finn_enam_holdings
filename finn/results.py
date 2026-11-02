"""First cut of a results filing: Revenue, EBITDA, PBT, PAT — QoQ and YoY — plus what to look at.

Sector-aware: for banks EBITDA is not meaningful and is labelled so instead of
printing a misleading number; for NBFCs the operating line is financing profit.
"""

from __future__ import annotations

from .util import fy_quarter, num, pct

LINES = {
    "default": [("Revenue", "Sales"), ("EBITDA", "Operating Profit"), ("PBT", "Profit before tax"), ("PAT", "Net Profit")],
    "nbfc": [("Revenue", "Revenue"), ("Financing profit", "Financing Profit"), ("PBT", "Profit before tax"), ("PAT", "Net Profit")],
    "bank": [("Revenue", "Revenue"), ("EBITDA", None), ("PBT", "Profit before tax"), ("PAT", "Net Profit")],
}

NOTES = {
    "EBITDA": "Operating profit before other income (screener definition).",
    "PAT": "Consolidated, before minority interest; the company's 'attributable' PAT can be slightly lower.",
    "Financing profit": "Revenue less interest and operating costs incl. provisions.",
}


def results_card(quarters: dict, kind: str = "default") -> dict | None:
    """Card for the latest quarter in a screener-style quarterly table."""
    labels, rows = quarters["labels"], quarters["rows"]
    if len(labels) < 5:
        return None
    i, q, y = len(labels) - 1, len(labels) - 2, len(labels) - 5
    lines = []
    for name, key in LINES.get(kind, LINES["default"]):
        if key is None:
            lines.append({"name": name, "value": None, "na": "not meaningful for banks"})
            continue
        series = [num(v) for v in rows.get(key, [])]
        if len(series) != len(labels):
            continue
        cur, prev, yago = series[i], series[q], series[y]
        lines.append({"name": name, "value": cur, "prev": prev, "yago": yago, "qoq": pct(cur, prev), "yoy": pct(cur, yago), "note": NOTES.get(name)})

    card = {"quarter": labels[i], "fq": fy_quarter(labels[i]), "vs_q": labels[q], "vs_y": labels[y], "lines": lines, "flags": []}
    sales = [num(v) for v in rows.get("Sales", rows.get("Revenue", []))]
    op = [num(v) for v in rows.get("Operating Profit", [])]
    other = [num(v) for v in rows.get("Other Income", [])]
    pbt = [num(v) for v in rows.get("Profit before tax", [])]
    tax = [num(v) for v in rows.get("Tax %", [])]

    if kind == "default" and op and sales:
        m_now, m_y, m_q = (round(op[k] / sales[k] * 100, 1) for k in (i, y, q))
        card["margin"] = {"now": m_now, "prev": m_q, "yago": m_y, "bps_yoy": round((m_now - m_y) * 100), "bps_qoq": round((m_now - m_q) * 100)}
        if abs(m_now - m_y) >= 1.0:
            card["flags"].append(f"EBITDA margin {m_now}% vs {m_y}% a year ago ({'+' if m_now > m_y else ''}{round((m_now - m_y) * 100)} bps)")
    if kind == "default" and other and pbt and pbt[i]:  # fee/treasury income is core business for lenders
        share = other[i] / pbt[i] * 100
        if share >= 25:
            card["flags"].append(f"Other income is {share:.0f}% of PBT — check what is one-off")
    if tax and tax[i] is not None and tax[y] is not None and abs(tax[i] - tax[y]) >= 8:
        card["flags"].append(f"Tax rate {tax[i]:.0f}% vs {tax[y]:.0f}% a year ago — PAT growth distorted")
    rev = next((l for l in lines if l["name"] == "Revenue"), None)
    pat = next((l for l in lines if l["name"] == "PAT"), None)
    if rev and pat and rev.get("yoy") is not None and pat.get("yoy") is not None and abs(pat["yoy"] - rev["yoy"]) >= 15:
        card["flags"].append(f"PAT {pat['yoy']:+.0f}% YoY vs revenue {rev['yoy']:+.0f}% — the gap is the story")
    return card

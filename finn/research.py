"""Pull-side research view, computed from primary-source financials.

Every number here is arithmetic on the company's reported statements (via screener's
standardised tables of the annual reports / results). The model is only used afterwards,
to write bull/bear bullets that must cite the fact ids produced below.
"""

from __future__ import annotations

from .util import num


def cagr(a: float | None, b: float | None, years: int) -> float | None:
    if not a or not b or a <= 0 or b <= 0 or years <= 0:
        return None
    return round(((b / a) ** (1 / years) - 1) * 100, 1)


def _s(d: dict, k: str) -> list[float | None]:
    return [num(v) for v in d.get(k, [])]


def snapshot(c: dict) -> dict:
    pl, top, ttm = c["pl"], c["top"], c.get("ttm", {})
    sales, op, np_ = _s(pl, "Sales"), _s(pl, "Operating Profit"), _s(pl, "Net Profit")
    eq = [a + b for a, b in zip(_s(c["bs"], "Equity Capital"), _s(c["bs"], "Reserves"))]
    debt = _s(c["bs"], "Borrowings")
    rev = ttm.get("Sales", sales[-1])
    return {
        "revenue_ttm": rev,
        "opm_ttm": round(ttm.get("Operating Profit", op[-1]) / rev * 100, 1),
        "pat_ttm": ttm.get("Net Profit", np_[-1]),
        "pat_margin_ttm": round(ttm.get("Net Profit", np_[-1]) / rev * 100, 1),
        "roce": top.get("roce"), "roe": top.get("roe"), "pe": top.get("pe"),
        "mcap_cr": top.get("mcap_cr"), "div_yield": top.get("div_yield"),
        "de": round(debt[-1] / eq[-1], 2) if eq[-1] else None,
    }


def trajectory(c: dict) -> dict:
    pl, years = c["pl"], c["years"]
    n = len(years) - 1
    lines = {}
    for k in ("Sales", "Operating Profit", "Net Profit", "Depreciation", "Interest", "Other Income"):
        s = _s(pl, k)
        if s:
            lines[k] = {"series": s, "cagr": cagr(s[0], s[-1], n), "cagr3": cagr(s[-4], s[-1], 3) if len(s) >= 4 else None, "last_yoy": round((s[-1] - s[-2]) / abs(s[-2]) * 100, 1) if s[-2] else None}
    sales, op = _s(pl, "Sales"), _s(pl, "Operating Profit")
    opm = [round(o / s * 100, 1) if s else None for o, s in zip(op, sales)]
    growing = [k for k, v in lines.items() if k in {"Sales", "Operating Profit", "Net Profit"} and (v["cagr3"] or 0) >= 12]
    slowing = [k for k, v in lines.items() if k in {"Sales", "Operating Profit", "Net Profit"} and v["last_yoy"] is not None and v["cagr3"] and v["last_yoy"] < v["cagr3"] / 2]
    return {"years": years, "lines": lines, "opm": opm, "opm_change_bps": round((opm[-1] - opm[0]) * 100), "growing": growing, "slowing": slowing}


def balance_sheet(c: dict) -> dict:
    bs, r, years = c["bs"], c["ratios"], c["years"]
    eq = [a + b for a, b in zip(_s(bs, "Equity Capital"), _s(bs, "Reserves"))]
    debt = _s(bs, "Borrowings")
    fa = [a + (b or 0) for a, b in zip(_s(bs, "Fixed Assets"), _s(bs, "CWIP"))]
    sales = _s(c["pl"], "Sales")
    return {
        "years": years,
        "equity": eq, "debt": debt,
        "de": [round(d / e, 2) if e else None for d, e in zip(debt, eq)],
        "asset_turn": [round(s / f, 1) if f else None for s, f in zip(sales, fa)],
        "fixed_assets": fa,
        "debtor_days": _s(r, "Debtor Days"), "inventory_days": _s(r, "Inventory Days"),
        "payable_days": _s(r, "Days Payable"), "wc_days": _s(r, "Working Capital Days"),
        "roce": _s(r, "ROCE %"),
    }


def cash_quality(c: dict) -> dict:
    cf, pl, years = c["cf"], c["pl"], c["years"]
    cfo, fcf = _s(cf, "CFO"), _s(cf, "FCF")
    op, np_ = _s(pl, "Operating Profit"), _s(pl, "Net Profit")
    conv = [round(a / b * 100) if b and b > 0 else None for a, b in zip(cfo, op)]
    cum_cfo, cum_pat, cum_fcf = sum(x for x in cfo if x), sum(x for x in np_ if x), sum(x for x in fcf if x)
    return {
        "years": years, "cfo": cfo, "fcf": fcf, "cfo_to_ebitda": conv,
        "cum_cfo_to_pat": round(cum_cfo / cum_pat * 100) if cum_pat > 0 else None,
        "cum_fcf_to_pat": round(cum_fcf / cum_pat * 100) if cum_pat > 0 else None,
        "verdict": "strong" if cum_pat > 0 and cum_cfo / cum_pat >= 1.0 else "adequate" if cum_pat > 0 and cum_cfo / cum_pat >= 0.7 else "weak",
    }


def signals(c: dict, traj: dict, bs: dict, cash: dict) -> list[dict]:
    """Deterministic observations an analyst would want flagged. Each gets an id the bull/bear bullets cite."""
    out: list[dict] = []
    pl, ttm = c["pl"], c.get("ttm", {})

    def add(sid, tone, text):
        out.append({"id": sid, "tone": tone, "text": text})

    s = traj["lines"]["Sales"]
    add("growth", "pos" if (s["cagr"] or 0) >= 15 else "neutral", f"Revenue {s['cagr']}% CAGR over {len(c['years']) - 1} yrs; last year {s['last_yoy']:+}%")
    add("margin", "pos" if traj["opm_change_bps"] > 100 else "neg" if traj["opm_change_bps"] < -100 else "neutral",
        f"Operating margin {traj['opm'][0]}% → {traj['opm'][-1]}% ({traj['opm_change_bps']:+} bps)")
    oi = ttm.get("Other Income")
    pbt_ttm = None
    pbt = _s(pl, "Profit before tax")
    if oi is not None and ttm.get("Net Profit"):
        pbt_ttm = ttm.get("Profit before tax")
    oi_last, pbt_last = _s(pl, "Other Income")[-1], pbt[-1]
    oi_v, pbt_v = (oi, pbt_ttm) if (oi is not None and pbt_ttm) else (oi_last, pbt_last)
    if oi_v is not None and pbt_v:
        share = oi_v / pbt_v * 100
        if share >= 25:
            add("other_income", "neg", f"Other income is {share:.0f}% of PBT — profit growth leans on non-operating items")
        elif oi_v < 0:
            add("other_income", "neg", f"Other income turned negative (₹{oi_v:,.0f} cr) — investigate treasury/forex losses")
    dd = [x for x in bs["debtor_days"] if x is not None]
    if len(dd) >= 3 and dd[-1] - dd[0] >= 15:
        add("receivables", "neg", f"Debtor days up {dd[0]:.0f} → {dd[-1]:.0f} — customers paying slower")
    wc = [x for x in bs["wc_days"] if x is not None]
    if wc and wc[-1] <= 0:
        add("wc", "pos", f"Negative working capital ({wc[-1]:.0f} days) — suppliers fund the growth")
    de = bs["de"][-1]
    add("leverage", "pos" if de is not None and de < 0.3 else "neg" if de and de > 1 else "neutral", f"Debt/equity {de}")
    fa = bs["fixed_assets"]
    if fa[-2] and (fa[-1] - fa[-2]) / fa[-2] >= 0.3:
        add("capex", "neutral", f"Fixed assets +{(fa[-1] - fa[-2]) / fa[-2] * 100:.0f}% in a year — capacity build ahead of revenue")
    add("cash", "pos" if cash["verdict"] == "strong" else "neg" if cash["verdict"] == "weak" else "neutral",
        f"{cash['cum_cfo_to_pat']}% of {len(c['years'])}-yr profit came in as operating cash; FCF {cash['cum_fcf_to_pat']}% of PAT")
    dep = traj["lines"].get("Depreciation")
    if dep and dep["last_yoy"] and dep["last_yoy"] >= 30:
        add("depreciation", "neutral", f"Depreciation +{dep['last_yoy']:.0f}% last year — new capacity/stores now in the P&L")
    payout = _s(pl, "Dividend Payout %")
    if payout and payout[-1] and payout[-1] >= 60:
        add("payout", "pos", f"Pays out {payout[-1]:.0f}% of profit as dividend")
    roce = [x for x in bs["roce"] if x is not None]
    if len(roce) >= 2 and roce[-1] < max(roce) - 5:
        add("returns", "neg", f"ROCE {roce[-1]:.0f}%, down from a {max(roce):.0f}% peak")
    pe = c.get("top", {}).get("pe")
    if pe:
        add("valuation", "neg" if pe >= 50 else "neutral", f"Trades at {pe}× trailing earnings")
    return out


def filing_checks(notes: dict | None, c: dict) -> tuple[dict | None, list[dict]]:
    """Auditor remarks, related-party approvals and contingent liabilities, sized against the balance sheet."""
    if not notes:
        return None, []
    sig: list[dict] = []
    eq = notes.get("equity_cr") or (lambda e: e[-1])([a + b for a, b in zip(_s(c["bs"], "Equity Capital"), _s(c["bs"], "Reserves"))])
    aud = notes.get("auditor") or {}
    for a in aud.get("attention", []):
        amt = a.get("amount_cr")
        if amt:
            a["pct_equity"] = round(amt / eq * 100, 1)
            net = amt - (a.get("offset_cr") or 0)
            a["net_pct_equity"] = round(net / eq * 100, 1)
            sig.append({"id": "audit", "tone": "neg", "text": f"Auditor draws attention to {a['topic']} of ₹{amt:,.0f} cr — {a['pct_equity']}% of net worth (net {a['net_pct_equity']}%) — still awaiting determination"})
    un = aud.get("unreviewed")
    if un and (un.get("revenue_share_pct") or 0) >= 10:
        sig.append({"id": "unreviewed", "tone": "neutral", "text": f"{un['revenue_share_pct']:.0f}% of quarterly revenue sits in {un['count']} subsidiaries the auditor did not review"})
    if aud.get("opinion") and aud["opinion"] != "unmodified":
        sig.append({"id": "audit_opinion", "tone": "neg", "text": f"Auditor's conclusion is {aud['opinion']}"})
    for r in (notes.get("rpt_approvals") or {}).get("items", []):
        x = round(r["limit_cr_per_year"] / r["last_year_actual_cr"], 1) if r.get("last_year_actual_cr") else None
        r["headroom_x"] = x
        sig.append({"id": "rpt", "tone": "neutral", "text": f"Seeks approval for up to ₹{r['limit_cr_per_year']:,.0f} cr a year of sales to {r['counterparty']} — {r['pct_of_turnover']}% of turnover" + (f", {x}× last year's ₹{r['last_year_actual_cr']:,.0f} cr" if x else "")})
    return notes, sig


def research(c: dict, notes: dict | None = None) -> dict:
    traj, bs, cash = trajectory(c), balance_sheet(c), cash_quality(c)
    checks, extra = filing_checks(notes, c)
    return {
        "name": c["name"], "about": c["about"], "segments": c.get("segments"),
        "snapshot": snapshot(c), "trajectory": traj, "balance_sheet": bs, "cash": cash,
        "signals": signals(c, traj, bs, cash) + extra, "shareholding": c.get("shareholding"), "filing_checks": checks,
    }

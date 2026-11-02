"""Promise ledger: what management said vs what then happened.

The model's job ends at *extraction* (turning a transcript into dated, structured statements).
Scoring is plain arithmetic here, so a status like "slipped 3 quarters" is reproducible and
testable rather than a model's opinion.
"""

from __future__ import annotations

from .util import quarter_index

TOL = 0.05  # 5% grace on numeric targets


def _mid(s: dict) -> float | None:
    lo, hi = s.get("lo"), s.get("hi")
    if lo is None and hi is None:
        return None
    if lo is None or hi is None:
        return lo if hi is None else hi
    return (lo + hi) / 2


def fmt(v: float, unit: str) -> str:
    if unit == "₹ cr":
        return f"₹{v:,.0f} cr"
    if unit.startswith("%"):
        return f"{v:g}%{unit[1:]}"
    if unit == "$ bn":
        return f"${v:g} bn"
    n = f"{v:,.0f}" if abs(v) >= 1000 else f"{v:g}"
    return f"{n} {unit}".strip()


def _range(s: dict, unit: str) -> str:
    lo, hi = s.get("lo"), s.get("hi")
    if lo is not None and hi is not None and lo != hi:
        # share the unit across the range: '₹7,500–8,000 cr', '2.8–3.1%', '40–42 mn units'
        n = lambda v: f"{v:,.0f}" if abs(v) >= 1000 else f"{v:g}"
        if unit == "₹ cr":
            return f"₹{n(lo)}–{n(hi)} cr"
        if unit == "%":
            return f"{n(lo)}–{n(hi)}%"
        if unit == "$ bn":
            return f"${n(lo)}–{n(hi)} bn"
        return f"{n(lo)}–{n(hi)} {unit}".strip()
    if lo is not None and hi is None:
        return "≥" + fmt(lo, unit)
    v = lo if lo is not None else hi
    return fmt(v, unit) if v is not None else s.get("text", "—")


def score(p: dict, current_q: str) -> dict:
    kind, unit, said = p["kind"], p.get("unit", ""), p["said"]
    first, last = said[0], said[-1]
    out = {"status": "open", "detail": "", "gap_pct": None, "slip_q": None}

    if kind == "numeric":
        a = p.get("actual")
        if not a:
            out["detail"] = f"Target {_range(first, unit)} — check on {p.get('check_on', 'next results')}"
            return out
        v, lo, hi = a["value"], first.get("lo"), first.get("hi")
        if lo is not None and v < lo * (1 - TOL):
            out.update(status="missed", gap_pct=round((v - lo) / lo * 100, 1))
        elif hi is not None and v > hi * (1 + TOL):
            out.update(status="beat", gap_pct=round((v - hi) / hi * 100, 1))
        else:
            out["status"] = "met"
        out["detail"] = f"Said {_range(first, unit)} · got {fmt(v, unit)}"
        if len(said) > 1 and _mid(last) is not None and _mid(first):
            change = (_mid(last) - _mid(first)) / _mid(first) * 100
            if abs(change) >= 5:
                out["detail"] += f" · target {'raised' if change > 0 else 'cut'} to {_range(last, unit)} along the way"

    elif kind == "runrate":
        a = p["actual"]
        target = last.get("lo") or last.get("hi")
        share = p.get("prior_year_share") or a.get("prior_year_share")
        annual = a["value"] / share if share else a["value"] / a["periods_elapsed"] * a["periods_total"]
        gap = (annual - target) / target * 100
        out.update(status="ahead" if gap > TOL * 100 else "behind" if gap < -TOL * 100 else "on track", gap_pct=round(gap, 1))
        basis = "seasonality-adjusted" if share else "straight-line"
        out["detail"] = f"Target {_range(last, unit)} · tracking ≈{fmt(annual, unit)} ({basis})"

    elif kind == "restated":
        m0, m1 = _mid(first), _mid(last)
        if m0 is not None and m1 is not None:
            change = (m1 - m0) / m0 * 100
            out["gap_pct"] = round(change, 1)
            out["status"] = "walked back" if change <= -5 else "raised" if change >= 5 else "reiterated"
            out["detail"] = f"{_range(first, unit)} → {_range(last, unit)}"
        else:
            out["status"] = "walked back" if p.get("direction") == "down" else "reiterated"
            out["detail"] = f"{first.get('text', _range(first, unit))} → {last.get('text', _range(last, unit))}"
        if first.get("note") and last.get("note") and first["note"] != last["note"]:
            out["detail"] += f" (basis changed: {first['note']} → {last['note']})"

    elif kind == "timeline":
        q0, q1 = first["due"], last["due"]
        slip = quarter_index(q1) - quarter_index(q0)
        out["slip_q"] = slip
        done = p.get("delivered")
        if done:
            late = quarter_index(done["on"]) - quarter_index(q0)
            out["status"] = "delivered late" if late > 0 else "delivered"
            out["slip_q"] = late
            out["detail"] = f"First promised {q0} · happened {done['on']}" + (f" ({late} qtr{'s' if late != 1 else ''} late)" if late > 0 else "")
        else:
            out["status"] = "slipped" if slip > 0 else "on schedule"
            overdue = quarter_index(current_q) > quarter_index(q1)
            due_now = quarter_index(current_q) == quarter_index(q1)
            out["detail"] = f"{q0} → {q1}" + (f" · slipped {slip} qtr{'s' if slip != 1 else ''}" if slip else "") + (" · now overdue" if overdue else " · due this quarter" if due_now else "")

    elif kind == "direction":
        a = p["actual"]
        delta = a["value"] - p["baseline"]
        out["status"] = "delivered" if delta >= p.get("material_change", 0) else "marginal" if delta > 0 else "not yet"
        out["detail"] = f"{fmt(p['baseline'], unit)} → {fmt(a['value'], unit)}"
    return out


GOOD = {"met", "beat", "ahead", "on track", "delivered", "on schedule", "raised", "reiterated"}
BAD = {"missed", "behind", "slipped", "walked back", "not yet", "delivered late"}


def build_ledger(company: dict, current_q: str) -> dict:
    calls = {c["id"]: c for c in company.get("calls", [])}
    items = []
    for p in company.get("promises", []):
        s = score(p, current_q)
        items.append({**p, **s, "said_on": [{**x, "date": calls.get(x["call"], {}).get("date")} for x in p["said"]]})

    hard = [x for x in items if x["kind"] in {"numeric", "runrate"} and x["status"] != "open"]
    kept = [x for x in hard if x["status"] in GOOD]
    tl = [x for x in items if x["kind"] == "timeline"]
    tl_on_time = [x for x in tl if x["status"] in {"on schedule", "delivered"}]
    slips = [x["slip_q"] for x in tl if x.get("slip_q")]
    cuts = [x for x in items if x["status"] == "walked back"]
    counts: dict[str, int] = {}
    for x in items:
        counts[x["status"]] = counts.get(x["status"], 0) + 1

    parts = []
    if hard:
        parts.append(f"{len(kept)}/{len(hard)} hard numbers kept")
    if tl:
        avg = f", avg slip {sum(slips) / len(slips):.1f} qtrs" if slips else ""
        parts.append(f"{len(tl_on_time)}/{len(tl)} dates kept{avg}")
    if cuts:
        parts.append(f"{len(cuts)} target{'s' if len(cuts) > 1 else ''} quietly cut")
    pattern = None
    if hard and tl and len(kept) / len(hard) >= 0.5 and len(tl_on_time) / len(tl) < 0.5:
        pattern = "Delivers on the numbers it controls; capacity and approval dates keep slipping."
    elif cuts and len(cuts) >= len(items) / 3:
        pattern = "Targets drift down between calls — discount the next one."
    elif cuts and hard and len(kept) == len(hard):
        pattern = "Keeps its few hard commitments; the softer targets, like margin, get re-worded downward between calls."
    elif cuts and len(hard) <= 1:
        pattern = "Guides in words more than numbers; the firm target it did set was walked back."
    return {"items": items, "counts": counts, "headline": " · ".join(parts), "pattern": pattern, "calls": company.get("calls", [])}

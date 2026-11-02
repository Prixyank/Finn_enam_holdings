"""Announcement triage: category, materiality score and the reasons behind it.

Deterministic rules handle the bulk of exchange filings for free. Only filings the rules
cannot place fall through to the cheap LLM tier (see `classify_with_fallback`).
Every score carries human-readable reasons so the app can show *why* an item ranks where it does.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .util import amounts_in_crore

# Order matters: routine copies of other filings are caught before the substantive rules.
# (category, subtype, pattern, base score)
RULES: list[tuple[str, str, str, int]] = [
    ("unclassified", "newspaper copy", r"newspaper (clipping|publication)", 8),
    ("unclassified", "compliance certificate", r"compliances?-certificate|reg\.?\s*74\s*\(5\)", 4),
    ("unclassified", "trading window", r"trading window", 4),
    ("unclassified", "ESOP", r"\besops?\b|\besps\b|stock options?|employee stock", 8),
    ("unclassified", "IEPF", r"\biepf\b|investor education", 4),
    ("unclassified", "ESG", r"\besg\b|\bbrsr\b|sustainability report", 10),
    ("unclassified", "monitoring agency", r"monitoring agency", 12),
    ("postal_ballot", "postal ballot", r"postal ballot", 25),
    ("agm_egm", "general meeting", r"\bagm\b|\begm\b|annual general meeting|extraordinary general meeting", 25),
    # A notice that results *will* be considered must win over the words "Results For The Quarter" in its title.
    ("results", "date set", r"board meeting (intimation|- intimation|- financial results)|intimation of (board )?meeting|notice of board meeting", 28),
    ("results", "board outcome", r"board meeting outcome|outcome of (the )?board meeting", 70),
    ("results", "filed", r"results? for the (quarter|half|year)|financial results.*(approv|outcome)|shareholders'? letter|^results\b", 88),
    ("earnings_call", "transcript", r"transcript", 35),
    ("earnings_call", "recording", r"audio recording|recording of (the )?(earnings|conference) call", 12),
    ("investor_meetings", "meeting", r"analyst|investor\(?s?\)?\s*meet|con\.?\s*call|roadshow", 15),
    ("management_change", "change", r"change in (management|directorate|managing director|key managerial)|resignation|appointment|cessation|retire", 50),
    ("M&A", "deal", r"acquisition|acquire|merger|amalgamation|demerger|joint venture|\bjv\b|restructuring|disinvestment|divest|initial public offer of|stake sale", 60),
    ("credit_rating", "rating", r"credit rating", 30),
    ("fund_raise", "raise", r"allotment|commercial paper|\bncds?\b|debenture|\bqip\b|rights issue|preferential|buy-?back|fund ?rais", 35),
    ("litigation", "legal", r"insolvency|\bcirp\b|\bnclt\b|\bnclat\b|\bitat\b|\bcci\b|court|tribunal|penalt|show cause|tax demand|litigation|\border\b.*(tax|tribunal|authority)", 55),
    ("dividend", "dividend", r"dividend|record date", 40),
    ("bonus_split", "bonus/split", r"\bbonus\b|stock split|sub-?division", 55),
    ("pledging", "pledge", r"pledg|encumbrance|regulation\s*31", 50),
    ("insider_trading", "large-holder trade", r"\bsast\b|reg\.?\s*29|insider|regulation\s*7\s*\(2\)", 42),
    ("capex", "capacity", r"capacity expansion|new plant|greenfield|brownfield|commissioning|capex", 50),
    ("press_release", "order win", r"bagging|order\(s\)|award.?of.?order|receipt.?of.?order|contract", 40),
    ("press_release", "news", r"press release|media release|media statement|launch|partnership", 25),
    ("unclassified", "guarantee", r"guarantee|indemnity|surety", 15),
    ("unclassified", "general update", r"general updates?|^updates?$", 15),
]

GENERIC_TITLE = re.compile(r"^(intimation|announcement|disclosure)s? under regulation 30\b.*$|^updates?$|^general updates?$", re.I)
EARNINGS_HINT = re.compile(r"transcript|earnings|conference call|results", re.I)

TITLE_PREFIXES = [
    r"^announcement under regulation 30 \(lodr\)\s*-\s*",
    r"^announcement under regulation 30 of sebi lodr\s*-\s*",
    r"^disclosure under regulation 30 and other applicable regulations of the sebi \(lodr\) regulations, 2015\s*-\s*",
    r"^intimation under regulation 30 of (the )?sebi \(lodr\) regulations, 2015\s*",
]


@dataclass
class Triage:
    category: str
    subtype: str
    score: int
    tier: str
    reasons: list[str] = field(default_factory=list)
    size_cr: float | None = None
    size_pct_mcap: float | None = None
    via: str = "rules"


def clean_title(title: str) -> str:
    t = title.strip()
    for p in TITLE_PREFIXES:
        t = re.sub(p, "", t, flags=re.I)
    t = re.sub(r"\s+\d{1,2} (jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)$", "", t, flags=re.I)
    t = t.replace("_", " ").strip(" -")
    return t[:1].upper() + t[1:] if t else title


def _match(text: str) -> tuple[str, str, int] | None:
    for cat, sub, pat, base in RULES:
        if re.search(pat, text, re.I):
            return cat, sub, base
    return None


def _role_score(text: str) -> tuple[int, str]:
    t = text.lower()
    if re.search(r"\b(md|ceo)\b|managing director|chief executive|chairman", t):
        return 95, "CEO / MD level change"
    if re.search(r"\bcfo\b|chief financial|director\s*\(?finance\)?", t):
        return 85, "CFO-level change"
    if re.search(r"whole-?time director|executive director|company secretary|key managerial", t):
        return 60, "Executive director / KMP change"
    if re.search(r"independent director|non-executive|nominee director", t):
        return 35, "Board seat change (non-executive)"
    return 30, "Senior staff change"


def tier_for(score: int) -> str:
    return "high" if score >= 70 else "medium" if score >= 40 else "low"


def classify(title: str, subtitle: str = "", mcap_cr: float | None = None) -> Triage | None:
    """Rules-only triage. Returns None when no rule applies (→ LLM fallback)."""
    head = clean_title(title)
    text = f"{head}. {subtitle}".strip()
    hit = _match(head)
    if hit is None or GENERIC_TITLE.match(head) or hit[1] in {"general update"}:
        hit = _match(subtitle) or hit
    if hit is None:
        return None
    cat, sub, score = hit
    reasons: list[str] = []
    low = text.lower()

    if cat == "investor_meetings" and EARNINGS_HINT.search(subtitle or ""):
        cat, sub, score = "earnings_call", "call / transcript", 25
    if cat == "management_change":
        score, why = _role_score(text)
        reasons.append(why)
        if re.search(r"re-?appoint|continuation|correct", low):
            score -= 15
            reasons.append("re-appointment / correction")
        if re.search(r"subsidiary|nominee director in \w+", low):
            score -= 20
            reasons.append("at a subsidiary")
    if cat == "credit_rating":
        if re.search(r"upgrad|downgrad|watch|outlook (revised|changed)|negative", low):
            score = 75
            reasons.append("rating action, not a reaffirmation")
        elif "reaffirm" in low:
            reasons.append("reaffirmed")
    if cat == "fund_raise" and re.search(r"repay|redeem|redemption", low):
        score = 10
        reasons.append("debt repayment, not a raise")
    if cat == "M&A":
        if re.search(r"initial public offer of", low):
            score = 80
            reasons.append("subsidiary IPO — value unlock")
        if re.search(r"nil consideration|internal restructuring|wholly.owned", low):
            score -= 15
            reasons.append("intra-group")
    if cat == "results" and sub == "filed":
        reasons.append("quarterly numbers out")
    if cat == "results" and sub == "date set":
        reasons.append("scheduling notice — goes on the calendar")
    if cat == "litigation" and re.search(r"order reserved|adjourn|not be taken up|next date|hearing (held|deferred)", low):
        score -= 25
        reasons.append("procedural hearing update")

    size_cr = max(amounts_in_crore(text), default=None)
    size_pct = None
    if size_cr and mcap_cr:
        size_pct = round(size_cr / mcap_cr * 100, 2)
        # Size only moves the needle where the amount *is* the event (a rating's facility size is not).
        if cat in {"M&A", "fund_raise", "litigation", "press_release", "capex"}:
            if size_pct >= 2:
                score += 25
            elif size_pct >= 0.5:
                score += 10
            elif size_pct < 0.1:
                score -= 10
        reasons.append(f"₹{size_cr:,.0f} cr ≈ {size_pct}% of market cap")
    elif size_cr:
        reasons.append(f"₹{size_cr:,.0f} cr")

    score = max(0, min(100, score))
    return Triage(cat, sub, score, tier_for(score), reasons, size_cr, size_pct)


def classify_with_fallback(title: str, subtitle: str, mcap_cr: float | None, llm=None) -> Triage:
    """Rules first; unmatched items go to the cheap model, constrained to the category list."""
    t = classify(title, subtitle, mcap_cr)
    if t is not None:
        return t
    if llm is not None:
        from .llm import CATEGORIES

        cat = llm.classify(clean_title(title), subtitle)
        if cat in CATEGORIES:
            base = {"unclassified": 10, "press_release": 25}.get(cat, 40)
            return Triage(cat, "model", base, tier_for(base), ["classified by cheap model"], via="llm")
    return Triage("unclassified", "unmatched", 10, "low", ["no rule matched"], via="none")

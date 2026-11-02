"""Management-change enrichment: who is coming in, who is leaving, and their background.

Step 1 (free): pull names and roles out of the filing's own text with patterns tuned on real
exchange summaries. Step 2 (cheap model, only if step 1 finds nothing): read the filing PDF.
Step 3 (search-grounded model, only for roles that matter): professional background with sources.
Results are cached by (company, person, role), so a CEO change is researched once.
"""

from __future__ import annotations

import re

HON = r"(?:(?:Mr|Ms|Mrs|Dr|Smt)\.?\s+|Shri\s+|Prof\.?\s+)?"
NAME_TOK = r"[A-Z](?:[a-z]+|\.)?"
NAME = rf"{HON}(?P<{{g}}>{NAME_TOK}(?:\s+{NAME_TOK}){{{{1,3}}}})"
END = r"(?=\s+(?:from|w\.?e\.?f|effective|with effect|for|on|subject)\b|,|\.|;|$)"
ROLE = r"(?P<role>[A-Za-z&()/\- ]{2,80}?)"


def _n(g: str) -> str:
    return NAME.format(g=g)


PATTERNS = [
    # "HAL appointed Anindya Biswas as Government Nominee Director from 7 October 2026"
    re.compile(rf"appoint(?:ed|s)\s+{_n('inc')}\s+as\s+(?:the\s+)?{ROLE}{END}"),
    # "Prashant Verma re-appointed CISO from ..." / "Anup Bagchi takes charge as MD & CEO"
    re.compile(rf"{_n('inc')},?\s+(?:has been |was |is )?(?P<act>re-?appointed|appointed|takes charge|named|elevated)\s+(?:as\s+)?(?:the\s+)?{ROLE}{END}"),
    # "Shri R Sriram, Executive Director (Finance), retires on 30 September 2026"
    re.compile(rf"{_n('out')},\s*{ROLE},\s*(?:has\s+)?(?P<act>retires?|retired|resigns?|resigned|ceases?|ceased)"),
    # "Mr. Harish Bhat resigned as non-executive non-independent director effective ..."
    re.compile(rf"{_n('out')}\s+(?:has\s+)?(?P<act>resigned|retired|stepped down|ceased)\s+(?:to be\s+)?(?:as\s+)?(?:the\s+)?{ROLE}{END}"),
]
OUTGOING = re.compile(rf"(?:replacing|succeeding|in place of)\s+{_n('out2')}")


def extract_people(text: str) -> dict | None:
    """{'incoming', 'outgoing', 'role', 'action'} from a filing summary, or None."""
    text = re.sub(r"\s+", " ", text or "").strip()
    for p in PATTERNS:
        m = p.search(text)
        if not m:
            continue
        g = m.groupdict()
        out = {"incoming": g.get("inc"), "outgoing": g.get("out"), "role": (g.get("role") or "").strip(" ,"), "action": (g.get("act") or "appointed").lower()}
        m2 = OUTGOING.search(text)
        if m2 and not out["outgoing"]:
            out["outgoing"] = m2.group("out2")
        return out
    return None


SENIOR = re.compile(r"\b(md|ceo|cfo|coo|chairman|chairperson|managing director|chief executive|chief financial|director\s*\(?finance\)?|whole-?time director|executive director)\b", re.I)


def worth_researching(person: dict | None, title: str) -> bool:
    """Background lookups cost a search call; spend it only on people who run the company."""
    if not person or not person.get("incoming"):
        return False
    return bool(SENIOR.search(person.get("role", "") + " " + title)) and "re-appoint" not in person.get("action", "")


def enrich_filing(f: dict, company: str, llm=None, pdf_text: str | None = None) -> dict | None:
    person = extract_people(f.get("subtitle", "")) or extract_people(f.get("title", ""))
    if person is None and pdf_text and llm is not None:
        got = llm.extract_notes(company, "management change filing", pdf_text[:8000])  # cheap tier, constrained JSON
        person = got.get("person") if isinstance(got, dict) else None
    if person is None:
        return None
    rec = {"ticker": f["ticker"], "effective": f["date"], "role": person["role"], "incoming": person.get("incoming"),
           "outgoing": person.get("outgoing"), "action": person["action"], "background": [], "sources": []}
    if llm is not None and worth_researching(person, f.get("title", "")):
        bio = llm.person_background(person["incoming"], person["role"], company)
        if bio.get("confidence") != "low":
            rec.update({k: bio[k] for k in ("background", "why_it_matters", "sources") if bio.get(k)})
    return rec

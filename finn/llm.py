"""Model routing with a content-addressed cache.

Tier 0  rules / arithmetic (classify.py, alerts.py, results.py, ledger.py, research.py) — free, most of the work
Tier 1  cheap + fast: leftover classification, one-line summaries, guidance extraction per transcript chunk
Tier 2  strong: bull/bear synthesis on the computed facts — on demand, one call per company per doc set

Every call is cached on sha256(model, prompt version, input), so re-running a day, or re-opening a
company whose filings haven't changed, costs nothing. Providers are called over plain HTTPS;
with no API keys set the engine still runs end to end on tiers 0 + cache.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path

import requests

CATEGORIES = [
    "results", "M&A", "fund_raise", "management_change", "litigation", "insider_trading", "earnings_call",
    "investor_meetings", "credit_rating", "dividend", "bonus_split", "capex", "press_release", "postal_ballot",
    "agm_egm", "pledging", "unclassified",
]

TIERS = {
    # Overridable per environment; defaults chosen for free tiers / low cost.
    "cheap": os.getenv("FINN_CHEAP_MODEL", "gemini:gemini-2.5-flash-lite"),
    "strong": os.getenv("FINN_STRONG_MODEL", "anthropic:claude-sonnet-5-5"),
    # search-grounded, only for push enrichment (a person's background is not in the filings)
    "search": os.getenv("FINN_SEARCH_MODEL", "gemini-search:gemini-2.5-flash"),
}

PROMPTS = Path(__file__).parent / "prompts"
CACHE = Path(os.getenv("FINN_CACHE", Path.home() / ".cache" / "finn" / "llm.sqlite"))


class LLM:
    def __init__(self, cache_path: Path = CACHE):
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(cache_path)
        self.db.execute("create table if not exists c (k text primary key, v text, model text, tin int, tout int, ts real)")
        self.spend = {"calls": 0, "cache_hits": 0, "tokens_in": 0, "tokens_out": 0}

    # ---- public tasks -------------------------------------------------
    def classify(self, title: str, subtitle: str) -> str:
        p = self._prompt("classify", title=title, subtitle=subtitle, categories=", ".join(CATEGORIES))
        out = self.complete("cheap", p, max_tokens=8).strip().strip(".").strip()
        return out if out in CATEGORIES else "unclassified"

    def one_liner(self, ticker: str, title: str, text: str) -> str:
        return self.complete("cheap", self._prompt("one_liner", ticker=ticker, title=title, text=text[:6000]), max_tokens=60).strip()

    def extract_guidance(self, company: str, call_label: str, chunk: str) -> list[dict]:
        raw = self.complete("cheap", self._prompt("extract_guidance", company=company, call=call_label, chunk=chunk), max_tokens=1500, json_mode=True)
        try:
            return json.loads(raw).get("statements", [])
        except json.JSONDecodeError:
            return []

    def extract_notes(self, company: str, document: str, chunk: str) -> dict:
        raw = self.complete("cheap", self._prompt("extract_notes", company=company, document=document, chunk=chunk), max_tokens=1200, json_mode=True)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def person_background(self, name: str, role: str, company: str) -> dict:
        """Push-side enrichment. Uses a search-grounded model (Gemini + Google Search) because a person's
        career history is outside the filings; every line must come with a source URL."""
        p = self._prompt("person", name=name, role=role, company=company)
        raw = self.complete("search", p, max_tokens=500, json_mode=False)
        try:
            return json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        except (json.JSONDecodeError, ValueError):
            return {}

    def bull_bear(self, company: str, facts: list[dict], ledger: dict) -> dict:
        p = self._prompt("bull_bear", company=company, facts=json.dumps(facts, ensure_ascii=False), ledger=json.dumps(ledger, ensure_ascii=False)[:8000])
        raw = self.complete("strong", p, max_tokens=700, json_mode=True)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"bull": [], "bear": []}

    # ---- plumbing -----------------------------------------------------
    def _prompt(self, name: str, **kw) -> str:
        return (PROMPTS / f"{name}.md").read_text().format(**kw)

    def complete(self, tier: str, prompt: str, max_tokens: int = 400, json_mode: bool = False) -> str:
        model = TIERS[tier]
        key = hashlib.sha256(f"{model}\x00{json_mode}\x00{prompt}".encode()).hexdigest()
        row = self.db.execute("select v from c where k=?", (key,)).fetchone()
        if row:
            self.spend["cache_hits"] += 1
            return row[0]
        provider, name = model.split(":", 1)
        text, tin, tout = getattr(self, "_" + provider.replace("-", "_"))(name, prompt, max_tokens, json_mode)
        self.db.execute("insert or replace into c values (?,?,?,?,?,?)", (key, text, model, tin, tout, time.time()))
        self.db.commit()
        self.spend["calls"] += 1
        self.spend["tokens_in"] += tin
        self.spend["tokens_out"] += tout
        return text

    def _gemini(self, model, prompt, max_tokens, json_mode):
        key = os.environ["GEMINI_API_KEY"]
        cfg = {"maxOutputTokens": max_tokens, "temperature": 0}
        if json_mode:
            cfg["responseMimeType"] = "application/json"
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
            json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": cfg}, timeout=60)
        r.raise_for_status()
        j = r.json()
        u = j.get("usageMetadata", {})
        return j["candidates"][0]["content"]["parts"][0]["text"], u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0)

    def _gemini_search(self, model, prompt, max_tokens, json_mode):
        """Gemini with Google Search grounding; appends the grounding sources so the answer stays checkable."""
        key = os.environ["GEMINI_API_KEY"]
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
            json={"contents": [{"parts": [{"text": prompt}]}], "tools": [{"google_search": {}}],
                  "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0}}, timeout=90)
        r.raise_for_status()
        j = r.json()
        cand = j["candidates"][0]
        text = "".join(p.get("text", "") for p in cand["content"]["parts"])
        chunks = cand.get("groundingMetadata", {}).get("groundingChunks", [])
        srcs = [{"title": c["web"].get("title", ""), "url": c["web"].get("uri", "")} for c in chunks if "web" in c]
        try:
            obj = json.loads(text[text.find("{"): text.rfind("}") + 1])
            obj.setdefault("sources", srcs)
            text = json.dumps(obj, ensure_ascii=False)
        except (json.JSONDecodeError, ValueError):
            pass
        u = j.get("usageMetadata", {})
        return text, u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0)

    def _groq(self, model, prompt, max_tokens, json_mode):
        body = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens, "temperature": 0}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", json=body,
                          headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"}, timeout=60)
        r.raise_for_status()
        j = r.json()
        return j["choices"][0]["message"]["content"], j["usage"]["prompt_tokens"], j["usage"]["completion_tokens"]

    def _anthropic(self, model, prompt, max_tokens, json_mode):
        if json_mode:
            prompt += "\n\nRespond with a single JSON object and nothing else."
        r = requests.post("https://api.anthropic.com/v1/messages",
                          headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
                          json={"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}, timeout=120)
        r.raise_for_status()
        j = r.json()
        return j["content"][0]["text"], j["usage"]["input_tokens"], j["usage"]["output_tokens"]


def available() -> bool:
    return any(os.getenv(k) for k in ("GEMINI_API_KEY", "GROQ_API_KEY", "ANTHROPIC_API_KEY"))

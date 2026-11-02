"""Primary documents (results PDFs, transcripts, annual reports) → text → chunks for the cheap model."""

from __future__ import annotations

import hashlib
import io
import re
from pathlib import Path

import requests

from .exchange import UA

CACHE = Path.home() / ".cache" / "finn" / "docs"


def fetch_pdf_text(url: str) -> str:
    """Download once (cached by URL hash), extract text with pdfplumber."""
    import pdfplumber

    CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(url.encode()).hexdigest()[:24]
    txt = CACHE / f"{key}.txt"
    if txt.exists():
        return txt.read_text()
    r = requests.get(url, headers={**UA, "Referer": "https://www.bseindia.com/"}, timeout=60)
    r.raise_for_status()
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    txt.write_text(text)
    return text


SPEAKER = re.compile(r"\n(?=[A-Z][A-Za-z .]{2,40}:)")


def chunk_transcript(text: str, max_chars: int = 12000) -> list[str]:
    """Split at speaker turns so a guidance statement is never cut in half; drop the
    safe-harbour boilerplate and the operator's queue announcements, which carry no guidance."""
    text = re.sub(r"(?is)safe harbou?r.*?(?=\n[A-Z][A-Za-z .]{2,40}:)", "", text, count=1)
    turns = [t for t in SPEAKER.split(text) if not t.strip().lower().startswith("moderator:")]
    chunks, cur = [], ""
    for t in turns:
        if len(cur) + len(t) > max_chars and cur:
            chunks.append(cur)
            cur = ""
        cur += "\n" + t
    if cur.strip():
        chunks.append(cur)
    return chunks

Write a tight bull case and bear case for {company} for a long-only fund manager.

You may use ONLY the facts below — computed from the company's own filings — and the promise ledger built from its earnings calls. Do not use outside knowledge, news, broker views or valuations not listed.

Facts (each has an id):
{facts}

Promise ledger (management statements vs outcomes):
{ledger}

Return JSON: {{"bull": [{{"point": str, "cites": [fact or promise ids]}}], "bear": [{{"point": str, "cites": [...]}}]}}
- 3 points each, each under 25 words, each citing at least one id.
- The strongest point first. Prefer points where numbers and management's track record agree (or clash).

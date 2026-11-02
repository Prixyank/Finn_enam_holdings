# AI build history

FINN was built in a single session with Claude (Opus 5.5) acting as a coding agent: reading the brief, probing data sources, writing the engine, tests and app, and validating results. Share the conversation link as the build history.

Notable turns in that session:
1. Source probing — Yahoo, NSE, BSE and screener were blocked from the sandbox shell; screener and investing.com were reachable through a web reader; stale caches were detected (Google Finance served a month-old quote; investing.com pages lagged until cache-busted) and only fresh, cross-checked data was kept.
2. Entity resolution — a transcript archive mixed in Tecsys (TSX: TCS) with Tata Consultancy Services; only the right calls were used.
3. First run of triage on real filings exposed three rule bugs (board-meeting notices scored as results; procedural hearings as material; duplicate notices not merged). Each became a test.
4. Validation — 18 cross-source checks; the TCS transcript's ₹73,288 cr revenue was traced to a speech-to-text error against the filing's ₹73,188 cr.
5. Model-written text (one-liners, bull/bear) is stored separately in `data/llm/` and labelled, so reviewers can tell computed facts from generated prose.

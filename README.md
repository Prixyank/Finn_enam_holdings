# FINN — Financial Investment Agent

A mobile-first agent that does one job for an investor: **filter**. It reads every exchange filing and every end-of-day price across a 15-stock portfolio, decides what deserves attention, and folds away the rest. On demand it researches a company from its own filings and earnings calls, and checks what management promised against what it delivered.

**Try it on a phone:** open `dist/index.html` (any static host; GitHub Pages config below), or the hosted prototype link in the covering note.

## What you see

| Tab | Mode | What it does |
|---|---|---|
| **Today** | Push · digest | Pick a window (24h / 3d / 7d / 30d, or any custom date range). Filings are scored 0–100 and split into *Needs a decision* (full card), *Worth a glance* (one line) and *Routine* (folded). EOD price/volume breaches sit alongside. Mark items done to reach inbox-zero. |
| **Rules** | Push · alerts | Sliders for volume spike (× trailing average), daily move (±%), materiality floor and which filing types may interrupt you. Every change re-runs the rules over the last 20 sessions and shows the consequence: a trigger map and "≈ N pings a day". |
| **Season** | Push · results | Q2 FY27 tracker: who has reported, who reports this week, and a first cut of each results filing — Revenue, EBITDA, PBT, PAT, QoQ and YoY, with flags (margin change, other-income share, tax-rate distortion). |
| **Research** | Pull | Snapshot, trajectory, balance sheet, cash quality, business mix, **auditor & related-party checks**, a **promise ledger** (what was said on each call vs what happened) and a bull/bear in which every point cites the fact it rests on. Optional "Ask" box answers questions from that data only. |

Two push treatments the brief asked for:
- **Management change** → the incoming person's background (HDFC Bank's new MD & CEO, effective 27 Oct 2026, is in the demo). `enrich.py` reads names and roles from the filing text for free (tested on real summaries) and, for senior roles only, asks a search-grounded model for the career history with sources.

**Real push.** `python -m finn notify` sends anything that crosses your rules to Telegram and/or email, exactly once per item (a state file remembers what went out). The GitHub Action polls filings every 30 minutes during market hours and runs the price/volume rules after the close.
- **Quarterly results** → the four headline numbers QoQ and YoY, sector-aware (EBITDA is shown as "not meaningful" for banks rather than a wrong number; NBFCs show financing profit).

## Run it

```bash
pip install -r requirements.txt
python -m finn build            # replay the committed 27-Oct-2026 snapshot → dist/index.html
python -m finn live             # today's data: NSE/BSE announcements, yfinance EOD, screener.in → dist/
python -m finn notify --dry-run # what would be pushed now (drop --dry-run to send)
python -m finn research PAGEIND # pull-side research for any NSE symbol screener covers (JSON)
python scripts/validate.py      # cross-source checks → data/validation.json
pytest                          # or: python tests/run.py
```

Model keys are optional (`GEMINI_API_KEY`, `GROQ_API_KEY`, `ANTHROPIC_API_KEY`). Without them every rule, number and score still runs; only summaries of unseen filings and guidance extraction from new transcripts are skipped.

`.github/workflows/eod.yml` runs `finn live` + `finn notify` every 30 min in market hours and at 16:15 IST, and publishes `dist/` to GitHub Pages. Secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` and/or `SMTP_*`, `ALERT_EMAIL_TO`; optional model keys.

## How it decides (and what it costs)

```
            ┌───────────── raw (same shape for live or snapshot) ─────────────┐
 NSE / BSE ─┤ announcements      yfinance ─ EOD bars      screener ─ statements │
            └──────────────┬───────────────────┬──────────────────┬──────────────┘
                           ▼                   ▼                  ▼
 Tier 0 · rules    classify.py           alerts.py          results.py  research.py
 (free, ~all)      type · role · size    vol× · ±%          QoQ / YoY   ratios, signals
                   vs market cap         (mirrored in JS)   + flags
                           │                                           ledger.py
 Tier 1 · cheap    unplaced filings, one-liners,          ◄── guidance statements
 (cached)          guidance extraction per transcript chunk   (model extracts, code scores)
 Tier 2 · strong   bull / bear from cited facts, once per company per document set
```

- **73 of 73 filings in the snapshot were triaged by rules** — no model call. The rules were tuned on the real feed: the first run scored three board-meeting *notices* as filed results and two procedural court hearings as material; both are now regression tests.
- **The model never produces a number the app displays as fact.** It extracts dated statements from transcripts; `ledger.py` scores them (5% grace on numeric targets; slippage counted in fiscal quarters).
- **Caching** is content-addressed (`sha256(model, prompt, input)`), so re-running a day or reopening a company is free.
- Estimated steady-state cost: ~10 one-liners a day on a free-tier flash model, plus ~100k cheap tokens and ~8k strong tokens per new company researched (cents).

## What is and isn't verified

**Verified in this build**
- 39 tests pass: triage on real filing titles, alert maths, results maths, ledger statuses, amount parsing, name/role extraction for management changes, push de-duplication, and **parity between the Python rules and the in-app JavaScript rules** on the real bars.
- 21/21 cross-source checks (`data/validation.json`, also in the app's ⓘ sheet): EOD closes from one source vs prices on another; TCS revenue, PAT and margin vs TCS's own release (screener's EBITDA less depreciation reproduces TCS's 24.0% operating margin); Dixon revenue/EBITDA vs four calls and vs its Q1 FY27 results filing on NSE.
- Two data traps caught and documented: the TCS call transcript says ₹73,288 cr (speech-to-text error; the filing says ₹73,188 cr), and screener's PAT includes minority interest (₹13,934 cr vs ₹13,884 cr attributable).

- Reading Dixon's Q1 FY27 results filing corrected my own first draft: Q1's profit jump is not a fair-value gain; the auditor draws attention to ₹1,110 cr of PLI income booked but still awaiting the government's determination (24% of net worth).

**Not verified here**
- The live connectors (`finn/sources/*`) were written against the sites' known interfaces, but NSE, BSE, Yahoo and screener were unreachable from the build sandbox, so they have not been run end to end. The snapshot was collected through a web reader instead and is replayed through the same processing code. The screener parser is tested against a hand-written fixture of its markup.
- Transcript extraction ran through a verbatim transcript archive because BSE PDFs were blocked; production reads the PDFs.
- Telegram/email delivery and the search-grounded background lookup are coded and unit-tested offline, but not exercised against the real services (no keys in the build sandbox).
- Contingent liabilities: Dixon's FY26 annual-report notes could not be read here (the company copy is image-based; the exchange copy was cut off after the AGM notice), and the app says so. The AGM notice's related-party resolutions and the auditor's Q1 review were read.

## Data in this repo

`data/raw/` — exactly what was collected on 27 Oct 2026 (sources in `data/raw/sources.json`). `data/llm/` — model-written text (one-liners, bull/bear), labelled as such. EOD prices for POLYCAB, HAL and CDSL came without volume; the app says so and the volume rule abstains for them.

Not investment advice.

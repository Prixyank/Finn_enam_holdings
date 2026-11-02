To: assessment@enam.com
Subject: ENAM - IIT screening - 2027

Hello ENAM team,

Please find my submission for the FINN build challenge.

- Prototype (open on a phone): [hosted link]
- Repository: [GitHub link]
- AI build history: [share link to the Claude conversation used to build this]

**What I built**

FINN is a filter, not an aggregator. It has four screens:

1. **Today (push digest).** Every filing across a 15-stock portfolio, for a window you pick, scored 0–100 by filing type, who is involved and deal size against market cap. Material items get a full card, mid items one line, and routine paperwork folds away. On the 27 Oct snapshot the 24-hour view comes down to two things: HDFC Bank's new MD & CEO (with his background) and Polycab's +4% close.
2. **Rules (push alerts).** Alerts are delivered for real: `finn notify` pushes each item that crosses your rules to Telegram or email exactly once; a GitHub Action polls filings every 30 minutes in market hours and runs price/volume rules after the close. In the app, you set what "unusual" means: volume multiple, price move, materiality floor, which filing types may interrupt you. Each change replays the last 20 sessions as a trigger map and tells you how many pings a day that setting would produce, so you tune the threshold against its consequence rather than guessing.
3. **Season.** A results-season tracker: first cut of each results filing (Revenue, EBITDA, PBT, PAT, QoQ/YoY, sector-aware) plus the calendar of who reports this week.
4. **Research (pull).** Built around the "promised vs delivered" example. For Dixon, 16 statements from four calls are scored: 5 of 8 hard numbers kept, 0 of 4 capacity dates kept (average slip 2.2 quarters), 3 targets cut. FINN's one-line read: delivers on the numbers it controls; capacity and approval dates keep slipping. Each row shows how the target moved from call to call, with the management quote behind it. Bull and bear points each cite the fact they rest on. An auditor & related-party section reads the filings themselves: Dixon's auditor gives a clean review but draws attention to ₹1,110 cr of PLI income still awaiting government determination (24% of net worth), and the AGM seeks approval for up to ₹4,500 cr a year of sales to Bharti Airtel, its JV partner's group. TCS's ledger covers four calls: it keeps its few hard commitments (order book, wage-hike impact) while its margin target is re-worded downward from call to call. An optional Ask box answers from that data only.

**Key decisions**

- **Rules first, models last.** All 73 filings in the snapshot were triaged without a model call. Models are used for extraction (guidance statements from transcripts) and synthesis (bull/bear), never to produce a number shown as fact. The ledger's statuses are arithmetic on extracted statements, so they are reproducible and tested.
- **Model routing and caching.** Cheap model for summaries and transcript extraction, strong model only for bull/bear, content-addressed cache so nothing is paid for twice.
- **Validation over polish.** 39 tests (including parity between the Python rules and the in-app JavaScript rules) and 21 cross-source checks. These caught a speech-to-text error in the TCS transcript (₹73,288 cr vs ₹73,188 cr filed), screener's PAT including minority interest, and three rule bugs on the first run against real filings.
- **Judgment encoded as rules.** A board-meeting notice is not a result; a nominee director at a subsidiary is not a CEO change; a ₹13,000 cr tax ruling (3.6% of Maruti's market cap) outranks a ₹62 cr guarantee; "other income > PBT" is a red flag for Eternal but normal for a bank.

**What I left out, and why**

- **Live data inside the hosted prototype.** My build environment could not reach NSE, BSE, Yahoo or screener directly, so the demo replays a real 27 Oct 2026 snapshot gathered through a web reader. The live connectors and a GitHub Action for a 16:15 IST daily run are in the repo but have not been run end to end; the README says exactly what is and isn't verified.
- **Narrative check for Trent.** Trent does not hold earnings calls, so its ledger is empty and the app says so rather than inventing one.
- **Per-filing PDF reading.** Push summaries use the exchange's own summary line; reading every attachment is the next step.
- **Contingent liabilities.** Dixon's annual-report notes were not machine-readable from my environment; the app says so instead of guessing.
- **Unexercised integrations.** Telegram/email delivery and the search-grounded background lookup are tested offline only; they need keys to run.

**Where I'd take it next**

1. Run the live pipeline daily and close the loop on open promises automatically: Dixon reports on 30 Oct, and its 9–9.2 mn unit Q2 promise should score itself.
2. Read every filing PDF with the cheap tier, so one-liners carry the filing's own numbers.
3. Feed "done" and "dismissed" actions back into the scoring so FINN learns each investor's threshold for "material".
4. Extend the ledger across the portfolio and rank managements by credibility.

Thank you,
[Your name]

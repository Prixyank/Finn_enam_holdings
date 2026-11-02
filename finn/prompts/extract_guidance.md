You are extracting management guidance from part of an earnings-call transcript for {company} ({call}).

Return JSON: {{"statements": [ {{"speaker": str, "theme": str, "metric": str, "kind": "numeric"|"timeline"|"direction"|"qualitative", "lo": number|null, "hi": number|null, "unit": str, "due": "Q<n>FY<yy>"|null, "period": str, "quote": str}} ]}}

Rules:
- Only forward-looking statements by company management (not analysts' questions, not past results).
- Convert dates to Indian fiscal quarters: Apr–Jun = Q1, Jul–Sep = Q2, Oct–Dec = Q3, Jan–Mar = Q4; FY27 = Apr 2026–Mar 2027. "By March 2026" → Q4FY26.
- Ranges stay ranges ("40 to 42 million" → lo 40, hi 42, unit "mn units"). "At least X" → lo X, hi null.
- quote: the shortest verbatim span (under 15 words) that carries the number or date.
- If management explicitly declines to guide on something, emit kind "qualitative" with metric and quote so the refusal is on record.
- Do not infer numbers that were not said. Do not use any knowledge outside this text.

Transcript chunk:
{chunk}

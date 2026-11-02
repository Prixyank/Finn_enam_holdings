Search the web for the professional background of {name}, newly named {role} at {company} (an Indian listed company).

Return only JSON:
{{"incoming": "{name}", "role": "{role}", "background": [str], "why_it_matters": str, "confidence": "high"|"low"}}

- background: 3–5 lines, newest role last, each "Title, Organisation (years)" or "Degree, Institution". Facts only.
- why_it_matters: one sentence for an investor: insider vs outsider, relevant prior experience. No praise, no speculation about performance.
- If you cannot find this specific person with confidence (common names, no match to the company), set confidence "low" and background [].

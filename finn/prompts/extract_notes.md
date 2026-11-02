You are reading part of a primary filing by {company}: {document}.

Extract only what this text states. Return JSON:
{{"auditor": {{"name": str|null, "opinion": "unmodified"|"qualified"|"adverse"|"disclaimer"|null,
   "attention": [{{"topic": str, "amount_cr": number|null, "detail": str}}],
   "key_audit_matters": [str],
   "unreviewed": {{"count": number|null, "revenue_cr": number|null, "revenue_share_pct": number|null}}}},
 "contingent_liabilities": [{{"item": str, "amount_cr": number|null}}],
 "related_party": [{{"counterparty": str, "relationship": str, "nature": str, "amount_cr": number|null, "limit_cr_per_year": number|null, "pct_of_turnover": number|null}}]}}

Rules: amounts in ₹ crore (convert lakh/million). "Emphasis of matter" or "draw attention to" items go in auditor.attention. Leave a list empty when the text has nothing on it. No outside knowledge.

Text:
{chunk}

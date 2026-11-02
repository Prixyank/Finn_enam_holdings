"""Portfolio, research set and default thresholds. Everything here is user-editable."""

from __future__ import annotations

from dataclasses import dataclass, field

# 15 NSE names: mega-caps to small-caps, eight sectors, a bank, an NBFC and a PSU.
PORTFOLIO: dict[str, dict] = {
    "RELIANCE": {"sector": "Energy & Telecom", "size": "mega"},
    "HDFCBANK": {"sector": "Banks", "size": "mega", "kind": "bank"},
    "TCS": {"sector": "IT Services", "size": "mega"},
    "ITC": {"sector": "FMCG", "size": "large"},
    "LT": {"sector": "Infrastructure", "size": "large"},
    "SUNPHARMA": {"sector": "Pharma", "size": "large"},
    "MARUTI": {"sector": "Autos", "size": "large"},
    "TITAN": {"sector": "Consumer", "size": "large"},
    "BAJFINANCE": {"sector": "NBFC", "size": "large", "kind": "nbfc"},
    "ETERNAL": {"sector": "Internet", "size": "large"},
    "HAL": {"sector": "Defence PSU", "size": "large"},
    "POLYCAB": {"sector": "Electricals", "size": "mid"},
    "DIXON": {"sector": "Electronics mfg", "size": "mid"},
    "CDSL": {"sector": "Market infra", "size": "small"},
    "KPITTECH": {"sector": "Auto software", "size": "small"},
}

# Pull-side demo set; the engine itself takes any NSE symbol screener.in covers.
RESEARCH_SET = ["DIXON", "TCS", "TRENT"]


@dataclass
class Thresholds:
    """What 'unusual' means. The app lets the user move these and re-runs the rules live."""

    volume_multiple: float = 2.0      # today's volume vs trailing average
    volume_lookback: int = 20         # sessions in the trailing average (fewer if history is short)
    min_lookback: int = 5             # below this, the volume rule abstains
    price_move_pct: float = 3.0       # absolute daily close-to-close move
    materiality_floor: int = 70       # announcement score that triggers an alert
    alert_categories: list[str] = field(
        default_factory=lambda: ["results", "M&A", "management_change", "litigation", "credit_rating", "fund_raise"]
    )


# Rough INR conversions for sizing amounts quoted in filings against market cap.
USD_INR = 88.0

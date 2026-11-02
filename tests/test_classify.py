"""Triage on real filing titles from the 27-Oct-2026 snapshot (not invented examples)."""

from finn.classify import classify, clean_title


def cat(title, sub="", mcap=None):
    t = classify(title, sub, mcap)
    return (t.category, t.tier) if t else None


def test_ceo_change_is_top_priority():
    t = classify("Disclosure Under Regulation 30 And Other Applicable Regulations Of The SEBI (LODR) Regulations, 2015 - Change In Managing Director And Chief Executive Officer Of The Bank")
    assert (t.category, t.tier) == ("management_change", "high") and t.score >= 90


def test_psu_finance_director_counts_as_cfo():
    assert cat("Announcement under Regulation 30 (LODR)-Change in Management", "Shri R Sriram, Executive Director (Finance), retires on 30 September 2026.") == ("management_change", "high")


def test_reappointment_and_subsidiary_roles_are_downweighted():
    assert cat("Announcement under Regulation 30 (LODR)-Change in Management", "Prashant Verma re-appointed CISO from 1 February 2027")[1] == "low"
    assert cat("Updates", "Dr. Rakeshkumar Kakkar resigned as CDSL nominee director in CVL effective September 28, 2026.")[1] == "low"


def test_board_notice_is_not_a_results_filing():
    # The bug the real feed exposed: "Results For The Quarter" inside a scheduling notice.
    t = classify("Board Meeting Intimation for Consider And Approve The Unaudited Financial Results For The Quarter Ended 30Th September 2026")
    assert (t.category, t.subtype, t.tier) == ("results", "date set", "low")
    assert classify("Results For The Quarter And Half Year Ended September 30, 2026").subtype == "filed"
    assert classify("Shareholders Letter").subtype == "filed"


def test_generic_title_falls_back_to_summary_and_sizes_against_mcap():
    t = classify("Intimation Under Regulation 30 Of SEBI (LODR) Regulations, 2015",
                 "ITAT order for FY14–FY20 and FY22 mostly favours the company; positive tax impact of about Rs. 130,000 million.", 358600)
    assert t.category == "litigation" and t.tier == "high"
    assert t.size_cr == 13000 and abs(t.size_pct_mcap - 3.63) < 0.01


def test_procedural_hearing_is_low():
    assert cat("Intimation Under Regulation 30 Of The SEBI (LODR) Regulations, 2015",
               "NCLAT hearing on CCI matter will not be taken up on 2 November 2026; next date pending.")[1] == "low"


def test_routine_paperwork_is_collapsed():
    for title in ["Compliances-Certificate under Reg. 74 (5) of SEBI (DP) Regulations, 2018", "Closure of Trading Window",
                  "Announcement under Regulation 30 (LODR)-Allotment of ESOP / ESPS", "Grant Of Stock Options Under Employee Stock Option Scheme",
                  "Newspaper Clipping - Proposed Initial Public Offer Of Jio Platforms Limited -Reservation For Eligible RIL Shareholders"]:
        assert cat(title) == ("unclassified", "low"), title


def test_subsidiary_ipo_is_ma_not_newspaper():
    assert cat("Initial Public Offer Of Jio Platforms Limited - Update 24 Oct") == ("M&A", "high")


def test_debt_repayment_is_not_a_raise():
    t = classify("Intimation of Repayment of Commercial Paper (CP)", "Titan fully redeemed ₹1,000 crore commercial paper", 383790)
    assert t.category == "fund_raise" and t.tier == "low"


def test_rating_reaffirmation_ignores_facility_size():
    t = classify("Announcement under Regulation 30 (LODR)-Credit Rating", "ICRA reaffirmed RIL's AAA/Stable NCD rating and assigned AAA/Stable to Rs50,000 crore bank facilities.", 1626340)
    assert t.category == "credit_rating" and t.tier == "low"


def test_investor_meet_with_transcript_is_earnings_call():
    assert cat("Announcement under Regulation 30 (LODR)-Analyst / Investor Meet - Outcome", "HDFC Bank released Q2 FY27 earnings call transcript")[0] == "earnings_call"
    assert cat("Announcement under Regulation 30 (LODR)-Analyst / Investor Meet - Intimation")[0] == "investor_meetings"


def test_clean_title():
    assert clean_title("Announcement under Regulation 30 (LODR)-Analyst / Investor Meet - Intimation 26 Oct") == "Analyst / Investor Meet - Intimation"

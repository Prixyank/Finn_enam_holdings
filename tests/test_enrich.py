"""Name/role extraction on real exchange summaries from the snapshot."""

from finn.enrich import extract_people, worth_researching


def test_appointed_as():
    p = extract_people("HAL appointed Anindya Biswas as Government Nominee Director from 7 October 2026, replacing K Rajalakshmi Menon.")
    assert p["incoming"] == "Anindya Biswas" and p["role"] == "Government Nominee Director" and p["outgoing"] == "K Rajalakshmi Menon"
    assert not worth_researching(p, "Change in Directorate")


def test_retirement_with_role_in_commas():
    p = extract_people("Shri R Sriram, Executive Director (Finance), retires on 30 September 2026.")
    assert p["outgoing"] == "R Sriram" and p["role"] == "Executive Director (Finance)" and p["action"] == "retires"


def test_reappointment_is_not_researched():
    p = extract_people("Prashant Verma re-appointed CISO from 1 February 2027 for three years, subject to approvals.")
    assert p["incoming"] == "Prashant Verma" and p["role"] == "CISO" and p["action"] == "re-appointed"
    assert not worth_researching(p, "Change in Management")


def test_resignation():
    p = extract_people("Mr. Harish Bhat resigned as non-executive non-independent director effective 17 October 2026.")
    assert p["outgoing"] == "Harish Bhat" and p["role"].startswith("non-executive") and p["action"] == "resigned"


def test_ceo_appointment_is_researched():
    p = extract_people("Anup Bagchi takes charge as MD & CEO, succeeding Sashidhar Jagdishan.")
    assert p["incoming"] == "Anup Bagchi" and p["role"] == "MD & CEO" and p["outgoing"] == "Sashidhar Jagdishan"
    assert worth_researching(p, "Change In Managing Director And Chief Executive Officer")


def test_no_person_in_title_only_filing():
    assert extract_people("Change In Managing Director And Chief Executive Officer Of The Bank") is None

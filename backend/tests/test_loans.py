from datetime import date

import pytest

from app.loans import LoanState, add_months, amortise, annuity_payment, early_repayment_indemnity, project_payments, simulate_payoff


def test_add_months_clips_to_month_end():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 11, 5), 3) == date(2027, 2, 5)


def test_zero_percent_plan_ends_on_the_stated_number_of_payments():
    loan = LoanState("4x", 95.12, 0.0, 47.56, next_payment_date=date(2026, 11, 27), payments_remaining=2)
    payments = project_payments(loan)
    assert [p.due_date for p in payments] == [date(2026, 11, 27), date(2026, 12, 27)]
    assert sum(p.total for p in payments) == pytest.approx(95.12)
    assert payments[-1].balance_after == 0


def test_annuity_loan_amortises_to_zero_with_a_smaller_last_payment():
    loan = LoanState("car", 3445.40, 3.5, 443.23, next_payment_date=date(2026, 12, 5))
    payments = project_payments(loan)
    assert len(payments) == 8
    assert payments[-1].balance_after == 0
    assert payments[-1].total <= 443.23


def test_payment_that_does_not_cover_interest_never_amortises():
    assert project_payments(LoanState("bad", 100_000, 6.0, 100, next_payment_date=date(2026, 12, 1))) == []


def test_annuity_and_amortise_agree():
    payment = annuity_payment(200_000, 3.0, 240)
    months, interest, _ = amortise(200_000, 3.0, payment, 0.0)
    assert months in (240, 241)
    assert interest == pytest.approx(payment * 240 - 200_000, rel=1e-3)


def test_early_repayment_indemnity_is_the_lower_legal_cap():
    assert early_repayment_indemnity(20_000, 3.3) == 330.0  # 6 months of interest < 3 %
    assert early_repayment_indemnity(20_000, 12.0) == 600.0  # 3 % < 6 months of interest


def test_payoff_redirects_freed_payments_to_the_highest_rate():
    loans = [("cheap", 1000.0, 0.0, 100.0, 0.0), ("dear", 1000.0, 20.0, 100.0, 0.0)]
    baseline = simulate_payoff(loans, 0.0, "avalanche", redirect=False)
    plan = simulate_payoff(loans, 100.0, "avalanche", redirect=True)
    assert plan.total_interest < baseline.total_interest
    assert plan.order[0] == "dear"  # the extra 100 goes to the 20 % loan first
    assert plan.months < baseline.months

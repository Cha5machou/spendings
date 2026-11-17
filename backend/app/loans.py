"""Loan maths: projection of future payments, payoff planning and what-if simulations.

Everything works on plain dataclasses so it is easy to test; the router does the I/O.
Amounts are euros, rates are nominal annual percent.
"""

import calendar
from dataclasses import dataclass, field
from datetime import date

MAX_MONTHS = 600
EARLY_REPAYMENT_CAP_RATE = 0.03  # French law: indemnity <= 3 % of the capital repaid ...
EARLY_REPAYMENT_MONTHS_OF_INTEREST = 6  # ... and <= 6 months of interest


@dataclass
class Payment:
    due_date: date
    principal: float
    interest: float
    insurance: float
    total: float
    balance_after: float


@dataclass
class LoanState:
    """The fields of a Loan the maths needs (decoupled from the database model)."""

    name: str
    remaining_balance: float
    annual_rate: float
    monthly_payment: float
    insurance_monthly: float = 0.0
    next_payment_date: date | None = None
    balance_date: date | None = None
    payments_remaining: int | None = None
    schedule: list = field(default_factory=list)  # LoanScheduleEntry-like rows, optional


def add_months(day: date, months: int) -> date:
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def project_payments(loan: LoanState) -> list[Payment]:
    """All payments after loan.balance_date, from the official table when there is one."""
    if loan.schedule:
        rows = [row for row in loan.schedule if loan.balance_date is None or row.due_date > loan.balance_date]
        return [
            Payment(row.due_date, row.principal, row.interest, row.insurance, row.total, round(row.capital_before - row.principal, 2))
            for row in sorted(rows, key=lambda row: row.due_date)
        ]
    if loan.remaining_balance <= 0 or loan.next_payment_date is None or loan.monthly_payment <= 0:
        return []
    monthly_rate = loan.annual_rate / 1200
    balance = loan.remaining_balance
    payments = []
    for index in range(MAX_MONTHS):
        due = add_months(loan.next_payment_date, index)
        interest = round(balance * monthly_rate, 2)
        owed = balance + interest + loan.insurance_monthly
        counted_last = loan.payments_remaining is not None and index == loan.payments_remaining - 1
        is_last = owed <= loan.monthly_payment + 0.005 or counted_last
        total = round(owed if is_last else loan.monthly_payment, 2)
        principal = round(balance if is_last else total - interest - loan.insurance_monthly, 2)
        if principal <= 0:
            break  # the payment does not even cover interest: it never amortises
        balance = round(balance - principal, 2)
        payments.append(Payment(due, principal, interest, loan.insurance_monthly, total, max(balance, 0.0)))
        if is_last or balance <= 0:
            break
    return payments


def split_by_today(payments: list[Payment], today: date) -> tuple[list[Payment], list[Payment]]:
    past = [payment for payment in payments if payment.due_date <= today]
    future = [payment for payment in payments if payment.due_date > today]
    return past, future


# --- payoff planner ---------------------------------------------------------


@dataclass
class PayoffResult:
    months: int
    total_interest: float
    payoff_month: dict  # loan name -> month index (1 = next month) when it reaches zero
    order: list  # loan names in the order they are cleared


def simulate_payoff(loans: list[tuple[str, float, float, float, float]], extra: float, strategy: str, redirect: bool) -> PayoffResult:
    """loans: (name, balance, annual_rate_percent, minimum_payment_all_in, insurance_monthly).

    Each month every loan gets its minimum. With `redirect`, the pool made of `extra`, the minimums of
    loans already cleared and any unused part of a final payment goes to the target picked by
    `strategy`: 'avalanche' (highest rate first) or 'snowball' (smallest balance first).
    Without `redirect` it is the plain schedule, used as the baseline."""
    state = {
        name: {"balance": balance, "rate": rate / 1200, "rate_pct": rate, "minimum": minimum, "insurance": insurance}
        for name, balance, rate, minimum, insurance in loans if balance > 0
    }
    total_interest = 0.0
    payoff_month: dict = {}
    order: list = []
    freed_minimums = 0.0
    month = 0
    while state and month < MAX_MONTHS:
        month += 1
        surplus = (extra + freed_minimums) if redirect else 0.0
        cleared = []
        for name, loan in state.items():
            interest = loan["balance"] * loan["rate"]
            total_interest += interest
            loan["balance"] += interest
            payment = min(loan["minimum"], loan["balance"] + loan["insurance"])
            loan["balance"] = max(loan["balance"] - (payment - loan["insurance"]), 0.0)
            if redirect:
                surplus += loan["minimum"] - payment
        if redirect and surplus > 0.005:
            key = (lambda item: (-item[1]["rate_pct"], item[1]["balance"])) if strategy == "avalanche" else (lambda item: (item[1]["balance"], -item[1]["rate_pct"]))
            for name, loan in sorted(((name, loan) for name, loan in state.items() if loan["balance"] > 0.005), key=key):
                applied = min(surplus, loan["balance"])
                loan["balance"] -= applied
                surplus -= applied
                if surplus <= 0.005:
                    break
        for name, loan in state.items():
            if loan["balance"] <= 0.005:
                cleared.append(name)
        for name in cleared:
            payoff_month[name] = month
            order.append(name)
            if redirect:
                freed_minimums += state[name]["minimum"]
            del state[name]
    return PayoffResult(month, round(total_interest, 2), payoff_month, order)


# --- mortgage what-if -------------------------------------------------------


def amortise(balance: float, annual_rate: float, payment_without_insurance: float, insurance_ratio: float) -> tuple[int, float, float]:
    """Months to clear the balance, total interest, total insurance. insurance_ratio = monthly insurance / balance."""
    monthly_rate = annual_rate / 1200
    months, interest_total, insurance_total = 0, 0.0, 0.0
    while balance > 0.005 and months < MAX_MONTHS:
        months += 1
        interest = balance * monthly_rate
        insurance = balance * insurance_ratio
        principal = min(payment_without_insurance - interest, balance)
        if principal <= 0:
            return MAX_MONTHS, float("inf"), float("inf")
        balance -= principal
        interest_total += interest
        insurance_total += insurance
    return months, round(interest_total, 2), round(insurance_total, 2)


def annuity_payment(balance: float, annual_rate: float, months: int) -> float:
    monthly_rate = annual_rate / 1200
    if monthly_rate == 0:
        return balance / months
    return balance * monthly_rate / (1 - (1 + monthly_rate) ** -months)


def early_repayment_indemnity(lump_sum: float, annual_rate: float) -> float:
    """Legal ceiling of the indemnity on a prepayment (banks often charge exactly this)."""
    return round(min(lump_sum * EARLY_REPAYMENT_CAP_RATE, lump_sum * annual_rate / 1200 * EARLY_REPAYMENT_MONTHS_OF_INTEREST), 2)

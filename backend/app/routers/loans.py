"""Loans and credits: stored balances, projected payments, debt-service timeline,
payoff planner and mortgage what-if. Maths lives in app/loans.py."""

import io
import re
from datetime import date

import pdfplumber
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from app.database import get_session
from app.loans import (
    LoanState, add_months, amortise, annuity_payment, early_repayment_indemnity,
    project_payments, simulate_payoff, split_by_today,
)
from app.models import Loan, LoanKind, LoanScheduleEntry, Transaction

router = APIRouter(prefix="/loans", tags=["loans"])

TIMELINE_MONTHS = 36
SCHEDULE_ROW = re.compile(r"^(\d{2}/\d{2}/\d{4})\s+(\d+,\d{2})\s+(\d+,\d{2})\s+(\d+,\d{2})\s+(\d+,\d{2})\s+(\d+,\d{2})\s*$")


class LoanPayload(BaseModel):
    name: str | None = None
    lender: str | None = None
    kind: LoanKind | None = None
    account_id: int | None = None
    is_active: bool | None = None
    original_amount: float | None = None
    start_date: date | None = None
    remaining_balance: float | None = None
    balance_date: date | None = None
    annual_rate: float | None = None
    taeg: float | None = None
    monthly_payment: float | None = None
    insurance_monthly: float | None = None
    next_payment_date: date | None = None
    payments_remaining: int | None = None
    end_date: date | None = None
    payment_pattern: str | None = None
    notes: str | None = None


def loan_state(loan: Loan, schedule: list[LoanScheduleEntry]) -> LoanState:
    return LoanState(
        name=loan.name, remaining_balance=loan.remaining_balance, annual_rate=loan.annual_rate,
        monthly_payment=loan.monthly_payment, insurance_monthly=loan.insurance_monthly,
        next_payment_date=loan.next_payment_date, balance_date=loan.balance_date,
        payments_remaining=loan.payments_remaining, schedule=schedule,
    )


def describe(loan: Loan, schedule: list[LoanScheduleEntry], today: date, session: Session) -> dict:
    payments = project_payments(loan_state(loan, schedule))
    past, future = split_by_today(payments, today)
    balance = past[-1].balance_after if past else loan.remaining_balance
    last_seen = None
    if loan.payment_pattern:
        match = session.exec(
            select(Transaction).where(Transaction.amount < 0).order_by(Transaction.date.desc())
        ).all()
        pattern = loan.payment_pattern.lower()
        found = next((t for t in match if pattern in t.label.lower()), None)
        if found:
            last_seen = {"date": found.date.isoformat(), "amount": found.amount}
    return {
        **loan.model_dump(),
        "has_schedule": bool(schedule),
        "current_balance": round(balance if loan.is_active else 0.0, 2),
        "months_left": len(future),
        "projected_end": future[-1].due_date.isoformat() if future else None,
        "next_payment": {"date": future[0].due_date.isoformat(), "total": future[0].total} if future else None,
        "remaining_interest": round(sum(payment.interest for payment in future), 2),
        "remaining_insurance": round(sum(payment.insurance for payment in future), 2),
        "remaining_total": round(sum(payment.total for payment in future), 2),
        "progress": round(1 - balance / loan.original_amount, 4) if loan.original_amount else None,
        "last_seen_payment": last_seen,
        "_future": future,
    }


def load_all(session: Session, today: date) -> list[dict]:
    loans = session.exec(select(Loan).order_by(Loan.kind, Loan.name)).all()
    schedules: dict[int, list] = {}
    for entry in session.exec(select(LoanScheduleEntry)).all():
        schedules.setdefault(entry.loan_id, []).append(entry)
    return [describe(loan, schedules.get(loan.id, []), today, session) for loan in loans]


@router.get("")
def list_loans(session: Session = Depends(get_session)):
    today = date.today()
    described = load_all(session, today)
    active = [loan for loan in described if loan["is_active"] and loan["current_balance"] > 0]

    # Debt-service timeline: what leaves the account each month, per loan.
    first_month = date(today.year, today.month, 1)
    months = [add_months(first_month, index) for index in range(TIMELINE_MONTHS + 1)]
    timeline = []
    for month_start in months:
        row = {"month": month_start.strftime("%Y-%m"), "total": 0.0}
        for loan in active:
            amount = sum(p.total for p in loan["_future"] if p.due_date.year == month_start.year and p.due_date.month == month_start.month)
            row[str(loan["id"])] = round(amount, 2)
            row["total"] += amount
        row["total"] = round(row["total"], 2)
        timeline.append(row)

    total_debt = sum(loan["current_balance"] for loan in active)
    # What leaves the accounts at the next instalment of each loan (one instalment per loan per month).
    monthly_now = sum(loan["next_payment"]["total"] for loan in active if loan["next_payment"])
    typical_income = None
    try:
        from app.routers.insights import insights as compute_insights
        overview = compute_insights(months=12, session=session)
        typical_income = None if overview.get("empty") else overview["overview"]["typical_income"]
    except Exception:  # noqa: BLE001 - income is a nice-to-have here
        typical_income = None

    totals = {
        "total_debt": round(total_debt, 2),
        "monthly_payments": round(monthly_now, 2),
        "average_rate": round(sum(loan["current_balance"] * loan["annual_rate"] for loan in active) / total_debt, 2) if total_debt else 0.0,
        "remaining_interest_and_insurance": round(sum(loan["remaining_interest"] + loan["remaining_insurance"] for loan in active), 2),
        "typical_income": typical_income,
        "debt_to_income": round(monthly_now / typical_income, 4) if typical_income else None,
        "last_payment_date": max((loan["projected_end"] for loan in active if loan["projected_end"]), default=None),
    }
    for loan in described:
        loan.pop("_future")
    return {
        "loans": described,
        "totals": totals,
        "timeline": timeline,
        "timeline_loans": [{"id": loan["id"], "name": loan["name"], "kind": loan["kind"]} for loan in active],
    }


@router.post("", status_code=201)
def create_loan(payload: LoanPayload, session: Session = Depends(get_session)):
    if not payload.name:
        raise HTTPException(422, "name is required")
    loan = Loan(**payload.model_dump(exclude_unset=True))
    session.add(loan)
    session.commit()
    session.refresh(loan)
    return loan


@router.patch("/{loan_id}")
def update_loan(loan_id: int, payload: LoanPayload, session: Session = Depends(get_session)):
    loan = session.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(loan, field, value)
    session.add(loan)
    session.commit()
    session.refresh(loan)
    return loan


@router.delete("/{loan_id}", status_code=204)
def delete_loan(loan_id: int, session: Session = Depends(get_session)):
    loan = session.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    for entry in session.exec(select(LoanScheduleEntry).where(LoanScheduleEntry.loan_id == loan_id)).all():
        session.delete(entry)
    session.delete(loan)
    session.commit()


@router.post("/{loan_id}/schedule")
async def import_schedule(loan_id: int, file: UploadFile, session: Session = Depends(get_session)):
    """Read the amortisation table of a loan offer (PDF with rows: date, capital due,
    principal, interest, insurance, instalment) and use it instead of the estimate."""
    loan = session.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    content = await file.read()
    number = lambda text: float(text.replace(",", "."))  # noqa: E731
    rows = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            for line in (page.extract_text() or "").splitlines():
                match = SCHEDULE_ROW.match(line.strip())
                if match:
                    day, month, year = match.group(1).split("/")
                    rows.append(LoanScheduleEntry(
                        loan_id=loan_id, due_date=date(int(year), int(month), int(day)),
                        capital_before=number(match.group(2)), principal=number(match.group(3)),
                        interest=number(match.group(4)), insurance=number(match.group(5)), total=number(match.group(6)),
                    ))
    if not rows:
        raise HTTPException(422, "No amortisation table found in this PDF")
    for entry in session.exec(select(LoanScheduleEntry).where(LoanScheduleEntry.loan_id == loan_id)).all():
        session.delete(entry)
    for entry in rows:
        session.add(entry)
    session.commit()
    return {"rows": len(rows), "first": rows[0].due_date.isoformat(), "last": rows[-1].due_date.isoformat()}


@router.get("/payoff")
def payoff_plan(extra: float = 0.0, strategy: str = "avalanche", include_mortgage: bool = False, session: Session = Depends(get_session)):
    """Keep paying today's total, redirect freed payments (plus optional extra) to the best target."""
    today = date.today()
    candidates = [
        loan for loan in load_all(session, today)
        if loan["is_active"] and loan["current_balance"] > 0 and (include_mortgage or loan["kind"] != LoanKind.mortgage.value)
    ]
    inputs = [(loan["name"], loan["current_balance"], loan["annual_rate"], loan["monthly_payment"], loan["insurance_monthly"]) for loan in candidates]
    baseline = simulate_payoff(inputs, 0.0, strategy, redirect=False)
    plan = simulate_payoff(inputs, extra, strategy, redirect=True)
    first_month = date(today.year, today.month, 1)
    return {
        "strategy": strategy,
        "extra": extra,
        "baseline": {"months": baseline.months, "interest": baseline.total_interest, "debt_free": add_months(first_month, baseline.months).isoformat()},
        "plan": {"months": plan.months, "interest": plan.total_interest, "debt_free": add_months(first_month, plan.months).isoformat()},
        "interest_saved": round(baseline.total_interest - plan.total_interest, 2),
        "months_saved": baseline.months - plan.months,
        "order": [
            {"name": name, "month": plan.payoff_month[name], "date": add_months(first_month, plan.payoff_month[name]).isoformat(),
             "baseline_date": add_months(first_month, baseline.payoff_month[name]).isoformat()}
            for name in plan.order
        ],
        "monthly_budget": round(sum(loan["monthly_payment"] for loan in candidates) + extra, 2),
    }


@router.get("/{loan_id}/what-if")
def what_if(loan_id: int, lump_sum: float = 0.0, new_rate: float | None = None, fees: float = 0.0, session: Session = Depends(get_session)):
    """Two questions on one loan: what a lump-sum prepayment saves, and whether a lower rate is worth its fees."""
    today = date.today()
    loan_row = session.get(Loan, loan_id)
    if loan_row is None:
        raise HTTPException(404, "Loan not found")
    schedule = session.exec(select(LoanScheduleEntry).where(LoanScheduleEntry.loan_id == loan_id)).all()
    described = describe(loan_row, schedule, today, session)
    balance = described["current_balance"]
    if balance <= 0 or not described["next_payment"]:
        raise HTTPException(422, "This loan has no remaining balance")
    first = described["_future"][0]
    payment = first.total - first.insurance
    insurance_ratio = first.insurance / balance
    rate = loan_row.annual_rate
    base_months, base_interest, base_insurance = amortise(balance, rate, payment, insurance_ratio)
    if schedule and base_insurance > 0:
        # Insurance in the official table is not exactly proportional to the capital: scale to its real total.
        insurance_ratio *= described["remaining_insurance"] / base_insurance
        base_months, base_interest, base_insurance = amortise(balance, rate, payment, insurance_ratio)
    base_cost = base_interest + base_insurance
    result = {
        "balance": balance, "annual_rate": rate, "payment_without_insurance": round(payment, 2),
        "baseline": {"months": base_months, "interest": base_interest, "insurance": base_insurance, "cost": round(base_cost, 2)},
        "scheduled": {"months": described["months_left"], "interest": described["remaining_interest"], "insurance": described["remaining_insurance"]},
    }
    if lump_sum > 0:
        reduced = max(balance - lump_sum, 0.0)
        indemnity = early_repayment_indemnity(lump_sum, rate)
        months, interest, insurance = amortise(reduced, rate, payment, insurance_ratio)
        lower_payment = annuity_payment(reduced, rate, base_months) if reduced else 0.0
        result["lump_sum"] = {
            "amount": lump_sum, "indemnity_max": indemnity,
            "shorter_duration": {"months": months, "months_saved": base_months - months, "cost_saved": round(base_cost - interest - insurance - indemnity, 2)},
            "lower_payment": {"payment": round(lower_payment, 2), "monthly_saving": round(payment - lower_payment, 2)},
            "note": "The indemnity is the legal ceiling (3 % of the capital repaid or 6 months of interest, whichever is lower); check your contract.",
        }
    if new_rate is not None:
        new_payment = annuity_payment(balance, new_rate, base_months)
        new_interest = new_payment * base_months - balance
        monthly_saving = payment - new_payment
        result["renegotiation"] = {
            "new_rate": new_rate, "new_payment": round(new_payment, 2), "monthly_saving": round(monthly_saving, 2),
            "interest_saved": round(base_interest - new_interest, 2), "fees": fees,
            "net_saving": round(base_interest - new_interest - fees, 2),
            "break_even_months": round(fees / monthly_saving, 1) if monthly_saving > 0 and fees else 0,
        }
    return result

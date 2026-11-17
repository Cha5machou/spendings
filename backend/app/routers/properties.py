"""Rental properties: real cash flow from transactions, the monthly economics implied by the lease,
and a sale scenario. Loan maths come from app/loans.py through the loans router."""

import calendar
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.database import get_session
from app.loans import early_repayment_indemnity
from app.models import Loan, LoanScheduleEntry, Property, Transaction
from app.routers.loans import describe

router = APIRouter(prefix="/properties", tags=["properties"])

FORFAIT_ACQUISITION_COSTS = 0.075  # French flat allowance for purchase costs when computing a gain
CAPITAL_GAIN_TAX_RATE = 0.362  # 19 % income tax + 17.2 % social charges (no abatement before year 6)


class PropertyPayload(BaseModel):
    name: str | None = None
    address: str | None = None
    furnished: bool | None = None
    surface_m2: float | None = None
    purchase_price: float | None = None
    purchase_date: date | None = None
    furnishing_and_works: float | None = None
    market_value: float | None = None
    loan_id: int | None = None
    income_category_id: int | None = None
    cost_category_id: int | None = None
    mortgage_category_id: int | None = None
    lease_start: date | None = None
    monthly_rent: float | None = None
    monthly_charges: float | None = None
    deposit: float | None = None
    agency: str | None = None
    management_fee_rate: float | None = None
    rent_insurance_rate: float | None = None
    syndic_quarterly: float | None = None
    property_tax_yearly: float | None = None
    notes: str | None = None


def month_key(day: date) -> str:
    return day.strftime("%Y-%m")


def loan_balance(session: Session, loan_id: int | None) -> tuple[Loan | None, dict | None]:
    if loan_id is None:
        return None, None
    loan = session.get(Loan, loan_id)
    if loan is None:
        return None, None
    schedule = session.exec(select(LoanScheduleEntry).where(LoanScheduleEntry.loan_id == loan_id)).all()
    return loan, describe(loan, schedule, date.today(), session)


def describe_property(prop: Property, session: Session) -> dict:
    today = date.today()
    transactions = session.exec(select(Transaction).where(Transaction.date <= today).order_by(Transaction.date, Transaction.id)).all()
    by_month = defaultdict(lambda: {"rent": 0.0, "costs": 0.0, "mortgage": 0.0})
    for transaction in transactions:
        if transaction.category_id is None:
            continue
        key = month_key(transaction.date)
        if transaction.category_id == prop.income_category_id:
            by_month[key]["rent"] += transaction.amount
        elif transaction.category_id == prop.cost_category_id:
            by_month[key]["costs"] += transaction.amount
        elif transaction.category_id == prop.mortgage_category_id:
            by_month[key]["mortgage"] += transaction.amount

    months = []
    cumulative = 0.0
    if by_month:
        year, month = map(int, min(by_month).split("-"))
        last = month_key(today)
        while f"{year:04d}-{month:02d}" <= last:
            key = f"{year:04d}-{month:02d}"
            row = by_month.get(key, {"rent": 0.0, "costs": 0.0, "mortgage": 0.0})
            net = row["rent"] + row["costs"] + row["mortgage"]
            cumulative += net
            months.append({"month": key, "rent": round(row["rent"], 2), "costs": round(row["costs"], 2),
                           "mortgage": round(row["mortgage"], 2), "net": round(net, 2), "cumulative": round(cumulative, 2)})
            month += 1
            if month == 13:
                year, month = year + 1, 1
    totals = {key: round(sum(row[key] for row in months), 2) for key in ("rent", "costs", "mortgage", "net")}
    months_with_rent = sum(1 for row in months if row["rent"] > 0)

    # Monthly economics implied by the lease and the contracts (what a normal month looks like now).
    loan, loan_info = loan_balance(session, prop.loan_id)
    collected = prop.monthly_rent + prop.monthly_charges
    management_fee = collected * prop.management_fee_rate / 100
    rent_insurance = collected * prop.rent_insurance_rate / 100
    syndic = prop.syndic_quarterly / 3
    property_tax = prop.property_tax_yearly / 12
    mortgage_payment = loan_info["next_payment"]["total"] if loan_info and loan_info["next_payment"] else 0.0
    # Charge provisions the tenant pays are meant to cover the co-ownership calls: count them as pass-through.
    lines = [
        {"label": "Rent", "amount": prop.monthly_rent},
        {"label": "Charge provisions paid by the tenant", "amount": prop.monthly_charges},
        {"label": f"Agency management fee ({prop.management_fee_rate:g} % incl. VAT)", "amount": -management_fee},
        {"label": f"Guaranteed-rent insurance ({prop.rent_insurance_rate:g} %)", "amount": -rent_insurance},
        {"label": "Co-ownership provisions (syndic)", "amount": -syndic},
        {"label": "Property tax", "amount": -property_tax},
        {"label": "Mortgage instalment (with insurance)", "amount": -mortgage_payment},
    ]
    monthly_result = round(sum(line["amount"] for line in lines), 2)
    net_from_agency = round(collected - management_fee - rent_insurance, 2)
    operating_result = round(prop.monthly_rent + prop.monthly_charges - management_fee - rent_insurance - syndic - property_tax, 2)

    invested = (prop.purchase_price or 0.0) + prop.furnishing_and_works
    yearly_rent = prop.monthly_rent * 12
    yields = {
        "gross": round(yearly_rent / prop.purchase_price, 4) if prop.purchase_price else None,
        "net_of_costs": round(operating_result * 12 / invested, 4) if invested else None,
        "loan_rate": loan.annual_rate / 100 if loan else None,
    }

    # Sensitivity: what moves the monthly result most.
    levers = []
    if loan_info and loan_info["current_balance"] > 0:
        levers.append({"label": "Each 0,5 point less on the mortgage rate", "monthly": round(loan_info["current_balance"] * 0.005 / 12, 2)})
    if collected:
        levers.append({"label": "Each 50 € more rent (before the agency fee and insurance)", "monthly": round(50 * (1 - (prop.management_fee_rate + prop.rent_insurance_rate) / 100), 2)})
        levers.append({"label": "Each point less on the agency fee", "monthly": round(collected / 100, 2)})

    checks = []
    if prop.syndic_quarterly > 0:
        syndic_debits = sorted(
            (t.date for t in transactions if t.category_id == prop.cost_category_id and t.amount < 0 and any(word in t.label.lower() for word in ("sdc", "syndic"))),
        )
        last_syndic = syndic_debits[-1] if syndic_debits else None
        if last_syndic is None or (today - last_syndic).days > 100:
            checks.append({
                "severity": "high",
                "title": "No co-ownership payment found since " + (last_syndic.strftime("%d/%m/%Y") if last_syndic else "the start"),
                "detail": f"The syndic calls {prop.syndic_quarterly:.2f} € every quarter (1 January, April, July, October), plus works calls. "
                          "Your accounts show no matching debit after the last one, so the July and October calls may be unpaid, "
                          "or paid from an account that is not imported here. Check the syndic's owner account: arrears can bring late fees.",
            })
    if prop.furnished:
        checks.append({
            "severity": "info",
            "title": "Furnished let: check your tax regime with an accountant",
            "detail": "Furnished rental income is normally taxed as industrial and commercial profit (LMNP). Under the real regime, depreciation of the building and furniture "
                      "can reduce taxable rent to close to zero for many years, and the furnishing and works you paid are usually deductible or depreciable. "
                      "Confirm that the activity is registered and which regime applies; this is the biggest lever that is not visible in your bank statements.",
        })
    if prop.property_tax_yearly and prop.purchase_price and prop.property_tax_yearly < prop.purchase_price * 0.002:
        checks.append({
            "severity": "medium",
            "title": "Property tax will rise",
            "detail": f"{prop.property_tax_yearly:.0f} € a year looks like a partial amount: new constructions are exempt for two years. "
                      "Budget several hundred euros a year, up to about a month of rent, until the first full notice arrives.",
        })
    if prop.lease_start:
        anniversary = prop.lease_start.replace(year=today.year if prop.lease_start.replace(year=today.year) >= today else today.year + 1)
        checks.append({
            "severity": "low",
            "title": f"Rent revision due on {anniversary.strftime('%d/%m/%Y')}",
            "detail": "The lease revises the rent every year on its anniversary, based on the INSEE rent reference index (IRL). The agency must apply it; ask them to.",
        })
    if monthly_result < 0:
        checks.insert(0, {
            "severity": "medium" if monthly_result > -300 else "high",
            "title": f"The flat costs you {-monthly_result:,.0f} € a month once it is rented".replace(",", " "),
            "detail": "That is before any tax effect. It shrinks with a lower mortgage rate, a higher rent or lower agency costs, see the levers below.",
        })

    return {
        **prop.model_dump(),
        "checks": checks,
        "months": months,
        "totals": totals,
        "months_with_rent": months_with_rent,
        "lines": [{"label": line["label"], "amount": round(line["amount"], 2)} for line in lines],
        "monthly_result": monthly_result,
        "operating_result": operating_result,
        "net_from_agency": net_from_agency,
        "yields": yields,
        "levers": levers,
        "invested": round(invested, 2),
        "loan": {"id": loan.id, "name": loan.name, "balance": loan_info["current_balance"], "rate": loan.annual_rate,
                 "remaining_months": loan_info["months_left"]} if loan and loan_info else None,
    }


@router.get("")
def list_properties(session: Session = Depends(get_session)):
    return [describe_property(prop, session) for prop in session.exec(select(Property).order_by(Property.name)).all()]


@router.post("", status_code=201)
def create_property(payload: PropertyPayload, session: Session = Depends(get_session)):
    if not payload.name:
        raise HTTPException(422, "name is required")
    prop = Property(**payload.model_dump(exclude_unset=True))
    session.add(prop)
    session.commit()
    session.refresh(prop)
    return prop


@router.patch("/{property_id}")
def update_property(property_id: int, payload: PropertyPayload, session: Session = Depends(get_session)):
    prop = session.get(Property, property_id)
    if prop is None:
        raise HTTPException(404, "Property not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(prop, field, value)
    session.add(prop)
    session.commit()
    session.refresh(prop)
    return prop


@router.delete("/{property_id}", status_code=204)
def delete_property(property_id: int, session: Session = Depends(get_session)):
    prop = session.get(Property, property_id)
    if prop is None:
        raise HTTPException(404, "Property not found")
    session.delete(prop)
    session.commit()


@router.get("/{property_id}/sale")
def sale_scenario(property_id: int, price: float, agent_fee_percent: float = 5.0, session: Session = Depends(get_session)):
    """What is left (or still to be paid) if the property is sold at `price` and the mortgage is cleared."""
    prop = session.get(Property, property_id)
    if prop is None:
        raise HTTPException(404, "Property not found")
    loan, loan_info = loan_balance(session, prop.loan_id)
    balance = loan_info["current_balance"] if loan_info else 0.0
    rate = loan.annual_rate if loan else 0.0
    agent_fee = price * agent_fee_percent / 100
    indemnity = early_repayment_indemnity(balance, rate) if balance else 0.0
    acquisition_cost = (prop.purchase_price or 0.0) * (1 + FORFAIT_ACQUISITION_COSTS)
    taxable_gain = max(0.0, price - agent_fee - acquisition_cost)
    gain_tax = taxable_gain * CAPITAL_GAIN_TAX_RATE
    proceeds = price - agent_fee - balance - indemnity - gain_tax
    monthly = describe_property(prop, session)["monthly_result"]
    return {
        "price": price, "agent_fee": round(agent_fee, 2), "loan_balance": round(balance, 2), "early_repayment_indemnity_max": indemnity,
        "estimated_gain_tax": round(gain_tax, 2), "net_proceeds": round(proceeds, 2),
        "monthly_result_if_kept": monthly,
        "months_of_losses_equivalent": round(-proceeds / -monthly, 1) if proceeds < 0 and monthly < 0 else None,
        "note": "Gain tax uses the flat 36,2 % rate and a 7,5 % flat allowance on the purchase price; it ignores furnished-rental depreciation "
                "recapture and any abatement. Treat it as an order of magnitude and confirm with a notary or accountant.",
    }

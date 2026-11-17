"""Goals and plan: a month-by-month projection of what is left after everything, where it goes,
the effect of selling the rented flat, and what a purchase in Aix could look like.

Assumptions are explicit and editable (PlanSettings). Nothing here is a forecast of markets:
returns are 0 % unless the user sets one."""

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from app.database import get_session
from app.loans import add_months, annuity_payment, early_repayment_indemnity
from app.models import AccountKind, Loan, LoanKind, PlanSettings, Property, Payslip
from app.routers.loans import load_all

router = APIRouter(prefix="/plan", tags=["plan"])

HORIZON_END = date(2030, 12, 1)
PRICE_GRID = [200_000, 250_000, 300_000, 350_000, 400_000]
HOUSING_DELTAS = [0, 100, 200, 300]
FORFAIT_ACQUISITION_COSTS = 0.075
CAPITAL_GAIN_TAX_RATE = 0.362


class SettingsPayload(BaseModel):
    split_pea: float | None = None
    split_cto: float | None = None
    split_livrets: float | None = None
    av_monthly: float | None = None
    livrets_target: float | None = None
    expected_return_pct: float | None = None
    new_credit_monthly: float | None = None
    housing_delta: float | None = None
    sale_date: date | None = None
    sale_price: float | None = None
    sale_agent_fee_pct: float | None = None
    purchase_date: date | None = None
    purchase_price: float | None = None
    purchase_savings_share_pct: float | None = None
    loan_rate_pct: float | None = None
    loan_years: int | None = None
    loan_insurance_pct: float | None = None
    notary_fees_pct: float | None = None
    rent_weight_pct: float | None = None
    max_debt_ratio_pct: float | None = None
    clear_sale_price: bool = False
    clear_purchase_price: bool = False


def get_settings(session: Session) -> PlanSettings:
    settings = session.get(PlanSettings, 1)
    if settings is None:
        settings = PlanSettings(id=1)
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return settings


def month_start(day: date) -> date:
    return date(day.year, day.month, 1)


def loan_capacity(payment: float, annual_rate: float, years: int, insurance_pct: float) -> float:
    """Capital a monthly payment (insurance included) can carry."""
    factor = annuity_payment(1.0, annual_rate, years * 12) + insurance_pct / 1200
    return payment / factor


def monthly_payment_for(capital: float, annual_rate: float, years: int, insurance_pct: float) -> float:
    return capital * (annuity_payment(1.0, annual_rate, years * 12) + insurance_pct / 1200)


def build_context(session: Session) -> dict:
    """Everything the projection starts from, read from the other modules."""
    from app.routers.insights import insights as compute_insights
    from app.routers.wealth import wealth as compute_wealth

    today = date.today()
    overview = compute_insights(months=12, session=session)
    rows = [] if overview.get("empty") else [row for row in overview["categories"] if row["kind"] == "expense"]
    months = max(overview["overview"]["months"], 1) if not overview.get("empty") else 1
    typical = lambda row: row["average"] - row["one_off_total"] / months  # noqa: E731
    properties = session.exec(select(Property)).all()
    prop = properties[0] if properties else None
    cost_category = prop.cost_category_id if prop else None
    is_debt = lambda row: any(word in row["name"].lower() for word in ("mortgage", "loan", "credit"))  # noqa: E731
    core_spending = sum(typical(row) for row in rows if not is_debt(row) and row["category_id"] != cost_category)
    housing = sum(typical(row) for row in rows if "housing" in row["name"].lower())
    payslip = session.exec(select(Payslip).order_by(Payslip.month.desc())).first()
    wealth = compute_wealth(session=session)

    buckets = {"pea": 0.0, "cto": 0.0, "av": 0.0, "livrets": 0.0}
    for account in wealth["accounts"]:
        name = account["name"].lower()
        if account["kind"] == AccountKind.savings.value:
            buckets["livrets"] += account["balance"]
        elif "assurance" in name:
            buckets["av"] += account["balance"]
        elif "pea" in name:
            buckets["pea"] += account["balance"]
        else:
            buckets["cto"] += account["balance"]

    loans = [loan for loan in load_all(session, today) if loan["is_active"] and loan["current_balance"] > 0]
    rent_net = 0.0
    flat_costs = 0.0
    rent_for_bank = 0.0
    if prop:
        collected = prop.monthly_rent + prop.monthly_charges
        rent_net = collected * (1 - (prop.management_fee_rate + prop.rent_insurance_rate) / 100)
        flat_costs = prop.syndic_quarterly / 3 + prop.property_tax_yearly / 12
        rent_for_bank = prop.monthly_rent
    return {
        "salary_net": payslip.net_paid if payslip else 0.0,
        "salary_net_before_tax": payslip.net_before_tax if payslip else 0.0,
        "rent_net": round(rent_net, 2), "rent_for_bank": rent_for_bank, "flat_costs": round(flat_costs, 2),
        "core_spending": round(core_spending, 2), "housing_cost": round(housing, 2),
        "balances": {key: round(value, 2) for key, value in buckets.items()},
        "checking": round(wealth["net_worth"]["checking"], 2),
        "loans": loans, "property": prop,
        "essential_typical": overview["overview"]["essential_typical"] if not overview.get("empty") else 0.0,
    }


def loan_balance_before(loans: list[dict], kind: LoanKind, day: date) -> float:
    """Capital still due on loans of `kind` just before `day` (from their payment schedules)."""
    total = 0.0
    for loan in loans:
        if loan["kind"] != kind.value:
            continue
        paid = [payment for payment in loan["_future"] if payment.due_date < day]
        total += paid[-1].balance_after if paid else loan["current_balance"]
    return total


def sale_outcome(context: dict, settings: PlanSettings) -> dict | None:
    prop = context["property"]
    if prop is None or settings.sale_date is None:
        return None
    price = settings.sale_price or prop.market_value or prop.purchase_price or 0.0
    balance = loan_balance_before(context["loans"], LoanKind.mortgage, settings.sale_date)
    rate = next((loan["annual_rate"] for loan in context["loans"] if loan["kind"] == LoanKind.mortgage.value), 0.0)
    agent_fee = price * settings.sale_agent_fee_pct / 100
    indemnity = early_repayment_indemnity(balance, rate) if balance else 0.0
    acquisition = (prop.purchase_price or 0.0) * (1 + FORFAIT_ACQUISITION_COSTS)
    gain_tax = max(0.0, price - agent_fee - acquisition) * CAPITAL_GAIN_TAX_RATE
    return {
        "date": settings.sale_date.isoformat(), "price": round(price, 2), "price_basis": "your sale price" if settings.sale_price else ("your market estimate" if prop.market_value else "the purchase price"),
        "agent_fee": round(agent_fee, 2), "loan_balance": round(balance, 2), "indemnity": indemnity, "gain_tax": round(gain_tax, 2),
        "net_proceeds": round(price - agent_fee - balance - indemnity - gain_tax, 2),
    }


def project(context: dict, settings: PlanSettings, housing_delta: float) -> list[dict]:
    """Month-by-month cash flow and balances from next month until the end of 2030 (or later if needed)."""
    today = date.today()
    start = add_months(month_start(today), 1)
    end = HORIZON_END
    for day in (settings.sale_date, settings.purchase_date):
        if day and day > end:
            end = add_months(month_start(day), 6)
    sale = sale_outcome(context, settings)
    buy_date = month_start(settings.purchase_date) if settings.purchase_date else None
    sale_month = month_start(settings.sale_date) if settings.sale_date and sale else None

    payments_by_month: dict[tuple[str, int, int], float] = {}
    for loan in context["loans"]:
        for payment in loan["_future"]:
            key = (loan["kind"], payment.due_date.year, payment.due_date.month)
            payments_by_month[key] = payments_by_month.get(key, 0.0) + payment.total

    monthly_return = (1 + settings.expected_return_pct / 100) ** (1 / 12) - 1
    split_total = (settings.split_pea + settings.split_cto + settings.split_livrets) or 1.0
    balances = dict(context["balances"])
    cash = context["checking"]
    sale_pot = 0.0  # proceeds of the flat, kept apart: they are meant for the next home, not for the investment split
    rows = []
    month = start
    purchase_info = None
    while month <= end:
        owns_flat = not (sale_month and month >= sale_month)
        income = context["salary_net"] + (context["rent_net"] if owns_flat else 0.0)
        spending = context["core_spending"] + (context["flat_costs"] if owns_flat else 0.0) + housing_delta + settings.new_credit_monthly
        debt = sum(amount for (kind, year, mon), amount in payments_by_month.items() if year == month.year and mon == month.month
                   and (owns_flat or kind != LoanKind.mortgage.value))
        events = []
        if sale_month and month == sale_month and sale:
            events.append({"type": "sale", "amount": sale["net_proceeds"]})
            sale_pot += sale["net_proceeds"]
        new_mortgage = 0.0
        if settings.purchase_price and buy_date and month >= buy_date:
            if purchase_info is None:
                pool = balances["pea"] + balances["cto"] + balances["livrets"]
                down = max(0.0, pool * settings.purchase_savings_share_pct / 100 + sale_pot)
                sale_pot = 0.0
                for key in ("pea", "cto", "livrets"):
                    balances[key] -= balances[key] * settings.purchase_savings_share_pct / 100
                capital = max(0.0, settings.purchase_price * (1 + settings.notary_fees_pct / 100) - down)
                purchase_info = {"capital": capital, "payment": monthly_payment_for(capital, settings.loan_rate_pct, settings.loan_years, settings.loan_insurance_pct), "down": down}
                events.append({"type": "purchase", "amount": -down})
            new_mortgage = purchase_info["payment"]
            spending -= min(context["housing_cost"], spending)  # no more rent once the home is bought
        surplus = income - spending - debt - new_mortgage - settings.av_monthly
        cash += surplus
        invest = 0.0
        if cash > 0:
            invest, cash = cash, 0.0
            to_livrets = 0.0
            if settings.livrets_target > balances["livrets"]:
                to_livrets = min(invest, settings.livrets_target - balances["livrets"])
            rest = invest - to_livrets
            balances["livrets"] += to_livrets + rest * settings.split_livrets / split_total
            balances["pea"] += rest * settings.split_pea / split_total
            balances["cto"] += rest * settings.split_cto / split_total
        balances["av"] += settings.av_monthly
        for key in ("pea", "cto", "av"):
            balances[key] *= 1 + monthly_return
        rows.append({
            "month": month.strftime("%Y-%m"), "income": round(income, 2), "spending": round(spending, 2), "debt_service": round(debt + new_mortgage, 2),
            "av": settings.av_monthly, "surplus": round(surplus, 2), "invested": round(invest, 2), "cash": round(cash, 2),
            "pea": round(balances["pea"], 2), "cto": round(balances["cto"], 2), "av_balance": round(balances["av"], 2), "livrets": round(balances["livrets"], 2),
            "sale_pot": round(sale_pot, 2), "total": round(sum(balances.values()) + sale_pot, 2), "events": events,
        })
        month = add_months(month, 1)
    return rows


def affordability(context: dict, settings: PlanSettings, at: date, sells_flat: bool, savings_pool: float, sale_net: float) -> dict:
    """What a bank would lend on `at`, with or without the flat, and the price that allows."""
    income = context["salary_net_before_tax"]
    existing = 0.0
    for loan in context["loans"]:
        if sells_flat and loan["kind"] == LoanKind.mortgage.value:
            continue
        existing += sum(p.total for p in loan["_future"] if p.due_date.year == at.year and p.due_date.month == at.month)
    if not sells_flat:
        income += context["rent_for_bank"] * settings.rent_weight_pct / 100
    max_total = income * settings.max_debt_ratio_pct / 100
    room = max(0.0, max_total - existing)
    capital_max = loan_capacity(room, settings.loan_rate_pct, settings.loan_years, settings.loan_insurance_pct)
    down = max(0.0, savings_pool * settings.purchase_savings_share_pct / 100 + (sale_net if sells_flat else 0.0))
    price_max = (capital_max + down) / (1 + settings.notary_fees_pct / 100)
    grid = []
    for price in PRICE_GRID:
        capital = max(0.0, price * (1 + settings.notary_fees_pct / 100) - down)
        payment = monthly_payment_for(capital, settings.loan_rate_pct, settings.loan_years, settings.loan_insurance_pct)
        ratio = (existing + payment) / income if income else None
        grid.append({"price": price, "capital": round(capital, 2), "payment": round(payment, 2), "ratio": round(ratio, 4) if ratio is not None else None,
                     "feasible": ratio is not None and ratio <= settings.max_debt_ratio_pct / 100})
    return {
        "sells_flat": sells_flat, "bank_income": round(income, 2), "existing_debt_payments": round(existing, 2),
        "max_total_payment": round(max_total, 2), "room_for_new_loan": round(room, 2), "capital_max": round(capital_max, 2),
        "down_payment": round(down, 2), "price_max": round(price_max, 2), "grid": grid,
    }


@router.get("")
def get_plan(session: Session = Depends(get_session)):
    settings = get_settings(session)
    context = build_context(session)
    rows = project(context, settings, settings.housing_delta)

    def at_month(day: str, key: str = "total"):
        row = next((r for r in rows if r["month"] == day), None)
        return row[key] if row else None

    first_positive = next((r["month"] for r in rows if r["surplus"] > 0), None)
    first_cash_clear = next((r["month"] for r in rows if r["cash"] >= 0 and r["invested"] > 0), None)
    steady = [r["surplus"] for r in rows if "2028-07" <= r["month"] <= "2029-06"]

    housing_scenarios = []
    for delta in sorted({*HOUSING_DELTAS, int(settings.housing_delta)}):
        scenario_rows = project(context, settings, float(delta))
        housing_scenarios.append({
            "delta": delta, "monthly_cost": round(context["housing_cost"] + delta, 2),
            "surplus_next_month": scenario_rows[0]["surplus"],
            "surplus_2027_09": next((r["surplus"] for r in scenario_rows if r["month"] == "2027-09"), None),
            "savings_end_2028": next((r["total"] for r in scenario_rows if r["month"] == "2028-12"), None),
        })

    sale = sale_outcome(context, settings)
    buy_at = settings.purchase_date or date(2030, 1, 1)
    pool_at_purchase = 0.0
    purchase_month = buy_at.strftime("%Y-%m")
    row_before = next((r for r in reversed(rows) if r["month"] < purchase_month), rows[-1])
    pool_at_purchase = row_before["pea"] + row_before["cto"] + row_before["livrets"]
    sale_net = sale["net_proceeds"] if sale else 0.0
    keep = affordability(context, settings, buy_at, False, pool_at_purchase, 0.0)
    sell = affordability(context, settings, buy_at, True, pool_at_purchase, sale_net)

    return {
        "settings": settings.model_dump(),
        "context": {k: v for k, v in context.items() if k not in ("loans", "property")},
        "property_name": context["property"].name if context["property"] else None,
        "projection": rows,
        "milestones": {
            "first_surplus_month": first_positive, "overdraft_cleared_month": first_cash_clear,
            "steady_surplus": round(sum(steady) / len(steady), 2) if steady else None,
            "savings_2027_12": at_month("2027-12"), "savings_2028_12": at_month("2028-12"), "savings_2029_06": at_month("2029-06"),
            "savings_end": rows[-1]["total"] if rows else None,
        },
        "housing_scenarios": housing_scenarios,
        "sale": sale,
        "purchase": {"date": buy_at.isoformat(), "savings_pool": round(pool_at_purchase, 2), "keep_flat": keep, "sell_flat": sell},
        "split_check": round(settings.split_pea + settings.split_cto + settings.split_livrets, 2),
    }


@router.patch("/settings")
def update_settings(payload: SettingsPayload, session: Session = Depends(get_session)):
    settings = get_settings(session)
    data = payload.model_dump(exclude_unset=True)
    if data.pop("clear_sale_price", False):
        settings.sale_price = None
    if data.pop("clear_purchase_price", False):
        settings.purchase_price = None
    for field, value in data.items():
        setattr(settings, field, value)
    session.add(settings)
    session.commit()
    return settings

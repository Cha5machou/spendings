"""Savings, investments and net worth. Accounts without transactions (Livret A, PEA, assurance-vie...)
are tracked through dated balance snapshots; positions through holdings."""

from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.database import get_session
from app.models import Account, AccountKind, BalanceSnapshot, Holding, Loan, LoanKind, Property, Transaction

router = APIRouter(prefix="/wealth", tags=["wealth"])

CLASS_LABEL = {
    "cash": "Cash & savings accounts", "etf": "ETFs and index funds", "stock": "Individual stocks", "fund": "Funds (assurance-vie)",
    "structured_bond": "Structured bonds", "crypto": "Crypto", "leveraged": "Leveraged products", "other": "Other",
}
TRACKED_KINDS = (AccountKind.savings, AccountKind.investment, AccountKind.crypto, AccountKind.other)
EMERGENCY_MONTHS = (3, 6)


class SnapshotPayload(BaseModel):
    account_id: int
    date: date
    balance: float
    source: str | None = None


def latest_snapshot(session: Session, account_id: int) -> BalanceSnapshot | None:
    return session.exec(select(BalanceSnapshot).where(BalanceSnapshot.account_id == account_id).order_by(BalanceSnapshot.date.desc())).first()


def checking_balance(session: Session, account: Account) -> float | None:
    if account.statement_balance is None:
        return None
    query = select(Transaction).where(Transaction.account_id == account.id)
    movements = sum(t.amount for t in session.exec(query).all() if account.statement_balance_date is None or t.date > account.statement_balance_date)
    return round(account.statement_balance + movements, 2)


@router.post("/snapshots", status_code=201)
def add_snapshot(payload: SnapshotPayload, session: Session = Depends(get_session)):
    account = session.get(Account, payload.account_id)
    if account is None:
        raise HTTPException(404, "Account not found")
    existing = session.exec(select(BalanceSnapshot).where(BalanceSnapshot.account_id == payload.account_id, BalanceSnapshot.date == payload.date)).first()
    snapshot = existing or BalanceSnapshot(account_id=payload.account_id, date=payload.date, balance=payload.balance)
    snapshot.balance, snapshot.source = payload.balance, payload.source
    session.add(snapshot)
    if account.statement_balance_date is None or payload.date >= account.statement_balance_date:
        account.statement_balance, account.statement_balance_date = payload.balance, payload.date
        session.add(account)
    session.commit()
    return {"ok": True}


class HoldingPayload(BaseModel):
    account_id: int
    name: str
    identifier: str | None = None
    asset_class: str = "other"
    value: float
    gain_loss: float | None = None
    as_of: date | None = None


@router.post("/holdings", status_code=201)
def add_holding(payload: HoldingPayload, session: Session = Depends(get_session)):
    holding = Holding(**payload.model_dump())
    session.add(holding)
    session.commit()
    session.refresh(holding)
    return holding


@router.delete("/holdings/{holding_id}", status_code=204)
def delete_holding(holding_id: int, session: Session = Depends(get_session)):
    holding = session.get(Holding, holding_id)
    if holding is None:
        raise HTTPException(404, "Holding not found")
    session.delete(holding)
    session.commit()


@router.get("")
def wealth(session: Session = Depends(get_session)):
    today = date.today()
    accounts = session.exec(select(Account).where(Account.is_active == True)).all()  # noqa: E712
    tracked = [account for account in accounts if account.kind in TRACKED_KINDS]
    snapshots = session.exec(select(BalanceSnapshot).order_by(BalanceSnapshot.date)).all()
    holdings = session.exec(select(Holding)).all()
    holdings_by_account = defaultdict(list)
    for holding in holdings:
        holdings_by_account[holding.account_id].append(holding)

    # ---- per account -------------------------------------------------------
    rows = []
    for account in tracked:
        series = [s for s in snapshots if s.account_id == account.id]
        latest = series[-1] if series else None
        balance = latest.balance if latest else (account.statement_balance or 0.0)
        first = series[0] if series else None
        year_ago = next((s for s in reversed(series) if (today - s.date).days >= 330), None)
        rows.append({
            "account_id": account.id, "name": account.name, "kind": account.kind.value, "bank": account.bank,
            "balance": round(balance, 2), "as_of": latest.date.isoformat() if latest else None,
            "since_first": round(balance - first.balance, 2) if first else None, "first_date": first.date.isoformat() if first else None,
            "change_12m": round(balance - year_ago.balance, 2) if year_ago else None,
            "holdings_total": round(sum(h.value for h in holdings_by_account.get(account.id, [])), 2),
        })

    # ---- history (snapshots share dates in practice; carry values forward) ---
    dates = sorted({s.date for s in snapshots})
    last_value: dict[int, float] = {}
    by_date = defaultdict(dict)
    for snapshot in snapshots:
        by_date[snapshot.date][snapshot.account_id] = snapshot.balance
    history = []
    for day in dates:
        last_value.update(by_date[day])
        entry = {"date": day.isoformat(), "total": round(sum(last_value.values()), 2)}
        for account in tracked:
            entry[str(account.id)] = round(last_value.get(account.id, 0.0), 2)
        history.append(entry)

    # ---- net worth ---------------------------------------------------------
    checking = [(account, checking_balance(session, account)) for account in accounts if account.kind in (AccountKind.checking, AccountKind.credit_card)]
    checking_total = sum(balance for _, balance in checking if balance is not None)
    cash_savings = sum(row["balance"] for row in rows if row["kind"] == "savings")
    invested = sum(row["balance"] for row in rows if row["kind"] != "savings")
    from app.routers.loans import load_all  # local import: loans router imports models only
    loans = [loan for loan in load_all(session, today) if loan["is_active"] and loan["current_balance"] > 0]
    mortgage_debt = sum(loan["current_balance"] for loan in loans if loan["kind"] == LoanKind.mortgage.value)
    other_debt = sum(loan["current_balance"] for loan in loans if loan["kind"] != LoanKind.mortgage.value)
    properties = session.exec(select(Property)).all()
    property_value = sum((prop.market_value or prop.purchase_price or 0.0) for prop in properties)
    property_basis = "your estimate" if properties and all(prop.market_value for prop in properties) else "purchase price (set your own estimate on the Rental page)"
    financial = checking_total + cash_savings + invested - other_debt
    net_worth = {
        "checking": round(checking_total, 2), "cash_savings": round(cash_savings, 2), "invested": round(invested, 2),
        "consumer_debt": round(other_debt, 2), "financial": round(financial, 2),
        "property_value": round(property_value, 2), "property_basis": property_basis, "mortgage": round(mortgage_debt, 2),
        "property_equity": round(property_value - mortgage_debt, 2), "total": round(financial + property_value - mortgage_debt, 2),
    }

    # ---- allocation --------------------------------------------------------
    by_class: dict[str, float] = defaultdict(float)
    for row in rows:
        positions = holdings_by_account.get(row["account_id"], [])
        if positions:
            for holding in positions:
                by_class[holding.asset_class] += holding.value
            remainder = row["balance"] - row["holdings_total"]
            if remainder > 1:
                by_class["cash"] += remainder
        else:
            by_class["cash" if row["kind"] == "savings" else "other"] += row["balance"]
    allocation = [{"asset_class": key, "label": CLASS_LABEL.get(key, key), "value": round(value, 2)} for key, value in sorted(by_class.items(), key=lambda item: -item[1])]

    # ---- checks ------------------------------------------------------------
    checks = []
    euro = lambda value: f"{value:,.0f} €".replace(",", " ")  # noqa: E731
    from app.routers.insights import insights as compute_insights
    overview = compute_insights(months=12, session=session)
    essential = overview["overview"]["essential_typical"] if not overview.get("empty") else 0.0
    if essential > 0:
        low, high = essential * EMERGENCY_MONTHS[0], essential * EMERGENCY_MONTHS[1]
        covered = cash_savings / essential
        if cash_savings < low:
            checks.append({
                "severity": "high" if covered < 1 else "medium",
                "title": f"Emergency cash covers {covered:.1f} months of essential spending",
                "detail": f"Livret A and LDDS hold {euro(cash_savings)}. Essential spending is about {euro(essential)} a month (housing, debt, food, insurance), so the usual target is {euro(low)} to {euro(high)}. "
                          "Your PEA is locked in practice (withdrawing can close it) and the assurance-vie takes days and tax on gains, so neither is a real buffer. "
                          "Both current accounts are also overdrawn today.",
            })
    if history:
        peak = max(history, key=lambda entry: entry["total"])
        latest_entry = history[-1]
        if peak["total"] > 0 and latest_entry["total"] < peak["total"] * 0.9:
            checks.append({
                "severity": "medium",
                "title": f"Savings and investments are {euro(peak['total'] - latest_entry['total'])} below their peak",
                "detail": f"Peak {euro(peak['total'])} on {peak['date']}, now {euro(latest_entry['total'])}. Part of the fall is money you withdrew "
                          "(Livret A, LDDS and the assurance-vie), not market losses; the balances alone cannot tell the two apart.",
            })
    equity_value = sum(h.value for h in holdings if h.asset_class in ("etf", "stock", "fund", "crypto", "leveraged"))
    for account in tracked:
        positions = sorted(holdings_by_account.get(account.id, []), key=lambda h: -h.value)
        total = sum(h.value for h in positions)
        if total > 0 and positions[0].value / total > 0.4 and len(positions) > 2:
            top = positions[0]
            note = {
                "etf": "It is an index fund, so the risk is the market rather than one company, but a Nasdaq-100 tracker is heavily concentrated on US technology and your other funds dilute that only partly.",
                "structured_bond": "A structured bond has a fixed maturity, a capital formula that depends on the product, and the issuer's credit risk: read its terms before relying on the amount.",
            }.get(top.asset_class, "Check that you are comfortable with this single position carrying so much of the account.")
            checks.append({
                "severity": "low",
                "title": f"{top.name} is {top.value / total:.0%} of {account.name}",
                "detail": note,
            })
    leveraged = [h for h in holdings if h.asset_class == "leveraged" and h.value > 0]
    if leveraged:
        checks.append({
            "severity": "medium",
            "title": "A leveraged product sits in your portfolio",
            "detail": ", ".join(f"{h.name} ({euro(h.value)})" for h in leveraged) + ". Daily-leveraged products reset every day and lose value over long periods even if the underlying rises; they are meant for short trades, not a monthly savings plan.",
        })
    single_stocks = [h for h in holdings if h.asset_class == "stock"]
    if single_stocks and equity_value > 0:
        share = sum(h.value for h in single_stocks) / equity_value
        if share > 0.15:
            checks.append({
                "severity": "low",
                "title": f"Individual stocks are {share:.0%} of your market investments",
                "detail": f"{len(single_stocks)} companies, {euro(sum(h.value for h in single_stocks))}. Fine as a satellite next to the index funds; mind that each Trade Republic plan buys small amounts of many separate assets, which adds up to many lines to follow.",
            })
    severity_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    checks.sort(key=lambda item: severity_order[item["severity"]])

    return {
        "accounts": rows, "history": history, "net_worth": net_worth, "allocation": allocation, "checks": checks,
        "checking": [{"account_id": account.id, "name": account.name, "balance": balance} for account, balance in checking],
        "holdings": [
            {"account_id": h.account_id, "name": h.name, "identifier": h.identifier, "asset_class": h.asset_class,
             "value": h.value, "gain_loss": h.gain_loss, "as_of": h.as_of.isoformat() if h.as_of else None}
            for h in sorted(holdings, key=lambda h: (h.account_id, -h.value))
        ],
        "liabilities": [{"name": loan["name"], "balance": loan["current_balance"], "kind": loan["kind"]} for loan in loans],
    }

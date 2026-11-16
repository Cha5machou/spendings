from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, func, select

from app.database import get_session
from app.models import Account, Transaction
from app.schemas import AccountCreate, AccountUpdate

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("")
def list_accounts(session: Session = Depends(get_session)):
    accounts = session.exec(select(Account).order_by(Account.name)).all()
    counts = dict(
        session.exec(select(Transaction.account_id, func.count(Transaction.id)).group_by(Transaction.account_id)).all()
    )
    result = []
    for account in accounts:
        # Current balance = last statement balance + everything booked after that statement.
        since_statement = select(func.coalesce(func.sum(Transaction.amount), 0.0)).where(Transaction.account_id == account.id)
        if account.statement_balance_date is not None:
            since_statement = since_statement.where(Transaction.date > account.statement_balance_date)
        movements_since = session.exec(since_statement).one()
        current_balance = (account.statement_balance or 0.0) + movements_since if account.statement_balance is not None else None
        result.append({
            **account.model_dump(),
            "transaction_count": counts.get(account.id, 0),
            "current_balance": round(current_balance, 2) if current_balance is not None else None,
            "movements_since_statement": round(movements_since, 2),
            "available": round(current_balance + account.overdraft_limit, 2) if current_balance is not None else None,
        })
    return result


@router.post("", status_code=201)
def create_account(payload: AccountCreate, session: Session = Depends(get_session)):
    account = Account(**payload.model_dump())
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


@router.patch("/{account_id}")
def update_account(account_id: int, payload: AccountUpdate, session: Session = Depends(get_session)):
    account = session.get(Account, account_id)
    if account is None:
        raise HTTPException(404, "Account not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(account, field, value)
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


@router.delete("/{account_id}", status_code=204)
def delete_account(account_id: int, session: Session = Depends(get_session)):
    account = session.get(Account, account_id)
    if account is None:
        raise HTTPException(404, "Account not found")
    has_transactions = session.exec(select(Transaction.id).where(Transaction.account_id == account_id)).first()
    if has_transactions:
        raise HTTPException(409, "Account has transactions; delete them first or deactivate the account")
    session.delete(account)
    session.commit()

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, func, or_, select

from app.categorizer import apply_rules
from app.database import get_session
from app.extraction import claude_extractor
from app.models import Category, CategoryRule, CategorySource, Transaction
from app.routers.documents import dedupe_hash
from app.schemas import BulkCategorize, TransactionCreate, TransactionPage, TransactionUpdate

router = APIRouter(prefix="/transactions", tags=["transactions"])


def build_filters(
    account_id: int | None,
    category_id: int | None,
    uncategorized: bool,
    start: date | None,
    end: date | None,
    search: str | None,
):
    conditions = []
    if account_id is not None:
        conditions.append(Transaction.account_id == account_id)
    if category_id is not None:
        conditions.append(Transaction.category_id == category_id)
    if uncategorized:
        conditions.append(Transaction.category_id.is_(None))
    if start is not None:
        conditions.append(Transaction.date >= start)
    if end is not None:
        conditions.append(Transaction.date <= end)
    if search:
        pattern = f"%{search}%"
        conditions.append(or_(Transaction.label.ilike(pattern), Transaction.notes.ilike(pattern)))
    return conditions


@router.get("", response_model=TransactionPage)
def list_transactions(
    account_id: int | None = None,
    category_id: int | None = None,
    uncategorized: bool = False,
    start: date | None = None,
    end: date | None = None,
    search: str | None = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    session: Session = Depends(get_session),
):
    conditions = build_filters(account_id, category_id, uncategorized, start, end, search)
    total = session.exec(select(func.count(Transaction.id)).where(*conditions)).one()
    total_amount = session.exec(select(func.coalesce(func.sum(Transaction.amount), 0.0)).where(*conditions)).one()
    items = session.exec(
        select(Transaction).where(*conditions).order_by(Transaction.date.desc(), Transaction.id.desc()).offset(offset).limit(limit)
    ).all()
    return TransactionPage(items=items, total=total, total_amount=total_amount)


@router.post("", status_code=201)
def create_transaction(payload: TransactionCreate, session: Session = Depends(get_session)):
    transaction = Transaction(
        **payload.model_dump(),
        category_source=CategorySource.manual if payload.category_id else CategorySource.none,
        dedupe_hash=dedupe_hash(payload.account_id, payload.date, payload.amount, payload.label),
    )
    session.add(transaction)
    session.commit()
    session.refresh(transaction)
    return transaction


@router.patch("/{transaction_id}")
def update_transaction(transaction_id: int, payload: TransactionUpdate, session: Session = Depends(get_session)):
    transaction = session.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(404, "Transaction not found")
    changes = payload.model_dump(exclude_unset=True, exclude={"create_rule_pattern"})
    if "category_id" in changes:
        transaction.category_source = CategorySource.manual if changes["category_id"] else CategorySource.none
    for field, value in changes.items():
        setattr(transaction, field, value)
    if payload.create_rule_pattern and transaction.category_id:
        session.add(CategoryRule(category_id=transaction.category_id, pattern=payload.create_rule_pattern, priority=10))
        session.flush()
        others = session.exec(
            select(Transaction).where(Transaction.id != transaction.id, Transaction.category_source != CategorySource.manual)
        ).all()
        apply_rules(session, list(others), overwrite_ai=True)
    session.add(transaction)
    session.commit()
    session.refresh(transaction)
    return transaction


@router.post("/bulk-categorize")
def bulk_categorize(payload: BulkCategorize, session: Session = Depends(get_session)):
    transactions = session.exec(select(Transaction).where(Transaction.id.in_(payload.transaction_ids))).all()
    for transaction in transactions:
        transaction.category_id = payload.category_id
        transaction.category_source = CategorySource.manual if payload.category_id else CategorySource.none
        session.add(transaction)
    session.commit()
    return {"updated": len(transactions)}


@router.delete("/{transaction_id}", status_code=204)
def delete_transaction(transaction_id: int, session: Session = Depends(get_session)):
    transaction = session.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(404, "Transaction not found")
    session.delete(transaction)
    session.commit()


@router.post("/suggest-categories")
def suggest_categories(limit: int = Query(200, le=500), session: Session = Depends(get_session)):
    """Ask Claude to categorize uncategorized transactions. Suggestions with
    confidence >= 0.6 are applied with source='ai' (still editable)."""
    if not claude_extractor.is_available():
        raise HTTPException(400, "ANTHROPIC_API_KEY is not configured")
    uncategorized = session.exec(
        select(Transaction).where(Transaction.category_id.is_(None)).order_by(Transaction.date.desc()).limit(limit)
    ).all()
    if not uncategorized:
        return {"applied": 0, "reviewed": 0}
    categories = session.exec(select(Category)).all()
    by_name = {category.name: category for category in categories}
    suggestions = claude_extractor.suggest_categories(
        [{"id": item.id, "label": item.label, "amount": item.amount} for item in uncategorized],
        list(by_name),
    )
    by_id = {item.id: item for item in uncategorized}
    applied = 0
    for suggestion in suggestions:
        transaction = by_id.get(suggestion.transaction_id)
        if transaction is None or suggestion.confidence < 0.6:
            continue
        transaction.category_id = by_name[suggestion.category_name].id
        transaction.category_source = CategorySource.ai
        session.add(transaction)
        applied += 1
    session.commit()
    return {"applied": applied, "reviewed": len(uncategorized)}

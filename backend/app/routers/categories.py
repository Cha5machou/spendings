from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.categorizer import apply_rules
from app.database import get_session
from app.models import Category, CategoryRule, CategorySource, Transaction
from app.schemas import CategoryCreate, CategoryUpdate, RuleCreate

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("")
def list_categories(session: Session = Depends(get_session)):
    return session.exec(select(Category).order_by(Category.kind, Category.name)).all()


@router.post("", status_code=201)
def create_category(payload: CategoryCreate, session: Session = Depends(get_session)):
    category = Category(**payload.model_dump())
    session.add(category)
    session.commit()
    session.refresh(category)
    return category


@router.patch("/{category_id}")
def update_category(category_id: int, payload: CategoryUpdate, session: Session = Depends(get_session)):
    category = session.get(Category, category_id)
    if category is None:
        raise HTTPException(404, "Category not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(category, field, value)
    session.add(category)
    session.commit()
    session.refresh(category)
    return category


@router.delete("/{category_id}", status_code=204)
def delete_category(category_id: int, session: Session = Depends(get_session)):
    category = session.get(Category, category_id)
    if category is None:
        raise HTTPException(404, "Category not found")
    for transaction in session.exec(select(Transaction).where(Transaction.category_id == category_id)):
        transaction.category_id = None
        transaction.category_source = CategorySource.none
        session.add(transaction)
    for rule in session.exec(select(CategoryRule).where(CategoryRule.category_id == category_id)):
        session.delete(rule)
    session.delete(category)
    session.commit()


@router.get("/rules")
def list_rules(session: Session = Depends(get_session)):
    return session.exec(select(CategoryRule).order_by(CategoryRule.priority.desc(), CategoryRule.id)).all()


@router.post("/rules", status_code=201)
def create_rule(payload: RuleCreate, session: Session = Depends(get_session)):
    if session.get(Category, payload.category_id) is None:
        raise HTTPException(404, "Category not found")
    rule = CategoryRule(**payload.model_dump(exclude={"apply_to_existing"}))
    session.add(rule)
    session.commit()
    session.refresh(rule)
    applied = 0
    if payload.apply_to_existing:
        uncategorized = session.exec(select(Transaction).where(Transaction.category_source != CategorySource.manual)).all()
        applied = apply_rules(session, list(uncategorized), overwrite_ai=True)
        session.commit()
    return {**rule.model_dump(), "applied_to": applied}


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, session: Session = Depends(get_session)):
    rule = session.get(CategoryRule, rule_id)
    if rule is None:
        raise HTTPException(404, "Rule not found")
    session.delete(rule)
    session.commit()


@router.post("/rules/apply")
def reapply_rules(session: Session = Depends(get_session)):
    """Re-run every rule over non-manual transactions (e.g. after editing rules)."""
    transactions = session.exec(select(Transaction).where(Transaction.category_source != CategorySource.manual)).all()
    changed = apply_rules(session, list(transactions), overwrite_ai=True)
    session.commit()
    return {"changed": changed}

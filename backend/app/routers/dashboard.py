from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.database import get_session
from app.models import Category, CategoryKind, Transaction
from app.schemas import CategoryTotal, DashboardOut, MonthTotals

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut)
def dashboard(
    start: date | None = None,
    end: date | None = None,
    account_id: int | None = None,
    session: Session = Depends(get_session),
):
    end = end or date.today()
    start = start or (end.replace(day=1) - timedelta(days=365)).replace(day=1)

    categories = {category.id: category for category in session.exec(select(Category)).all()}
    conditions = [Transaction.date >= start, Transaction.date <= end]
    if account_id is not None:
        conditions.append(Transaction.account_id == account_id)
    transactions = session.exec(select(Transaction).where(*conditions)).all()

    income = expenses = savings = 0.0
    by_category: dict[int | None, CategoryTotal] = {}
    by_month: dict[str, MonthTotals] = {}
    merchants: dict[str, CategoryTotal] = defaultdict(lambda: CategoryTotal(category_id=None, category_name="", kind=None, color=None, total=0.0, count=0))
    uncategorized_count = 0

    for transaction in transactions:
        category = categories.get(transaction.category_id)
        kind = category.kind if category else None
        month_key = transaction.date.strftime("%Y-%m")
        month = by_month.setdefault(month_key, MonthTotals(month=month_key, income=0.0, expenses=0.0, savings=0.0, net=0.0))

        if kind == CategoryKind.transfer:
            continue  # internal moves are neither income nor spending
        # The sign decides income vs expense; the category kind only matters for
        # savings and transfers (a refund in an expense category is still money in).
        if kind == CategoryKind.savings:
            savings += -transaction.amount
            month.savings += -transaction.amount
        elif transaction.amount > 0:
            income += transaction.amount
            month.income += transaction.amount
        else:
            expenses += -transaction.amount
            month.expenses += -transaction.amount
        month.net = month.income - month.expenses - month.savings

        if category is None:
            uncategorized_count += 1
        entry = by_category.setdefault(
            transaction.category_id,
            CategoryTotal(
                category_id=transaction.category_id,
                category_name=category.name if category else "Uncategorized",
                kind=kind,
                color=category.color if category else None,
                total=0.0,
                count=0,
            ),
        )
        entry.total += transaction.amount
        entry.count += 1

        if transaction.amount < 0:
            merchant_key = transaction.label.lower()[:40]
            merchant = merchants[merchant_key]
            merchant.category_name = merchant.category_name or transaction.label[:40]
            merchant.total += transaction.amount
            merchant.count += 1

    top_merchants = sorted(merchants.values(), key=lambda entry: entry.total)[:10]
    return DashboardOut(
        start=start,
        end=end,
        income=round(income, 2),
        expenses=round(expenses, 2),
        savings=round(savings, 2),
        net=round(income - expenses - savings, 2),
        by_category=sorted(by_category.values(), key=lambda entry: entry.total),
        by_month=[by_month[key] for key in sorted(by_month)],
        uncategorized_count=uncategorized_count,
        top_merchants=top_merchants,
    )

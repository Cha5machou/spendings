"""Where the user is in the guided setup: what exists, what is missing, what comes next."""

from fastapi import APIRouter, Depends
from sqlmodel import Session, func, select

from app.database import get_session
from app.models import Account, AccountKind, Document, Goal, Loan, Payslip, Property, Transaction
from app.routers.plan import get_settings

router = APIRouter(prefix="/setup", tags=["setup"])


@router.get("")
def setup_status(session: Session = Depends(get_session)):
    count = lambda model, *conditions: session.exec(select(func.count()).select_from(model).where(*conditions)).one()  # noqa: E731
    settings = get_settings(session)
    accounts = count(Account)
    banks = count(Account, Account.kind.in_([AccountKind.checking, AccountKind.credit_card]))
    payslips = count(Payslip)
    loans = count(Loan)
    properties = count(Property)
    documents = count(Document)
    transactions = count(Transaction)
    uncategorized = count(Transaction, Transaction.category_id.is_(None))
    goals = count(Goal)

    steps = [
        {"key": "accounts", "title": "Add your accounts", "route": "/accounts", "required": True, "done": banks > 0,
         "detail": f"{accounts} account(s)" if accounts else "Start with your current account; add savings accounts too."},
        {"key": "payslips", "title": "Add your payslips", "route": "/income", "required": False, "done": payslips > 0,
         "detail": f"{payslips} payslip(s)" if payslips else "Gives your real income, tax and bracket. Optional if you have no salary."},
        {"key": "loans", "title": "Add your credits and loans", "route": "/loans", "required": False, "done": loans > 0 or settings.skipped_loans,
         "detail": f"{loans} credit(s)" if loans else "Mortgage, car loan, instalment plans. Mark it done if you have none."},
        {"key": "property", "title": "Add a rented property", "route": "/rental", "required": False, "done": properties > 0 or settings.skipped_property,
         "detail": f"{properties} property" if properties else "Only if you rent a property out. Skip otherwise."},
        {"key": "documents", "title": "Upload your bank statements", "route": "/documents", "required": True, "done": documents > 0,
         "detail": f"{documents} file(s) imported, {transactions} transactions" if documents else "PDF, CSV or Excel exports from your bank."},
        {"key": "transactions", "title": "Check your categories", "route": "/transactions?uncategorized=1", "required": True, "done": transactions > 0 and uncategorized == 0,
         "detail": f"{uncategorized} transaction(s) still without a category" if transactions else "Appears once statements are imported."},
        {"key": "goals", "title": "Define your goals", "route": "/plan", "required": True, "done": goals > 0,
         "detail": f"{goals} goal(s)" if goals else "What you want to save for, and by when."},
    ]
    required_done = all(step["done"] for step in steps if step["required"])
    return {
        "steps": steps,
        "complete": required_done,
        "next": next((step["key"] for step in steps if not step["done"] and step["required"]), None),
        "counts": {"accounts": accounts, "payslips": payslips, "loans": loans, "properties": properties, "documents": documents, "transactions": transactions, "goals": goals},
    }

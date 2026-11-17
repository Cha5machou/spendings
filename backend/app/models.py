import datetime
from enum import Enum

from sqlmodel import Field, SQLModel


class AccountKind(str, Enum):
    checking = "checking"
    credit_card = "credit_card"
    savings = "savings"
    investment = "investment"
    loan = "loan"
    crypto = "crypto"
    other = "other"


class CategoryKind(str, Enum):
    expense = "expense"
    income = "income"
    transfer = "transfer"  # money moving between the user's own accounts
    savings = "savings"  # contributions to savings/investments


class CategorySource(str, Enum):
    none = "none"
    rule = "rule"
    ai = "ai"
    manual = "manual"


class DocumentStatus(str, Enum):
    uploaded = "uploaded"
    imported = "imported"
    failed = "failed"


class Account(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    bank: str | None = None
    kind: AccountKind = AccountKind.checking
    currency: str = "EUR"
    is_active: bool = True
    notes: str | None = None
    overdraft_limit: float = 0.0  # découvert autorisé (positive number)
    # Last balance known from a statement; current balance = this + transactions after that date.
    statement_balance: float | None = None
    statement_balance_date: datetime.date | None = None
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))


class Category(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    kind: CategoryKind = CategoryKind.expense
    parent_id: int | None = Field(default=None, foreign_key="category.id")
    color: str | None = None
    is_default: bool = False  # seeded categories, kept generic for any user
    # "essential" (hard to cut: housing, debt, food...) or "flexible" (discretionary). None = unclassified.
    necessity: str | None = None


class CategoryRule(SQLModel, table=True):
    """Label matching rule: when a transaction label matches `pattern`,
    the transaction gets `category_id`. Highest priority wins."""

    id: int | None = Field(default=None, primary_key=True)
    category_id: int = Field(foreign_key="category.id")
    pattern: str
    match_type: str = "contains"  # "contains" (case-insensitive) or "regex"
    priority: int = 0
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))


class LoanKind(str, Enum):
    mortgage = "mortgage"
    personal = "personal"  # amortising consumer / personal / car loan
    revolving = "revolving"  # revolving credit line or ETALIS-style drawdown
    installment = "installment"  # buy-now-pay-later (PayPal 4x, Cofidis, ...), usually 0 %
    other = "other"


class Loan(SQLModel, table=True):
    """One debt. A revolving credit with several plans, or several 4x payments, are one row each."""

    id: int | None = Field(default=None, primary_key=True)
    name: str
    lender: str | None = None
    kind: LoanKind = LoanKind.personal
    account_id: int | None = Field(default=None, foreign_key="account.id")  # account it is debited from
    is_active: bool = True
    original_amount: float | None = None
    start_date: datetime.date | None = None
    # Balance as stated by the lender on balance_date; the projection starts from here.
    remaining_balance: float = 0.0
    balance_date: datetime.date | None = None
    annual_rate: float = 0.0  # nominal, percent (3.3 = 3.3 %)
    taeg: float | None = None  # effective annual rate incl. fees and insurance, percent
    monthly_payment: float = 0.0  # all-in instalment (capital + interest + insurance)
    insurance_monthly: float = 0.0  # part of the instalment that is insurance
    next_payment_date: datetime.date | None = None  # first instalment after balance_date
    payments_remaining: int | None = None  # when the lender states a number of instalments
    end_date: datetime.date | None = None  # end date stated by the lender
    payment_pattern: str | None = None  # text found in the bank label, to match real payments
    notes: str | None = None
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))


class LoanScheduleEntry(SQLModel, table=True):
    """Official amortisation table (imported from the loan offer); overrides the computed projection."""

    id: int | None = Field(default=None, primary_key=True)
    loan_id: int = Field(foreign_key="loan.id", index=True)
    due_date: datetime.date
    capital_before: float
    principal: float
    interest: float
    insurance: float
    total: float


class Document(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    account_id: int | None = Field(default=None, foreign_key="account.id")
    filename: str
    stored_path: str
    mime_type: str
    size_bytes: int = 0
    status: DocumentStatus = DocumentStatus.uploaded
    extraction_method: str | None = None  # csv | pdf_text | claude
    transactions_imported: int = 0
    duplicates_skipped: int = 0
    closing_balance: float | None = None
    period_end: datetime.date | None = None
    error: str | None = None
    uploaded_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))


class Transaction(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id", index=True)
    document_id: int | None = Field(default=None, foreign_key="document.id")
    date: datetime.date = Field(index=True)
    label: str
    amount: float  # signed: negative = money out, positive = money in
    currency: str = "EUR"
    category_id: int | None = Field(default=None, foreign_key="category.id", index=True)
    category_source: CategorySource = CategorySource.none
    notes: str | None = None
    # Same account + date + amount + label => considered the same transaction on re-import.
    dedupe_hash: str = Field(index=True, unique=True)
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))

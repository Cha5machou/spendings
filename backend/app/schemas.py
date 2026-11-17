import datetime

from pydantic import BaseModel, ConfigDict

from app.models import AccountKind, CategoryKind, CategorySource


class AccountCreate(BaseModel):
    name: str
    bank: str | None = None
    kind: AccountKind = AccountKind.checking
    currency: str = "EUR"
    notes: str | None = None


class AccountUpdate(BaseModel):
    name: str | None = None
    bank: str | None = None
    kind: AccountKind | None = None
    currency: str | None = None
    is_active: bool | None = None
    notes: str | None = None
    overdraft_limit: float | None = None
    statement_balance: float | None = None
    statement_balance_date: datetime.date | None = None


class CategoryCreate(BaseModel):
    name: str
    kind: CategoryKind = CategoryKind.expense
    parent_id: int | None = None
    color: str | None = None
    necessity: str | None = None


class CategoryUpdate(BaseModel):
    name: str | None = None
    kind: CategoryKind | None = None
    parent_id: int | None = None
    color: str | None = None
    necessity: str | None = None


class RuleCreate(BaseModel):
    category_id: int
    pattern: str
    match_type: str = "contains"
    priority: int = 0
    apply_to_existing: bool = True


class TransactionCreate(BaseModel):
    account_id: int
    date: datetime.date
    label: str
    amount: float
    category_id: int | None = None
    notes: str | None = None


class TransactionUpdate(BaseModel):
    date: datetime.date | None = None
    label: str | None = None
    amount: float | None = None
    category_id: int | None = None
    notes: str | None = None
    # When the user sets a category, optionally turn the label into a rule for next time.
    create_rule_pattern: str | None = None


class BulkCategorize(BaseModel):
    transaction_ids: list[int]
    category_id: int | None


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    document_id: int | None
    date: datetime.date
    label: str
    amount: float
    currency: str
    category_id: int | None
    category_source: CategorySource
    notes: str | None


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    total: int
    total_amount: float


class ImportSummary(BaseModel):
    document_id: int
    status: str
    extraction_method: str | None
    transactions_imported: int
    duplicates_skipped: int
    auto_categorized: int
    warnings: list[str]
    error: str | None = None


class CategoryTotal(BaseModel):
    category_id: int | None
    category_name: str
    kind: CategoryKind | None
    color: str | None
    total: float
    count: int


class MonthTotals(BaseModel):
    month: str  # YYYY-MM
    income: float
    expenses: float
    savings: float
    net: float


class DashboardOut(BaseModel):
    start: datetime.date
    end: datetime.date
    income: float
    expenses: float
    savings: float
    net: float
    by_category: list[CategoryTotal]
    by_month: list[MonthTotals]
    uncategorized_count: int
    top_merchants: list[CategoryTotal]

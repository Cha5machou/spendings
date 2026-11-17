"""Default categories and a few generic rules. Generic enough for anyone; the
user adds their own rules from the Transactions page."""

from sqlmodel import Session, select

from app.models import Category, CategoryKind, CategoryRule

DEFAULT_CATEGORIES: list[tuple[str, CategoryKind, str]] = [
    # (name, kind, color)
    ("Salary", CategoryKind.income, "#2f7d6a"),
    ("Rental income", CategoryKind.income, "#3d8f7a"),
    ("Other income", CategoryKind.income, "#4fa08a"),
    ("Refunds", CategoryKind.income, "#6cb09a"),
    ("Housing (rent & charges)", CategoryKind.expense, "#4f6fb5"),
    ("Mortgage", CategoryKind.expense, "#3c5aa0"),
    ("Loans & credits", CategoryKind.expense, "#5a4fb5"),
    ("Property (rented out)", CategoryKind.expense, "#6f7fcf"),
    ("Groceries", CategoryKind.expense, "#c56a2d"),
    ("Restaurants & bars", CategoryKind.expense, "#d98a3f"),
    ("Fuel", CategoryKind.expense, "#8a5a2b"),
    ("Transport", CategoryKind.expense, "#9c7a45"),
    ("Utilities (energy, water, internet, phone)", CategoryKind.expense, "#7a8a3a"),
    ("Insurance", CategoryKind.expense, "#5d7a52"),
    ("Taxes", CategoryKind.expense, "#a53f3f"),
    ("Health", CategoryKind.expense, "#b05a7a"),
    ("Subscriptions", CategoryKind.expense, "#8f5fa0"),
    ("Shopping", CategoryKind.expense, "#c06aa8"),
    ("Leisure & travel", CategoryKind.expense, "#3f8fb0"),
    ("Bank fees", CategoryKind.expense, "#7a7a7a"),
    ("Business (own company)", CategoryKind.expense, "#4a4a8a"),
    ("Cash withdrawal", CategoryKind.expense, "#8a8a5a"),
    ("Other expense", CategoryKind.expense, "#9a9a9a"),
    ("Savings & investments", CategoryKind.savings, "#2a7a9a"),
    ("Internal transfer", CategoryKind.transfer, "#aaaaaa"),
]

ESSENTIAL_CATEGORIES = {
    "Housing (rent & charges)", "Mortgage", "Loans & credits", "Property (rented out)", "Groceries", "Fuel",
    "Transport", "Utilities (energy, water, internet, phone)", "Insurance", "Taxes", "Health", "Bank fees",
}
FLEXIBLE_CATEGORIES = {
    "Restaurants & bars", "Subscriptions", "Shopping", "Leisure & travel", "Cash withdrawal", "Other expense",
    "Business (own company)", "Donations", "Family & friends",
}

DEFAULT_RULES: list[tuple[str, str]] = [
    # (pattern, category name) - case-insensitive "contains"
    ("carrefour", "Groceries"),
    ("leclerc", "Groceries"),
    ("auchan", "Groceries"),
    ("lidl", "Groceries"),
    ("intermarche", "Groceries"),
    ("monoprix", "Groceries"),
    ("franprix", "Groceries"),
    ("casino", "Groceries"),
    ("total energies", "Fuel"),
    ("totalenergies", "Fuel"),
    ("station", "Fuel"),
    ("esso", "Fuel"),
    ("sncf", "Transport"),
    ("ratp", "Transport"),
    ("uber", "Transport"),
    ("netflix", "Subscriptions"),
    ("spotify", "Subscriptions"),
    ("amazon prime", "Subscriptions"),
    ("edf", "Utilities (energy, water, internet, phone)"),
    ("engie", "Utilities (energy, water, internet, phone)"),
    ("free mobile", "Utilities (energy, water, internet, phone)"),
    ("orange", "Utilities (energy, water, internet, phone)"),
    ("bouygues", "Utilities (energy, water, internet, phone)"),
    ("sfr", "Utilities (energy, water, internet, phone)"),
    ("pharmacie", "Health"),
    ("dgfip", "Taxes"),
    ("impot", "Taxes"),
    ("tresor public", "Taxes"),
    ("retrait", "Cash withdrawal"),
    ("frais bancaires", "Bank fees"),
    ("cotisation", "Bank fees"),
    ("livret a", "Savings & investments"),
    ("ldds", "Savings & investments"),
    ("assurance vie", "Savings & investments"),
    ("pea", "Savings & investments"),
    ("cofidis", "Loans & credits"),
    ("sofinco", "Loans & credits"),
    ("paypal credit", "Loans & credits"),
    ("echeance pret", "Mortgage"),
    ("pret immo", "Mortgage"),
    ("salaire", "Salary"),
    ("gestion locative", "Rental income"),
    ("loyer", "Housing (rent & charges)"),
]


def backfill_necessity(session: Session) -> None:
    """Classify known category names as essential / flexible once; never overrides a user's choice."""
    for category in session.exec(select(Category).where(Category.necessity == None)).all():  # noqa: E711
        if category.kind != CategoryKind.expense:
            continue
        if category.name in ESSENTIAL_CATEGORIES:
            category.necessity = "essential"
        elif category.name in FLEXIBLE_CATEGORIES:
            category.necessity = "flexible"
        session.add(category)
    session.commit()


def seed_defaults(session: Session) -> None:
    existing = session.exec(select(Category)).first()
    if existing is not None:
        backfill_necessity(session)
        return
    categories_by_name: dict[str, Category] = {}
    for name, kind, color in DEFAULT_CATEGORIES:
        category = Category(name=name, kind=kind, color=color, is_default=True)
        session.add(category)
        categories_by_name[name] = category
    session.commit()
    for pattern, category_name in DEFAULT_RULES:
        session.add(CategoryRule(category_id=categories_by_name[category_name].id, pattern=pattern))
    session.commit()
    backfill_necessity(session)

"""Spending analysis: run rate, category trends, recurring payments, overdraft usage
and computed recommendations. Everything is derived from the transactions; no AI needed.

Conventions
- A "complete month" is any month before the current one. All averages use the last
  `months` complete months (zeros included), the current month is reported separately.
- Spending of a category = -(sum of its amounts), so refunds net the category down.
- One-offs are single movements >= ONE_OFF_THRESHOLD that do not repeat (seen fewer than 3
  times, or at least 2.5x the usual amount of the same merchant). A 1 465 EUR mortgage
  instalment is therefore regular, a 5 171 EUR cheque is a one-off. They are shown but kept
  out of the "typical month".
"""

import re
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.database import get_session
from app.models import Account, Category, CategoryKind, Transaction

router = APIRouter(prefix="/insights", tags=["insights"])

ONE_OFF_THRESHOLD = 1000.0
TARGET_SAVINGS_RATE = 0.20
MAX_DEBT_RATIO = 0.33
DISCRETIONARY_TRIM = 0.10

# --- merchant normalisation -------------------------------------------------

PREFIXES = re.compile(
    r"^(?:\d+\s+PAIEMENTS?\s+\d{4}|PAIEMENT\s+(?:PSC|CB)\s+\d{4}|PRLV\s+SEPA|VIR\s+(?:INST|SEPA)|VIREMENT|PRELEVEMENT|CB)\s+",
    re.IGNORECASE,
)
CARD_TAIL = re.compile(r"\s+CARTE\s+\d+.*$", re.IGNORECASE)
PLACES = re.compile(r"\b(?:AIX EN PROVEN(?:CE)?|AIX EN PRO|AIX PROV|MARSEILLE|PARIS)\b", re.IGNORECASE)
COUNTRY_PREFIX = re.compile(r"^(?:FR|IT|ES|US|GB|DE|TN)\s+", re.IGNORECASE)
NOISE_TOKENS = {"EUROPE", "ET", "CIE", "SEPA", "SIEGE"}


def merchant_key(label: str) -> str:
    text = CARD_TAIL.sub("", label.strip())
    previous = None
    while previous != text:
        previous = text
        text = PREFIXES.sub("", text)
    text = COUNTRY_PREFIX.sub("", PLACES.sub(" ", text))
    tokens = [
        token for token in re.findall(r"[A-Za-z][A-Za-z&'\-]*", text.upper())
        if len(token) > 1 and token not in NOISE_TOKENS
    ]
    return " ".join(tokens[:2]) or label.strip().upper()[:30]


# --- small helpers ----------------------------------------------------------


def month_of(day: date) -> str:
    return day.strftime("%Y-%m")


def month_range(first: str, last: str) -> list[str]:
    year, month = int(first[:4]), int(first[5:])
    months = []
    while f"{year:04d}-{month:02d}" <= last:
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return months


def coefficient_of_variation(values: list[float]) -> float:
    mean = statistics.fmean(values)
    return statistics.pstdev(values) / abs(mean) if mean else 0.0


def name_has(category: Category | None, *words: str) -> bool:
    return category is not None and any(word in category.name.lower() for word in words)


def account_balance_history(account: Account, transactions: list[Transaction], first_day: date, today: date) -> list[tuple[date, float]]:
    """End-of-day balance for each day, walking backwards from the current balance."""
    movements_after_statement = sum(t.amount for t in transactions if account.statement_balance_date and t.date > account.statement_balance_date)
    current = (account.statement_balance or 0.0) + movements_after_statement
    daily_net: dict[date, float] = defaultdict(float)
    for transaction in transactions:
        daily_net[transaction.date] += transaction.amount
    history = []
    balance = current
    day = max(today, max(daily_net, default=today))
    while day >= first_day:
        history.append((day, round(balance, 2)))
        balance -= daily_net.get(day, 0.0)
        day -= timedelta(days=1)
    return history[::-1]


# --- endpoint ---------------------------------------------------------------


@router.get("")
def insights(months: int = 12, session: Session = Depends(get_session)):
    today = date.today()
    categories = {category.id: category for category in session.exec(select(Category)).all()}
    accounts = session.exec(select(Account)).all()
    all_transactions = session.exec(select(Transaction).where(Transaction.date <= today)).all()
    if not all_transactions:
        return {"empty": True}

    current_month = month_of(today)
    complete = sorted({month_of(t.date) for t in all_transactions if month_of(t.date) < current_month})
    window = month_range(complete[-months:][0] if months > 0 else complete[0], complete[-1]) if complete else []
    window_set = set(window)
    month_count = max(len(window), 1)

    def kind_of(transaction: Transaction) -> CategoryKind | None:
        category = categories.get(transaction.category_id)
        return category.kind if category else None

    # ---- one-off detection ---------------------------------------------------
    amounts_by_merchant = defaultdict(list)
    for transaction in all_transactions:
        if kind_of(transaction) not in (CategoryKind.transfer, CategoryKind.savings):
            amounts_by_merchant[(merchant_key(transaction.label), transaction.amount > 0)].append(abs(transaction.amount))

    def is_one_off(transaction: Transaction) -> bool:
        if abs(transaction.amount) < ONE_OFF_THRESHOLD:
            return False
        usual = amounts_by_merchant[(merchant_key(transaction.label), transaction.amount > 0)]
        return len(usual) < 3 or abs(transaction.amount) >= 2.5 * statistics.median(usual)

    # ---- aggregate per month / category / merchant -------------------------
    category_month = defaultdict(lambda: defaultdict(float))  # category_id -> month -> spending (+) or income (+)
    category_counts = Counter()
    category_merchants = defaultdict(lambda: defaultdict(lambda: {"total": 0.0, "count": 0, "last": None}))
    one_offs = []
    month_totals = defaultdict(lambda: {"income": 0.0, "spending": 0.0, "saved": 0.0, "one_offs": 0.0, "income_one_offs": 0.0})
    uncategorized = 0

    for transaction in all_transactions:
        kind = kind_of(transaction)
        if kind == CategoryKind.transfer:
            continue
        month = month_of(transaction.date)
        if transaction.category_id is None:
            uncategorized += 1
            kind = CategoryKind.income if transaction.amount > 0 else CategoryKind.expense
        if kind == CategoryKind.income:
            category_month[transaction.category_id][month] += transaction.amount
            month_totals[month]["income"] += transaction.amount
            if transaction.amount > 0 and is_one_off(transaction):
                month_totals[month]["income_one_offs"] += transaction.amount
                one_offs.append(transaction)
        elif kind == CategoryKind.savings:
            category_month[transaction.category_id][month] += -transaction.amount
            month_totals[month]["saved"] += -transaction.amount
        else:
            category_month[transaction.category_id][month] += -transaction.amount
            month_totals[month]["spending"] += -transaction.amount
            if transaction.amount < 0 and is_one_off(transaction):
                month_totals[month]["one_offs"] += -transaction.amount
                one_offs.append(transaction)
        if month in window_set or month == current_month:
            category_counts[transaction.category_id] += 1
            if transaction.amount < 0 and kind != CategoryKind.income:
                entry = category_merchants[transaction.category_id][merchant_key(transaction.label)]
                entry["total"] += -transaction.amount
                entry["count"] += 1
                entry["last"] = max(entry["last"] or transaction.date, transaction.date)

    # ---- categories --------------------------------------------------------
    category_rows = []
    one_off_by_category = defaultdict(float)
    for transaction in one_offs:
        if month_of(transaction.date) in window_set:
            one_off_by_category[transaction.category_id] += abs(transaction.amount)
    for category_id, per_month in category_month.items():
        category = categories.get(category_id)
        kind = category.kind if category else (CategoryKind.expense)
        series = [round(per_month.get(month, 0.0), 2) for month in window]
        total = sum(series)
        if not window or (total == 0 and per_month.get(current_month, 0.0) == 0):
            continue
        present = [value for value in series if abs(value) > 0.005]
        presence = len(present) / month_count
        average = total / month_count
        recent = series[-3:]
        earlier = series[:-3] or series
        recent_average = statistics.fmean(recent) if recent else 0.0
        earlier_average = statistics.fmean(earlier) if earlier else 0.0
        if presence >= 0.75 and len(present) >= 3 and coefficient_of_variation(present) < 0.35:
            pattern = "fixed"
        elif presence >= 0.5:
            pattern = "recurring"
        else:
            pattern = "occasional"
        merchants = sorted(category_merchants[category_id].items(), key=lambda item: -item[1]["total"])[:6]
        category_rows.append({
            "category_id": category_id,
            "name": category.name if category else "Uncategorized",
            "kind": kind.value,
            "color": category.color if category else None,
            "necessity": category.necessity if category else None,
            "series": series,
            "total": round(total, 2),
            "average": round(average, 2),
            "median": round(statistics.median(series), 2) if series else 0.0,
            "recent_average": round(recent_average, 2),
            "earlier_average": round(earlier_average, 2),
            "last_month": series[-1] if series else 0.0,
            "current_month": round(per_month.get(current_month, 0.0), 2),
            "one_off_total": round(one_off_by_category.get(category_id, 0.0), 2),
            "transactions": category_counts.get(category_id, 0),
            "months_present": len(present),
            "pattern": pattern,
            "top_merchants": [
                {"name": name.title(), "total": round(data["total"], 2), "count": data["count"], "last": data["last"].isoformat() if data["last"] else None}
                for name, data in merchants
            ],
        })

    expense_rows = [row for row in category_rows if row["kind"] == "expense"]
    income_rows = [row for row in category_rows if row["kind"] == "income"]
    saving_rows = [row for row in category_rows if row["kind"] == "savings"]
    total_spending = sum(row["total"] for row in expense_rows)
    for row in category_rows:
        row["share"] = round(row["total"] / total_spending, 4) if row["kind"] == "expense" and total_spending > 0 else None
    category_rows.sort(key=lambda row: (row["kind"] != "expense", -row["total"]))

    # ---- month series & run rate ------------------------------------------
    series = []
    for month in sorted(set(window) | {current_month}):
        totals = month_totals[month]
        series.append({
            "month": month,
            "income": round(totals["income"], 2),
            "spending": round(totals["spending"], 2),
            "saved": round(totals["saved"], 2),
            "one_offs": round(totals["one_offs"], 2),
            "income_one_offs": round(totals["income_one_offs"], 2),
            "partial": month == current_month,
        })
    window_series = [entry for entry in series if not entry["partial"]]
    income_total = sum(entry["income"] for entry in window_series)
    spending_total = sum(entry["spending"] for entry in window_series)
    one_off_total = sum(entry["one_offs"] for entry in window_series)
    income_one_off_total = sum(entry["income_one_offs"] for entry in window_series)
    saved_total = sum(entry["saved"] for entry in window_series)
    typical_income = (income_total - income_one_off_total) / month_count
    typical_spending = (spending_total - one_off_total) / month_count
    essential_spending = sum(row["average"] for row in expense_rows if row["necessity"] == "essential")
    flexible_spending = sum(row["average"] for row in expense_rows if row["necessity"] == "flexible")
    unclassified_spending = sum(row["average"] for row in expense_rows if row["necessity"] is None)
    savings_rate = (typical_income - typical_spending) / typical_income if typical_income > 0 else None

    overview = {
        "window_start": window[0] if window else None,
        "window_end": window[-1] if window else None,
        "months": len(window),
        "typical_income": round(typical_income, 2),
        "typical_spending": round(typical_spending, 2),
        "average_spending_with_one_offs": round(spending_total / month_count, 2),
        "typical_saved_or_invested": round(saved_total / month_count, 2),
        "typical_surplus": round(typical_income - typical_spending, 2),
        "savings_rate": round(savings_rate, 4) if savings_rate is not None else None,
        "essential_spending": round(essential_spending, 2),
        "flexible_spending": round(flexible_spending, 2),
        "unclassified_spending": round(unclassified_spending, 2),
        "one_off_total": round(one_off_total, 2),
        "income_one_off_total": round(income_one_off_total, 2),
        "uncategorized_transactions": uncategorized,
    }

    # ---- recurring payments -----------------------------------------------
    groups = defaultdict(list)
    for transaction in all_transactions:
        if transaction.amount < 0 and kind_of(transaction) in (CategoryKind.expense, None):
            groups[merchant_key(transaction.label)].append(transaction)
    recurring = []
    for key, items in groups.items():
        per_month = defaultdict(float)
        for item in items:
            per_month[month_of(item.date)] += -item.amount
        first, last = min(per_month), max(per_month)
        span = len(month_range(first, last))
        if len(per_month) < 3 or len(per_month) / span < 0.6:
            continue
        monthly_values = list(per_month.values())
        variation = coefficient_of_variation(monthly_values)
        per_month_count = len(items) / len(per_month)
        is_fixed = variation < 0.12
        if not is_fixed and not (len(per_month) / span >= 0.75 and per_month_count <= 2.5 and variation < 0.8):
            continue
        category_counter = Counter(categories[item.category_id].name if item.category_id in categories else "Uncategorized" for item in items)
        category_id_counter = Counter(item.category_id for item in items)
        recurring.append({
            "name": key.title(),
            "category_id": category_id_counter.most_common(1)[0][0],
            "category_name": category_counter.most_common(1)[0][0],
            "monthly_amount": round(statistics.median(monthly_values), 2),
            "yearly_cost": round(statistics.median(monthly_values) * 12, 2),
            "fixed_amount": is_fixed,
            "months_seen": len(per_month),
            "first_month": first,
            "last_month": last,
            "active": last >= month_of(today - timedelta(days=45)),
            "example_label": Counter(item.label for item in items).most_common(1)[0][0],
        })
    recurring.sort(key=lambda entry: (not entry["active"], -entry["monthly_amount"]))

    # ---- overdraft usage ---------------------------------------------------
    overdraft = []
    window_first_day = date.fromisoformat(window[0] + "-01") if window else today - timedelta(days=365)
    for account in accounts:
        account_transactions = [t for t in all_transactions if t.account_id == account.id]
        if account.statement_balance is None or not account_transactions:
            continue
        history = [(day, balance) for day, balance in account_balance_history(account, account_transactions, window_first_day, today)]
        negative_days = [(day, balance) for day, balance in history if balance < 0]
        beyond_limit = [day for day, balance in history if balance < -account.overdraft_limit]
        by_month = defaultdict(lambda: {"days_negative": 0, "lowest_balance": None})
        for day, balance in history:
            entry = by_month[month_of(day)]
            entry["days_negative"] += 1 if balance < 0 else 0
            entry["lowest_balance"] = balance if entry["lowest_balance"] is None else min(entry["lowest_balance"], balance)
        overdraft.append({
            "account_id": account.id,
            "account_name": account.name,
            "overdraft_limit": account.overdraft_limit,
            "days_tracked": len(history),
            "days_negative": len(negative_days),
            "days_beyond_limit": len(beyond_limit),
            "lowest_balance": min((balance for _, balance in history), default=None),
            "lowest_balance_date": min(history, key=lambda item: item[1])[0].isoformat() if history else None,
            "by_month": [{"month": month, **values} for month, values in sorted(by_month.items())],
        })

    # ---- recommendations ---------------------------------------------------
    recommendations = []

    def recommend(key, severity, title, detail, monthly_impact=None, category_id=None, saving=False):
        recommendations.append({
            "key": key, "severity": severity, "title": title, "detail": detail,
            "monthly_impact": round(monthly_impact, 2) if monthly_impact else None,
            "category_id": category_id, "saving": saving,
        })

    euro = lambda value: f"{value:,.0f} €".replace(",", " ")  # noqa: E731

    if savings_rate is not None and typical_income > 0:
        surplus = typical_income - typical_spending
        gap = TARGET_SAVINGS_RATE * typical_income - surplus
        context = (f"Typical month: {euro(typical_income)} in, {euro(typical_spending)} out "
                   f"(single movements over {euro(ONE_OFF_THRESHOLD)} that do not repeat are left out).")
        if surplus < 0:
            recommend("savings_rate", "high", f"A typical month runs a deficit of {euro(-surplus)}",
                      f"{context} The gap is covered by overdraft, savings withdrawals or one-offs. "
                      f"Closing it takes {euro(-surplus)} a month, and {euro(gap)} a month to reach a {TARGET_SAVINGS_RATE:.0%} savings rate.",
                      monthly_impact=-surplus)
        elif savings_rate < TARGET_SAVINGS_RATE:
            recommend("savings_rate", "high" if savings_rate < 0.1 else "medium",
                      f"You keep {savings_rate:.0%} of your income, the usual target is {TARGET_SAVINGS_RATE:.0%}",
                      f"{context} Reaching {TARGET_SAVINGS_RATE:.0%} means freeing about {euro(gap)} a month.", monthly_impact=gap)
        else:
            recommend("savings_rate", "info", f"You keep {savings_rate:.0%} of your income",
                      f"{context} That is above the {TARGET_SAVINGS_RATE:.0%} target. Make sure the surplus of {euro(surplus)} a month lands in savings or investments.")

    debt_rows = [row for row in expense_rows if name_has(categories.get(row["category_id"]), "mortgage", "loan", "credit")]
    if debt_rows and typical_income > 0:
        debt_service = sum(row["average"] - row["one_off_total"] / month_count for row in debt_rows)
        ratio = debt_service / typical_income
        breakdown = ", ".join(f"{row['name']} {euro(row['average'] - row['one_off_total'] / month_count)}" for row in debt_rows)
        rental_row = next((row for row in income_rows if name_has(categories.get(row["category_id"]), "rental", "rent")), None)
        rental_note = ""
        if rental_row and rental_row["average"] > 0:
            # Banks usually count about 70 % of rents as income when sizing a new loan.
            rental_note = f" Rents received average {euro(rental_row['average'])} a month; they are already in the income used for this ratio."
        if ratio > MAX_DEBT_RATIO:
            recommend("debt_ratio", "high", f"Debt payments take {ratio:.0%} of your income",
                      f"{breakdown} a month, above the {MAX_DEBT_RATIO:.0%} limit banks use.{rental_note} "
                      "This will cap a new mortgage; paying off the most expensive credit first helps most.")
        else:
            recommend("debt_ratio", "info", f"Debt payments take {ratio:.0%} of your income",
                      f"{breakdown} a month, under the {MAX_DEBT_RATIO:.0%} limit banks use. Rental income is not counted in this ratio.")
    consumer_credit = [row for row in debt_rows if name_has(categories.get(row["category_id"]), "loan", "credit")]
    if consumer_credit:
        monthly_credit = sum(row["average"] for row in consumer_credit)
        names = ", ".join(merchant["name"] for row in consumer_credit for merchant in row["top_merchants"][:4])
        recommend("consumer_credit", "medium" if monthly_credit > 0.1 * typical_income else "low",
                  f"Consumer credits cost {euro(monthly_credit)} a month",
                  f"Seen in your statements: {names}. List each balance and rate in the loans module (next step), then repay the highest rate first; "
                  "a small credit at 14 % costs far more than the 3-4 % a savings account earns.")

    fees_row = next((row for row in expense_rows if name_has(categories.get(row["category_id"]), "bank fee", "frais")), None)
    ordinary_fees = fees_row["total"] - fees_row["one_off_total"] if fees_row else 0
    if fees_row and ordinary_fees > 60:
        fee_merchants = ", ".join(f"{merchant['name']} ({euro(merchant['total'])})" for merchant in fees_row["top_merchants"][:3])
        one_off_note = f" Not counted here: a one-off fee of {euro(fees_row['one_off_total'])}." if fees_row["one_off_total"] else ""
        recommend("bank_fees", "medium", f"You paid {euro(ordinary_fees)} in bank fees over {len(window)} months",
                  f"Biggest: {fee_merchants}. Incident and overdraft fees are avoidable, and card and account fees can be negotiated or dropped by moving daily banking to a free online account.{one_off_note}",
                  monthly_impact=ordinary_fees / month_count * 0.7, category_id=fees_row["category_id"], saving=True)

    for entry in overdraft:
        if entry["days_negative"] > 15:
            share = entry["days_negative"] / max(entry["days_tracked"], 1)
            recommend(f"overdraft_{entry['account_id']}", "high" if share > 0.5 or entry["days_beyond_limit"] else "medium",
                      f"{entry['account_name']} was overdrawn {entry['days_negative']} days out of {entry['days_tracked']}",
                      f"Lowest point {euro(entry['lowest_balance'])} on {entry['lowest_balance_date']} against an authorised overdraft of {euro(entry['overdraft_limit'])}."
                      + (f" It went beyond the limit on {entry['days_beyond_limit']} days." if entry["days_beyond_limit"] else "")
                      + " Moving the salary date or the biggest direct debits to just after payday usually stops this.")

    for row in expense_rows:
        if row["months_present"] < 3 or len(window) < 4:
            continue
        others = row["series"][:-1]
        typical = statistics.median(others)
        if typical > 0 and row["last_month"] > typical * 1.3 and row["last_month"] - typical >= 50 and row["pattern"] != "occasional":
            recommend(f"spike_{row['category_id']}", "low", f"{row['name']}: {euro(row['last_month'])} last month vs {euro(typical)} usual",
                      "Check the transactions of last month for a one-off or a new habit.", category_id=row["category_id"])
        elif row["earlier_average"] > 0 and row["recent_average"] > row["earlier_average"] * 1.25 and row["recent_average"] - row["earlier_average"] >= 30 and row["pattern"] != "occasional":
            recommend(f"trend_{row['category_id']}", "low", f"{row['name']} is trending up",
                      f"Last 3 months average {euro(row['recent_average'])} against {euro(row['earlier_average'])} before.", category_id=row["category_id"])

    flexible_rows = sorted((row for row in expense_rows if row["necessity"] == "flexible"), key=lambda row: -row["average"])
    leisure_rows = [row for row in flexible_rows if not name_has(categories.get(row["category_id"]), "business", "donation", "family", "other", "cash")]
    if leisure_rows:  # trimmed below; also reused for the subscriptions check
        trim = sum(row["average"] for row in leisure_rows[:3]) * DISCRETIONARY_TRIM
        names = ", ".join(f"{row['name']} {euro(row['average'])}" for row in leisure_rows[:3])
        recommend("discretionary", "medium", f"A {DISCRETIONARY_TRIM:.0%} trim on your top discretionary categories frees {euro(trim)} a month",
                  f"Monthly averages: {names}. Set a monthly budget slightly under these and track it in the explorer below.",
                  monthly_impact=trim, category_id=leisure_rows[0]["category_id"], saving=True)

    leisure_names = {row["name"] for row in leisure_rows}
    active_recurring = [entry for entry in recurring if entry["active"] and entry["category_name"] in leisure_names]
    if active_recurring:
        monthly = sum(entry["monthly_amount"] for entry in active_recurring)
        names = ", ".join(entry["name"] for entry in active_recurring[:6])
        recommend("subscriptions", "low", f"{len(active_recurring)} recurring discretionary payments, {euro(monthly)} a month",
                  f"{names}. Cancel what you no longer use; a yearly review of this list is the cheapest saving there is.", monthly_impact=monthly * 0.3, saving=True)

    donation_row = next((row for row in expense_rows if name_has(categories.get(row["category_id"]), "donation")), None)
    if donation_row and donation_row["total"] > 0:
        yearly = donation_row["total"] / max(len(window), 1) * 12
        recommend("donations", "info", f"Your donations ({euro(yearly)} a year) can cut your income tax by 66 %",
                  f"In France, gifts to qualifying charities give a tax reduction of 66 % (75 % up to 1 000 € for aid to people in difficulty), i.e. about {euro(yearly * 0.66)} back. "
                  "Keep the tax receipts and declare them in the donation boxes of your tax return.", monthly_impact=yearly * 0.66 / 12, category_id=donation_row["category_id"], saving=True)

    business_row = next((row for row in expense_rows if name_has(categories.get(row["category_id"]), "business")), None)
    if business_row and business_row["total"] > 0:
        recommend("business", "medium", f"{euro(business_row['total'])} spent on your company from personal accounts",
                  "Make sure each of these is reimbursed by the company (expense report) or recorded as a shareholder loan, otherwise you finance the company yourself and lose the deduction.",
                  monthly_impact=business_row["average"], category_id=business_row["category_id"], saving=True)

    essential_monthly = essential_spending - sum(row["one_off_total"] for row in expense_rows if row["necessity"] == "essential") / month_count
    liquid_savings = sum(
        (account.statement_balance or 0.0) for account in accounts if account.kind.value == "savings" and account.is_active
    )
    if essential_monthly > 0:
        target_low, target_high = essential_monthly * 3, essential_monthly * 6
        if liquid_savings <= 0:
            recommend("emergency_fund", "medium", f"Build an emergency fund of {euro(target_low)} to {euro(target_high)}",
                      f"That is 3 to 6 months of essential spending ({euro(essential_monthly)} a month). No savings account is tracked yet: add your Livret A / LDDS as accounts with their balance so the app can follow it.")
        elif liquid_savings < target_low:
            recommend("emergency_fund", "medium", f"Emergency fund {euro(liquid_savings)}, target {euro(target_low)} to {euro(target_high)}",
                      f"Covers {liquid_savings / essential_monthly:.1f} months of essential spending. Fill the Livret A first: it is liquid and tax free.")
        else:
            recommend("emergency_fund", "info", f"Emergency fund covers {liquid_savings / essential_monthly:.1f} months of essential spending",
                      "Above the 3 month floor. Beyond 6 months, extra cash is better placed in a PEA, assurance-vie or PER depending on your horizon.")

    if uncategorized:
        recommend("uncategorized", "low", f"{uncategorized} transactions are still uncategorized",
                  "They are missing from every figure above. Use the Transactions page, filter 'Uncategorized only'.")
    if overview["unclassified_spending"] > 0:
        recommend("necessity", "low", "Some categories are not marked essential or flexible",
                  f"{euro(overview['unclassified_spending'])} a month is unclassified, so the essential / flexible split is incomplete. Set it on the Categories page.")

    severity_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    recommendations.sort(key=lambda item: (severity_order[item["severity"]], -(item["monthly_impact"] or 0)))
    potential = sum(item["monthly_impact"] or 0 for item in recommendations if item["saving"])

    one_off_rows = sorted(
        [t for t in one_offs if month_of(t.date) in window_set or month_of(t.date) == current_month], key=lambda t: t.amount
    )[:12]

    return {
        "empty": False,
        "overview": overview,
        "potential_monthly_savings": round(potential, 2),
        "months": series,
        "categories": category_rows,
        "recurring": recurring,
        "overdraft": overdraft,
        "recommendations": recommendations,
        "one_offs": [
            {"id": t.id, "date": t.date.isoformat(), "label": t.label, "amount": t.amount,
             "category_name": categories[t.category_id].name if t.category_id in categories else "Uncategorized"}
            for t in one_off_rows
        ],
    }

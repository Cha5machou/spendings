"""Action plan: turns what the app knows into dated, concrete things to do.

Every item answers three questions: what is the issue (with the numbers), what exactly to do (steps),
and by when (this week, next 30 days, next 3 months, next 6-12 months). Nothing here is advice from a
licensed adviser: it is the app's own analysis of the user's data, written as a to-do list.

Near-term cash is forecast day by day from what is known: current balances, loan instalments,
user-entered upcoming payments, fixed recurring debits and the usual salary and rent days."""

import calendar
import re
import statistics
from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.database import get_session
from app.models import AccountKind, Category, Transaction
from app.routers.accounts import list_accounts
from app.routers.income import income as compute_income
from app.routers.insights import insights as compute_insights, merchant_key
from app.routers.plan import build_context, compute_plan, get_settings
from app.routers.properties import list_properties
from app.routers.wealth import wealth as compute_wealth

router = APIRouter(prefix="/actions", tags=["actions"])

FORECAST_DAYS = 45
HORIZONS = [("week", "This week"), ("month", "Next 30 days"), ("quarter", "Next 3 months"), ("year", "Next 6 to 12 months")]
DEBT_WORDS = ("mortgage", "loan", "credit")
MIN_RECURRING = 15.0


def euro(value: float) -> str:
    return f"{abs(value):,.0f} €".replace(",", " ")


def signed(value: float) -> str:
    return f"-{euro(value)}" if value < 0 else euro(value)


def short_date(day: date) -> str:
    return f"{day.day} {day.strftime('%b')}"


def month_name(month: str | None) -> str:
    if not month:
        return "later"
    return date(int(month[:4]), int(month[5:7]), 1).strftime("%B %Y")


def horizon_for(day: date, today: date) -> str:
    days = (day - today).days
    return "week" if days <= 7 else "month" if days <= 30 else "quarter" if days <= 92 else "year"


def day_in_month(year: int, month: int, day_of_month: int) -> date:
    return date(year, month, min(day_of_month, calendar.monthrange(year, month)[1]))


def typical_day(days: list[date]) -> int | None:
    return int(statistics.median([day.day for day in days])) if days else None


# ---------------------------------------------------------------------------------------------
# Cash forecast
# ---------------------------------------------------------------------------------------------


def forecast_cash(session: Session, today: date, context: dict, insight_data: dict, loans: list[dict], properties: list[dict]) -> dict | None:
    accounts = [a for a in list_accounts(session=session)
                if a["kind"] in (AccountKind.checking, AccountKind.credit_card) and a["is_active"] and a["current_balance"] is not None]
    if not accounts:
        return None
    start_balance = sum(a["current_balance"] for a in accounts)
    limit = sum(a["overdraft_limit"] for a in accounts)

    categories = {category.id: category for category in session.exec(select(Category)).all()}
    since = today - timedelta(days=180)
    transactions = session.exec(select(Transaction).where(Transaction.date >= since, Transaction.date <= today).order_by(Transaction.date)).all()

    events: dict[date, list[tuple[str, float]]] = defaultdict(list)

    def add(day: date, label: str, amount: float):
        if today < day <= today + timedelta(days=FORECAST_DAYS):
            events[day].append((label, amount))

    # Known commitments: loan instalments and the user's upcoming payments.
    for loan in loans:
        for payment in loan["_future"]:
            add(payment.due_date, loan["name"], -payment.total)
    for day, amount, label in context["scheduled"]:
        add(day, label, -amount)

    # Salary and rent usually arrive on a similar day each month.
    salary_dates = [t.date for t in transactions if t.amount > 0 and categories.get(t.category_id) and categories[t.category_id].kind.value == "income" and "salary" in categories[t.category_id].name.lower()]
    salary_day = typical_day(salary_dates[-6:])
    if salary_day and context["salary_net"]:
        for offset in range(0, 3):
            month_index = today.month - 1 + offset
            day = day_in_month(today.year + month_index // 12, month_index % 12 + 1, salary_day)
            add(day, "Salary", context["salary_net"])
    prop = properties[0] if properties else None
    if prop and prop.get("income_category_id") and context["rent_net"]:
        rent_dates = [t.date for t in transactions if t.category_id == prop["income_category_id"] and t.amount > 0]
        rent_day = typical_day(rent_dates[-4:])
        if rent_day:
            for offset in range(0, 3):
                month_index = today.month - 1 + offset
                add(day_in_month(today.year + month_index // 12, month_index % 12 + 1, rent_day), "Rent from your tenant", context["rent_net"])

    # Fixed recurring debits that are not loans (rent, phone, insurance...): placed on their usual day.
    by_key: dict[str, list[date]] = defaultdict(list)
    for t in transactions:
        category = categories.get(t.category_id)
        if t.amount < 0 and category and category.kind.value == "expense":
            by_key[merchant_key(t.label).title()].append(t.date)
    recurring_total = 0.0
    recurring_days = []
    for entry in insight_data["recurring"]:
        if not entry["active"] or entry["monthly_amount"] < MIN_RECURRING or any(word in (entry["category_name"] or "").lower() for word in DEBT_WORDS):
            continue
        day_of_month = typical_day(by_key.get(entry["name"], [])[-6:])
        if not day_of_month:
            continue
        recurring_total += entry["monthly_amount"]
        recurring_days.append({"name": entry["name"], "amount": entry["monthly_amount"], "day": day_of_month, "fixed": entry["fixed_amount"]})
        for offset in range(0, 3):
            month_index = today.month - 1 + offset
            add(day_in_month(today.year + month_index // 12, month_index % 12 + 1, day_of_month), entry["name"], -entry["monthly_amount"])

    # Everything else (food, leisure, fuel...) is spread evenly across the days.
    daily_other = max(0.0, context["core_spending"] - recurring_total) / 30.4

    rows = []
    balance = start_balance
    for offset in range(1, FORECAST_DAYS + 1):
        day = today + timedelta(days=offset)
        known = events.get(day, [])
        change = sum(amount for _, amount in known) - daily_other
        balance += change
        rows.append({"date": day.isoformat(), "balance": round(balance, 2), "events": [{"label": label, "amount": round(amount, 2)} for label, amount in known if abs(amount) >= 20]})
    lowest = min(rows, key=lambda row: row["balance"])
    beyond = next((row for row in rows if row["balance"] < -limit), None)
    return {
        "start_balance": round(start_balance, 2), "limit": round(limit, 2), "daily_other_spending": round(daily_other, 2),
        "salary_day": salary_day, "rows": rows,
        "lowest": {"date": lowest["date"], "balance": lowest["balance"]},
        "first_beyond_limit": beyond["date"] if beyond else None,
        "worst_gap": round(max(0.0, -limit - lowest["balance"]), 2),
        "days_overdrawn": sum(1 for row in rows if row["balance"] < 0),
        "recurring_days": sorted(recurring_days, key=lambda item: -item["amount"])[:6],
    }


# ---------------------------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------------------------


def build_actions(session: Session, today: date, context: dict, insight_data: dict, loans: list[dict], properties: list[dict],
                  wealth_data: dict, plan: dict, income_data: dict, forecast: dict | None) -> list[dict]:
    actions: list[dict] = []

    def add(horizon: str, title: str, issue: str, steps: list[str], *, monthly: float | None = None, once: float | None = None,
            priority: int = 2, link: str | None = None, link_label: str | None = None, due: date | None = None, key: str):
        actions.append({
            "key": key, "horizon": horizon, "title": title, "issue": issue, "steps": steps, "priority": priority,
            "impact": {"monthly": round(monthly, 2) if monthly else None, "once": round(once, 2) if once else None},
            "link": link, "link_label": link_label, "due": due.isoformat() if due else None,
        })

    overview = insight_data["overview"]
    recommendations = {rec["key"]: rec for rec in insight_data["recommendations"]}
    milestones = plan["milestones"]
    settings = plan["settings"]

    # 1. Cash in the next days ---------------------------------------------------------------
    if forecast:
        low_day = date.fromisoformat(forecast["lowest"]["date"])
        before_payday = [e for row in forecast["rows"] if row["date"] <= forecast["lowest"]["date"] for e in row["events"] if e["amount"] < 0 and e["label"] != "Salary"]
        biggest = sorted(before_payday, key=lambda e: e["amount"])[:3]
        biggest_text = ", ".join(f"{e['label']} {euro(e['amount'])}" for e in biggest) if biggest else "your usual spending"
        if forecast["first_beyond_limit"]:
            day = date.fromisoformat(forecast["first_beyond_limit"])
            days_away = (day - today).days
            add("week" if days_away <= 7 else "month", f"Cover a {euro(forecast['worst_gap'])} gap before {short_date(day)}",
                f"Your current accounts are forecast to reach {signed(forecast['lowest']['balance'])} on {short_date(low_day)}, but your authorised overdraft stops at -{euro(forecast['limit'])}. "
                f"The pressure comes from payments before the next salary ({biggest_text}).",
                ["Check the real balances of your accounts now against the forecast below.",
                 f"Before {short_date(day)}, move about {euro(forecast['worst_gap'] + 100)} onto the account that will be short: from your savings, or ask your bank for a temporary overdraft increase.",
                 "If you can, postpone one non-essential payment or purchase until after payday.",
                 "After payday, ask the bank to move the date of your direct debits (see 'Stop living in the overdraft')."],
                once=forecast["worst_gap"], priority=1, due=day, key="cash_gap", link="/accounts", link_label="Open accounts")
        elif forecast["lowest"]["balance"] < 0:
            add(horizon_for(low_day, today) if (low_day - today).days <= 30 else "month", f"Expect to use {euro(forecast['lowest']['balance'])} of overdraft until payday",
                f"The forecast low point is {signed(forecast['lowest']['balance'])} on {short_date(low_day)}, within your {euro(forecast['limit'])} authorised overdraft. Main payments before payday: {biggest_text}.",
                ["Keep non-essential spending to a minimum until your salary arrives.", "Do not let an unexpected bill land on the low-point day."],
                priority=2, due=low_day, key="cash_low")

    # 2. Dated payments you entered ------------------------------------------------------------
    for day, amount, label in context["scheduled"]:
        if (day - today).days <= 60 and amount >= 100:
            add(horizon_for(day, today), f"{label}: {euro(amount)} on {short_date(day)}",
                f"You listed this upcoming payment. It leaves your account on {short_date(day)}.",
                ["Make sure the account that is debited holds the money that day (see the cash forecast).",
                 "If it is not an automatic debit, pay it on time to avoid penalties."],
                once=amount, priority=1 if (day - today).days <= 14 else 2, due=day, key=f"scheduled_{day.isoformat()}_{int(amount)}")

    # 3. Credits ending soon: decide where the freed money goes -----------------------------
    endings: dict[str, list[dict]] = defaultdict(list)
    for loan in loans:
        if loan["kind"] == "mortgage" or not loan["projected_end"]:
            continue
        end = date.fromisoformat(loan["projected_end"])
        if 0 < (end - today).days <= 190 and loan["monthly_payment"] >= 5:
            endings[loan["projected_end"][:7]].append(loan)
    for month, group in sorted(endings.items()):
        names = ", ".join(loan["name"] for loan in group)
        freed = sum(loan["monthly_payment"] for loan in group)
        end_day = date(int(month[:4]), int(month[5:7]), 1)
        add("month" if (end_day - today).days <= 40 else "quarter", f"{month_name(month)}: {names} end, so redirect {euro(freed)} a month",
            f"{len(group)} credit(s) finish in {month_name(month)}. If nothing is planned, that {euro(freed)} a month is absorbed by everyday spending.",
            ["After the last payment, check that the direct debit really stops.",
             f"Set up a standing order of {euro(freed)} on payday to your savings (livret first, then PEA/CTO), starting the month after the last payment.",
             "Do not replace it with a new instalment plan."],
            monthly=freed, priority=2, due=end_day, key=f"ending_{month}", link="/loans", link_label="See my credits")

    # 4. Too many instalment plans ------------------------------------------------------------
    plans = [loan for loan in loans if loan["kind"] in ("installment", "revolving")]
    if len(plans) >= 3:
        recent = [loan for loan in plans if loan.get("start_date") and (today - loan["start_date"]).days <= 120]
        owed = sum(loan["current_balance"] for loan in plans)
        monthly = sum(loan["monthly_payment"] for loan in plans)
        add("week", "Stop opening new instalment plans",
            f"{len(plans)} instalment or revolving credits are running ({euro(owed)} still owed, {euro(monthly)} a month){f', {len(recent)} of them started in the last 4 months' if recent else ''}. "
            "They keep your account in the red and hide the real cost of purchases.",
            ["Before the next purchase on PayPal in 4, Cofidis, Sofinco and the like: pay from savings or wait until you can pay in full.",
             "Cancel stored cards or limits that make these plans one click away if needed.",
             "Use the payoff planner to see which credit to clear first."],
            priority=2, key="no_new_credit", link="/loans", link_label="Open payoff planner")

    # 5. Overdraft habit ----------------------------------------------------------------------
    overdrawn = [entry for entry in insight_data["overdraft"] if entry["days_negative"] > 15]
    if overdrawn:
        worst = max(overdrawn, key=lambda entry: entry["days_negative"])
        accounts_text = "; ".join(f"{entry['account_name']} was overdrawn {entry['days_negative']} of {entry['days_tracked']} days" + (f" and went beyond its limit on {entry['days_beyond_limit']}" if entry["days_beyond_limit"] else "") for entry in overdrawn)
        debits = forecast["recurring_days"][:3] if forecast else []
        debit_text = ", ".join(f"{d['name']} ({euro(d['amount'])}, around the {d['day']}th)" for d in debits) or "your largest direct debits"
        fees = recommendations.get("bank_fees")
        add("month", "Stop living in the overdraft",
            f"{accounts_text}. Overdrafts bring incident fees and make every payment risky.",
            [f"Pick one account for salary and fixed bills, and keep the other for as few payments as possible.",
             f"Ask your bank (or change the date in your online space) to move the biggest direct debits to just after payday: {debit_text}.",
             "Once credits end (see below) keep a small positive cushion on the main account before investing.",
             "If a second account only holds a few debits, consider closing it to simplify."],
            monthly=(fees["monthly_impact"] if fees else None), priority=2, key="overdraft_habit", link="/insights", link_label="See the overdraft chart")

    # 6. Findings from the analysis, written as actions ------------------------------------
    moved = [rec for rec in insight_data["recommendations"] if rec["key"].startswith(("spike_", "trend_"))]
    if moved:
        add("week", f"Look at {len(moved)} categories that moved recently",
            "Spending in these categories changed compared with your usual level. It may be one-off, or a new habit that will cost you every month.",
            [f"{rec['title']}. {rec['detail']}" for rec in moved][:6] + ["Open each category, read last month's lines, and decide: one-off or new habit?"],
            priority=3, key="categories_moved", link="/insights", link_label="Open the analysis")
    for rec in insight_data["recommendations"]:
        key = rec["key"]
        link_category = f"/transactions?category_id={rec['category_id']}" if rec.get("category_id") else "/insights"
        if key == "bank_fees":
            add("month", "Cut your bank fees", rec["title"] + ". " + rec["detail"],
                ["Call or write to your bank and ask for the incident and overdraft fees to be refunded: it is often granted once.",
                 "Compare your account package with a free online account for daily banking.",
                 "Avoid the cause: see 'Stop living in the overdraft'."], monthly=rec["monthly_impact"], priority=3, key=key, link=link_category, link_label="See the fees")
        elif key == "business":
            add("month", "Get your company costs reimbursed", rec["title"] + ". " + rec["detail"],
                ["List the payments you made personally for the company (open the category).",
                 "Send an expense report or invoice to the company for each, or record them as a shareholder loan with your accountant.",
                 "From now on pay company costs from the company account."], monthly=rec["monthly_impact"], priority=2, key=key, link=link_category, link_label="See these payments")
        elif key == "discretionary":
            add("month", "Set a monthly budget for your top discretionary categories", rec["title"] + ". " + rec["detail"],
                ["Write the three monthly limits down (the averages in the analysis, minus 10 %).", "Check the totals on the Transactions page once a week.",
                 "If you overshoot one month, take it from the next, not from savings."], monthly=rec["monthly_impact"], priority=3, key=key, link=link_category, link_label="Open the category")
        elif key == "subscriptions":
            add("week", "Review your subscriptions", rec["title"] + ". " + rec["detail"],
                ["Open the recurring payments list in the analysis.", "Cancel what you have not used in the last two months.", "Put a yearly reminder to repeat this."],
                monthly=rec["monthly_impact"], priority=3, key=key, link="/insights", link_label="Open recurring payments")
        elif key == "donations":
            add("year", "Keep your donation receipts for your tax return", rec["title"] + ". " + rec["detail"],
                ["Collect the tax receipts of every charity you gave to (most send them in the spring).", "Enter the amounts in the donation boxes of your tax return.", "Keep them for three years."],
                monthly=rec["monthly_impact"], priority=3, key=key, link=link_category, link_label="See my donations")
        elif key == "debt_ratio" and rec["severity"] == "high":
            add("year", "Bring your debt ratio under 33 % before asking for a new loan", rec["title"] + ". " + rec["detail"],
                ["Do not open any new credit: every instalment counts in the ratio banks compute.", "Let the small credits end (dates in the plan) and check the ratio again afterwards.",
                 "Ask a broker or your bank to simulate the ratio at the date you plan to borrow."], priority=2, key=key, link="/loans", link_label="Open credits")
        elif key == "uncategorized":
            add("week", rec["title"], rec["detail"], ["Open Transactions, filter on 'Uncategorized only'.", "Pick a category and accept the suggested rule so it is automatic next time."],
                priority=2, key=key, link="/transactions?uncategorized=1", link_label="Categorize now")

    # 7. The flat -----------------------------------------------------------------------------
    for prop in properties:
        for check in prop["checks"]:
            title = check["title"]
            if title.startswith("No co-ownership payment"):
                add("week", "Check your co-ownership account for unpaid calls", check["detail"],
                    ["Log in to the syndic's owner portal (or ask the agency) and read the account balance.", "Pay any call that is due: late fees accrue.", "Set up the direct debit so it does not happen again."],
                    priority=1, key="syndic_arrears", link="/rental", link_label="Open rental property")
            elif title.startswith("Rent revision due"):
                match = re.search(r"(\d{2})/(\d{2})/(\d{4})", title)
                due = date(int(match.group(3)), int(match.group(2)), int(match.group(1))) if match else None
                add(horizon_for(due, today) if due else "year", f"Ask the agency to apply the rent revision{' on ' + short_date(due) + ' ' + str(due.year) if due else ''}", check["detail"],
                    ["Write to the agency a month before the date and ask them to apply the index revision.", "Check the new rent on the next statement."],
                    priority=3, due=due, key="rent_revision", link="/rental", link_label="Open rental property")
            elif title.startswith("Furnished let"):
                add("quarter", "Check the tax regime of your furnished rental with an accountant", check["detail"],
                    ["Book an accountant who knows furnished rentals (LMNP).", "Gather the purchase invoices of the furniture and the works.", "Confirm the activity registration and which regime you are under."],
                    priority=2, key="lmnp", link="/rental", link_label="Open rental property")
            elif title.startswith("Property tax will rise"):
                add("year", "Budget for a higher property tax", check["detail"], ["Add the expected amount as an upcoming payment in the Goals page once you know it."],
                    priority=3, key="property_tax", link="/plan", link_label="Open goals")
            elif title.startswith("The flat costs you"):
                levers = " ".join(f"{lever['label']}: +{euro(lever['monthly'])}/month." for lever in prop["levers"])
                add("year", f"Improve what the rental costs you each month ({euro(prop['monthly_result'])})", check["detail"] + " " + levers,
                    ["Ask your bank for a quote on the mortgage rate (a buy-back or renegotiation) and compare with the fees.", "Ask the agency to review its fee, or compare another agency.",
                     "Check the rent against similar listings and apply the yearly revision."],
                    monthly=max(prop["levers"][0]["monthly"] if prop["levers"] else 0, 0), priority=2, key="rental_economics", link="/loans", link_label="Test a lower rate")

    # 8. Savings: the buffer first, then automatic investing -----------------------------------
    essential = context["essential_typical"]
    cash_savings = wealth_data["net_worth"]["cash_savings"]
    if essential > 0 and cash_savings < essential * 3:
        low, high = essential * 3, essential * 6
        start_month = milestones["overdraft_cleared_month"]
        add("quarter", f"Build an emergency buffer of {euro(low)} to {euro(high)}",
            f"Emergency cash is {euro(cash_savings)}, which covers {cash_savings / essential:.1f} months of essential spending ({euro(essential)} a month). One unexpected bill puts you back in the red.",
            ["Open a Livret A or LDDS if you do not have one (free, instantly available).",
             f"Set a standing order on payday{' from ' + month_name(start_month) if start_month else ''}: start with whatever is left after the plan, even 100 € a month.",
             "Keep PEA and CTO for long-term money, not for emergencies.",
             "In 'Goals', add an emergency-fund goal with this target to follow it."],
            priority=2, key="emergency_fund", link="/plan", link_label="Add it as a goal")
    if milestones["overdraft_cleared_month"] and milestones["steady_surplus"] and milestones["steady_surplus"] > 50:
        total = settings["split_pea"] + settings["split_cto"] + settings["split_livrets"] or 1
        steady = milestones["steady_surplus"]
        parts = [("PEA", settings["split_pea"]), ("CTO", settings["split_cto"]), ("livrets", settings["split_livrets"])]
        split_text = ", ".join(f"{euro(steady * share / total)} to {name}" for name, share in parts if share)
        start = date.fromisoformat(milestones["overdraft_cleared_month"] + "-01")
        add(horizon_for(start, today), f"From {month_name(milestones['overdraft_cleared_month'])}: invest about {euro(steady)} a month automatically",
            f"Until then your surplus goes into clearing the overdraft and the one-off payments. After that the plan leaves about {euro(steady)} a month.",
            [f"Create standing orders on payday: {split_text}.", "Automate them so the money leaves before you can spend it.", "Re-check the plan every quarter."],
            monthly=steady, priority=2, due=start, key="start_investing", link="/plan", link_label="Open my plan")

    # 9. Goals that are not on track -----------------------------------------------------------
    for goal in plan["goals"]:
        progress = goal.get("progress")
        if progress and not progress["on_track"] and not progress["beyond_projection"] and goal["target_date"]:
            months_left = max(goal["months_away"] or 1, 1)
            extra = progress["gap"] / months_left
            add("quarter" if months_left <= 12 else "year", f"Goal '{goal['title']}' is {euro(progress['gap'])} short",
                f"By {month_name(goal['target_date'][:7])} the plan reaches {euro(progress['projected_at_date'])} against a target of {euro(goal['target_amount'])}.",
                [f"Either save about {euro(extra)} more per month toward it,"
                 + (f" or accept the date {month_name(progress['reached_month'])}," if progress["reached_month"] else "") + " or lower the target.",
                 "Edit the goal or the plan assumptions in Goals and see the effect."],
                monthly=extra, priority=2, key=f"goal_{goal['id']}", link="/plan", link_label="Open goals")

    # 10. Income and tax -----------------------------------------------------------------------
    if not income_data.get("empty"):
        add("month", "Ask your employer about a company savings plan (PEE or PERCO)",
            "Your payslips show no company savings plan. If one exists, the employer often tops up what you pay in, which is free money.",
            ["Ask HR whether a PEE/PERCO exists and what the employer contribution is.", "If it does, compare it with your own plan before paying in."], priority=3, key="pee", link="/income", link_label="See my payslips")
        if income_data["marginal_rate"] >= 0.30 and cash_savings >= essential * 3 > 0:
            per = income_data["per"]
            add("year", "Decide about a PER payment before year end",
                f"You are in the {round(income_data['marginal_rate'] * 100)} % bracket: each 1 000 € paid in saves about {euro(per['tax_saved_per_1000'])} of tax, up to about {euro(per['max_tax_saved'])}.",
                ["Check the exact ceiling on your tax notice.", "Only use money you will not need before retirement or the purchase of your main home.", "Pay before 31 December to count for this year."],
                once=per["max_tax_saved"], priority=3, key="per", link="/income", link_label="See the estimate")

    # 11. Wealth checks that are not about the buffer ------------------------------------------
    for check in wealth_data["checks"]:
        if check["title"].startswith("A leveraged product"):
            add("year", "Review the leveraged product in your portfolio", check["detail"],
                ["Decide if it is meant as a short trade; if not, stop the automatic purchases.", "Replace it with a broad index fund if you want to keep the exposure."], priority=3, key="leveraged", link="/wealth", link_label="Open savings")

    order = {"week": 0, "month": 1, "quarter": 2, "year": 3}
    actions.sort(key=lambda action: (order[action["horizon"]], action["priority"], action["due"] or "9999", -(action["impact"]["monthly"] or 0)))
    return actions


def routine_items(session: Session, today: date, wealth_data: dict, income_data: dict) -> list[dict]:
    last_transaction = session.exec(select(Transaction.date).order_by(Transaction.date.desc())).first()
    stale_statement = last_transaction is None or (today - last_transaction).days > 25
    snapshot_dates = [date.fromisoformat(a["as_of"]) for a in wealth_data["accounts"] if a["as_of"]]
    stale_balances = bool(snapshot_dates) and (today - max(snapshot_dates)).days > 35
    last_payslip = income_data["payslips"][-1]["month"] if not income_data.get("empty") else None
    expected_payslip = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    return [
        {"title": "Import your latest bank statements", "when": "After each month end", "link": "/documents",
         "status": f"Last transaction imported: {last_transaction.strftime('%d %b %Y')}" if last_transaction else "Nothing imported yet", "due": stale_statement},
        {"title": "Update your savings balances", "when": "Once a month", "link": "/wealth",
         "status": f"Last update: {max(snapshot_dates).strftime('%d %b %Y')}" if snapshot_dates else "No balance recorded", "due": stale_balances},
        {"title": "Add the new payslip", "when": "Once a month", "link": "/income",
         "status": f"Last payslip: {last_payslip}" if last_payslip else "No payslip yet", "due": bool(last_payslip) and last_payslip < expected_payslip},
        {"title": "Check new transactions are categorised", "when": "After each import", "link": "/transactions?uncategorized=1", "status": "", "due": False},
        {"title": "Re-read this action plan", "when": "Once a month", "link": "/", "status": "", "due": False},
    ]


@router.get("")
def action_plan(session: Session = Depends(get_session)):
    today = date.today()
    context = build_context(session)
    insight_data = compute_insights(months=12, session=session)
    if insight_data.get("empty"):
        return {"empty": True}
    loans = context["loans"]
    properties = list_properties(session=session)
    wealth_data = compute_wealth(session=session)
    plan = compute_plan(session, get_settings(session))
    income_data = compute_income(session=session)
    forecast = forecast_cash(session, today, context, insight_data, loans, properties)
    actions = build_actions(session, today, context, insight_data, loans, properties, wealth_data, plan, income_data, forecast)

    # ---- the situation in a few lines -------------------------------------------------------
    overview = insight_data["overview"]
    surplus = overview["typical_surplus"]
    debt_monthly = sum(row["monthly_payment"] for row in loans)
    income_typical = overview["typical_income"]
    first_debt = plan["projection"][0]["debt_service"] if plan["projection"] else 0
    relief = next((row for row in plan["projection"] if first_debt and row["debt_service"] <= first_debt * 0.65), None)
    bullets = []
    bullets.append(f"In a typical month {euro(income_typical)} comes in and {euro(overview['typical_spending'])} goes out: you are {euro(surplus)} {'short' if surplus < 0 else 'ahead'}.")
    if debt_monthly and income_typical:
        bullets.append(f"Credits and the mortgage take {euro(debt_monthly)} a month, {round(debt_monthly / income_typical * 100)} % of your income.")
    if relief:
        bullets.append(f"Relief is coming: payments fall from {euro(first_debt)} now to {euro(relief['debt_service'])} by {month_name(relief['month'])}.")
    if forecast and forecast["first_beyond_limit"]:
        bullets.append(f"Urgent: your accounts are forecast {euro(forecast['worst_gap'])} beyond the authorised overdraft before payday.")
    elif wealth_data["net_worth"]["cash_savings"] < context["essential_typical"]:
        bullets.append(f"Your emergency cash is {euro(wealth_data['net_worth']['cash_savings'])}: one unexpected bill puts you back in the red.")
    urgent = sum(1 for action in actions if action["horizon"] == "week" and action["priority"] == 1)

    grouped = [{"key": key, "label": label, "actions": [a for a in actions if a["horizon"] == key]} for key, label in HORIZONS]
    return {
        "empty": False,
        "headline": {
            "bullets": bullets, "urgent": urgent, "tone": "attention" if (urgent or surplus < 0) else "ok",
            "metrics": {
                "typical_surplus": surplus, "debt_monthly": round(debt_monthly, 2), "debt_share": round(debt_monthly / income_typical, 4) if income_typical else None,
                "cash_savings": wealth_data["net_worth"]["cash_savings"], "essential_monthly": context["essential_typical"],
                "forecast_low": forecast["lowest"] if forecast else None, "forecast_limit": forecast["limit"] if forecast else None,
            },
        },
        "forecast": forecast,
        "horizons": grouped,
        "routine": routine_items(session, today, wealth_data, income_data),
    }

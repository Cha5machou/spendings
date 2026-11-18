"""A read-only assistant that answers questions about the user's own finances.

Claude is given tools that read the app's data (spending, loans, rental flat, savings, income, plan)
and one what-if tool that recomputes the plan with different assumptions without saving anything.
Nothing here can modify data."""

import json
from datetime import date

import anthropic
from sqlmodel import Session, select

from app.config import settings
from app.extraction import claude_extractor
from app.models import Category, PlanSettings, Transaction

MAX_TOOL_ROUNDS = 8
MAX_TOOL_RESULT_CHARS = 24_000

SYSTEM_PROMPT = """You are the analyst built into the user's personal-finance app. You answer questions about THEIR money using the tools provided, which read their real data.

Rules:
- Ground every number in a tool result. If you do not have the data, say so instead of guessing, and say which part of the app would hold it.
- Be concrete and brief: lead with the answer, then the few numbers that support it. Amounts in euros, French formats are fine in labels.
- State assumptions when a calculation depends on them (rates, dates, sale price...). The plan tool can test other assumptions: use it for what-if questions rather than doing mental arithmetic.
- You are not a licensed adviser. Give analysis and options, and point to a tax adviser, notary or the bank where the decision depends on rules you cannot see (tax regime, loan contracts, early-repayment terms).
- You can only read data. Never claim to have changed anything; if a change is needed, tell the user where in the app to make it.
- The user writes in English; keep to their language. Today is {today}."""

TOOLS = [
    {"name": "get_spending_analysis", "description": "Typical month (income, spending, surplus), every category with its monthly average, last month, recent trend and top merchants, recurring payments, one-offs, overdraft usage per account and the computed recommendations. Use for any question about where money goes.",
     "input_schema": {"type": "object", "properties": {"months": {"type": "integer", "description": "Window of complete months: 1, 6, 12 or 0 for all time. Default 12."}}}},
    {"name": "search_transactions", "description": "Search individual transactions. Amounts are signed: negative = money out. Returns at most `limit` rows, newest first.",
     "input_schema": {"type": "object", "properties": {
         "text": {"type": "string", "description": "Case-insensitive text to find in the label"},
         "category": {"type": "string", "description": "Category name (exact or partial)"},
         "start": {"type": "string", "description": "YYYY-MM-DD"}, "end": {"type": "string", "description": "YYYY-MM-DD"},
         "min_amount": {"type": "number"}, "max_amount": {"type": "number"},
         "limit": {"type": "integer", "description": "Default 30, maximum 100"}}}},
    {"name": "get_accounts", "description": "Current accounts with current balance, authorised overdraft and available amount.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_loans", "description": "All loans and credits: balance, instalment, rate, end date, remaining interest, plus totals (debt, monthly payments, debt-to-income) and the monthly debt-service timeline.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_rental_property", "description": "The rented flat: lease terms, agency fees, monthly economics, real cash flow by month, checks to be aware of.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_wealth", "description": "Savings and investments per account, history, net worth, allocation, positions and the savings checks.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_income", "description": "Payslips: gross, net, income-tax withholding, estimated tax bracket and PER ceiling.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_plan", "description": "The saved plan: milestones, savings projection highlights, housing-cost scenarios, sale of the rented flat and what a purchase in Aix could reach, with the assumptions used.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "run_plan_scenario", "description": "Recompute the plan with different assumptions WITHOUT saving them. Pass only the settings to change. Keys: split_pea, split_cto, split_livrets (percent), av_monthly, livrets_target, expected_return_pct, new_credit_monthly, housing_delta (extra monthly housing cost), sale_date, sale_price, sale_agent_fee_pct, purchase_date (YYYY-MM-DD), purchase_price, purchase_savings_share_pct, loan_rate_pct, loan_years, loan_insurance_pct, notary_fees_pct, rent_weight_pct, max_debt_ratio_pct.",
     "input_schema": {"type": "object", "properties": {"overrides": {"type": "object", "description": "Settings to change, e.g. {\"housing_delta\": 200, \"loan_rate_pct\": 3.2}"}}, "required": ["overrides"]}},
]


def compact(value):
    """JSON text of a tool result, cut if huge so one call cannot flood the context."""
    text = json.dumps(value, default=str, ensure_ascii=False, separators=(",", ":"))
    if len(text) > MAX_TOOL_RESULT_CHARS:
        text = text[:MAX_TOOL_RESULT_CHARS] + '..."[truncated]"'
    return text


def strip_plan(plan: dict) -> dict:
    """Plan without the month-by-month rows (hundreds of lines); keep a yearly sample instead."""
    sample = [row for row in plan["projection"] if row["month"].endswith(("-06", "-12"))]
    return {**{key: value for key, value in plan.items() if key != "projection"}, "projection_sample": sample}


def run_tool(name: str, arguments: dict, session: Session):
    from app.routers.accounts import list_accounts
    from app.routers.income import income
    from app.routers.insights import insights
    from app.routers.loans import list_loans
    from app.routers.plan import compute_plan, get_settings
    from app.routers.properties import list_properties
    from app.routers.wealth import wealth

    if name == "get_spending_analysis":
        data = insights(months=int(arguments.get("months", 12)), session=session)
        if data.get("empty"):
            return data
        data["categories"] = [
            {key: row[key] for key in ("name", "kind", "necessity", "average", "typical", "months_basis", "last_month", "recent_average", "earlier_average", "current_month", "one_off_total", "pattern", "series", "top_merchants")}
            for row in data["categories"] if row["kind"] != "transfer"
        ]
        data["recurring"] = [entry for entry in data["recurring"] if entry["active"]]
        for account in data["overdraft"]:
            account.pop("by_month", None)
        return data
    if name == "search_transactions":
        query = select(Transaction).order_by(Transaction.date.desc())
        categories = {category.id: category.name for category in session.exec(select(Category)).all()}
        if arguments.get("start"):
            query = query.where(Transaction.date >= date.fromisoformat(arguments["start"]))
        if arguments.get("end"):
            query = query.where(Transaction.date <= date.fromisoformat(arguments["end"]))
        if arguments.get("min_amount") is not None:
            query = query.where(Transaction.amount >= arguments["min_amount"])
        if arguments.get("max_amount") is not None:
            query = query.where(Transaction.amount <= arguments["max_amount"])
        if arguments.get("text"):
            query = query.where(Transaction.label.ilike(f"%{arguments['text']}%"))
        wanted = (arguments.get("category") or "").lower()
        if wanted:
            ids = [category_id for category_id, category_name in categories.items() if wanted in category_name.lower()]
            query = query.where(Transaction.category_id.in_(ids or [-1]))
        limit = min(int(arguments.get("limit", 30)), 100)
        rows = session.exec(query.limit(limit)).all()
        return {"count": len(rows), "transactions": [
            {"date": row.date.isoformat(), "amount": row.amount, "label": row.label, "category": categories.get(row.category_id, "Uncategorized")} for row in rows]}
    if name == "get_accounts":
        return [{key: account.get(key) for key in ("name", "kind", "current_balance", "overdraft_limit", "available", "statement_balance_date")} for account in list_accounts(session=session)]
    if name == "get_loans":
        data = list_loans(session=session)
        data["loans"] = [{key: loan[key] for key in ("name", "lender", "kind", "current_balance", "monthly_payment", "annual_rate", "taeg", "months_left", "projected_end",
                                                   "remaining_interest", "remaining_insurance", "notes")} for loan in data["loans"] if loan["is_active"]]
        data["timeline"] = [{"month": row["month"], "total": row["total"]} for row in data["timeline"][:30]]
        data.pop("timeline_loans", None)
        return data
    if name == "get_rental_property":
        return [{key: value for key, value in prop.items() if key not in ("months",)} | {"months": prop["months"][-14:]} for prop in list_properties(session=session)]
    if name == "get_wealth":
        data = wealth(session=session)
        data["history"] = data["history"][-14:]
        return data
    if name == "get_income":
        data = income(session=session)
        if not data.get("empty"):
            data["payslips"] = data["payslips"][-12:]
        return data
    if name == "get_plan":
        return strip_plan(compute_plan(session, get_settings(session)))
    if name == "run_plan_scenario":
        base = get_settings(session).model_dump()
        allowed = set(PlanSettings.model_fields) - {"id", "owner"}
        overrides = {key: value for key, value in (arguments.get("overrides") or {}).items() if key in allowed}
        for key in ("sale_date", "purchase_date"):
            if isinstance(overrides.get(key), str):
                overrides[key] = date.fromisoformat(overrides[key])
        scenario = PlanSettings(**{**base, **overrides})
        result = strip_plan(compute_plan(session, scenario))
        result["scenario_overrides"] = overrides
        return result
    raise ValueError(f"Unknown tool {name}")


def ask(messages: list[dict], session: Session) -> dict:
    """Run the tool loop for one user turn. `messages` is the visible conversation: [{role, content}]."""
    if not claude_extractor.is_available():
        raise RuntimeError("No ANTHROPIC_API_KEY is configured")
    client = claude_extractor.get_client()
    conversation = [{"role": message["role"], "content": message["content"]} for message in messages]
    tools_used: list[str] = []
    usage = {"input_tokens": 0, "output_tokens": 0}
    for _ in range(MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=6000,
            system=SYSTEM_PROMPT.format(today=date.today().isoformat()),
            tools=TOOLS,
            messages=conversation,
        )
        usage["input_tokens"] += response.usage.input_tokens
        usage["output_tokens"] += response.usage.output_tokens
        if response.stop_reason != "tool_use":
            answer = "".join(block.text for block in response.content if block.type == "text").strip()
            return {"answer": answer or "I could not produce an answer.", "tools_used": tools_used, "usage": usage}
        conversation.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            tools_used.append(block.name)
            try:
                content, is_error = compact(run_tool(block.name, block.input or {}, session)), False
            except Exception as error:  # noqa: BLE001 - report the failure to the model so it can adapt
                content, is_error = f"Tool failed: {error}", True
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": content, "is_error": is_error})
        conversation.append({"role": "user", "content": results})
    return {"answer": "I needed too many steps to answer that. Try a narrower question.", "tools_used": tools_used, "usage": usage}

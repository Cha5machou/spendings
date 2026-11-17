"""Where the money goes: average monthly flows as nodes and links for a Sankey diagram.

Income sources -> "Money in" -> groups (essential, debt, flexible, saved) -> categories.
If spending exceeds income the gap appears as a "Shortfall" source (overdraft, savings withdrawals,
credit); if income exceeds spending the rest is "Left over". Both sides always add up."""

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.database import get_session
from app.routers.insights import insights as compute_insights

router = APIRouter(prefix="/flows", tags=["flows"])

MIN_FLOW = 1.0  # euros per month: smaller flows are noise in the diagram
GROUP_COLORS = {
    "Essential": "#4f6fb5", "Debt payments": "#c93a3a", "Flexible": "#eb6834", "Other spending": "#9a9a9a",
    "Saved & invested": "#1baf7a", "Left over": "#1baf7a", "Money in": "#2a78d6", "Shortfall": "#c93a3a",
}
INCOME_COLOR = "#2f7d6a"


@router.get("")
def flows(months: int = 12, include_one_offs: bool = False, session: Session = Depends(get_session)):
    data = compute_insights(months=months, session=session)
    if data.get("empty") or not data["overview"]["months"]:
        return {"empty": True}
    month_count = max(data["overview"]["months"], 1)

    def typical(row: dict) -> float:
        """Average per month; single big non-repeating movements are left out unless asked for."""
        return row["average"] if include_one_offs else row["typical"]

    is_debt = lambda row: any(word in row["name"].lower() for word in ("mortgage", "loan", "credit"))  # noqa: E731
    sources: list[tuple[str, float, str | None]] = []  # (name, amount, color)
    groups: dict[str, list[tuple[str, float, str | None]]] = {name: [] for name in ("Essential", "Debt payments", "Flexible", "Other spending", "Saved & invested")}

    for row in data["categories"]:
        if row["kind"] == "transfer":
            continue
        amount = typical(row)
        if abs(amount) < MIN_FLOW:
            continue
        if row["kind"] == "income":
            if amount > 0:
                sources.append((row["name"], amount, row["color"] or INCOME_COLOR))
        elif row["kind"] == "savings":
            if amount > 0:
                groups["Saved & invested"].append((row["name"], amount, row["color"]))
            else:
                sources.append((f"{row['name']} withdrawn", -amount, row["color"] or INCOME_COLOR))
        else:  # expense
            if amount < 0:  # net refunds in an expense category count as money in
                sources.append((f"{row['name']} refunds", -amount, row["color"] or INCOME_COLOR))
                continue
            if is_debt(row):
                group = "Debt payments"
            elif row["necessity"] == "essential":
                group = "Essential"
            elif row["necessity"] == "flexible":
                group = "Flexible"
            else:
                group = "Other spending"
            groups[group].append((row["name"], amount, row["color"]))

    total_in = sum(amount for _, amount, _ in sources)
    total_out = sum(amount for members in groups.values() for _, amount, _ in members)
    shortfall = max(0.0, total_out - total_in)
    left_over = max(0.0, total_in - total_out)
    if shortfall >= MIN_FLOW:
        sources.append(("Spent beyond income", shortfall, GROUP_COLORS["Shortfall"]))

    nodes: list[dict] = []
    index: dict[str, int] = {}

    def node(name: str, color: str | None, group: str) -> int:
        if name not in index:
            index[name] = len(nodes)
            nodes.append({"name": name, "color": color or GROUP_COLORS.get(group, "#9a9a9a"), "group": group})
        return index[name]

    links: list[dict] = []
    money_in = node("Money in", GROUP_COLORS["Money in"], "Money in")
    for name, amount, color in sorted(sources, key=lambda item: -item[1]):
        links.append({"source": node(name, color, "source"), "target": money_in, "value": round(amount, 2)})
    group_totals = {}
    for group, members in groups.items():
        members = [member for member in members if member[1] >= MIN_FLOW]
        total = sum(amount for _, amount, _ in members)
        if total < MIN_FLOW:
            continue
        group_totals[group] = round(total, 2)
        group_node = node(group, GROUP_COLORS[group], group)
        links.append({"source": money_in, "target": group_node, "value": round(total, 2)})
        for name, amount, color in sorted(members, key=lambda item: -item[1]):
            links.append({"source": group_node, "target": node(name, color, group), "value": round(amount, 2)})
    if left_over >= MIN_FLOW:
        links.append({"source": money_in, "target": node("Left over", GROUP_COLORS["Left over"], "Left over"), "value": round(left_over, 2)})
        group_totals["Left over"] = round(left_over, 2)

    income_total = round(total_in + shortfall, 2)
    return {
        "empty": False,
        "months": month_count,
        "window": [data["overview"]["window_start"], data["overview"]["window_end"]],
        "include_one_offs": include_one_offs,
        "nodes": nodes,
        "links": links,
        "totals": {
            "money_in": income_total, "from_income": round(total_in, 2), "shortfall": round(shortfall, 2), "left_over": round(left_over, 2),
            "groups": group_totals,
            "shares": {group: round(value / income_total, 4) for group, value in group_totals.items()} if income_total else {},
        },
    }

import re

from sqlmodel import Session, select

from app.models import CategoryRule, CategorySource, Transaction


def load_rules(session: Session) -> list[CategoryRule]:
    return list(session.exec(select(CategoryRule).order_by(CategoryRule.priority.desc(), CategoryRule.id)))


def match_rule(label: str, rules: list[CategoryRule]) -> CategoryRule | None:
    lowered = label.lower()
    for rule in rules:
        if rule.match_type == "regex":
            try:
                if re.search(rule.pattern, label, flags=re.IGNORECASE):
                    return rule
            except re.error:
                continue
        elif rule.pattern.lower() in lowered:
            return rule
    return None


def apply_rules(session: Session, transactions: list[Transaction], overwrite_ai: bool = False) -> int:
    """Set category on transactions matching a rule. Manual categories are never touched."""
    rules = load_rules(session)
    changed = 0
    for transaction in transactions:
        if transaction.category_source == CategorySource.manual:
            continue
        if transaction.category_source == CategorySource.ai and not overwrite_ai:
            continue
        rule = match_rule(transaction.label, rules)
        if rule is None:
            continue
        if transaction.category_id != rule.category_id or transaction.category_source != CategorySource.rule:
            transaction.category_id = rule.category_id
            transaction.category_source = CategorySource.rule
            session.add(transaction)
            changed += 1
    return changed

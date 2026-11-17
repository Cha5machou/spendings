from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.routers.properties import co_ownership_check

TODAY = date(2026, 11, 17)
PROPERTY = SimpleNamespace(syndic_quarterly=444.41, cost_category_id=8)


def call(**overrides):
    base = dict(doc_type="syndic_call", amount_due=569.50, previous_balance=500.01, doc_date=date(2026, 11, 6), due_date=None,
                paid=False, created_at=datetime(2026, 11, 17, tzinfo=timezone.utc), id=1)
    return SimpleNamespace(**{**base, **overrides})


def payment(day, amount):
    return SimpleNamespace(amount=amount, date=day, category_id=8, label="VIR SYNDIC")


def test_unpaid_call_on_file_is_flagged_with_its_details():
    check = co_ownership_check(PROPERTY, [call()], [], TODAY)
    assert check["severity"] == "high"
    assert "569.50" in check["title"] and "500.01" in check["detail"]


def test_a_matching_payment_after_the_call_clears_it():
    assert co_ownership_check(PROPERTY, [call()], [payment(date(2026, 11, 17), -565.0)], TODAY) is None


def test_a_payment_before_the_call_does_not_count():
    assert co_ownership_check(PROPERTY, [call()], [payment(date(2026, 10, 1), -569.5)], TODAY) is not None


def test_marking_it_paid_clears_it():
    assert co_ownership_check(PROPERTY, [call(paid=True)], [], TODAY) is None


def test_without_documents_it_asks_for_one_only_when_payments_went_quiet():
    assert co_ownership_check(PROPERTY, [], [], TODAY)["title"].startswith("Add your latest co-ownership call")
    assert co_ownership_check(PROPERTY, [], [payment(date(2026, 10, 5), -444.41)], TODAY) is None

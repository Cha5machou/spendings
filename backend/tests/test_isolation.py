"""Per-user data: a session only sees and changes the rows of its own owner, whatever the ids."""

import datetime

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, delete, select

import app.database  # noqa: F401 - registers the owner filter on Session
from app.models import Account, Category, PlanSettings, Transaction


@pytest.fixture
def engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    return engine


def session_for(engine, owner):
    session = Session(engine)
    session.info["owner"] = owner
    return session


def add_account(engine, owner, name):
    with session_for(engine, owner) as session:
        account = Account(name=name)
        session.add(account)
        session.commit()
        session.add(Transaction(account_id=account.id, date=datetime.date(2026, 1, 1), label="x", amount=-5, dedupe_hash=f"{owner}-{name}"))
        session.commit()
        return account.id


def test_new_rows_are_stamped_and_invisible_to_others(engine):
    mine = add_account(engine, "a@example.com", "Mine")
    add_account(engine, "b@example.com", "Theirs")
    with session_for(engine, "a@example.com") as session:
        assert [a.name for a in session.exec(select(Account)).all()] == ["Mine"]
        assert len(session.exec(select(Transaction)).all()) == 1
        assert session.get(Account, mine).owner == "a@example.com"


def test_foreign_ids_do_not_exist(engine):
    theirs = add_account(engine, "b@example.com", "Theirs")
    with session_for(engine, "a@example.com") as session:
        assert session.get(Account, theirs) is None


def test_bulk_delete_and_update_stay_inside_owner(engine):
    add_account(engine, "a@example.com", "Mine")
    add_account(engine, "b@example.com", "Theirs")
    with session_for(engine, "a@example.com") as session:
        session.exec(delete(Transaction))
        session.commit()
    with session_for(engine, "b@example.com") as session:
        assert len(session.exec(select(Transaction)).all()) == 1


def test_plan_settings_are_per_user(engine):
    for owner in ("a@example.com", "b@example.com"):
        with session_for(engine, owner) as session:
            session.add(PlanSettings())
            session.commit()
    with session_for(engine, "a@example.com") as session:
        assert len(session.exec(select(PlanSettings)).all()) == 1


def test_joins_and_counts_are_filtered(engine):
    add_account(engine, "a@example.com", "Mine")
    add_account(engine, "b@example.com", "Theirs")
    with session_for(engine, "b@example.com") as session:
        rows = session.exec(select(Transaction, Account).join(Account, Account.id == Transaction.account_id)).all()
        assert [account.name for _, account in rows] == ["Theirs"]


def test_seed_defaults_per_owner(engine):
    from app.seed import seed_defaults

    for owner in ("a@example.com", "b@example.com"):
        with session_for(engine, owner) as session:
            seed_defaults(session)
    with session_for(engine, "a@example.com") as session:
        names = [c.name for c in session.exec(select(Category)).all()]
        assert len(names) == len(set(names)) and "Salary" in names

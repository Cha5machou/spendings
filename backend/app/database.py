from collections.abc import Iterator

from fastapi import Depends
from sqlalchemy import event, update
from sqlalchemy.orm import with_loader_criteria
from sqlmodel import Session, SQLModel, create_engine

from app.auth import require_user
from app.config import settings
from app.models import Owned

connect_args = {"check_same_thread": False} if settings.resolved_database_url.startswith("sqlite") else {}
engine = create_engine(settings.resolved_database_url, connect_args=connect_args)

LOCAL_OWNER = "local"  # the single owner when authentication is disabled


def create_tables() -> None:
    SQLModel.metadata.create_all(engine)
    add_missing_columns()
    adopt_legacy_rows()


def owned_tables():
    return [table for table in SQLModel.metadata.sorted_tables if "owner" in table.columns]


def add_missing_columns() -> None:
    """Lightweight migration: add columns that were added to a model after the
    table was created (SQLite cannot drop/alter columns, but it can add them)."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    with engine.begin() as connection:
        for table in SQLModel.metadata.sorted_tables:
            existing = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                column_type = column.type.compile(engine.dialect)
                connection.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {column_type}'))


def adopt_legacy_rows() -> None:
    """Rows created before accounts existed have no owner: they belong to "local" and, once
    authentication is on, to LEGACY_DATA_OWNER (the e-mail of whoever used the app so far)."""
    target = settings.legacy_data_owner if settings.auth_enabled and settings.legacy_data_owner else LOCAL_OWNER
    with engine.begin() as connection:
        for table in owned_tables():
            unowned = table.c.owner.is_(None)
            if target != LOCAL_OWNER:
                unowned = unowned | (table.c.owner == LOCAL_OWNER)
            connection.execute(update(table).where(unowned).values(owner=target))


# --- per-user isolation ---------------------------------------------------------------------
# A session is opened for one owner. Every SELECT/UPDATE/DELETE on an owned table is filtered on
# it, and every new row is stamped with it, so a router cannot read or touch another user's rows
# even by guessing ids: a foreign id simply does not exist for that session.

OWNED_MODELS = [model for model in Owned.__subclasses__() if hasattr(model, "__table__")]


@event.listens_for(Session, "do_orm_execute")
def _limit_to_owner(state) -> None:
    owner = state.session.info.get("owner")
    if owner is None or state.is_column_load or state.is_relationship_load:
        return
    if state.is_select or state.is_update or state.is_delete:
        state.statement = state.statement.options(
            *(with_loader_criteria(model, model.owner == owner, include_aliases=True) for model in OWNED_MODELS)
        )


@event.listens_for(Session, "before_flush")
def _stamp_owner(session, flush_context, instances) -> None:
    owner = session.info.get("owner")
    if owner is None:
        return
    for instance in session.new:
        if isinstance(instance, Owned):
            instance.owner = owner


_seeded_owners: set[str] = set()


def open_session(owner: str) -> Session:
    """A session limited to one owner, whose categories and rules exist (seeded on first use)."""
    from app.seed import seed_defaults

    session = Session(engine)
    session.info["owner"] = owner
    if owner not in _seeded_owners:
        seed_defaults(session)
        _seeded_owners.add(owner)
    return session


def get_session(user: str | None = Depends(require_user)) -> Iterator[Session]:
    with open_session(user or LOCAL_OWNER) as session:
        yield session

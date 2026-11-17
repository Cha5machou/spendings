"""Goals CRUD and validation, and the guided-setup status, on an in-memory database."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401  (registers the tables)
from app.database import get_session
from app.routers import goals, scheduled, setup


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    application = FastAPI()
    application.include_router(goals.router, prefix="/api")
    application.include_router(setup.router, prefix="/api")
    application.include_router(scheduled.router, prefix="/api")

    def session_override():
        with Session(engine) as session:
            yield session

    application.dependency_overrides[get_session] = session_override
    return TestClient(application)


def test_goal_lifecycle(client):
    created = client.post("/api/goals", json={"title": "Emergency fund", "kind": "emergency_fund", "target_amount": 9000, "target_date": "2027-06-01"})
    assert created.status_code == 201
    goal_id = created.json()["id"]
    assert client.get("/api/goals").json()[0]["title"] == "Emergency fund"
    assert client.patch(f"/api/goals/{goal_id}", json={"target_amount": 12000}).json()["target_amount"] == 12000
    assert client.delete(f"/api/goals/{goal_id}").status_code == 204
    assert client.get("/api/goals").json() == []


@pytest.mark.parametrize("payload", [
    {"title": ""}, {"title": "x", "kind": "nonsense"}, {"title": "x", "funded_by": "bank"}, {"title": "x", "priority": 9},
])
def test_goal_validation(client, payload):
    assert client.post("/api/goals", json=payload).status_code == 422


def test_missing_goal_is_404(client):
    assert client.patch("/api/goals/999", json={"title": "x"}).status_code == 404
    assert client.delete("/api/goals/999").status_code == 404


def test_setup_starts_empty_and_follows_the_data(client):
    status = client.get("/api/setup").json()
    assert not status["complete"]
    assert status["next"] == "accounts"
    assert [step["key"] for step in status["steps"]] == ["accounts", "payslips", "loans", "property", "documents", "transactions", "goals"]

    client.post("/api/goals", json={"title": "Save"})
    steps = {step["key"]: step["done"] for step in client.get("/api/setup").json()["steps"]}
    assert steps["goals"] is True and steps["accounts"] is False


def test_scheduled_payments_are_validated_and_sorted(client):
    assert client.post("/api/scheduled", json={"label": "Tax", "date": "2026-12-28", "amount": 358}).status_code == 201
    assert client.post("/api/scheduled", json={"label": "Tax", "date": "2026-11-26", "amount": 357}).status_code == 201
    assert [item["date"] for item in client.get("/api/scheduled").json()] == ["2026-11-26", "2026-12-28"]
    assert client.post("/api/scheduled", json={"label": "Tax", "date": "2026-12-28", "amount": -5}).status_code == 422
    assert client.post("/api/scheduled", json={"date": "2026-12-28", "amount": 5}).status_code == 422
    assert client.delete("/api/scheduled/999").status_code == 404

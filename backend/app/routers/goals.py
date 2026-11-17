from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.database import get_session
from app.models import Goal

router = APIRouter(prefix="/goals", tags=["goals"])

KINDS = {"savings", "emergency_fund", "home_purchase", "property_sale", "housing_change", "retirement", "other"}
FUNDED_BY = {"livrets", "pea", "cto", "av", "any"}


class GoalPayload(BaseModel):
    title: str | None = None
    kind: str | None = None
    target_amount: float | None = None
    target_date: date | None = None
    funded_by: str | None = None
    priority: int | None = None
    notes: str | None = None


def validated(data: dict) -> dict:
    if data.get("kind") is not None and data["kind"] not in KINDS:
        raise HTTPException(422, f"kind must be one of {sorted(KINDS)}")
    if data.get("funded_by") is not None and data["funded_by"] not in FUNDED_BY:
        raise HTTPException(422, f"funded_by must be one of {sorted(FUNDED_BY)}")
    if data.get("priority") is not None and data["priority"] not in (1, 2, 3):
        raise HTTPException(422, "priority must be 1, 2 or 3")
    return data


@router.get("")
def list_goals(session: Session = Depends(get_session)):
    return session.exec(select(Goal).order_by(Goal.priority, Goal.target_date, Goal.id)).all()


@router.post("", status_code=201)
def create_goal(payload: GoalPayload, session: Session = Depends(get_session)):
    data = validated(payload.model_dump(exclude_unset=True))
    if not (data.get("title") or "").strip():
        raise HTTPException(422, "A goal needs a title")
    goal = Goal(**data)
    session.add(goal)
    session.commit()
    session.refresh(goal)
    return goal


@router.patch("/{goal_id}")
def update_goal(goal_id: int, payload: GoalPayload, session: Session = Depends(get_session)):
    goal = session.get(Goal, goal_id)
    if goal is None:
        raise HTTPException(404, "Goal not found")
    for field, value in validated(payload.model_dump(exclude_unset=True)).items():
        setattr(goal, field, value)
    session.add(goal)
    session.commit()
    session.refresh(goal)
    return goal


@router.delete("/{goal_id}", status_code=204)
def delete_goal(goal_id: int, session: Session = Depends(get_session)):
    goal = session.get(Goal, goal_id)
    if goal is None:
        raise HTTPException(404, "Goal not found")
    session.delete(goal)
    session.commit()

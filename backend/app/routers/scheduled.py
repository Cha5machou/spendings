import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.database import get_session
from app.models import ScheduledPayment

router = APIRouter(prefix="/scheduled", tags=["scheduled"])


class ScheduledPayload(BaseModel):
    label: str | None = None
    date: datetime.date | None = None
    amount: float | None = None
    notes: str | None = None


@router.get("")
def list_scheduled(session: Session = Depends(get_session)):
    return session.exec(select(ScheduledPayment).order_by(ScheduledPayment.date, ScheduledPayment.id)).all()


@router.post("", status_code=201)
def create_scheduled(payload: ScheduledPayload, session: Session = Depends(get_session)):
    data = payload.model_dump(exclude_unset=True)
    if not (data.get("label") or "").strip() or data.get("date") is None or data.get("amount") is None:
        raise HTTPException(422, "A scheduled payment needs a label, a date and an amount")
    if data["amount"] <= 0:
        raise HTTPException(422, "The amount is the money going out, so it must be positive")
    payment = ScheduledPayment(**data)
    session.add(payment)
    session.commit()
    session.refresh(payment)
    return payment


@router.patch("/{payment_id}")
def update_scheduled(payment_id: int, payload: ScheduledPayload, session: Session = Depends(get_session)):
    payment = session.get(ScheduledPayment, payment_id)
    if payment is None:
        raise HTTPException(404, "Scheduled payment not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(payment, field, value)
    session.add(payment)
    session.commit()
    session.refresh(payment)
    return payment


@router.delete("/{payment_id}", status_code=204)
def delete_scheduled(payment_id: int, session: Session = Depends(get_session)):
    payment = session.get(ScheduledPayment, payment_id)
    if payment is None:
        raise HTTPException(404, "Scheduled payment not found")
    session.delete(payment)
    session.commit()

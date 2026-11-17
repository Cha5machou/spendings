from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app import assistant
from app.database import get_session

router = APIRouter(prefix="/assistant", tags=["assistant"])


class Message(BaseModel):
    role: str
    content: str


class AskPayload(BaseModel):
    messages: list[Message]


@router.post("")
def ask(payload: AskPayload, session: Session = Depends(get_session)):
    if not payload.messages or payload.messages[-1].role != "user":
        raise HTTPException(422, "The last message must come from the user")
    try:
        return assistant.ask([message.model_dump() for message in payload.messages][-20:], session)
    except RuntimeError as error:
        raise HTTPException(503, str(error)) from error
    except Exception as error:  # noqa: BLE001 - API/network failures surface as a clear 502
        raise HTTPException(502, f"The assistant could not answer: {error}") from error

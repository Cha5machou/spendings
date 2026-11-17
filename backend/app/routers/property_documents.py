"""Papers attached to a property. Claude can read them (when a key is configured and the user asks for it)
to find the type, the amount due and the due date; everything stays editable."""

import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlmodel import Session, select

from app.database import get_session
from app.extraction import claude_extractor
from app.models import Property, PropertyDocument
from app.storage import get_storage

router = APIRouter(prefix="/property-documents", tags=["property-documents"])


class DocumentPatch(BaseModel):
    doc_type: str | None = None
    title: str | None = None
    issuer: str | None = None
    doc_date: datetime.date | None = None
    amount_due: float | None = None
    previous_balance: float | None = None
    due_date: datetime.date | None = None
    paid: bool | None = None
    summary: str | None = None


def parse_date(text: str | None) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(text) if text else None
    except ValueError:
        return None


@router.get("")
def list_documents(property_id: int, session: Session = Depends(get_session)):
    return session.exec(
        select(PropertyDocument).where(PropertyDocument.property_id == property_id).order_by(PropertyDocument.doc_date.desc(), PropertyDocument.id.desc())
    ).all()


@router.post("", status_code=201)
async def upload_documents(property_id: int = Form(...), read_with_claude: bool = Form(True), files: list[UploadFile] = (), session: Session = Depends(get_session)):
    if session.get(Property, property_id) is None:
        raise HTTPException(404, "Property not found")
    storage = get_storage()
    created, warnings = [], []
    for file in files:
        content = await file.read()
        document = PropertyDocument(
            property_id=property_id, filename=file.filename or "document", stored_path=storage.save(file.filename or "document", content),
            mime_type=file.content_type or "application/pdf", size_bytes=len(content), title=file.filename,
        )
        is_pdf = (file.content_type == "application/pdf") or (file.filename or "").lower().endswith(".pdf")
        if read_with_claude and is_pdf and claude_extractor.is_available():
            try:
                found = claude_extractor.extract_property_document(content)
                document.doc_type = found.document_type if found.document_type in claude_extractor.PROPERTY_DOC_TYPES else "other"
                document.title, document.issuer, document.summary = found.title, found.issuer, found.summary
                document.doc_date, document.due_date = parse_date(found.document_date), parse_date(found.due_date)
                document.amount_due, document.previous_balance, document.extracted = found.amount_due, found.previous_balance, True
            except Exception as error:  # noqa: BLE001 - keep the file even if reading fails
                warnings.append(f"{file.filename}: could not be read automatically ({error}). Fill it in by hand.")
        elif read_with_claude and not claude_extractor.is_available():
            warnings.append(f"{file.filename}: stored. Add an Anthropic key to read documents automatically, or fill in the fields by hand.")
        session.add(document)
        session.commit()
        session.refresh(document)
        created.append(document)
    return {"documents": created, "warnings": warnings}


@router.patch("/{document_id}")
def update_document(document_id: int, payload: DocumentPatch, session: Session = Depends(get_session)):
    document = session.get(PropertyDocument, document_id)
    if document is None:
        raise HTTPException(404, "Document not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(document, field, value)
    session.add(document)
    session.commit()
    session.refresh(document)
    return document


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: int, session: Session = Depends(get_session)):
    document = session.get(PropertyDocument, document_id)
    if document is None:
        raise HTTPException(404, "Document not found")
    session.delete(document)
    session.commit()


@router.get("/{document_id}/file")
def download_document(document_id: int, session: Session = Depends(get_session)):
    document = session.get(PropertyDocument, document_id)
    if document is None:
        raise HTTPException(404, "Document not found")
    return Response(content=get_storage().read(document.stored_path), media_type=document.mime_type,
                    headers={"Content-Disposition": f'inline; filename="{document.filename}"'})

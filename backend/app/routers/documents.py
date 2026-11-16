import hashlib
from collections import Counter

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session, select

from app.categorizer import apply_rules
from app.database import get_session
from app.extraction import extract_transactions
from app.models import Account, Document, DocumentStatus, Transaction
from app.schemas import ImportSummary
from app.storage import get_storage

router = APIRouter(prefix="/documents", tags=["documents"])


def dedupe_hash(account_id: int, transaction_date, amount: float, label: str, occurrence: int = 0) -> str:
    """Same account + date + amount + label = same transaction on re-import. `occurrence`
    distinguishes genuinely repeated lines inside one statement (two identical transfers)."""
    key = f"{account_id}|{transaction_date.isoformat()}|{amount:.2f}|{label.strip().lower()}|{occurrence}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


@router.get("")
def list_documents(session: Session = Depends(get_session)):
    return session.exec(select(Document).order_by(Document.uploaded_at.desc())).all()


@router.post("/upload", response_model=ImportSummary)
async def upload_document(
    account_id: int = Form(...),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    account = session.get(Account, account_id)
    if account is None:
        raise HTTPException(404, "Account not found")

    content = await file.read()
    storage = get_storage()
    stored_path = storage.save(file.filename or "document", content)
    document = Document(
        account_id=account_id,
        filename=file.filename or "document",
        stored_path=stored_path,
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
    )
    session.add(document)
    session.commit()
    session.refresh(document)

    try:
        result = extract_transactions(content, document.filename, document.mime_type)
    except Exception as error:  # parsing failures are reported, not raised
        document.status = DocumentStatus.failed
        document.error = str(error)
        session.add(document)
        session.commit()
        return ImportSummary(
            document_id=document.id,
            status=document.status,
            extraction_method=None,
            transactions_imported=0,
            duplicates_skipped=0,
            auto_categorized=0,
            warnings=[],
            error=document.error,
        )

    existing_hashes = set(session.exec(select(Transaction.dedupe_hash).where(Transaction.account_id == account_id)).all())
    imported: list[Transaction] = []
    duplicates = 0
    occurrences: Counter[tuple] = Counter()
    for extracted in result.transactions:
        occurrence_key = (extracted.date, round(extracted.amount, 2), extracted.label.strip().lower())
        transaction_hash = dedupe_hash(account_id, extracted.date, extracted.amount, extracted.label, occurrences[occurrence_key])
        occurrences[occurrence_key] += 1
        if transaction_hash in existing_hashes:
            duplicates += 1
            continue
        existing_hashes.add(transaction_hash)
        transaction = Transaction(
            account_id=account_id,
            document_id=document.id,
            date=extracted.date,
            label=extracted.label,
            amount=extracted.amount,
            currency=account.currency,
            dedupe_hash=transaction_hash,
        )
        session.add(transaction)
        imported.append(transaction)

    auto_categorized = apply_rules(session, imported)
    document.status = DocumentStatus.imported
    document.extraction_method = result.method
    document.transactions_imported = len(imported)
    document.duplicates_skipped = duplicates
    document.closing_balance = result.closing_balance
    document.period_end = result.period_end
    session.add(document)
    # A newer statement gives us a fresh known balance for the account.
    if result.closing_balance is not None and result.period_end is not None:
        if account.statement_balance_date is None or result.period_end >= account.statement_balance_date:
            account.statement_balance = result.closing_balance
            account.statement_balance_date = result.period_end
            session.add(account)
    session.commit()

    return ImportSummary(
        document_id=document.id,
        status=document.status,
        extraction_method=result.method,
        transactions_imported=len(imported),
        duplicates_skipped=duplicates,
        auto_categorized=auto_categorized,
        warnings=result.warnings,
    )


@router.post("/{document_id}/reextract")
def reextract_document(document_id: int, session: Session = Depends(get_session)):
    """Re-run extraction on a stored document (after a parser improvement) and
    refresh labels/dates in place, keeping categories and notes. Transactions are
    matched on (date, amount, occurrence); new lines are added, vanished ones removed."""
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(404, "Document not found")
    account = session.get(Account, document.account_id)
    content = get_storage().read(document.stored_path)
    result = extract_transactions(content, document.filename, document.mime_type)

    existing = session.exec(select(Transaction).where(Transaction.document_id == document_id)).all()
    by_key: dict[tuple, list[Transaction]] = {}
    for transaction in existing:
        by_key.setdefault((transaction.date, round(transaction.amount, 2)), []).append(transaction)

    used_hashes = set(session.exec(select(Transaction.dedupe_hash)).all())
    occurrences: Counter[tuple] = Counter()
    updated = added = 0
    kept: set[int] = set()
    for extracted in result.transactions:
        key = (extracted.date, round(extracted.amount, 2))
        candidates = [item for item in by_key.get(key, []) if item.id not in kept]
        occurrence_key = (extracted.date, round(extracted.amount, 2), extracted.label.strip().lower())
        new_hash = dedupe_hash(account.id, extracted.date, extracted.amount, extracted.label, occurrences[occurrence_key])
        occurrences[occurrence_key] += 1
        if candidates:
            transaction = candidates[0]
            kept.add(transaction.id)
            if transaction.label != extracted.label:
                transaction.label = extracted.label
                updated += 1
            if new_hash not in used_hashes or transaction.dedupe_hash == new_hash:
                used_hashes.discard(transaction.dedupe_hash)
                transaction.dedupe_hash = new_hash
                used_hashes.add(new_hash)
            session.add(transaction)
        elif new_hash not in used_hashes:
            used_hashes.add(new_hash)
            transaction = Transaction(
                account_id=account.id, document_id=document.id, date=extracted.date, label=extracted.label,
                amount=extracted.amount, currency=account.currency, dedupe_hash=new_hash,
            )
            session.add(transaction)
            kept.add(-added - 1)
            added += 1
    removed = 0
    for transaction in existing:
        if transaction.id not in kept:
            session.delete(transaction)
            removed += 1
    session.flush()
    auto_categorized = apply_rules(session, [item for item in existing if item.id in kept and item.category_id is None])
    document.closing_balance = result.closing_balance
    document.period_end = result.period_end
    document.extraction_method = result.method
    session.add(document)
    session.commit()
    return {"updated_labels": updated, "added": added, "removed": removed, "auto_categorized": auto_categorized}


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: int, delete_transactions: bool = True, session: Session = Depends(get_session)):
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(404, "Document not found")
    for transaction in session.exec(select(Transaction).where(Transaction.document_id == document_id)):
        if delete_transactions:
            session.delete(transaction)
        else:
            transaction.document_id = None
            session.add(transaction)
    session.delete(document)
    session.commit()

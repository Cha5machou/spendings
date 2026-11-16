"""Shared logic for tabular exports (CSV and Excel): find the header row, map the
date / label / amount (or débit + crédit) columns, and read the rows below.

Also handles headerless exports (LCL CSV): column 0 = date, column 1 = signed
amount, the rest is the label; rows with only a date, an amount and an account
number are balance lines (first = opening, last = closing)."""

import re
from datetime import date

from app.extraction.common import StatementParse, normalize_label, parse_amount, parse_date

DATE_HEADERS = ("date", "date opération", "date operation", "date de l'opération", "transaction date", "booking date")
LABEL_HEADERS = ("libellé", "libelle", "label", "description", "détail", "detail", "intitulé", "memo", "payee", "nom")
AMOUNT_HEADERS = ("montant", "amount", "valeur", "value")
DEBIT_HEADERS = ("débit", "debit", "sortie", "withdrawal")
CREDIT_HEADERS = ("crédit", "credit", "entrée", "deposit")
ACCOUNT_NUMBER = re.compile(r"^[\d ]{5,}[A-Z]?$")
BALANCE_CELL = re.compile(r"solde\s+(?:au\s+(\d{2}/\d{2}/\d{4}))?", re.IGNORECASE)

Row = list[str]


def cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if hasattr(value, "isoformat"):
        return value.date().isoformat() if hasattr(value, "date") else value.isoformat()
    return str(value).strip()


def cell_amount(value) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return parse_amount(cell_text(value))


def cell_date(value) -> date | None:
    if hasattr(value, "date") and not isinstance(value, str):
        return value.date()
    if isinstance(value, date):
        return value
    return parse_date(cell_text(value))


def find_column(headers: list[str], candidates: tuple[str, ...]) -> int | None:
    lowered = [header.strip().lower() for header in headers]
    for candidate in candidates:
        for index, header in enumerate(lowered):
            if header == candidate or header.startswith(candidate):
                return index
    return None


def is_header_row(row: list) -> bool:
    texts = [cell_text(cell).lower() for cell in row]
    has_date = any(text.startswith("date") for text in texts)
    has_label = any(text.startswith(("libell", "label", "description", "intitul", "detail", "détail")) for text in texts)
    has_amount = any(text.startswith(("montant", "amount", "débit", "debit", "crédit", "credit")) for text in texts)
    return has_date and (has_label or has_amount)


def parse_rows(rows: list[list]) -> StatementParse:
    from app.extraction import ExtractedTransaction

    result = StatementParse()
    header_index = next((index for index, row in enumerate(rows[:30]) if is_header_row(row)), None)

    if header_index is None:
        return parse_headerless(rows)

    headers = [cell_text(cell) for cell in rows[header_index]]
    date_column = find_column(headers, DATE_HEADERS)
    label_column = find_column(headers, LABEL_HEADERS)
    amount_column = find_column(headers, AMOUNT_HEADERS)
    debit_column = find_column(headers, DEBIT_HEADERS)
    credit_column = find_column(headers, CREDIT_HEADERS)
    # "Valeur" is a value-date column, not an amount, when débit/crédit columns exist.
    if amount_column is not None and headers[amount_column].strip().lower().startswith("valeur") and debit_column is not None:
        amount_column = None
    if date_column is None or label_column is None or (amount_column is None and debit_column is None):
        raise ValueError(f"Could not recognise the columns. Headers found: {headers}")

    for row in rows[header_index + 1 :]:
        texts = [cell_text(cell) for cell in row]
        # "Solde au 16/11/2026 : " ... -637.97  -> closing balance
        balance_cell = next((text for text in texts if BALANCE_CELL.match(text)), None)
        if balance_cell:
            amounts = [cell_amount(cell) for cell in row if cell_amount(cell) is not None and not BALANCE_CELL.match(cell_text(cell))]
            if amounts:
                result.closing_balance = amounts[-1]
            balance_date = BALANCE_CELL.match(balance_cell).group(1)
            if balance_date:
                result.period_end = parse_date(balance_date)
            continue
        if len(row) <= max(date_column, label_column):
            continue
        transaction_date = cell_date(row[date_column])
        if transaction_date is None:
            continue
        amount = None
        if amount_column is not None and amount_column < len(row):
            amount = cell_amount(row[amount_column])
        if amount is None and debit_column is not None:
            debit = cell_amount(row[debit_column]) if debit_column < len(row) else None
            credit = cell_amount(row[credit_column]) if credit_column is not None and credit_column < len(row) else None
            if debit is not None and debit != 0:
                amount = -abs(debit)
            elif credit is not None:
                amount = abs(credit)
        if amount is None:
            continue
        result.transactions.append(
            ExtractedTransaction(date=transaction_date, label=normalize_label(texts[label_column]), amount=amount)
        )
    if result.period_end is None and result.transactions:
        result.period_end = max(transaction.date for transaction in result.transactions)
    return result


def parse_headerless(rows: list[list]) -> StatementParse:
    from app.extraction import ExtractedTransaction

    result = StatementParse()
    balance_dates: list[date] = []
    for row in rows:
        if len(row) < 2:
            continue
        transaction_date = cell_date(row[0])
        amount = cell_amount(row[1])
        if transaction_date is None or amount is None:
            continue
        label_cells = [cell_text(cell) for cell in row[2:]]
        label_cells = [text for text in label_cells if text and not ACCOUNT_NUMBER.match(text)]
        if not label_cells:
            # Only a date, an amount and the account number: a balance line.
            if result.opening_balance is None:
                result.opening_balance = amount
            result.closing_balance = amount
            balance_dates.append(transaction_date)
            continue
        result.transactions.append(
            ExtractedTransaction(date=transaction_date, label=normalize_label(" ".join(label_cells)), amount=amount)
        )
    if balance_dates:
        result.period_end = max(balance_dates)
    elif result.transactions:
        result.period_end = max(transaction.date for transaction in result.transactions)
    if result.opening_balance is not None and result.opening_balance == result.closing_balance and len(balance_dates) < 2:
        result.opening_balance = None  # a single balance line: it is the closing one
    return result

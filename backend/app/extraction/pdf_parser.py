"""Text-based PDF statement parser.

Works on statements that print one operation per line with separate
Débit / Crédit columns (Crédit Mutuel, LCL, and most French banks):

    DD/MM[/YYYY]  [value date]  LABEL ...            DEBIT     CREDIT

The column header line ("Date ... Débit ... Crédit") gives the x-position of
each column, which tells debit from credit and keeps page-margin text out of the
labels. Lines without a date continue the previous label (multi-line labels).
"""

import io
import re
from dataclasses import dataclass
from datetime import date, timedelta

import pdfplumber

from app.extraction.common import StatementParse, normalize_label, parse_amount, parse_date

DATE_WORD = re.compile(r"^\d{2}[/.]\d{2}(?:[/.]\d{2,4})?$")
FULL_DATE = re.compile(r"\b(\d{2})[/.](\d{2})[/.](20\d{2})\b")
AMOUNT_WORD = re.compile(r"^[+-]?\d{1,3}(?:[.  ]?\d{3})*,\d{2}$|^[+-]?\d+\.\d{2}$")
HEADER_DEBIT = re.compile(r"^d[ée]bit", re.IGNORECASE)
HEADER_CREDIT = re.compile(r"^cr[ée]dit", re.IGNORECASE)
HEADER_VALUE_DATE = re.compile(r"^valeur", re.IGNORECASE)
HEADER_LABEL = re.compile(r"^(op[ée]ration|libell[ée]|d[ée]signation|nature)", re.IGNORECASE)
PERIOD_END = re.compile(r"\bau\s+(\d{2})[./](\d{2})[./](20\d{2})", re.IGNORECASE)
# "SOLDE CREDITEUR AU ...", "Réf : 006 SOLDE DEBITEUR AU ...", "ANCIEN SOLDE", "SOLDE EN EUROS"
# but not an operation such as "SOLDE IMPOT REVENUS".
BALANCE_LINE = re.compile(r"\b(?:ancien solde|nouveau solde|solde (?:cr[ée]diteur|d[ée]biteur|en euros))\b", re.IGNORECASE)
SKIP_LABEL_PREFIXES = ("<<suite", "report")
SKIP_CONTINUATION_PREFIXES = ("ref.client", "ref.mandat", "id.creancier", "ref.", "<<suite")
END_OF_OPERATIONS_PREFIXES = ("totaux", "total", "solde", "nouveau solde")
CLOSING_BALANCE = re.compile(
    r"(?:SOLDE\s+(CREDITEUR|DEBITEUR)\s+AU\s+(\d{2}/\d{2}/\d{4})|SOLDE EN EUROS)\s+(-?[\d .\u00a0]+,\d{2})",
    re.IGNORECASE,
)
LINE_TOLERANCE = 3.0


@dataclass
class Columns:
    left_edge: float
    label_start: float
    label_end: float
    debit_start: float
    credit_start: float
    right_edge: float


def cluster_lines(words: list[dict]) -> list[list[dict]]:
    """Group words into visual lines, tolerating small baseline differences."""
    lines: list[list[dict]] = []
    for word in sorted(words, key=lambda item: (item["top"], item["x0"])):
        if lines and abs(word["top"] - lines[-1][0]["top"]) <= LINE_TOLERANCE:
            lines[-1].append(word)
        else:
            lines.append([word])
    return [sorted(line, key=lambda item: item["x0"]) for line in lines]


def detect_columns(line: list[dict]) -> Columns | None:
    debit = next((word for word in line if HEADER_DEBIT.match(word["text"])), None)
    credit = next((word for word in line if HEADER_CREDIT.match(word["text"])), None)
    if debit is None or credit is None or credit["x0"] <= debit["x0"]:
        return None
    value_date = next((word for word in line if HEADER_VALUE_DATE.match(word["text"])), None)
    label_header = next((word for word in line if HEADER_LABEL.match(word["text"])), None)
    # The label runs up to the next column on its right: the value-date column
    # when it is printed after the label (LCL), otherwise the debit column (CM).
    label_end = debit["x0"]
    if value_date is not None and (label_header is None or value_date["x0"] > label_header["x0"]):
        label_end = value_date["x0"]
    return Columns(
        left_edge=min(word["x0"] for word in line) - 20,
        label_start=(label_header["x0"] if label_header else min(word["x0"] for word in line)) - 20,
        label_end=label_end - 2,
        debit_start=debit["x0"] - 20,
        credit_start=credit["x0"],
        right_edge=credit["x0"] + 90,
    )


def statement_period_end(text: str) -> date | None:
    """Prefer 'au DD/MM/YYYY' (statement period / balance date); else the latest date printed."""
    for pattern in (PERIOD_END, FULL_DATE):
        dates = []
        for day, month, year in pattern.findall(text):
            try:
                dates.append(date(int(year), int(month), int(day)))
            except ValueError:
                continue
        if dates:
            return max(dates)
    return None


def closing_balance_from_text(text: str) -> float | None:
    """Last 'SOLDE CREDITEUR/DEBITEUR AU ...' (CM) or 'SOLDE EN EUROS' (LCL) line."""
    matches = CLOSING_BALANCE.findall(text)
    if not matches:
        return None
    sign_word, _, amount_text = matches[-1]
    amount = parse_amount(amount_text)
    if amount is None:
        return None
    return -abs(amount) if sign_word.upper() == "DEBITEUR" else amount


def parse(content: bytes):
    return parse_statement(content).transactions


def parse_statement(content: bytes) -> StatementParse:
    from app.extraction import ExtractedTransaction

    transactions: list[ExtractedTransaction] = []
    balances: list[float] = []  # signed SOLDE lines in reading order: first = opening, last = closing
    columns: Columns | None = None

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        full_text = "\n".join((page.extract_text() or "") for page in pdf.pages)
        period_end = statement_period_end(full_text)
        fallback_year = period_end.year if period_end else date.today().year

        for page in pdf.pages:
            current: ExtractedTransaction | None = None
            for line in cluster_lines(page.extract_words(use_text_flow=True)):
                header = detect_columns(line)
                if header is not None:
                    columns = header
                    current = None
                    continue
                if columns is None:
                    continue

                band = [word for word in line if word["x0"] >= columns.left_edge and word["x1"] <= columns.right_edge]
                if not band:
                    continue
                date_words = [word for word in band if DATE_WORD.match(word["text"]) and word["x1"] <= columns.label_end]
                amount_words = [word for word in band if AMOUNT_WORD.match(word["text"]) and word["x0"] >= columns.debit_start]
                label_words = [
                    word for word in band
                    if word not in date_words and word not in amount_words and word["x1"] <= columns.label_end + 5
                ]
                label_text = normalize_label(" ".join(word["text"] for word in label_words))

                amount = None
                if amount_words:
                    amount_word = amount_words[-1]
                    amount_text = amount_word["text"]
                    # "1 000,00" is sometimes split into two words: glue the thousands back on.
                    position = band.index(amount_word)
                    while position > 0 and re.fullmatch(r"\d{1,3}", band[position - 1]["text"]) and amount_word["x0"] - band[position - 1]["x1"] < 8:
                        position -= 1
                        amount_text = band[position]["text"] + amount_text
                    amount = parse_amount(amount_text)
                    if amount is not None and not amount_text.startswith(("+", "-")):
                        is_credit = amount_word["x1"] > columns.credit_start
                        amount = abs(amount) if is_credit else -abs(amount)

                if BALANCE_LINE.search(label_text):
                    # Balance lines use the same columns: debit column = overdraft (negative).
                    if amount is not None:
                        balances.append(amount)
                    if current is not None and current.amount != 0.0:
                        transactions.append(current)
                    current = None
                    continue

                starts_with_date = bool(date_words) and band[0] is date_words[0]
                if starts_with_date:
                    if current is not None and current.amount != 0.0:
                        transactions.append(current)
                    current = None
                    if label_text.lower().startswith(SKIP_LABEL_PREFIXES):
                        continue
                    transaction_date = parse_date(date_words[0]["text"].replace(".", "/"), fallback_year)
                    if transaction_date is None:
                        continue
                    # A statement issued in January may list late-December operations.
                    if period_end and transaction_date > period_end + timedelta(days=15):
                        transaction_date = transaction_date.replace(year=transaction_date.year - 1)
                    current = ExtractedTransaction(date=transaction_date, label=label_text, amount=amount or 0.0)
                elif current is not None:
                    lowered = label_text.lower()
                    # Footer / legal text starts left of the table or runs across the
                    # amount columns: it is never part of an operation label.
                    spans_columns = any(
                        word["x0"] > columns.label_end + 5 and not AMOUNT_WORD.match(word["text"]) and word["text"] != "."
                        for word in band
                    )
                    # Continuation lines start in the label column; footer text starts further left.
                    if (spans_columns and amount is None) or band[0]["x0"] < columns.label_start:
                        if current.amount != 0.0:
                            transactions.append(current)
                        current = None
                        continue
                    if lowered.startswith(END_OF_OPERATIONS_PREFIXES):
                        if current.amount != 0.0:
                            transactions.append(current)
                        current = None
                        continue
                    if lowered.startswith(SKIP_CONTINUATION_PREFIXES):
                        continue
                    if amount is not None and current.amount == 0.0:
                        current.amount = amount
                    if label_text:
                        extra = label_text[len("LIBELLE:"):] if lowered.startswith("libelle:") else label_text
                        current.label = normalize_label(f"{current.label} {extra}")
            if current is not None and current.amount != 0.0:
                transactions.append(current)

    return StatementParse(
        transactions,
        balances[0] if balances else None,
        balances[-1] if balances else closing_balance_from_text(full_text),
        period_end,
    )

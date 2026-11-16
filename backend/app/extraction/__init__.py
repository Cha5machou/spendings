"""Turn an uploaded document into a list of ExtractedTransaction.

Order of attempts:
1. CSV / Excel exports -> local table parser (header-based or headerless)
2. PDF -> local column-position parser (validated on Crédit Mutuel and LCL statements)
3. If nothing (or almost nothing) came out and an Anthropic key is configured -> Claude
"""

from dataclasses import dataclass
from datetime import date

from app.extraction import claude_extractor, csv_parser, pdf_parser, xlsx_parser


@dataclass
class ExtractedTransaction:
    date: date
    label: str
    amount: float  # signed, negative = money out


@dataclass
class ExtractionResult:
    transactions: list[ExtractedTransaction]
    method: str
    warnings: list[str]
    closing_balance: float | None = None  # balance printed at the end of the statement
    period_end: date | None = None


def extract_transactions(content: bytes, filename: str, mime_type: str) -> ExtractionResult:
    lowered = filename.lower()
    warnings: list[str] = []

    if lowered.endswith((".csv", ".txt", ".tsv")) or mime_type in ("text/csv", "text/plain"):
        parsed = csv_parser.parse_statement(content)
        return ExtractionResult(parsed.transactions, "csv", warnings, parsed.closing_balance, parsed.period_end)

    if lowered.endswith((".xlsx", ".xlsm")):
        parsed = xlsx_parser.parse_statement(content)
        return ExtractionResult(parsed.transactions, "xlsx", warnings, parsed.closing_balance, parsed.period_end)

    if lowered.endswith(".pdf") or mime_type == "application/pdf":
        parsed = pdf_parser.parse_statement(content)
        transactions = parsed.transactions
        if len(transactions) >= 3:
            return ExtractionResult(transactions, "pdf_text", warnings, parsed.closing_balance, parsed.period_end)
        if claude_extractor.is_available():
            warnings.append(
                f"Local PDF parser found only {len(transactions)} transaction(s); used Claude instead."
            )
            return ExtractionResult(claude_extractor.extract_from_pdf(content), "claude", warnings)
        warnings.append("Local PDF parser found few transactions and no ANTHROPIC_API_KEY is set.")
        return ExtractionResult(transactions, "pdf_text", warnings, parsed.closing_balance, parsed.period_end)

    if claude_extractor.is_available():
        return ExtractionResult(claude_extractor.extract_from_image_or_pdf(content, mime_type), "claude", warnings)

    raise ValueError(f"Unsupported file type: {filename} ({mime_type})")

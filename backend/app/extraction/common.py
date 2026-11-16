import re
from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class StatementParse:
    """What every statement parser returns: the lines plus the balances printed on it."""

    transactions: list = field(default_factory=list)
    opening_balance: float | None = None
    closing_balance: float | None = None
    period_end: date | None = None

DATE_FORMATS = ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%d/%m")


def parse_date(raw: str, fallback_year: int | None = None) -> date | None:
    raw = raw.strip()
    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
        if fmt == "%d/%m":
            parsed = parsed.replace(year=fallback_year or date.today().year)
        return parsed
    return None


def parse_amount(raw: str) -> float | None:
    """Accepts '1 234,56', '-1234.56', '1.234,56', '(12,00)', '12,00 €', '+ 50,00'."""
    cleaned = raw.strip().replace("€", "").replace("EUR", "").replace(" ", "").replace(" ", "")
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = cleaned.strip("()")
    if not cleaned:
        return None
    # Decide which symbol is the decimal separator: the last one wins.
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    if not re.fullmatch(r"[+-]?\d+(\.\d+)?", cleaned):
        return None
    value = float(cleaned)
    return -value if negative else value


def normalize_label(label: str) -> str:
    return re.sub(r"\s+", " ", label).strip()

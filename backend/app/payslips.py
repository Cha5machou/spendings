"""Read a French payslip PDF (Payfit-style layout) into the few numbers worth tracking."""

import io
import re
from dataclasses import dataclass
from datetime import date

import pdfplumber

MONEY = r"(-?\d[\d   ]*,\d{2})"


@dataclass
class ParsedPayslip:
    month: str  # YYYY-MM
    employer: str | None
    gross: float
    net_before_tax: float
    tax_rate: float  # withholding rate, percent
    tax_withheld: float
    net_paid: float
    taxable_net: float | None  # "net imposable" of the month
    bonus: float | None


def number(text: str) -> float:
    return float(re.sub(r"[\s  ]", "", text).replace(",", "."))


def first_amount(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text, re.IGNORECASE)
    return number(match.group(1)) if match else None


FRENCH_MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]


def pay_month(text: str) -> str:
    for pattern in (r"Du (\d{2})/(\d{2})/(\d{4}) au", r"Fin de période\s*:\s*(\d{2})/(\d{2})/(\d{4})"):
        match = re.search(pattern, text)
        if match:
            return f"{match.group(3)}-{match.group(2)}"
    match = re.search(r"bulletin de paie de\s*(" + "|".join(FRENCH_MONTHS) + r")\s*(\d{4})?", text, re.IGNORECASE)
    if match:
        year = match.group(2) or re.search(r"(20\d{2})", text).group(1)
        return f"{year}-{FRENCH_MONTHS.index(match.group(1).lower()) + 1:02d}"
    raise ValueError("Could not find the pay period")


def parse_payslip(content: bytes) -> ParsedPayslip:
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        text = "\n".join((page.extract_text() or "") for page in pdf.pages)
    gross = first_amount(r"Rémunération brute\s+" + MONEY, text)
    net_before_tax = first_amount(r"Votre salaire avant impôt\s+" + MONEY, text)
    net_paid = first_amount(r"Net à payer\s+" + MONEY, text)
    tax = re.search(r"Prélèvement à la source \((\d+,\d+) ?%\)\s+" + MONEY, text)
    if None in (gross, net_before_tax, net_paid) or not tax:
        raise ValueError("Unrecognised payslip layout")
    tax_rate, tax_withheld = number(tax.group(1)), number(tax.group(2))
    employer = re.search(r"\n([A-Z0-9][A-Z0-9 &'.-]{2,}) Ahmed", text)
    return ParsedPayslip(
        month=pay_month(text),
        employer=employer.group(1).strip() if employer else None,
        gross=gross, net_before_tax=net_before_tax, net_paid=net_paid,
        tax_rate=tax_rate, tax_withheld=tax_withheld,
        taxable_net=round(tax_withheld / (tax_rate / 100), 2) if tax_rate > 0 else None,
        bonus=first_amount(r"Dont\s+" + MONEY + r"\s+de primes", text),
    )

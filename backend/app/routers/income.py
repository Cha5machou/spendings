"""Salary from payslips: what is earned, taxed and kept, plus the tax bracket that drives retirement-saving advice."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from app.database import get_session
from app.models import Payslip
from app.payslips import parse_payslip

router = APIRouter(prefix="/income", tags=["income"])

# French income tax brackets for a single person (one part), on taxable income after the 10 % allowance.
# Indicative: check the current scale on impots.gouv.fr.
BRACKETS = [(11497, 0.0), (29315, 0.11), (83823, 0.30), (180294, 0.41), (float("inf"), 0.45)]
ALLOWANCE = 0.10
PER_CEILING_RATE = 0.10  # deduction ceiling: about 10 % of last year's net professional income


def marginal_rate(taxable_income: float) -> float:
    for ceiling, rate in BRACKETS:
        if taxable_income <= ceiling:
            return rate
    return BRACKETS[-1][1]


@router.post("/payslips")
async def upload_payslips(files: list[UploadFile], session: Session = Depends(get_session)):
    imported, failed = [], []
    for file in files:
        try:
            parsed = parse_payslip(await file.read())
        except Exception as error:  # noqa: BLE001 - report per file
            failed.append({"filename": file.filename, "error": str(error)})
            continue
        existing = session.exec(select(Payslip).where(Payslip.month == parsed.month)).first() or Payslip(month=parsed.month)
        for field, value in parsed.__dict__.items():
            setattr(existing, field, value)
        session.add(existing)
        imported.append(parsed.month)
    session.commit()
    return {"imported": sorted(imported), "failed": failed}


class PayslipPayload(BaseModel):
    month: str  # YYYY-MM
    gross: float
    net_before_tax: float
    tax_rate: float = 0.0  # withholding rate, percent
    net_paid: float
    employer: str | None = None
    bonus: float | None = None


@router.post("/payslips/manual", status_code=201)
def add_payslip_manually(payload: PayslipPayload, session: Session = Depends(get_session)):
    """For payslips the PDF reader cannot handle: type the four numbers instead."""
    import re

    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", payload.month):
        raise HTTPException(422, "month must look like 2026-03")
    payslip = session.exec(select(Payslip).where(Payslip.month == payload.month)).first() or Payslip(month=payload.month)
    payslip.gross, payslip.net_before_tax, payslip.net_paid = payload.gross, payload.net_before_tax, payload.net_paid
    payslip.tax_rate, payslip.employer, payslip.bonus = payload.tax_rate, payload.employer, payload.bonus
    payslip.tax_withheld = round(max(payload.net_before_tax - payload.net_paid, 0.0), 2)
    payslip.taxable_net = payload.net_before_tax
    session.add(payslip)
    session.commit()
    return {"ok": True}


@router.delete("/payslips/{month}", status_code=204)
def delete_payslip(month: str, session: Session = Depends(get_session)):
    payslip = session.exec(select(Payslip).where(Payslip.month == month)).first()
    if payslip is None:
        raise HTTPException(404, "Payslip not found")
    session.delete(payslip)
    session.commit()


@router.get("")
def income(session: Session = Depends(get_session)):
    payslips = session.exec(select(Payslip).order_by(Payslip.month)).all()
    if not payslips:
        return {"empty": True}
    last_twelve = payslips[-12:]
    count = len(last_twelve)
    average = lambda key: sum(getattr(p, key) for p in last_twelve) / count  # noqa: E731
    annual_gross = average("gross") * 12
    annual_taxable = sum((p.taxable_net or 0.0) for p in last_twelve) / count * 12
    taxable_after_allowance = annual_taxable * (1 - ALLOWANCE)
    rate = marginal_rate(taxable_after_allowance)
    per_ceiling = taxable_after_allowance * PER_CEILING_RATE
    return {
        "empty": False,
        "payslips": [
            {"month": p.month, "gross": p.gross, "net_before_tax": p.net_before_tax, "tax_rate": p.tax_rate,
             "tax_withheld": p.tax_withheld, "net_paid": p.net_paid, "bonus": p.bonus}
            for p in payslips
        ],
        "employer": payslips[-1].employer,
        "months": count,
        "average": {"gross": round(average("gross"), 2), "net_before_tax": round(average("net_before_tax"), 2),
                    "tax_withheld": round(average("tax_withheld"), 2), "net_paid": round(average("net_paid"), 2)},
        "annual_gross": round(annual_gross, 2),
        "annual_taxable_estimate": round(taxable_after_allowance, 2),
        "withholding_share": round(sum(p.tax_withheld for p in last_twelve) / max(sum(p.net_before_tax for p in last_twelve), 1), 4),
        "marginal_rate": rate,
        "per": {
            "ceiling_estimate": round(per_ceiling, 2),
            "tax_saved_per_1000": round(1000 * rate, 2),
            "max_tax_saved": round(per_ceiling * rate, 2),
        },
        "net_share_of_gross": round(sum(p.net_paid for p in last_twelve) / max(sum(p.gross for p in last_twelve), 1), 4),
    }

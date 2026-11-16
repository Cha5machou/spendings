"""Excel exports (e.g. Crédit Mutuel "comptes_YYYYMM.xlsx"): the first sheet that
contains a Date / Libellé / Débit / Crédit table is parsed with the shared table logic."""

import io

import openpyxl

from app.extraction.common import StatementParse
from app.extraction.table_rows import is_header_row, parse_rows


def parse_statement(content: bytes) -> StatementParse:
    workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    best = StatementParse()
    for sheet in workbook.worksheets:
        if sheet.sheet_state != "visible":
            continue
        rows = [list(row) for row in sheet.iter_rows(values_only=True)]
        if not any(is_header_row(row) for row in rows[:30]):
            continue
        parsed = parse_rows(rows)
        if len(parsed.transactions) > len(best.transactions):
            best = parsed
    return best


def parse(content: bytes):
    return parse_statement(content).transactions

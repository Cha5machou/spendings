"""Generic bank CSV parser: detects encoding and delimiter, then hands the rows
to the shared table logic (header-based or headerless)."""

import csv
import io

from app.extraction.common import StatementParse
from app.extraction.table_rows import parse_rows


def decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def parse_statement(content: bytes) -> StatementParse:
    text = decode(content)
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return StatementParse()
    sample = "\n".join(lines[:20])
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=";,\t|").delimiter
    except csv.Error:
        delimiter = ";" if sample.count(";") >= sample.count(",") else ","
    rows = list(csv.reader(io.StringIO("\n".join(lines)), delimiter=delimiter))
    return parse_rows(rows)


def parse(content: bytes):
    return parse_statement(content).transactions

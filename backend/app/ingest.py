"""CSV ingestion into Close Copilot's canonical transaction contract."""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable, Mapping
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import IO, Literal

Source = Literal["bank", "gl"]
CsvInput = str | Path | IO[str]


class IngestError(ValueError):
    """Raised when a source row cannot be converted without guessing."""


_ALIASES: dict[str, tuple[str, ...]] = {
    "id": ("id", "transaction_id", "txn_id", "entry_id"),
    "date": ("date", "transaction_date", "posting_date", "posted_at"),
    "amount": ("amount", "transaction_amount", "net_amount"),
    "currency": ("currency", "currency_code", "ccy"),
    "counterparty": (
        "counterparty",
        "description",
        "vendor",
        "payee",
        "account_name",
    ),
    "reference": ("reference", "ref", "memo", "invoice", "invoice_number"),
}


def _normalized_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _column_map(fieldnames: Iterable[str] | None) -> dict[str, str]:
    if not fieldnames:
        raise IngestError("CSV has no header row")
    normalized = {_normalized_header(name): name for name in fieldnames}
    result: dict[str, str] = {}
    for canonical, aliases in _ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                result[canonical] = normalized[alias]
                break
    missing = {"date", "amount"} - result.keys()
    if missing:
        raise IngestError(
            f"CSV is missing required columns: {', '.join(sorted(missing))}"
        )
    return result


def _parse_date(value: str, *, row_number: int) -> str:
    candidate = value.strip()
    try:
        if match := re.fullmatch(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", candidate):
            year, month, day = map(int, match.groups())
        elif match := re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", candidate):
            month, day, year = map(int, match.groups())
        elif match := re.fullmatch(r"(\d{1,2})-(\d{1,2})-(\d{4})", candidate):
            day, month, year = map(int, match.groups())
        else:
            # ISO timestamps are common in exports; their date prefix is all
            # this canonical transaction contract needs.
            return date.fromisoformat(candidate[:10]).isoformat()
        return date(year, month, day).isoformat()
    except (TypeError, ValueError) as exc:
        raise IngestError(f"row {row_number}: invalid date {value!r}") from exc


def _parse_amount(value: str, *, row_number: int) -> float:
    candidate = value.strip()
    negative = candidate.startswith("(") and candidate.endswith(")")
    if negative:
        candidate = candidate[1:-1]
    candidate = re.sub(r"[$,€£\s]", "", candidate)
    try:
        amount = Decimal(candidate)
    except InvalidOperation as exc:
        raise IngestError(f"row {row_number}: invalid amount {value!r}") from exc
    if negative:
        amount = -amount
    if not amount.is_finite():
        raise IngestError(f"row {row_number}: amount must be finite")
    return float(amount.quantize(Decimal("0.01")))


def _value(row: Mapping[str, str | None], columns: Mapping[str, str], key: str) -> str:
    column = columns.get(key)
    if column is None:
        return ""
    return (row.get(column) or "").strip()


def _ingest_stream(source: Source, stream: IO[str]) -> list[dict[str, object]]:
    reader = csv.DictReader(stream)
    columns = _column_map(reader.fieldnames)
    prefix = "BNK" if source == "bank" else "GL"
    transactions: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for row_number, row in enumerate(reader, start=2):
        raw = {str(key): "" if value is None else value for key, value in row.items()}
        transaction_id = _value(row, columns, "id") or f"{prefix}-{row_number - 1:04d}"
        if transaction_id in seen_ids:
            raise IngestError(f"row {row_number}: duplicate id {transaction_id!r}")
        seen_ids.add(transaction_id)
        transactions.append(
            {
                "id": transaction_id,
                "source": source,
                "date": _parse_date(
                    _value(row, columns, "date"), row_number=row_number
                ),
                "amount": _parse_amount(
                    _value(row, columns, "amount"), row_number=row_number
                ),
                "currency": _value(row, columns, "currency").upper() or "USD",
                "counterparty": _value(row, columns, "counterparty"),
                "reference": _value(row, columns, "reference"),
                "raw": raw,
            }
        )
    return transactions


def ingest_csv(source: Source, csv_input: CsvInput) -> list[dict[str, object]]:
    """Read one CSV and return validated canonical transactions.

    Original column names and values are retained under ``raw`` so every later
    decision can point back to source evidence.
    """

    if source not in ("bank", "gl"):
        raise IngestError(f"unsupported source {source!r}; expected 'bank' or 'gl'")
    if hasattr(csv_input, "read"):
        return _ingest_stream(source, csv_input)  # type: ignore[arg-type]
    with Path(csv_input).open("r", encoding="utf-8-sig", newline="") as stream:
        return _ingest_stream(source, stream)


def ingest_pair(
    bank_csv: CsvInput, gl_csv: CsvInput
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Ingest the two source files used by a close run."""

    return ingest_csv("bank", bank_csv), ingest_csv("gl", gl_csv)

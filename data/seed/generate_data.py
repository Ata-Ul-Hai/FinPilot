"""Generate Close Copilot's deterministic synthetic reconciliation benchmark."""

from __future__ import annotations

import csv
import json
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

SEED = 20260905
ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DIR = ROOT / "data" / "sample"
LABELS_PATH = ROOT / "eval" / "labels.jsonl"
FIELDS = ["id", "date", "amount", "currency", "counterparty", "reference"]

VENDORS = [
    "Acme Freight",
    "Beacon Consulting",
    "Blue River Logistics",
    "Cedar Office Supply",
    "Northstar Software",
    "Summit Telecom",
    "Vertex Cloud Services",
]

TYPO_PAIRS = [
    ("Acme Freight", "ACM FRT"),
    ("Northstar Software", "NRTHSTR SFT"),
    ("Blue River Logistics", "BL RVR LGSTCS"),
    ("Beacon Consulting", "BCN CNSLTNG"),
]


@dataclass
class Builder:
    rng: random.Random
    bank: list[dict[str, str]]
    gl: list[dict[str, str]]
    labels: list[dict[str, str | None]]

    @classmethod
    def create(cls) -> Builder:
        return cls(random.Random(SEED), [], [], [])

    def row(
        self,
        source: str,
        *,
        amount: float,
        posted: date,
        counterparty: str,
        reference: str,
    ) -> dict[str, str]:
        target = self.bank if source == "bank" else self.gl
        prefix = "BNK" if source == "bank" else "GL"
        row = {
            "id": f"{prefix}-{len(target) + 1:04d}",
            "date": posted.isoformat(),
            "amount": f"{amount:.2f}",
            "currency": "USD",
            "counterparty": counterparty,
            "reference": reference,
        }
        target.append(row)
        return row

    def pair(
        self,
        *,
        truth: str,
        index: int,
        bank_date: date,
        gl_date: date | None = None,
        bank_amount: float | None = None,
        gl_amount: float | None = None,
        bank_counterparty: str | None = None,
        gl_counterparty: str | None = None,
        gl_reference: str | None = None,
    ) -> tuple[dict[str, str], dict[str, str]]:
        amount = (
            bank_amount
            if bank_amount is not None
            else -round(self.rng.uniform(25, 4900), 2)
        )
        vendor = bank_counterparty or VENDORS[index % len(VENDORS)]
        reference = f"INV-{4400 + index}"
        bank = self.row(
            "bank",
            amount=amount,
            posted=bank_date,
            counterparty=vendor,
            reference=reference,
        )
        gl = self.row(
            "gl",
            amount=amount if gl_amount is None else gl_amount,
            posted=gl_date or bank_date,
            counterparty=gl_counterparty or vendor,
            reference=reference if gl_reference is None else gl_reference,
        )
        self.labels.append({"bank_id": bank["id"], "gl_id": gl["id"], "truth": truth})
        return bank, gl


def build() -> Builder:
    builder = Builder.create()
    close_date = date(2026, 8, 31)

    for index in range(1, 62):
        builder.pair(truth="matched", index=index, bank_date=close_date)

    for index, days in enumerate((3, 4, 5, 6), start=62):
        builder.pair(
            truth="TIMING_DIFF",
            index=index,
            bank_date=close_date,
            gl_date=close_date + timedelta(days=days),
        )

    # Three duplicate exception groups: one bank transaction and two GL
    # bookings per group, as specified by the frozen taxonomy.
    for index in range(66, 69):
        bank, first_gl = builder.pair(
            truth="DUPLICATE", index=index, bank_date=close_date
        )
        duplicate_gl = builder.row(
            "gl",
            amount=float(first_gl["amount"]),
            posted=close_date,
            counterparty=first_gl["counterparty"],
            reference=first_gl["reference"],
        )
        # The label points at the repeated (erroneous) posting. The original
        # GL row remains the legitimate candidate in the ambiguity group.
        builder.labels[-1]["gl_id"] = duplicate_gl["id"]

    for index in range(69, 72):
        bank = builder.row(
            "bank",
            amount=-round(builder.rng.uniform(15, 250), 2),
            posted=close_date,
            counterparty=VENDORS[index % len(VENDORS)],
            reference=f"BANK-{index}",
        )
        builder.labels.append(
            {"bank_id": bank["id"], "gl_id": None, "truth": "MISSING_ENTRY"}
        )

    for index, delta in enumerate((0.01, 0.03, 1.25, 5.00), start=72):
        amount = -round(builder.rng.uniform(75, 3000), 2)
        builder.pair(
            truth="AMOUNT_MISMATCH",
            index=index,
            bank_date=close_date,
            bank_amount=amount,
            gl_amount=round(amount + delta, 2),
        )

    for index, (canonical, corrupted) in enumerate(TYPO_PAIRS, start=76):
        builder.pair(
            truth="COUNTERPARTY_MISMATCH",
            index=index,
            bank_date=close_date,
            bank_counterparty=canonical,
            gl_counterparty=corrupted,
            gl_reference="",
        )

    assert len(builder.bank) == 79
    assert len(builder.gl) == 79
    assert len(builder.labels) == 79
    assert sum(label["truth"] != "matched" for label in builder.labels) == 18
    return builder


def write() -> None:
    builder = build()
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    LABELS_PATH.parent.mkdir(parents=True, exist_ok=True)
    for path, rows in (
        (SAMPLE_DIR / "bank.csv", builder.bank),
        (SAMPLE_DIR / "gl.csv", builder.gl),
    ):
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    with LABELS_PATH.open("w", encoding="utf-8") as stream:
        for label in builder.labels:
            stream.write(json.dumps(label, sort_keys=True) + "\n")


if __name__ == "__main__":
    write()

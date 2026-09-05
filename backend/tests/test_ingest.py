from io import StringIO

import pytest

from backend.app.ingest import IngestError, ingest_csv, ingest_pair


def test_ingest_canonicalizes_aliases_and_preserves_raw_row() -> None:
    source = StringIO(
        "Transaction ID,Posting Date,Transaction Amount,CCY,Vendor,Memo\n"
        'bank-7,08/31/2026,"($1,234.56)",usd, Acme Freight , INV-4471 \n'
    )

    rows = ingest_csv("bank", source)

    assert rows == [
        {
            "id": "bank-7",
            "source": "bank",
            "date": "2026-08-31",
            "amount": -1234.56,
            "currency": "USD",
            "counterparty": "Acme Freight",
            "reference": "INV-4471",
            "raw": {
                "Transaction ID": "bank-7",
                "Posting Date": "08/31/2026",
                "Transaction Amount": "($1,234.56)",
                "CCY": "usd",
                "Vendor": " Acme Freight ",
                "Memo": " INV-4471 ",
            },
        }
    ]


def test_ingest_pair_generates_stable_ids() -> None:
    bank, gl = ingest_pair(
        StringIO("date,amount\n2026-08-31,10.00\n"),
        StringIO("date,amount\n2026-08-31,10.00\n"),
    )

    assert bank[0]["id"] == "BNK-0001"
    assert gl[0]["id"] == "GL-0001"
    assert bank[0]["raw"] == {"date": "2026-08-31", "amount": "10.00"}


@pytest.mark.parametrize(
    ("csv_text", "message"),
    [
        ("date,memo\n2026-08-31,x\n", "missing required columns: amount"),
        ("date,amount\nnot-a-date,1\n", "invalid date"),
        ("date,amount\n2026-08-31,nope\n", "invalid amount"),
    ],
)
def test_ingest_rejects_ambiguous_or_invalid_rows(csv_text: str, message: str) -> None:
    with pytest.raises(IngestError, match=message):
        ingest_csv("bank", StringIO(csv_text))


def test_ingest_rejects_duplicate_source_ids() -> None:
    with pytest.raises(IngestError, match="duplicate id"):
        ingest_csv(
            "gl",
            StringIO("id,date,amount\nGL-1,2026-08-31,1\nGL-1,2026-08-31,2\n"),
        )

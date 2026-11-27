"""Private fixture documents; generated outside the agent's workspace."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from random import Random


def pdf_bytes(text: str) -> bytes:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 40 760 Td ({escaped}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length "
        + str(len(stream)).encode()
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
    ]
    # A binary PDF comment ensures text transcription cannot preserve the original.
    data = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(
        (
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n"
        ).encode()
    )
    return bytes(data)


@dataclass(frozen=True)
class Invoice:
    number: str
    period: str
    total: str
    document: bytes


def invoices(seed: int) -> tuple[Invoice, ...]:
    rng = Random(seed)  # noqa: S311 -- reproducible fixture records, not credentials
    result: list[Invoice] = []
    for month in (5, 6, 7):
        number = f"DOC-{rng.randrange(100000, 999999)}"
        period = f"2026-{month:02d}"
        total = str(Decimal(rng.randrange(1000, 9000)) / 100)
        text = f"Cedar Services Invoice {number} Period {period} Total EUR {total} Paid"
        result.append(Invoice(number, period, total, pdf_bytes(text)))
    return tuple(result)

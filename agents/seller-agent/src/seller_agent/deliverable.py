"""The demo deliverable: a small market report as a zip, built deterministically.

The same deal always gives the same bytes: fixed entry order and timestamps, no
compression, no platform-dependent attributes. Money is in integer minor units.
"""

from __future__ import annotations

import io
import json
import zipfile

MEDIA_TYPE = "application/zip"
REPORT, DATA, SUMMARY = "report.md", "data.csv", "summary.json"
FIXED_TIME = (2026, 1, 1, 0, 0, 0)
ROWS: tuple[tuple[str, int, int], ...] = (
    ("north", 120, 1440000),
    ("south", 95, 1092500),
    ("east", 143, 1787500),
    ("west", 88, 968000),
)


def _files(deal_id: str) -> dict[str, str]:
    units = sum(row[1] for row in ROWS)
    revenue = sum(row[2] for row in ROWS)
    top = max(ROWS, key=lambda row: row[2])[0]
    report = (
        "# Market report\n\n"
        f"Deal: {deal_id}\n\n"
        f"Four regions were surveyed. Together they sold {units} units for "
        f"{revenue} minor units (EUR). The strongest region is {top}.\n\n"
        f"The figures are in `{DATA}`; `{SUMMARY}` holds the totals.\n"
    )
    data = "region,units,revenue_minor\n" + "".join(
        f"{region},{count},{amount}\n" for region, count, amount in ROWS
    )
    summary = {
        "deal_id": deal_id,
        "currency": "EUR",
        "regions": len(ROWS),
        "units": units,
        "revenue_minor": revenue,
        "top_region": top,
    }
    return {
        REPORT: report,
        DATA: data,
        SUMMARY: json.dumps(summary, sort_keys=True, indent=2) + "\n",
    }


def build_deliverable(deal_id: str, *, include_summary: bool = True) -> bytes:
    """Zip bytes of the deliverable; without ``summary.json`` it is the broken one."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, text in _files(deal_id).items():
            if name == SUMMARY and not include_summary:
                continue
            info = zipfile.ZipInfo(name, date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o644 << 16
            archive.writestr(info, text.encode("utf-8"))
    return buffer.getvalue()

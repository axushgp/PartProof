import io
from decimal import Decimal
from typing import Any, Dict, List, Optional
import openpyxl

from app.schemas.procurement import DocumentProvenance, ExtractedDocument
from app.services.procurement.parsers.csv_parser import (
    _clean_str,
    _normalize_header,
    _parse_decimal,
)


def parse_xlsx_document(
    content_bytes: bytes,
    filename: str,
    doc_type: str = "bom",
    supplier_id: Optional[str] = None,
    supplier_name: Optional[str] = None,
) -> ExtractedDocument:
    """
    Safely extracts procurement items from XLSX spreadsheets.
    Enforces read-only, data-only mode to prevent formula/macro execution.
    """
    try:
        wb = openpyxl.load_workbook(
            io.BytesIO(content_bytes),
            data_only=True,
            read_only=True,
            keep_vba=False,
        )
    except Exception as e:
        return ExtractedDocument(
            filename=filename,
            doc_type="bom" if doc_type == "bom" else "quote",
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            warnings=[f"Failed to open Excel workbook: {str(e)}"],
            has_extractable_text=False,
        )

    sheet_names = wb.sheetnames
    if not sheet_names:
        return ExtractedDocument(
            filename=filename,
            doc_type="bom" if doc_type == "bom" else "quote",
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            warnings=["Excel file contains no worksheets."],
            has_extractable_text=False,
        )

    ws = wb[sheet_names[0]]
    rows_iter = ws.iter_rows(values_only=True)

    rows: List[List[Any]] = []
    for r in rows_iter:
        if any(cell is not None for cell in r):
            rows.append(list(r))

    wb.close()

    if not rows:
        return ExtractedDocument(
            filename=filename,
            doc_type="bom" if doc_type == "bom" else "quote",
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            warnings=["Worksheet contains no data."],
            has_extractable_text=False,
        )

    raw_headers = rows[0]
    col_mapping = {
        idx: _normalize_header(str(h)) for idx, h in enumerate(raw_headers) if h is not None
    }

    items: List[Dict[str, Any]] = []
    sheet_name = sheet_names[0]

    for row_idx, row in enumerate(rows[1:], start=2):
        if not any(bool(_clean_str(c)) for c in row):
            continue
        item: Dict[str, Any] = {
            "part_number": "",
            "description": "",
            "qty": Decimal("1"),
            "uom": "pcs",
            "unit_price": Decimal("0"),
            "pack_size": Decimal("1"),
            "moq": Decimal("1"),
            "tax_pct": Decimal("0.18"),
            "freight": Decimal("0"),
            "lead_time_days": 14,
            "warranty_months": 12,
            "payment_terms": "Net 30",
        }
        for col_idx, cell in enumerate(row):
            field = col_mapping.get(col_idx)
            if not field or cell is None:
                continue
            cleaned = _clean_str(cell)
            if field in ("qty", "required_qty"):
                item["qty"] = _parse_decimal(cleaned, Decimal("1"))
            elif field in ("unit_price", "target_unit_price"):
                item["unit_price"] = _parse_decimal(cleaned, Decimal("0"))
            elif field == "pack_size":
                item["pack_size"] = _parse_decimal(cleaned, Decimal("1"))
            elif field == "moq":
                item["moq"] = _parse_decimal(cleaned, Decimal("1"))
            elif field == "tax_pct":
                item["tax_pct"] = _parse_decimal(cleaned, Decimal("0.18"))
            elif field == "freight":
                item["freight"] = _parse_decimal(cleaned, Decimal("0"))
            elif field == "lead_time_days":
                d = _parse_decimal(cleaned, Decimal("14"))
                item["lead_time_days"] = int(d)
            elif field == "warranty_months":
                w = _parse_decimal(cleaned, Decimal("12"))
                item["warranty_months"] = int(w)
            elif field in item:
                item[field] = cleaned

        if not item["part_number"] and not item["description"]:
            continue

        raw_row_text = " | ".join(str(c) for c in row if c is not None)
        provenance = DocumentProvenance(
            filename=filename,
            doc_type="bom" if doc_type == "bom" else "quote",
            sheet_name=sheet_name,
            row_number=row_idx,
            raw_text=raw_row_text[:200],
        )
        item["provenance"] = provenance.model_dump()
        items.append(item)

    return ExtractedDocument(
        filename=filename,
        doc_type="bom" if doc_type == "bom" else "quote",
        supplier_id=supplier_id,
        supplier_name=supplier_name,
        items=items,
        page_count=len(sheet_names),
        has_extractable_text=True,
    )

import io
import re
from decimal import Decimal
from typing import Any, Dict, List, Optional
import pdfplumber
import pypdf

from app.schemas.procurement import DocumentProvenance, ExtractedDocument
from app.services.procurement.parsers.csv_parser import (
    _clean_str,
    _normalize_header,
    _parse_decimal,
)


def parse_pdf_document(
    content_bytes: bytes,
    filename: str,
    doc_type: str = "quote",
    supplier_id: Optional[str] = None,
    supplier_name: Optional[str] = None,
) -> ExtractedDocument:
    """
    Extracts text and tables from digital PDFs using pdfplumber with pypdf fallback.
    Explicitly detects scanned PDFs and emits an OCR-required warning without treating them as empty.
    """
    warnings: List[str] = []
    items: List[Dict[str, Any]] = []
    total_text_length = 0
    scanned_pages: List[int] = []
    page_count = 0

    try:
        with pdfplumber.open(io.BytesIO(content_bytes)) as pdf:
            page_count = len(pdf.pages)
            if page_count == 0:
                return ExtractedDocument(
                    filename=filename,
                    doc_type="bom" if doc_type == "bom" else "quote",
                    supplier_id=supplier_id,
                    supplier_name=supplier_name,
                    warnings=["PDF contains zero pages."],
                    has_extractable_text=False,
                )

            for page_idx, page in enumerate(pdf.pages, start=1):
                page_text = page.extract_text() or ""
                text_len = len(page_text.strip())
                total_text_length += text_len

                if text_len < 15:
                    scanned_pages.append(page_idx)

                # 1. Try table extraction
                tables = page.extract_tables() or []
                table_extracted = False

                for table in tables:
                    if not table or len(table) < 2:
                        continue
                    headers = [_clean_str(h) for h in table[0] if h is not None]
                    col_mapping = {idx: _normalize_header(h) for idx, h in enumerate(headers)}
                    
                    if not any(k in col_mapping.values() for k in ["part_number", "description", "qty", "unit_price"]):
                        continue

                    table_extracted = True
                    for row_idx, row in enumerate(table[1:], start=2):
                        if not any(bool(_clean_str(c)) for c in row if c is not None):
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
                            page_number=page_idx,
                            row_number=row_idx,
                            raw_text=raw_row_text[:200],
                        )
                        item["provenance"] = provenance.model_dump()
                        items.append(item)

                # 2. Text regex fallback if no table was extracted
                if not table_extracted and text_len >= 15:
                    lines = page_text.splitlines()
                    for line_idx, line in enumerate(lines, start=1):
                        cleaned_line = _clean_str(line)
                        # Heuristic for line item: e.g. "BRG-6204-2RS Deep Groove Bearing 200 $11.50"
                        parts = cleaned_line.split()
                        if len(parts) >= 3 and any(char.isdigit() for char in cleaned_line):
                            price_match = re.search(r"[\$₹]?([0-9]+\.?[0-9]*)", cleaned_line)
                            unit_price = Decimal(price_match.group(1)) if price_match else Decimal("0")
                            item = {
                                "part_number": parts[0],
                                "description": " ".join(parts[1: len(parts) - 1]),
                                "qty": Decimal("1"),
                                "uom": "pcs",
                                "unit_price": unit_price,
                                "pack_size": Decimal("1"),
                                "moq": Decimal("1"),
                                "tax_pct": Decimal("0.18"),
                                "freight": Decimal("0"),
                                "lead_time_days": 14,
                                "warranty_months": 12,
                                "payment_terms": "Net 30",
                                "provenance": DocumentProvenance(
                                    filename=filename,
                                    doc_type="bom" if doc_type == "bom" else "quote",
                                    page_number=page_idx,
                                    row_number=line_idx,
                                    raw_text=cleaned_line[:200],
                                ).model_dump(),
                            }
                            items.append(item)

    except Exception as pdfplumber_err:
        # Fallback to pypdf for text inspection
        try:
            reader = pypdf.PdfReader(io.BytesIO(content_bytes))
            page_count = len(reader.pages)
            for page_idx, page in enumerate(reader.pages, start=1):
                pt = page.extract_text() or ""
                total_text_length += len(pt.strip())
                if len(pt.strip()) < 15:
                    scanned_pages.append(page_idx)
        except Exception:
            warnings.append(f"Failed to parse PDF: {str(pdfplumber_err)}")

    ocr_required = False
    if total_text_length < 30 or len(scanned_pages) == page_count:
        ocr_required = True
        warnings.append(
            f"OCR REQUIRED: Document '{filename}' contains no extractable digital text. "
            f"Scanned image PDF detected. Manual line entry or external OCR is required."
        )
    elif scanned_pages:
        warnings.append(
            f"OCR WARNING: Pages {scanned_pages} contained no digital text. Items on these pages were skipped."
        )

    return ExtractedDocument(
        filename=filename,
        doc_type="bom" if doc_type == "bom" else "quote",
        supplier_id=supplier_id,
        supplier_name=supplier_name,
        items=items,
        warnings=warnings,
        ocr_required=ocr_required,
        page_count=page_count,
        has_extractable_text=(not ocr_required),
    )

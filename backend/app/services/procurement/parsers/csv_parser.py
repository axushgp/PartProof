import csv
import io
import re
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.procurement import DocumentProvenance, ExtractedDocument


def _clean_str(val: Any) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    # Strip null bytes and control chars
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)


def _parse_decimal(val: Any, default: Decimal = Decimal("0")) -> Decimal:
    if val is None:
        return default
    s = _clean_str(val).replace("$", "").replace("₹", "").replace(",", "").strip()
    if not s:
        return default
    try:
        return Decimal(s)
    except Exception:
        # Match leading numeric part
        m = re.match(r"^[-+]?[0-9]*\.?[0-9]+", s)
        if m:
            try:
                return Decimal(m.group(0))
            except Exception:
                pass
        return default


def _normalize_header(header: str) -> str:
    h = _clean_str(header).lower().replace(" ", "_").replace("-", "_").replace("#", "_no")
    
    if any(k in h for k in ["part_no", "part_num", "part_number", "part", "pn", "sku", "code"]):
        return "part_number"
    if any(k in h for k in ["description", "desc", "specification", "spec", "item_name", "title"]):
        return "description"
    if any(k in h for k in ["unit_price", "price", "rate", "unit_cost", "cost", "target_price"]):
        return "unit_price"
    if any(k in h for k in ["qty", "quantity", "req_qty", "units"]):
        return "qty"
    if any(k in h for k in ["uom", "unit_of_measure"]) or h == "unit":
        return "uom"
    if any(k in h for k in ["pack_size", "pack", "package_size", "box_qty"]):
        return "pack_size"
    if any(k in h for k in ["moq", "min_order", "minimum_order"]):
        return "moq"
    if any(k in h for k in ["tax", "gst", "vat"]):
        return "tax_pct"
    if any(k in h for k in ["freight", "shipping"]):
        return "freight"
    if any(k in h for k in ["lead_time", "delivery_days", "delivery"]):
        return "lead_time_days"
    if any(k in h for k in ["warranty", "guarantee"]):
        return "warranty_months"
    if any(k in h for k in ["payment_term", "payment"]):
        return "payment_terms"
    return h


def parse_csv_document(
    content_bytes: bytes,
    filename: str,
    doc_type: str = "bom",
    supplier_id: Optional[str] = None,
    supplier_name: Optional[str] = None,
) -> ExtractedDocument:
    """Safely extracts line items from CSV with encoding & delimiter detection."""
    text = ""
    for enc in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
        try:
            text = content_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    if not text:
        return ExtractedDocument(
            filename=filename,
            doc_type="bom" if doc_type == "bom" else "quote",
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            warnings=["Could not decode CSV text with standard encodings."],
            has_extractable_text=False,
        )

    # Sniff delimiter
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ExtractedDocument(
            filename=filename,
            doc_type="bom" if doc_type == "bom" else "quote",
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            warnings=["CSV file is empty."],
            has_extractable_text=False,
        )

    sample = "\n".join(lines[:10])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        delimiter = dialect.delimiter
    except Exception:
        delimiter = ","

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        return ExtractedDocument(
            filename=filename,
            doc_type="bom" if doc_type == "bom" else "quote",
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            warnings=["No rows found in CSV."],
            has_extractable_text=False,
        )

    raw_headers = rows[0]
    col_mapping = {idx: _normalize_header(h) for idx, h in enumerate(raw_headers)}

    items: List[Dict[str, Any]] = []
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
            if not field:
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

        raw_row_text = delimiter.join(row)
        provenance = DocumentProvenance(
            filename=filename,
            doc_type="bom" if doc_type == "bom" else "quote",
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
        page_count=1,
        has_extractable_text=True,
    )

import re
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.procurement import (
    BOMItem,
    DocumentProvenance,
    ExtractedDocument,
    QuoteItem,
)
from app.services.procurement.parsers.csv_parser import parse_csv_document
from app.services.procurement.parsers.pdf_parser import parse_pdf_document
from app.services.procurement.parsers.xlsx_parser import parse_xlsx_document

INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(?:all\s+)?(?:previous\s+)?instructions", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"<\s*script[^>]*>", re.IGNORECASE),
    re.compile(r"```(?:python|bash|sh|cmd)", re.IGNORECASE),
    re.compile(r"\brm\s+-rf\b", re.IGNORECASE),
    re.compile(r"\bformat\s+c:", re.IGNORECASE),
]


def sanitize_untrusted_text(text: Optional[str]) -> str:
    """Strips null characters, control codes, and adversarial prompt-injection signatures."""
    if not text:
        return ""
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(text)).strip()
    for pattern in INJECTION_PATTERNS:
        cleaned = pattern.sub("[FILTERED_INPUT]", cleaned)
    return cleaned


def parse_and_normalize_file(
    content_bytes: bytes,
    filename: str,
    doc_type: str = "bom",
    supplier_id: Optional[str] = None,
    supplier_name: Optional[str] = None,
) -> ExtractedDocument:
    """Dispatches to the correct parser based on file extension."""
    lower_fn = filename.lower()
    if lower_fn.endswith(".csv"):
        return parse_csv_document(content_bytes, filename, doc_type, supplier_id, supplier_name)
    elif lower_fn.endswith(".xlsx"):
        return parse_xlsx_document(content_bytes, filename, doc_type, supplier_id, supplier_name)
    elif lower_fn.endswith(".pdf"):
        return parse_pdf_document(content_bytes, filename, doc_type, supplier_id, supplier_name)
    else:
        # Fallback treat as CSV
        return parse_csv_document(content_bytes, filename, doc_type, supplier_id, supplier_name)


def normalize_to_bom_items(extracted: ExtractedDocument) -> List[BOMItem]:
    """Converts raw extracted item dicts into validated BOMItem models."""
    bom_items: List[BOMItem] = []
    for idx, item in enumerate(extracted.items, start=1):
        pn = sanitize_untrusted_text(item.get("part_number") or f"PART-{idx:03d}")
        desc = sanitize_untrusted_text(item.get("description") or f"Item {pn}")
        qty = Decimal(str(item.get("qty") or "1"))
        uom = sanitize_untrusted_text(item.get("uom") or "pcs").lower()
        price = Decimal(str(item.get("unit_price") or "0")) if item.get("unit_price") else None
        
        prov_dict = item.get("provenance")
        prov = DocumentProvenance.model_validate(prov_dict) if prov_dict else None

        bom_items.append(
            BOMItem(
                item_id=f"bom-item-{idx:03d}",
                part_number=pn,
                description=desc,
                category=sanitize_untrusted_text(item.get("category") or "general"),
                required_qty=max(qty, Decimal("1")),
                uom=uom,
                target_unit_price=price,
                currency="USD",
                spec_notes=sanitize_untrusted_text(item.get("spec_notes") or ""),
                provenance=prov,
            )
        )
    return bom_items


def normalize_to_quote_items(
    extracted: ExtractedDocument,
    supplier_id: str,
    supplier_name: str,
) -> List[QuoteItem]:
    """Converts raw extracted item dicts into validated QuoteItem models."""
    quote_items: List[QuoteItem] = []
    for idx, item in enumerate(extracted.items, start=1):
        pn = sanitize_untrusted_text(item.get("part_number") or f"QPART-{idx:03d}")
        desc = sanitize_untrusted_text(item.get("description") or f"Quoted {pn}")
        qty = Decimal(str(item.get("qty") or "1"))
        price = Decimal(str(item.get("unit_price") or "0"))
        pack_size = Decimal(str(item.get("pack_size") or "1"))
        moq = Decimal(str(item.get("moq") or "1"))
        tax_pct = Decimal(str(item.get("tax_pct") or "0.18"))
        freight = Decimal(str(item.get("freight") or "0"))

        prov_dict = item.get("provenance")
        prov = DocumentProvenance.model_validate(prov_dict) if prov_dict else None

        quote_items.append(
            QuoteItem(
                quote_item_id=f"quote-{supplier_id}-{idx:03d}",
                supplier_id=supplier_id,
                supplier_name=supplier_name,
                part_number=pn,
                description=desc,
                quoted_qty=max(qty, Decimal("1")),
                pack_size=max(pack_size, Decimal("1")),
                moq=max(moq, Decimal("1")),
                unit_price=max(price, Decimal("0.00")),
                currency="USD",
                tax_pct=tax_pct,
                tax_inclusive=bool(item.get("tax_inclusive", False)),
                freight_terms=item.get("freight_terms", "included"),
                freight_amount=freight,
                lead_time_days=int(item.get("lead_time_days") or 14),
                warranty_months=int(item.get("warranty_months") or 12),
                payment_terms=sanitize_untrusted_text(item.get("payment_terms") or "Net 30"),
                provenance=prov,
            )
        )
    return quote_items

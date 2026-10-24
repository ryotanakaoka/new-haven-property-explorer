"""Untrusted offering-memo PDF extraction. No instructions in the document are executed."""
from __future__ import annotations
import io
import re
from pypdf import PdfReader

FIELD_PATTERNS = {
    "asking_price": r"(?:asking|offer|purchase)\s*(?:price)?\s*[:=-]?\s*\$?\s*([\d,]+)",
    "unit_count": r"(?:units?|apartments?)\s*[:=-]?\s*(\d+)",
    "annual_rent": r"(?:annual|gross)\s*(?:rent|revenue)\s*[:=-]?\s*\$?\s*([\d,]+)",
    "annual_expenses": r"(?:annual|operating)\s*(?:expenses?|costs?)\s*[:=-]?\s*\$?\s*([\d,]+)",
    "occupancy": r"occupancy\s*[:=-]?\s*(\d+(?:\.\d+)?)\s*%",
}

def extract_offering_text_pages(pages: list[str]) -> dict:
    fields = {}
    conflicts = []
    page_records = []
    for page_number, text in enumerate(pages, start=1):
        page_records.append({"page": page_number, "text": text})
        for field, pattern in FIELD_PATTERNS.items():
            match = re.search(pattern, text, re.I)
            if not match:
                continue
            raw = match.group(1).replace(",", "")
            value = float(raw) if field == "occupancy" else int(raw)
            if field == "occupancy": value /= 100
            if field in fields and fields[field]["value"] != value:
                conflicts.append(f"{field}: page {fields[field]['page']} says {fields[field]['value']}; page {page_number} says {value}")
            fields[field] = {"value": value, "page": page_number, "citation": f"Offering memo p. {page_number}"}
    missing = [field for field in FIELD_PATTERNS if field not in fields]
    untrusted_terms = re.findall(r"(?i)ignore\s+(?:all\s+)?(?:prior|previous|above)\s+instructions|system\s+message|developer\s+message|reveal\s+secret", "\n".join(p["text"] for p in page_records))
    return {"fields": fields, "missing": missing, "conflicts": conflicts, "pages": len(page_records), "untrusted_instructions_found": bool(untrusted_terms), "untrusted_warning": "Instruction-like text was ignored; only labeled numeric fields were extracted." if untrusted_terms else None}


def extract_offering_pdf(pdf_bytes: bytes) -> dict:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return extract_offering_text_pages([(page.extract_text() or "") for page in reader.pages])

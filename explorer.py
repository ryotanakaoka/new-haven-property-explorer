"""Filtering helpers for the public sales explorer."""
from __future__ import annotations
from datetime import date, datetime
import re
from statistics import median

AI_RECORD_CAP = 5000

def filter_sales(rows, property_types=None, start_date=None, end_date=None, min_price=None, max_price=None, unsupported_location=False):
    out = []
    for row in rows:
        if property_types and row.get("property_type") not in property_types: continue
        try: sale_date = datetime.fromisoformat(row["sale_date"][:10]).date()
        except (KeyError, ValueError, TypeError): continue
        price = row.get("sale_price")
        if start_date and sale_date < start_date: continue
        if end_date and sale_date > end_date: continue
        if min_price is not None and (price is None or price < min_price): continue
        if max_price is not None and (price is None or price > max_price): continue
        out.append(row)
    return out

def parse_natural_language_filters(text: str, known_types):
    """Conservative parser; unspecified filters remain unset and never create records."""
    result = {"property_types": [], "min_price": None, "max_price": None, "start_date": None, "end_date": None, "unsupported_location": False}
    lowered = text.lower()
    result["unsupported_location"] = bool(re.search(r"\b(downtown|neighborhood|near|location|address|street)\b", lowered))
    for typ in known_types:
        if typ.lower() in lowered or typ.lower().rstrip("s") in lowered:
            result["property_types"].append(typ)
    prices = []
    # Currency-marked values: $600,000, USD 600000, 600k, and 0.9m.
    marked = re.findall(r"(?:\$|USD\s*)(\d[\d,]*(?:\.\d+)?)\s*([kKmM])?", text, re.I)
    marked += re.findall(r"(\d+(?:\.\d+)?)\s*([kKmM])\b", text, re.I)
    for number, suffix in marked:
        value = float(number.replace(',', ''))
        if suffix.lower() == 'k': value *= 1_000
        if suffix.lower() == 'm': value *= 1_000_000
        prices.append(int(value))
    # Bare numbers are accepted only when clear price language introduces them.
    for match in re.finditer(r"(?:price|priced|sale price|sales price)\D+(\d[\d,]*(?:\.\d+)?)", text, re.I):
        value = int(float(match.group(1).replace(',', '')))
        if not 1900 <= value <= 2100: prices.append(value)
    if "under" in text.lower() or "below" in text.lower():
        if prices: result["max_price"] = prices[0]
    elif "over" in text.lower() or "above" in text.lower():
        if prices: result["min_price"] = prices[0]
    elif len(prices) >= 2:
        result["min_price"], result["max_price"] = min(prices[:2]), max(prices[:2])
    years = [int(year) for year in re.findall(r"\b(20\d{2})\b", text)]
    if len(years) >= 2:
        start_year, end_year = sorted(years[:2])
        result["start_date"] = date(start_year, 1, 1)
        result["end_date"] = date(end_year, 12, 31)
    elif len(years) == 1:
        result["start_date"] = date(years[0], 1, 1)
        result["end_date"] = date(years[0], 12, 31)
    return result

def search_request_result(text: str, known_types) -> dict:
    """Return the UI flow decision before any records are filtered or displayed."""
    parsed = parse_natural_language_filters(text, known_types)
    if parsed.get("unsupported_location", False):
        return {"stop": True, "message": "Location search is not supported. Use the property-type, date, and price filters instead.", "filters": parsed}
    if text.strip() and not any(parsed.get(key) for key in ("property_types", "start_date", "end_date", "min_price", "max_price")):
        return {"stop": True, "message": "No supported filter was found in that search. Use a property type, sale date, or price range.", "filters": parsed}
    return {"stop": False, "message": None, "filters": parsed}

def combine_search_filters(sidebar_filters: dict, natural_filters: dict) -> dict:
    """Intersect sidebar and natural-language filters without mutating either input."""
    combined = dict(sidebar_filters)
    natural_types = set(natural_filters.get("property_types") or [])
    sidebar_types = set(sidebar_filters.get("property_types") or [])
    combined["property_types"] = sorted(natural_types & sidebar_types) if natural_types else list(sidebar_types)
    for key, mode in (("start_date", max), ("end_date", min)):
        values = [v for v in (sidebar_filters.get(key), natural_filters.get(key)) if v is not None]
        combined[key] = mode(values) if values else None
    mins = [v for v in (sidebar_filters.get("min_price"), natural_filters.get("min_price")) if v is not None]
    maxes = [v for v in (sidebar_filters.get("max_price"), natural_filters.get("max_price")) if v is not None]
    combined["min_price"] = max(mins) if mins else None
    combined["max_price"] = min(maxes) if maxes else None
    return combined

def build_ai_records_payload(filtered: list[dict], cap: int = AI_RECORD_CAP) -> dict:
    """Build a compact payload from exactly the rows currently shown by Python."""
    if len(filtered) > cap:
        raise ValueError(f"AI record cap exceeded: {len(filtered)} > {cap}")
    prices = [row["sale_price"] for row in filtered if row.get("sale_price") is not None]
    records = [{key: row.get(key) for key in ("record_id", "address", "property_type", "sale_date", "sale_price", "assessment")} for row in filtered]
    return {"matching_count": len(filtered), "median_sale_price": median(prices) if prices else None, "record_ids": [row.get("record_id") for row in filtered], "records": records}

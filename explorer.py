"""Filtering helpers for the public sales explorer."""
from __future__ import annotations
from datetime import date, datetime
import re
from statistics import median
from collections import defaultdict

AI_RECORD_CAP = 5000
MAX_AI_CALLS_PER_SESSION = 5
MAX_AI_QUESTION_CHARS = 500
PROMPT_INJECTION_RE = re.compile(
    r"\b(?:ignore|disregard|override)\b.{0,80}\b(?:all\s+)?(?:previous|prior|above|system|developer)\s+instructions?\b"
    r"|\b(?:reveal|print|show)\b.{0,80}\b(?:system prompt|developer message|hidden instructions|secrets?)\b",
    re.I,
)


def is_prompt_injection_request(text: str) -> bool:
    """Recognize common instruction-override or secret-extraction attempts."""
    return bool(PROMPT_INJECTION_RE.search(text or ""))


def ai_request_guard(calls_made: int, question: str) -> dict:
    """Bound AI use in one Streamlit session and reject oversized questions."""
    if len(question or "") > MAX_AI_QUESTION_CHARS:
        return {
            "allowed": False,
            "message": f"Questions are limited to {MAX_AI_QUESTION_CHARS} characters.",
        }
    if calls_made >= MAX_AI_CALLS_PER_SESSION:
        return {
            "allowed": False,
            "message": f"This browser session has reached its limit of {MAX_AI_CALLS_PER_SESSION} AI requests. Start a new session or continue with the Python results.",
        }
    return {"allowed": True, "message": None}

def readable_sale_date(value) -> str | None:
    """Return the public-facing ISO calendar date without a timestamp."""
    if not value:
        return None
    return str(value)[:10]

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
    """Apply stated natural-language filters, retaining sidebar values only when unstated."""
    combined = dict(sidebar_filters)
    natural_types = set(natural_filters.get("property_types") or [])
    sidebar_types = set(sidebar_filters.get("property_types") or [])
    combined["property_types"] = sorted(natural_types) if natural_types else list(sidebar_types)
    for key in ("start_date", "end_date", "min_price", "max_price"):
        if natural_filters.get(key) is not None:
            combined[key] = natural_filters[key]
    return combined

def filter_override_messages(sidebar_filters: dict, natural_filters: dict) -> list[str]:
    """Describe sidebar values replaced by explicitly stated natural-language filters."""
    labels = {"property_types": "property type", "start_date": "start date", "end_date": "end date", "min_price": "minimum price", "max_price": "maximum price"}
    messages = []
    def display(value):
        if isinstance(value, (int, float)):
            return f"USD {value:,.0f}"
        return ", ".join(value) if isinstance(value, (list, tuple, set)) else str(value)
    for key, label in labels.items():
        natural = natural_filters.get(key)
        sidebar = sidebar_filters.get(key)
        if natural is not None and natural != sidebar:
            messages.append(f"Natural-language {label} ({display(natural)}) overrides sidebar value ({display(sidebar)}).")
    return messages

def build_ai_records_payload(filtered: list[dict], cap: int = AI_RECORD_CAP) -> dict:
    """Build a compact payload from exactly the rows currently shown by Python."""
    if len(filtered) > cap:
        raise ValueError(f"AI record cap exceeded: {len(filtered)} > {cap}")
    prices = [row["sale_price"] for row in filtered if row.get("sale_price") is not None]
    records = [{**{key: row.get(key) for key in ("record_id", "address", "property_type", "sale_price", "assessment", "sales_source")}, "sale_date": readable_sale_date(row.get("sale_date"))} for row in filtered]
    return {"matching_count": len(filtered), "median_sale_price": median(prices) if prices else None, "record_ids": [row.get("record_id") for row in filtered], "records": records}

def analyze_filtered_records(rows: list[dict], question: str) -> dict:
    """Calculate supported factual analyses using only the already filtered rows."""
    text = (question or "").lower()
    prices = [r for r in rows if r.get("sale_price") is not None]
    cited = lambda records: [{"record_id": r.get("record_id"), "sale_date": readable_sale_date(r.get("sale_date")), "sale_price": r.get("sale_price"), "sales_source": r.get("sales_source")} for r in records[:5]]
    if any(word in text for word in ("recent", "latest", "newest")):
        ordered = sorted(prices, key=lambda r: r.get("sale_date", ""), reverse=True)
        return {"supported": True, "analysis": "recent_sales", "count": len(ordered), "records": cited(ordered[:5])}
    if any(word in text for word in ("highest", "most expensive", "maximum")):
        ordered = sorted(prices, key=lambda r: r["sale_price"], reverse=True)
        return {"supported": True, "analysis": "highest_prices", "records": cited(ordered[:5]), "prices": [r["sale_price"] for r in ordered[:5]]}
    if any(word in text for word in ("lowest", "cheapest", "minimum")):
        ordered = sorted(prices, key=lambda r: r["sale_price"])
        return {"supported": True, "analysis": "lowest_prices", "records": cited(ordered[:5]), "prices": [r["sale_price"] for r in ordered[:5]]}
    if "trend" in text or "over time" in text:
        grouped = defaultdict(list)
        for row in prices:
            grouped[row["sale_date"][:4]].append(row["sale_price"])
        return {"supported": True, "analysis": "annual_trend", "by_year": {year: {"count": len(vals), "median_sale_price": median(vals)} for year, vals in sorted(grouped.items())}, "data_quality_note": "2025 data is partial through September 22 and should not be directly compared with full years."}
    if any(word in text for word in ("compare", "comparison", "by property type", "property types")):
        grouped = defaultdict(list)
        for row in prices:
            grouped[row.get("property_type") or "Unknown"].append(row["sale_price"])
        return {"supported": True, "analysis": "property_type_comparison", "by_property_type": {typ: {"count": len(vals), "median_sale_price": median(vals)} for typ, vals in sorted(grouped.items())}}
    return {"supported": False, "message": "The filtered public sales cannot answer that question. Ask about recent sales, highest or lowest prices, trends over time, or comparisons by property type."}

def build_sales_analysis_payload(filtered: list[dict], question: str) -> dict:
    """Return only the compact Python result needed to explain a sales question."""
    if is_prompt_injection_request(question):
        return {
            "supported": False,
            "message": "This request includes instructions outside the supported public-record analysis and was blocked before AI.",
        }
    if len(question or "") > MAX_AI_QUESTION_CHARS:
        return {
            "supported": False,
            "message": f"Questions are limited to {MAX_AI_QUESTION_CHARS} characters.",
        }
    analysis = analyze_filtered_records(filtered, question)
    if not analysis["supported"]:
        return analysis
    return {"matching_count": len(filtered), "python_analysis": analysis}

def analysis_records_status(count: int, sent: bool = False) -> str:
    return f"Records sent to AI: {count}" if sent else f"Records prepared for analysis: {count}"

def format_cama_details(details: dict) -> dict:
    """Format matched CAMA values for the single-property details panel."""
    def value(key):
        item = details.get(key)
        return "Not available" if item in (None, "") else str(item)
    def whole_value(key):
        item = details.get(key)
        return "Not available" if item in (None, "") else f"{float(item):.0f}"
    assessment = details.get("assessment")
    living_area = details.get("living_area")
    return {
        "Assessment": "Not available" if assessment in (None, "") else f"USD {float(assessment):,.0f}",
        "Valuation year": whole_value("valuation_year"),
        "Living area": "Not available" if living_area in (None, "") else f"{float(living_area):,.0f} sq ft",
        "Year built": whole_value("year_built"),
        "Condition": value("condition"),
        "Bedrooms": whole_value("bedrooms"),
        "Bathrooms": whole_value("bathrooms"),
    }

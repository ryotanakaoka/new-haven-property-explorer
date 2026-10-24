"""Filtering helpers for the public sales explorer."""
from __future__ import annotations
from datetime import date, datetime
import re

def filter_sales(rows, property_types=None, start_date=None, end_date=None, min_price=None, max_price=None):
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
    """Conservative parser; unspecified filters remain unset."""
    result = {"property_types": [], "min_price": None, "max_price": None, "start_date": None, "end_date": None}
    for typ in known_types:
        if typ.lower() in text.lower(): result["property_types"].append(typ)
    prices = [int(x.replace(',', '')) for x in re.findall(r"\$?([\d]{3,}(?:,\d{3})*)", text)]
    if "under" in text.lower() or "below" in text.lower():
        if prices: result["max_price"] = prices[0]
    elif "over" in text.lower() or "above" in text.lower():
        if prices: result["min_price"] = prices[0]
    elif len(prices) >= 2:
        result["min_price"], result["max_price"] = min(prices[:2]), max(prices[:2])
    return result

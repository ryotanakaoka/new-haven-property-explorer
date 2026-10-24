"""Python-only deal screening calculations."""
from __future__ import annotations

def screen_deal(asking_price: float, annual_rent: float, annual_expenses: float, address: str = "", unit_count: int = 0) -> dict:
    if asking_price <= 0 or annual_rent < 0 or annual_expenses < 0:
        raise ValueError("asking price must be positive; rent and expenses must be non-negative")
    noi = annual_rent - annual_expenses
    return {"address": address.strip(), "unit_count": int(unit_count), "asking_price": asking_price, "annual_rent": annual_rent, "annual_expenses": annual_expenses, "noi": noi, "cap_rate": noi / asking_price}

def compare_to_comps(deal: dict, comps: list[dict]) -> dict:
    prices = [row["sale_price"] for row in comps if row.get("sale_price") is not None and row["sale_price"] > 0]
    median = sorted(prices)[len(prices) // 2] if prices else None
    return {"sale_count": len(prices), "median_sale_price": median, "asking_vs_median": deal["asking_price"] / median if median else None}


def final_screen_verdict(deal: dict, hurdle_rate: float, coverage: dict) -> dict:
    """Return a preliminary data-quality/due-diligence gate, never an investment recommendation."""
    if not 0 <= hurdle_rate <= 1:
        raise ValueError("hurdle rate must be between 0% and 100%")
    if deal["unit_count"] <= 0:
        return {"verdict": "INSUFFICIENT DATA", "reason": "Unit count is missing or invalid."}
    if not coverage.get("enough"):
        return {"verdict": "INSUFFICIENT DATA", "reason": "There are not enough verified eligible comparable sales."}
    types = set(coverage.get("property_types", []))
    if deal["unit_count"] == 1 and types == {"Apartments"}:
        return {"verdict": "INSUFFICIENT DATA", "reason": "The one-unit subject is being compared only with Apartment records, which are not a sufficiently matched property basis."}
    if deal["cap_rate"] >= hurdle_rate:
        return {"verdict": "ADVANCE TO DUE DILIGENCE", "reason": "The Python-calculated cap rate meets the entered hurdle and verified comparable coverage is sufficient."}
    return {"verdict": "PASS", "reason": "The Python-calculated cap rate is below the entered hurdle."}

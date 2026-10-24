"""Deterministic, synthetic commercial real-estate cash-flow calculator."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Literal


@dataclass(frozen=True)
class StressInputs:
    annual_rent: float
    operating_expenses: float
    loan_balance: float
    current_interest_rate: float
    lease_expiry_year: int
    loan_maturity_year: int
    vacancy_months_after_expiry: int
    refinancing_rate: float


def validate_inputs(i: StressInputs) -> None:
    nonnegative = {
        "annual_rent": i.annual_rent,
        "operating_expenses": i.operating_expenses,
        "loan_balance": i.loan_balance,
        "current_interest_rate": i.current_interest_rate,
        "refinancing_rate": i.refinancing_rate,
    }
    for name, value in nonnegative.items():
        if value < 0:
            raise ValueError(f"{name} must be non-negative")
    if i.annual_rent == 0:
        raise ValueError("annual_rent must be greater than zero")
    if not 0 <= i.vacancy_months_after_expiry <= 12:
        raise ValueError("vacancy_months_after_expiry must be between 0 and 12")
    if i.lease_expiry_year < 2000 or i.loan_maturity_year < 2000:
        raise ValueError("expiry and maturity years must be 2000 or later")


def calculate_cash_flows(i: StressInputs, scenario: Literal["base", "downside"] = "base") -> list[dict]:
    """Return annual figures; no principal payments or taxes are modeled."""
    validate_inputs(i)
    if scenario not in ("base", "downside"):
        raise ValueError("scenario must be 'base' or 'downside'")
    end_year = max(i.lease_expiry_year, i.loan_maturity_year) + 2
    rows = []
    for year in range(min(i.lease_expiry_year, i.loan_maturity_year) - 2, end_year + 1):
        rent = i.annual_rent
        # The stated vacancy period is the following lease year only. Rent
        # returns to the contractual annual amount after that one-year window.
        if scenario == "downside" and year == i.lease_expiry_year + 1:
            rent *= max(0, 12 - i.vacancy_months_after_expiry) / 12
        rate = i.current_interest_rate if year < i.loan_maturity_year else i.refinancing_rate
        income = rent
        noi = income - i.operating_expenses
        interest = i.loan_balance * rate
        rows.append({
            "year": year,
            "rental_income": round(income, 2),
            "operating_expenses": round(i.operating_expenses, 2),
            "noi": round(noi, 2),
            "interest_rate": rate,
            "interest_expense": round(interest, 2),
            "cash_flow_after_interest": round(noi - interest, 2),
            "lease_expiry": year == i.lease_expiry_year,
            "loan_maturity": year == i.loan_maturity_year,
            "overlap": year == i.lease_expiry_year == i.loan_maturity_year,
            "vacancy_effect": scenario == "downside" and year == i.lease_expiry_year + 1,
        })
    return rows


def calculator_tool(**kwargs) -> dict:
    """Agent-facing tool: calculate both scenarios from validated inputs."""
    inputs = StressInputs(**kwargs)
    return {"inputs": asdict(inputs), "base": calculate_cash_flows(inputs, "base"), "downside": calculate_cash_flows(inputs, "downside")}


def break_even_refinancing_rate(i: StressInputs, scenario: Literal["base", "downside"] = "base") -> float:
    """Return the highest refinance rate keeping every post-refi year non-negative.

    This is a model result based on the entered assumptions. It reuses the
    existing calculator's NOI values and solves NOI - loan_balance * rate >= 0
    for the worst year after loan maturity.
    """
    validate_inputs(i)
    rows = calculate_cash_flows(i, scenario)
    post_refinancing = [row for row in rows if row["year"] >= i.loan_maturity_year]
    if not post_refinancing:
        raise ValueError("no post-refinancing years available")
    if i.loan_balance == 0:
        return float("inf")
    return round(min(row["noi"] / i.loan_balance for row in post_refinancing), 6)

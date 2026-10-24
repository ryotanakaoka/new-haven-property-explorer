"""Optional PydanticAI + Portkey explanation layer. Calculations remain deterministic."""
from __future__ import annotations
import os
import re
from typing import Any
from pathlib import Path
from dotenv import load_dotenv
from dataclasses import asdict
from calculator import StressInputs, calculate_cash_flows

load_dotenv(Path.cwd() / ".env")
load_dotenv(Path.cwd().parent / ".env")

INVENTION_RE = re.compile(r"\b(invent|make up|fabricat|ignore the calculator|pretend)\b", re.I)
currency_re = re.compile(r"\$(?=\d)")
SCENARIO_FIELDS = (
    "annual_rent", "operating_expenses", "loan_balance", "current_interest_rate",
    "lease_expiry_year", "loan_maturity_year", "vacancy_months_after_expiry", "refinancing_rate",
)


def blocks_invention_request(prompt: str) -> bool:
    return bool(INVENTION_RE.search(prompt))


def format_explanation_for_display(text: str) -> str:
    """Avoid Markdown math parsing while preserving the agent's wording."""
    return currency_re.sub("USD ", text)


def extract_stated_assumptions(text: str, base_inputs: StressInputs) -> dict:
    """Extract only explicit scenario values; never fill or calculate values."""
    patterns = {
        "annual_rent": r"(?:annual\s+)?rent[^$\d]*(?:\$\s*)?([\d,]+)",
        "operating_expenses": r"(?:operating\s+)?expenses?[^$\d]*(?:\$\s*)?([\d,]+)",
        "loan_balance": r"loan(?:\s+balance)?[^$\d]*(?:\$\s*)?([\d,]+)",
        "current_interest_rate": r"current(?:\s+interest)?\s+rate[^\d]*(\d+(?:\.\d+)?)\s*%",
        "lease_expiry_year": r"lease[^\d]*(?:expiry|expires?)[^\d]*(20\d{2})",
        "loan_maturity_year": r"loan[^\d]*(?:maturity|matures?)[^\d]*(20\d{2})",
        "vacancy_months_after_expiry": r"vacancy[^\d]*(\d+)\s*months?",
        "refinancing_rate": r"refinanc(?:e|ing)[^\d]*(\d+(?:\.\d+)?)\s*%",
    }
    stated = {}
    for field, pattern in patterns.items():
        match = re.search(pattern, text, re.I)
        if match:
            raw = match.group(1).replace(",", "")
            stated[field] = float(raw) if "rate" in field else int(raw)
            if "rate" in field:
                stated[field] /= 100
    proposed = asdict(base_inputs)
    proposed.update(stated)
    return {"stated": stated, "proposed": proposed, "missing": [f for f in SCENARIO_FIELDS if f not in stated]}


def calculate_confirmed_scenario(proposed: dict, base_inputs: StressInputs) -> dict:
    """Run the existing Python calculator only for user-confirmed inputs."""
    scenario_inputs = StressInputs(**proposed)
    return {
        "scenario_inputs": asdict(scenario_inputs),
        "scenario": calculate_cash_flows(scenario_inputs, "downside"),
        "base": calculate_cash_flows(base_inputs, "base"),
    }


def usage_cost(usage: Any) -> dict:
    if not usage:
        return {"available": False, "message": "Usage data unavailable."}
    def get(*names):
        for name in names:
            value = getattr(usage, name, None) if not isinstance(usage, dict) else usage.get(name)
            if value is not None:
                return int(value)
        return 0
    inp, cached, cache_write, out = (get("input_tokens", "prompt_tokens"), get("cached_input_tokens", "cache_read_tokens"), get("cache_write_tokens"), get("output_tokens", "completion_tokens"))
    cost = (inp*.10 + cached*.01 + cache_write*.125 + out*.50) / 1_000_000
    return {"available": True, "input_tokens": inp, "cached_input_tokens": cached, "cache_write_tokens": cache_write, "output_tokens": out, "cost_usd": round(cost, 6)}


def _redact_error(exc: Exception, secret: str | None = None) -> str:
    message = str(exc).replace(secret, "[REDACTED]") if secret else str(exc)
    return message[:500] or type(exc).__name__


async def explain_with_agent(prompt: str, calculator_result: dict) -> tuple[str, dict]:
    if blocks_invention_request(prompt):
        return "I can't invent or alter figures. Please ask about the calculator results.", {"available": False, "message": "Request blocked by validation."}
    try:
        from openai import AsyncOpenAI
        from pydantic_ai import Agent
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        portkey_key = os.getenv("PORTKEY_API_KEY")
        if not portkey_key:
            return "Agent unavailable: PORTKEY_API_KEY is missing from .env in this folder or its parent. The deterministic results above are still valid.", {"available": False, "message": "PORTKEY_API_KEY is not configured; usage unavailable."}
        # Portkey exposes an OpenAI-compatible endpoint. The key is used only
        # in memory and is never included in the UI or returned error text.
        openai_client = AsyncOpenAI(
            api_key=portkey_key,
            base_url="https://api.portkey.ai/v1",
            default_headers={"x-portkey-api-key": portkey_key},
        )
        model = OpenAIChatModel("gpt-6-luna", provider=OpenAIProvider(openai_client=openai_client))
        def calculator() -> dict:
            """Return the deterministic calculation; never generate figures."""
            return calculator_result
        agent = Agent(
            model,
            system_prompt="Explain only the supplied calculator results. Call the calculator before answering. Never invent figures. State that principal and taxes are excluded.",
            tools=[calculator],
            # gpt-6-luna's Portkey deployment requires reasoning to be off
            # when function tools are sent through /v1/chat/completions.
            model_settings={"openai_reasoning_effort": "none"},
        )
        result = await agent.run(prompt)
        usage_value = getattr(result, "usage", None)
        usage = usage_value() if callable(usage_value) else usage_value
        return result.output, usage_cost(usage)
    except Exception as exc:
        return f"Agent request failed: {_redact_error(exc, locals().get('portkey_key'))}. The deterministic results above are still valid.", {"available": False, "message": "Usage data unavailable.", "error": _redact_error(exc, locals().get('portkey_key'))}

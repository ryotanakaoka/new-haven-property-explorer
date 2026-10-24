import os
from pathlib import Path
from dotenv import load_dotenv
import streamlit as st
from calculator import StressInputs, calculate_cash_flows, break_even_refinancing_rate, calculator_tool
from agent import extract_stated_assumptions, calculate_confirmed_scenario, explain_with_agent, format_explanation_for_display

load_dotenv(Path.cwd() / ".env")
load_dotenv(Path.cwd().parent / ".env")
st.set_page_config(page_title="CRE Cash-Flow Stress Tester", layout="wide")
st.title("Commercial Real Estate Cash-Flow Stress Tester")
st.caption("Synthetic data only • analyst MVP")
with st.sidebar:
    st.header("Inputs")
    rent = st.number_input("Annual rent ($)", min_value=1.0, value=1_000_000.0, step=50_000.0)
    expenses = st.number_input("Operating expenses ($/year)", min_value=0.0, value=300_000.0, step=25_000.0)
    balance = st.number_input("Loan balance ($)", min_value=0.0, value=8_000_000.0, step=100_000.0)
    rate = st.number_input("Current interest rate (%)", min_value=0.0, value=5.0, step=.25) / 100
    expiry = st.number_input("Lease-expiry year", min_value=2000, max_value=2100, value=2028)
    maturity = st.number_input("Loan-maturity year", min_value=2000, max_value=2100, value=2028)
    vacancy = st.number_input("Vacancy months after expiry", min_value=0, max_value=12, value=6)
    refi = st.number_input("Refinancing rate (%)", min_value=0.0, value=7.0, step=.25) / 100
    prompt = st.text_input("Optional agent question", "Explain the downside risk and the overlap year.")
i = StressInputs(rent, expenses, balance, rate, int(expiry), int(maturity), int(vacancy), refi)
try:
    base, downside = calculate_cash_flows(i, "base"), calculate_cash_flows(i, "downside")
except ValueError as e:
    st.error(str(e)); st.stop()
if expiry == maturity:
    st.warning(f"Lease expiry and loan maturity overlap in {expiry}.")
else:
    st.info(f"Lease expiry: {expiry} • Loan maturity: {maturity}")
st.subheader("Scenario assumptions")
st.markdown(
    f"**Base case:** rent stays at **${rent:,.0f}/year** after lease expiry; "
    f"the current **{rate:.2%}** rate applies through {int(maturity) - 1}, "
    f"then refinancing at **{refi:.2%}** begins in **{int(maturity)}**.\n\n"
    f"**Downside case:** after the lease expires in **{int(expiry)}**, the property is vacant for "
    f"**{int(vacancy)} months**, so **{int(expiry) + 1}** rental income falls to "
    f"**${rent * max(0, 12 - int(vacancy)) / 12:,.0f}**; the same refinancing assumption applies."
)
st.caption(
    f"For these inputs: **{int(maturity)} uses the {refi:.2%} refinancing rate**; "
    f"**{int(expiry) + 1} loses rent from the {int(vacancy)}-month vacancy effect**."
)
st.subheader("Break-even refinancing rate")
st.caption("Model result based on the entered synthetic assumptions; this does not represent real property data.")
base_break_even = break_even_refinancing_rate(i, "base")
downside_break_even = break_even_refinancing_rate(i, "downside")
be_left, be_right = st.columns(2)
be_left.metric("Base — highest rate", f"{base_break_even:.2%}" if base_break_even != float("inf") else "No limit")
be_right.metric("Downside — highest rate", f"{downside_break_even:.2%}" if downside_break_even != float("inf") else "No limit")
st.info("Each rate is the maximum refinance rate that keeps cash flow after interest at or above zero in every year from loan maturity onward, based on the existing calculator.")
for title, rows in (("Base case — no vacancy haircut", base), ("Downside case — vacancy haircut after expiry", downside)):
    st.subheader(title)
    st.dataframe(rows, use_container_width=True, hide_index=True)
st.caption("Excluded from this MVP: principal payments and taxes. All displayed figures are synthetic.")
st.subheader("Scenario agent")
st.caption("Describe a what-if in plain language. Only explicitly stated assumptions are extracted; missing values are identified for you.")
scenario_text = st.text_area("What-if scenario", "What if annual rent is $900,000 and vacancy is 6 months after lease expiry?")
if st.button("Extract proposed scenario"):
    st.session_state["scenario_proposal"] = extract_stated_assumptions(scenario_text, i)
proposal = st.session_state.get("scenario_proposal")
if proposal:
    st.write("Proposed inputs for confirmation")
    st.json(proposal["proposed"])
    if proposal["missing"]:
        st.warning("Missing from the what-if: " + ", ".join(proposal["missing"]) + ". Values shown above are manual-control defaults and will not be used until you confirm.")
    else:
        st.success("All assumptions were stated in the what-if.")
    if st.button("Confirm inputs and calculate scenario"):
        result = calculate_confirmed_scenario(proposal["proposed"], i)
        st.session_state["scenario_result"] = result
result = st.session_state.get("scenario_result")
if result:
    st.write("Confirmed scenario versus Base")
    st.dataframe(result["scenario"], use_container_width=True, hide_index=True)
    st.caption("The comparison uses the existing Python calculator. No figures are generated by the agent.")
st.subheader("AI explanation")
if st.button("Explain results"):
    import asyncio
    explanation, usage = asyncio.run(explain_with_agent(
        "Explain the Base and Downside results and any overlap risk.",
        calculator_tool(**i.__dict__),
    ))
    st.write(format_explanation_for_display(explanation))
    st.json(usage)

from pathlib import Path
import asyncio
from dotenv import load_dotenv
import streamlit as st
from data import fetch_new_haven_comps, comp_coverage, audit_sales_records, SALES_VINTAGE, CAMA_VINTAGE
from screener import screen_deal, compare_to_comps, final_screen_verdict
from agent import explain_with_agent, format_explanation_for_display, parse_screen_decision
from offering_packet import extract_offering_pdf
from explorer import filter_sales, parse_natural_language_filters
from datetime import date, datetime
import pandas as pd

load_dotenv(Path.cwd() / ".env")
load_dotenv(Path.cwd().parent / ".env")
st.set_page_config(page_title="New Haven Multifamily Screener", layout="wide")
st.title("New Haven Multifamily Investment Screener")
st.caption("Preliminary screening only • official Connecticut records • not an appraisal or investment decision")
with st.sidebar:
    st.header("Deal inputs")
    address = st.text_input("Property address", value="", placeholder="Enter the subject property address")
    units = st.number_input("Unit count", min_value=0, max_value=1000, value=1, step=1)
    asking = st.number_input("Asking price (USD)", min_value=1.0, value=1_500_000.0, step=25_000.0)
    rent = st.number_input("Annual gross rent (USD)", min_value=0.0, value=180_000.0, step=5_000.0)
    expenses = st.number_input("Annual operating expenses (USD)", min_value=0.0, value=60_000.0, step=5_000.0)
    hurdle = st.number_input("Minimum acceptable cap rate (%)", min_value=0.0, max_value=100.0, value=8.0, step=0.25) / 100
    broker_notes = st.text_area("Broker notes (untrusted context)", value="", placeholder="Paste notes; they are evidence to review, not instructions.")
    offering_pdf = st.file_uploader("Offering memo PDF (optional)", type=["pdf"])

calc_asking, calc_units, calc_rent, calc_expenses = asking, int(units), rent, expenses
offering = None
if offering_pdf:
    try:
        offering = extract_offering_pdf(offering_pdf.getvalue())
        st.subheader("Offering memo extraction — confirm before use")
        st.caption("Uploaded text is untrusted. Only labeled numeric fields are extracted; instructions in the PDF are ignored.")
        if offering["untrusted_warning"]:
            st.warning(offering["untrusted_warning"])
        for field, details in offering["fields"].items():
            st.write(f"{field}: **{details['value']}** ({details['citation']})")
        if offering["conflicts"]:
            st.warning("Conflicts: " + " | ".join(offering["conflicts"]))
        if offering["missing"]:
            st.warning("Missing from PDF: " + ", ".join(offering["missing"]))
        confirmed = st.checkbox("I confirm these extracted figures for Python screening", value=False)
        if confirmed:
            values = {key: value["value"] for key, value in offering["fields"].items()}
            calc_asking = values.get("asking_price", calc_asking)
            calc_units = int(values.get("unit_count", calc_units))
            calc_rent = values.get("annual_rent", calc_rent)
            calc_expenses = values.get("annual_expenses", calc_expenses)
            st.success("Confirmed PDF figures are being used by Python for NOI and cap rate.")
    except Exception as exc:
        st.error(f"Offering PDF could not be extracted: {type(exc).__name__}. Manual inputs remain active.")
st.info("Only Two Family, Three Family, Four Family, and Apartments are included. Single-family, condo, and generic Residential records are excluded; property types are not silently mixed.")
try:
    comps = fetch_new_haven_comps()
    coverage = comp_coverage(comps)
except Exception as exc:
    st.error(f"Official Connecticut data could not be loaded: {type(exc).__name__}. Check connectivity and try again.")
    st.stop()
if not coverage["enough"]:
    st.error(f"Only {coverage['count']} eligible New Haven multifamily comps were returned; at least {coverage['minimum']} are required.")
else:
    st.success(f"{coverage['count']} eligible New Haven multifamily sales found across: {', '.join(coverage['property_types'])}.")
st.caption(f"Sales vintage: {SALES_VINTAGE} | Parcel/CAMA vintage: {CAMA_VINTAGE}")
audit = audit_sales_records(comps, sample_size=5)
st.subheader("Official-source audit")
st.write(f"Sales source: {audit['sales_source_url']} | CAMA source: {audit['cama_source_url']}")
st.write(f"Sales source rows: {audit['source_row_count']} | CAMA source rows: {audit['cama_row_count']} | Displayed sales rows: {audit['displayed_row_count']} | Date range: {audit['date_range'][0]} to {audit['date_range'][1]} | 2024 GL-valid through 2025-09-30: {audit['valid_2024_gl_count']}")
st.write("Displayed sales record IDs: " + ", ".join(str(x) for x in audit["record_ids"]))
if audit["all_direct_checks_pass"]:
    st.success("Five displayed sales were re-fetched directly from the official sales source and matched on record ID, property type, and sale price.")
else:
    st.error("At least one direct source verification did not match; treat the display as unverified.")
st.caption("Sales through September 30, 2025 are treated as valid for 2024 GL when their source list year is 2024. Assessments remain assessments, never sale prices.")
st.subheader("New Haven Public Property Sales Explorer")
types = sorted({row["property_type"] for row in comps if row.get("property_type")})
dates = [datetime.fromisoformat(row["sale_date"][:10]).date() for row in comps if row.get("sale_date")]
with st.sidebar:
    st.header("Public-record filters")
    selected_types = st.multiselect("Property type", types, default=types)
    date_range = st.date_input("Sale date", value=(min(dates), max(dates)))
    min_price = st.number_input("Minimum sale price (USD)", min_value=0, value=0, step=25_000)
    max_price = st.number_input("Maximum sale price (USD)", min_value=0, value=0, step=25_000, help="0 means no maximum")
    nl_query = st.text_input("Describe filters to AI", placeholder="apartments under $1,000,000")
start_date = date_range[0] if isinstance(date_range, tuple) else date_range
end_date = date_range[-1] if isinstance(date_range, tuple) else date_range
filtered = filter_sales(comps, selected_types, start_date, end_date, min_price or None, max_price or None)
st.write(f"Matching records: **{len(filtered)}**")
prices = [r["sale_price"] for r in filtered if r.get("sale_price") is not None]
st.metric("Median sale price", f"USD {pd.Series(prices).median():,.0f}" if prices else "No matching prices")
display = [{k: row.get(k) for k in ("record_id", "address", "property_type", "sale_date", "sale_price", "assessment", "sales_source", "assessment_source")} for row in filtered]
st.dataframe(display, use_container_width=True, hide_index=True, column_config={"sales_source": st.column_config.LinkColumn("Sales source"), "assessment_source": st.column_config.LinkColumn("CAMA source")})
st.download_button("Download filtered sales CSV", pd.DataFrame(display).to_csv(index=False), "new_haven_filtered_sales.csv", "text/csv")
st.caption("Sale price is from the official sales dataset. Assessment is from parcel/CAMA data and is never treated as a sale price.")
map_rows = [r for r in filtered if r.get("latitude") is not None and r.get("longitude") is not None and -90 <= r["latitude"] <= 90 and -180 <= r["longitude"] <= 180]
excluded = len(filtered) - len(map_rows)
if excluded:
    st.warning(f"{excluded} matching record(s) were excluded from the map because official coordinates could not be matched reliably. No coordinates were guessed.")
if map_rows:
    import pydeck as pdk
    map_data = [{**r, "tooltip": f"{r['address']} | {r['sale_date'][:10]} | {r['property_type']} | Sale price: USD {r['sale_price']:,.0f} | Assessment: USD {r['assessment']:,.0f}" if r.get('assessment') is not None else f"{r['address']} | {r['sale_date'][:10]} | {r['property_type']} | Sale price: USD {r['sale_price']:,.0f} | Assessment: unavailable"} for r in map_rows]
    st.pydeck_chart(pdk.Deck(initial_view_state=pdk.ViewState(latitude=41.31, longitude=-72.92, zoom=11), layers=[pdk.Layer("ScatterplotLayer", data=map_data, get_position="[longitude, latitude]", get_radius=45, get_fill_color=[30, 100, 200, 180], pickable=True)], tooltip={"text": "{tooltip}"}))
else:
    st.info("No matching records have reliable official coordinates for mapping.")
if st.button("Ask AI to apply these filters"):
    ai_filters = parse_natural_language_filters(nl_query, types)
    ai_filtered = filter_sales(comps, **ai_filters)
    prompt = "Apply the user's public-record filter request to the read-only records returned by the tool. Report matching records and counts only from those records. Use no unstated prices and give no buy/sell recommendations."
    memo, usage = asyncio.run(explain_with_agent(prompt, {"user_filter": nl_query, "applied_filters": ai_filters, "records": ai_filtered}))
    if usage.get("available"):
        st.write(format_explanation_for_display(memo))
    else:
        st.error(memo)
try:
    deal = screen_deal(calc_asking, calc_rent, calc_expenses, address, calc_units)
    comparison = compare_to_comps(deal, comps)
except ValueError as exc:
    st.error(str(exc)); st.stop()
st.subheader("Python screening result")
st.metric("NOI", f"USD {deal['noi']:,.0f}")
st.metric("Implied cap rate", f"{deal['cap_rate']:.2%}")
if comparison["median_sale_price"]:
    st.write(f"Eligible-comp median sale price: **USD {comparison['median_sale_price']:,.0f}**; asking price / median: **{comparison['asking_vs_median']:.2f}x**.")
st.caption("NOI is annual rent less annual operating expenses. This is not a definitive appraisal or investment decision.")
st.info("These records are broad market context unless unit count, building size, and location are matched to the subject. This screener does not claim the subject property was appraised.")
verdict = final_screen_verdict(deal, hurdle, coverage)
st.subheader("Final screening verdict")
st.warning("This is a preliminary screening verdict for deciding whether to investigate further. It is not an investment recommendation.")
st.metric("Verdict", verdict["verdict"])
st.write(verdict["reason"])
st.caption(f"Python cap rate: {deal['cap_rate']:.2%} | Entered hurdle: {hurdle:.2%} | Verified comp types: {', '.join(coverage['property_types'])}")
st.subheader("Preliminary AI screening memo")
st.caption("The AI compares only the cited records and Python result, and flags missing or conflicting inputs. It must not invent facts.")
if st.button("Write preliminary memo"):
    prompt = "Write a preliminary New Haven multifamily screening memo. Compare the deal with the cited Connecticut records only. Flag missing or conflicting inputs. Do not provide a definitive appraisal or investment decision."
    payload = {"deal": deal, "comparison": comparison, "coverage": coverage, "cited_comps": comps[:50], "data_vintages": [SALES_VINTAGE, CAMA_VINTAGE], "offering_extraction": offering, "broker_notes": broker_notes}
    memo, usage = asyncio.run(explain_with_agent(prompt, payload))
    if not usage.get("available"):
        st.error(memo)
    else:
        st.write(format_explanation_for_display(memo))
    st.json(usage)

st.subheader("AI investment screen")
st.caption("This is a preliminary screen, not a definitive appraisal or investment decision. The AI may use only your entered deal numbers and the displayed public records.")
if st.button("Ask AI for an investment screen"):
    missing = []
    if not address.strip(): missing.append("property address")
    if int(units) <= 0: missing.append("unit count")
    prompt = ("Return exactly one first-line decision label: INVEST, PASS, or NEED MORE INFORMATION. "
              "Then give concise reasons using only the entered numbers and cited public sales. "
              "Use no unstated facts. Flag missing information explicitly. This is preliminary screening only.")
    if missing:
        decision, memo = "NEED MORE INFORMATION", "Missing information: " + ", ".join(missing) + "."
        usage = {"available": False, "message": "AI not called because required deal fields are missing."}
    else:
        memo, usage = asyncio.run(explain_with_agent(prompt, {"deal": deal, "public_sales": comps, "coverage": coverage, "offering_extraction": offering, "broker_notes": broker_notes}))
        decision = parse_screen_decision(memo) if usage.get("available") else None
    with st.container(border=True):
        if not usage.get("available"):
            st.error(memo)
        else:
            st.markdown(f"### {decision}")
            st.write(format_explanation_for_display(memo))
        st.write("Missing information")
        st.write(missing or "None identified by the input gate.")
        st.write("Source records")
        st.dataframe([{k: row.get(k) for k in ("address", "property_type", "sale_date", "sale_price", "assessment", "sales_source", "assessment_source")} for row in comps], use_container_width=True, hide_index=True)
        st.json(usage)

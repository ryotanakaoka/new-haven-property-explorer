from pathlib import Path
import asyncio
from datetime import datetime
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from data import fetch_new_haven_comps, comp_coverage, audit_sales_records, SALES_VINTAGE, CAMA_VINTAGE
from explorer import filter_sales, search_request_result, combine_search_filters, build_ai_records_payload, build_sales_analysis_payload
from agent import explain_with_agent, format_explanation_for_display

load_dotenv(Path.cwd() / ".env")
load_dotenv(Path.cwd().parent / ".env")
st.set_page_config(page_title="New Haven Public Property Sales Explorer", layout="wide")
st.title("New Haven Public Property Sales Explorer")
st.subheader("Explore official New Haven property sales by asking factual search questions.")
st.caption("Public-record explorer only • no investment recommendations • assessments are not sale prices")
with st.expander("How to use", expanded=True):
    st.markdown("**1.** Type a search request such as *apartments under USD 1,000,000*.\n\n**2.** Review the Python-applied filters and matching source records.\n\n**3.** Use the map, median, table, and CSV export. AI answers only from the matching public records and never invents records.")

try:
    comps = fetch_new_haven_comps()
    coverage = comp_coverage(comps)
except Exception as exc:
    st.error(f"Official Connecticut data could not be loaded: {type(exc).__name__}.")
    st.stop()
st.success(f"Loaded records: {len(comps)} across: {', '.join(coverage['property_types'])}.")
st.caption(f"Sales vintage: {SALES_VINTAGE} | Parcel/CAMA vintage: {CAMA_VINTAGE}")
audit = audit_sales_records(comps, sample_size=5)
with st.expander("Official-source audit"):
    st.write(f"Sales source: {audit['sales_source_url']} | CAMA source: {audit['cama_source_url']}")
    st.write(f"Sales source rows: {audit['source_row_count']} | CAMA source rows: {audit['cama_row_count']} | Loaded sales rows: {audit['displayed_row_count']} | Date range: {audit['date_range'][0]} to {audit['date_range'][1]}")
    st.write("Record IDs: " + ", ".join(str(x) for x in audit["record_ids"]))
    if audit["all_direct_checks_pass"]: st.success("Five displayed sales were directly verified against the official source.")
    else: st.error("A direct source verification failed.")

types = sorted({r["property_type"] for r in comps if r.get("property_type")})
dates = [datetime.fromisoformat(r["sale_date"][:10]).date() for r in comps if r.get("sale_date")]
with st.sidebar:
    st.header("Search filters")
    selected_types = st.multiselect("Property type", types, default=types)
    date_range = st.date_input("Sale date", value=(min(dates), max(dates)))
    min_price = st.number_input("Minimum sale price (USD)", min_value=0, value=0, step=25_000)
    max_price = st.number_input("Maximum sale price (USD; 0 = no maximum)", min_value=0, value=0, step=25_000)

st.subheader("Filter public sales")
chat = st.text_area("Natural-language filter (optional)", placeholder="Show apartments under USD 1,000,000", height=80)
sidebar_filters = {"property_types": selected_types, "start_date": date_range[0] if isinstance(date_range, tuple) else date_range, "end_date": date_range[-1] if isinstance(date_range, tuple) else date_range, "min_price": min_price or None, "max_price": max_price or None}
if st.button("Apply search"):
    search_result = search_request_result(chat, types)
    parsed = search_result["filters"]
    if search_result["stop"]:
        st.error(search_result["message"])
        st.stop()
    else:
        parsed = combine_search_filters(sidebar_filters, parsed)
        filtered = filter_sales(comps, **{k: parsed[k] for k in ("property_types", "start_date", "end_date", "min_price", "max_price")})
else:
    if chat:
        search_result = search_request_result(chat, types)
        if search_result["stop"]:
            st.error(search_result["message"])
            st.stop()
        parsed = combine_search_filters(sidebar_filters, search_result["filters"])
    else:
        parsed = sidebar_filters
    filtered = filter_sales(comps, **parsed)
st.write("Python-applied filters:", parsed)
st.write(f"Matching source records: **{len(filtered)}**")
prices = [r["sale_price"] for r in filtered if r.get("sale_price") is not None]
st.metric("Median sale price", f"USD {pd.Series(prices).median():,.0f}" if prices else "No matching prices")
table = [{k: r.get(k) for k in ("record_id", "address", "property_type", "sale_date", "sale_price", "assessment", "sales_source", "assessment_source")} for r in filtered]
st.dataframe(table, use_container_width=True, hide_index=True, column_config={"sales_source": st.column_config.LinkColumn("Sales source"), "assessment_source": st.column_config.LinkColumn("CAMA source")})
st.download_button("Download filtered sales CSV", pd.DataFrame(table).to_csv(index=False), "new_haven_filtered_sales.csv", "text/csv")
st.caption("Sale price and assessment are separate official fields. No assessment is treated as a sale price.")
map_rows = [r for r in filtered if r.get("latitude") is not None and r.get("longitude") is not None and -90 <= r["latitude"] <= 90 and -180 <= r["longitude"] <= 180]
st.write(f"{len(map_rows)} of {len(filtered)} matching records mapped")
if len(map_rows) < len(filtered): st.warning(f"{len(filtered)-len(map_rows)} record(s) excluded from the map because reliable official coordinates were unavailable; no coordinates were guessed.")
if map_rows:
    import pydeck as pdk
    map_data = [{**r, "tooltip": f"{r['address']} | {r['sale_date'][:10]} | {r['property_type']} | Sale price: USD {r['sale_price']:,.0f} | Assessment: USD {r['assessment']:,.0f}" if r.get('assessment') is not None else f"{r['address']} | {r['sale_date'][:10]} | {r['property_type']} | Sale price: USD {r['sale_price']:,.0f} | Assessment: unavailable"} for r in map_rows]
    st.pydeck_chart(pdk.Deck(initial_view_state=pdk.ViewState(latitude=41.31, longitude=-72.92, zoom=11), layers=[pdk.Layer("ScatterplotLayer", data=map_data, get_position="[longitude, latitude]", get_radius=90, get_fill_color=[255, 215, 0, 230], stroked=True, get_line_color=[20, 20, 20, 255], line_width_min_pixels=3, pickable=True)], tooltip={"text": "{tooltip}"}))
else: st.info("No matching records have reliable official coordinates for mapping.")

st.subheader("Ask a factual question about matching records")
analysis_question = st.text_area("Question", placeholder="What were the highest sale prices, and which records support them?", height=80)
if st.button("Ask AI about matching records"):
    prompt = "Answer only from the Python analysis and read-only public sales records supplied by the application. Explain the exact result concisely, cite record IDs and source links, and say when the data cannot answer. Do not invent facts or make recommendations."
    try:
        if len(filtered) == len(comps):
            st.error("Apply an effective property type, date, price, or natural-language filter before asking AI; sending all records is disabled.")
            st.stop()
        if not analysis_question.strip():
            st.error("Enter a factual question about the matching records before asking AI.")
            st.stop()
        analysis_payload = build_sales_analysis_payload(filtered, analysis_question)
        if not analysis_payload["python_analysis"]["supported"]:
            st.error(analysis_payload["python_analysis"]["message"])
            st.stop()
        compact_count = len(analysis_payload["python_analysis"].get("records", []))
        st.caption(f"Records sent to AI: {compact_count} compact analysis records (from {len(filtered)} matching records)")
        memo, usage = asyncio.run(explain_with_agent(prompt + " Cite the supplied record IDs and source links.\nUser question: " + analysis_question, {"filters": parsed, **analysis_payload}))
        if usage.get("available"): st.write(format_explanation_for_display(memo))
        else: st.error(memo)
        st.json(usage)
    except ValueError as exc:
        st.error(str(exc) + ". Narrow the filters before asking AI.")

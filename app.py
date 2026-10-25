from pathlib import Path
import asyncio
from datetime import datetime
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from data import fetch_new_haven_comps, load_sample_comps, comp_coverage, audit_sales_records, SALES_VINTAGE, CAMA_VINTAGE
from explorer import filter_sales, search_request_result, combine_search_filters, filter_override_messages, build_sales_analysis_payload, analysis_records_status, readable_sale_date, format_cama_details, ai_request_guard, MAX_AI_CALLS_PER_SESSION
from agent import explain_with_agent, format_explanation_for_display, format_usage_summary

load_dotenv(Path.cwd() / ".env")
load_dotenv(Path.cwd().parent / ".env")
st.set_page_config(page_title="New Haven Public Property Sales Explorer", layout="wide")
st.session_state.setdefault("ai_calls_made", 0)
st.session_state.setdefault("ai_reported_spend_usd", 0.0)


@st.cache_data(ttl=3600, show_spinner="Loading and caching official Connecticut records…")
def load_live_comps_cached():
    return fetch_new_haven_comps()


@st.cache_data(ttl=3600, show_spinner="Checking the official sales source…")
def audit_sales_cached(rows, sample_size=5):
    return audit_sales_records(rows, sample_size=sample_size)
st.markdown("""
<style>
:root {
    --nh-navy: #12304a;
    --nh-blue: #e8f2f8;
    --nh-blue-strong: #2f6f95;
    --nh-gold: #b08a3e;
    --nh-ink: #17232d;
}
body, .stApp { color: var(--nh-ink); }
[data-testid="stSidebar"] { background: var(--nh-blue); }
h1, h2, h3 { color: var(--nh-navy); }
div.stButton > button, div.stDownloadButton > button {
    background: var(--nh-navy); color: #ffffff; border: 1px solid var(--nh-navy);
}
div.stButton > button:hover, div.stDownloadButton > button:hover {
    background: var(--nh-blue-strong); color: #ffffff; border-color: var(--nh-blue-strong);
}
/* Selected filter pills: navy text on a light-blue surface, with gold accent. */
[data-baseweb="tag"] { background-color: var(--nh-blue-strong) !important; color: #ffffff !important; }
[data-baseweb="tag"] svg { color: #ffffff !important; }
[data-testid="stMetricValue"] { color: var(--nh-navy); }
hr { border-color: var(--nh-gold); }
</style>
""", unsafe_allow_html=True)
st.title("New Haven Public Property Sales Explorer")
st.subheader("Explore official New Haven property sales by asking factual search questions.")
st.caption("Public-record explorer only • no investment recommendations • assessments are not sale prices")
with st.expander("How to use", expanded=True):
    st.markdown("**1.** Type a search request such as *apartments under USD 1,000,000*.\n\n**2.** Review the Python-applied filters and matching source records.\n\n**3.** Use the map, median, table, and CSV export. AI answers only from the matching public records and never invents records.")

using_sample_data = False
sample_metadata = {}
live_load_error = None
try:
    comps = load_live_comps_cached()
    coverage = comp_coverage(comps)
except Exception as exc:
    live_load_error = type(exc).__name__
    try:
        comps, sample_metadata = load_sample_comps()
        coverage = comp_coverage(comps)
        using_sample_data = True
    except Exception as sample_exc:
        st.error(f"Live Connecticut data and bundled sample could not be loaded ({live_load_error}; {type(sample_exc).__name__}).")
        st.stop()
if using_sample_data:
    st.warning(
        f"Offline demonstration snapshot: {len(comps)} real public records captured on "
        f"{sample_metadata.get('snapshot_date', 'an unknown date')}. This is a small, historical sample, not the complete or current dataset. "
        f"Live source load failed ({live_load_error})."
    )
else:
    st.success(f"Loaded records: {len(comps)} across: {', '.join(coverage['property_types'])}.")
st.caption(f"Sales vintage: {SALES_VINTAGE} | Parcel/CAMA vintage: {CAMA_VINTAGE}")
audit = None
audit_error = None
if not using_sample_data:
    try:
        audit = audit_sales_cached(comps, sample_size=5)
    except Exception as exc:
        audit_error = type(exc).__name__
with st.expander("Official-source audit"):
    if using_sample_data:
        st.info("The bundled rows come from the official sales and CAMA sources, but this offline snapshot is not re-audited live.")
    elif audit is None:
        st.warning(f"Live source audit could not complete ({audit_error}). The app data loaded, but this session is not marked audited.")
    else:
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
if chat:
    natural_filters = search_request_result(chat, types)["filters"]
    overrides = filter_override_messages(sidebar_filters, natural_filters)
    if overrides:
        st.info("Sidebar values overridden by the natural-language filter:\n\n" + "\n".join(f"- {message}" for message in overrides))
st.write(f"Matching source records: **{len(filtered)}**")
prices = [r["sale_price"] for r in filtered if r.get("sale_price") is not None]
st.metric("Median sale price", f"USD {pd.Series(prices).median():,.0f}" if prices else "No matching prices")
table = [{**{k: r.get(k) for k in ("record_id", "address", "property_type", "sale_price", "assessment", "sales_source", "assessment_source")}, "Date recorded": readable_sale_date(r.get("sale_date"))} for r in filtered]
st.dataframe(table, use_container_width=True, hide_index=True, column_config={"sales_source": st.column_config.LinkColumn("Sales source", display_text="Open sales source"), "assessment_source": st.column_config.LinkColumn("CAMA source", display_text="Open CAMA source")})
if filtered:
    property_options = {f"{row.get('address') or 'Address unavailable'} ({row.get('record_id')})": index for index, row in enumerate(filtered)}
    selected_label = st.selectbox("Property details", list(property_options), help="Select one matching property to view its matched CAMA details.")
    selected_row = filtered[property_options[selected_label]]
    details = selected_row.get("cama_details") or {}
    with st.expander("Property details", expanded=True):
        st.caption("Matched Connecticut CAMA record; these details are separate from the sale record.")
        fields = format_cama_details(details)
        left, right = st.columns(2)
        items = list(fields.items())
        for column, pair in zip((left, right), (items[:4], items[4:])):
            with column:
                for label, value in pair:
                    st.write(f"**{label}**")
                    st.write(value)
        st.link_button("Open CAMA source", details.get("source") or "https://data.ct.gov/", disabled=not bool(details.get("source")))
st.download_button("Download filtered sales CSV", pd.DataFrame(table).to_csv(index=False), "new_haven_filtered_sales.csv", "text/csv")
st.caption("Sale price and assessment are separate official fields. No assessment is treated as a sale price.")
map_rows = [r for r in filtered if r.get("latitude") is not None and r.get("longitude") is not None and -90 <= r["latitude"] <= 90 and -180 <= r["longitude"] <= 180]
st.write(f"{len(map_rows)} of {len(filtered)} matching records mapped")
if len(map_rows) < len(filtered): st.warning(f"{len(filtered)-len(map_rows)} record(s) excluded from the map because reliable official coordinates were unavailable; no coordinates were guessed.")
if map_rows:
    import pydeck as pdk
    map_data = [{**r, "tooltip": f"{r['address']} | Date recorded: {r['sale_date'][:10]} | {r['property_type']} | Sale price: USD {r['sale_price']:,.0f} | Assessment: USD {r['assessment']:,.0f}" if r.get('assessment') is not None else f"{r['address']} | Date recorded: {r['sale_date'][:10]} | {r['property_type']} | Sale price: USD {r['sale_price']:,.0f} | Assessment: unavailable"} for r in map_rows]
    st.pydeck_chart(pdk.Deck(initial_view_state=pdk.ViewState(latitude=41.31, longitude=-72.92, zoom=11), layers=[pdk.Layer("ScatterplotLayer", data=map_data, get_position="[longitude, latitude]", get_radius=90, get_fill_color=[255, 215, 0, 230], stroked=True, get_line_color=[20, 20, 20, 255], line_width_min_pixels=3, pickable=True)], tooltip={"text": "{tooltip}"}))
else: st.info("No matching records have reliable official coordinates for mapping.")

st.subheader("Ask a factual question about matching records")
analysis_question = st.text_area("Question", placeholder="What were the highest sale prices, and which records support them?", height=80)
st.caption(
    f"AI requests this browser session: {st.session_state.ai_calls_made}/{MAX_AI_CALLS_PER_SESSION} · "
    f"reported spend: USD {st.session_state.ai_reported_spend_usd:.6f}. "
    "A session limit and per-run token limits reduce accidental repeat spend; this is not a per-account billing cap."
)
if st.button("Ask AI about matching records"):
    prompt = "Answer only from the Python analysis and read-only public sales records supplied by the application. Explain the exact result concisely, cite record IDs and source links, and say when the data cannot answer. Do not invent facts or make recommendations."
    try:
        if len(filtered) == len(comps):
            st.error("Apply an effective property type, date, price, or natural-language filter before asking AI; sending all records is disabled.")
            st.stop()
        if not analysis_question.strip():
            st.error("Enter a factual question about the matching records before asking AI.")
            st.stop()
        request_guard = ai_request_guard(st.session_state.ai_calls_made, analysis_question)
        if not request_guard["allowed"]:
            st.caption("Records sent to AI: 0")
            st.error(request_guard["message"])
            st.stop()
        analysis_payload = build_sales_analysis_payload(filtered, analysis_question)
        python_analysis = analysis_payload.get("python_analysis")
        if not python_analysis or not python_analysis.get("supported", False):
            st.caption("Records sent to AI: 0")
            st.error(analysis_payload.get("message", "This question is not supported by the available Python analysis."))
            st.stop()
        if python_analysis["analysis"] == "annual_trend":
            st.write("Python-computed annual trend")
            st.warning(python_analysis["data_quality_note"])
            st.dataframe(
                [{"Sale year": year, "Matching sales": values["count"], "Median sale price": f"USD {values['median_sale_price']:,.0f}"}
                 for year, values in python_analysis["by_year"].items()],
                hide_index=True,
                use_container_width=True,
            )
        compact_count = len(analysis_payload["python_analysis"].get("records", []))
        if python_analysis["analysis"] == "annual_trend":
            st.caption("Individual records sent to AI: 0; Python-computed annual summary sent.")
        else:
            st.caption(f"{analysis_records_status(compact_count)} compact analysis records (from {len(filtered)} matching records)")
        ai_request = {"filters": parsed, **analysis_payload}
        # Count attempts before the network call so provider errors cannot be
        # retried indefinitely within the same Streamlit browser session.
        st.session_state.ai_calls_made += 1
        memo, usage = asyncio.run(explain_with_agent(prompt + " Cite the supplied record IDs and source links.\nUser question: " + analysis_question, ai_request))
        if usage.get("available"):
            st.session_state.ai_reported_spend_usd += float(usage.get("cost_usd", 0.0))
            if python_analysis["analysis"] == "annual_trend":
                st.success("Individual records sent to AI: 0; Python-computed annual summary sent.")
            else:
                st.success(f"{analysis_records_status(compact_count, sent=True)}")
            st.write(format_explanation_for_display(memo))
            st.caption(format_usage_summary(usage))
        else: st.error(memo)
        with st.expander("Raw AI request and usage JSON", expanded=False):
            st.json({"request": ai_request, "usage": usage})
    except ValueError as exc:
        st.error(str(exc) + ". Narrow the filters before asking AI.")

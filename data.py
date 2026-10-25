"""Official Connecticut open-data access for the New Haven screener."""
from __future__ import annotations
import re
import requests
from datetime import datetime

SALES_DATASET = "5mzw-sjtu"
CAMA_DATASET = "rny9-6ak2"
SALES_VINTAGE = "Connecticut Real Estate Sales, list years 2007–2024 (accessed 2026-10-23)"
CAMA_VINTAGE = "Connecticut Parcel and CAMA Data 2025 (accessed 2026-10-23)"
SALES_URL = f"https://data.ct.gov/resource/{SALES_DATASET}.json"
CAMA_URL = f"https://data.ct.gov/resource/{CAMA_DATASET}.json"
MULTIFAMILY_TYPES = ("Two Family", "Three Family", "Four Family", "Apartments")

def _number(value):
    try: return float(value)
    except (TypeError, ValueError): return None

def normalize_address(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())

def fetch_sales_pages(where: str, page_size: int = 1000, request_get=None) -> list[dict]:
    """Fetch every matching Socrata row using offset pagination."""
    request_get = request_get or requests.get
    rows, offset = [], 0
    while True:
        response = request_get(SALES_URL, params={"$where": where, "$order": "listyear DESC, daterecorded DESC", "$limit": page_size, "$offset": offset}, timeout=20)
        response.raise_for_status()
        page = response.json()
        rows.extend(page)
        if len(page) < page_size:
            return rows
        offset += page_size


def fetch_new_haven_comps(page_size: int = 1000) -> list[dict]:
    where = "upper(town)='NEW HAVEN' AND propertytype in ('Two Family','Three Family','Four Family','Apartments')"
    sales_rows = fetch_sales_pages(where, page_size)
    cama = requests.get(CAMA_URL, params={"$where": "upper(property_city)='NEW HAVEN'", "$limit": 50000}, timeout=30)
    cama.raise_for_status()
    assessments = {normalize_address(row.get("location")): row for row in cama.json() if row.get("location")}
    rows = []
    for row in sales_rows:
        address = row.get("address", "")
        parcel = assessments.get(normalize_address(address), {})
        record_id = row.get("serialnumber", "")
        source_query = f"serialnumber='{record_id}' AND upper(town)='NEW HAVEN'"
        coords = row.get("geo_coordinates") or {}
        lon = coords.get("coordinates", [None, None])[0] if isinstance(coords, dict) else None
        lat = coords.get("coordinates", [None, None])[1] if isinstance(coords, dict) else None
        rows.append({"property_type": row.get("propertytype"), "sale_date": row.get("daterecorded") or row.get("listyear"), "sale_price": _number(row.get("saleamount")), "assessment": _number(parcel.get("assessed_total")), "address": address, "latitude": _number(lat), "longitude": _number(lon), "sales_source": f"{SALES_URL}?$where={source_query}", "assessment_source": parcel.get("cama_site_link", {}).get("url") or CAMA_URL, "sales_vintage": SALES_VINTAGE, "cama_vintage": CAMA_VINTAGE})
        rows[-1]["record_id"] = row.get("serialnumber")
        rows[-1]["valid_2024_gl"] = bool(row.get("listyear") == "2024" and (row.get("daterecorded", "")[:10] <= "2025-09-30"))
    return rows

def comp_coverage(rows: list[dict], minimum: int = 5) -> dict:
    types = sorted({row["property_type"] for row in rows if row.get("property_type")})
    return {"count": len(rows), "enough": len(rows) >= minimum, "property_types": types, "minimum": minimum}


def audit_sales_records(rows: list[dict], sample_size: int = 5) -> dict:
    """Re-fetch displayed IDs from the official sales source and compare key fields."""
    count_response = requests.get(SALES_URL, params={"$select": "count(*) as count", "$where": "upper(town)='NEW HAVEN' AND propertytype in ('Two Family','Three Family','Four Family','Apartments')"}, timeout=20)
    count_response.raise_for_status()
    source_row_count = int(count_response.json()[0]["count"])
    cama_count_response = requests.get(CAMA_URL, params={"$select": "count(*) as count", "$where": "upper(property_city)='NEW HAVEN'"}, timeout=20)
    cama_count_response.raise_for_status()
    cama_row_count = int(cama_count_response.json()[0]["count"])
    sample = rows[:sample_size]
    verified = []
    for row in sample:
        record_id = row.get("record_id")
        response = requests.get(SALES_URL, params={"$where": f"serialnumber='{record_id}' AND upper(town)='NEW HAVEN'", "$limit": 1}, timeout=20)
        response.raise_for_status()
        source_rows = response.json()
        source = source_rows[0] if source_rows else {}
        verified.append({"record_id": record_id, "verified": bool(source and str(source.get("serialnumber")) == str(record_id) and source.get("propertytype") == row.get("property_type") and _number(source.get("saleamount")) == row.get("sale_price")), "source_url": row.get("sales_source")})
    dates = sorted(row.get("sale_date", "")[:10] for row in rows if row.get("sale_date"))
    return {"sales_source_url": SALES_URL, "cama_source_url": CAMA_URL, "source_row_count": source_row_count, "cama_row_count": cama_row_count, "displayed_row_count": len(rows), "date_range": (dates[0], dates[-1]) if dates else (None, None), "record_ids": [row.get("record_id") for row in rows], "valid_2024_gl_cutoff": "2025-09-30", "valid_2024_gl_count": sum(row.get("valid_2024_gl", False) for row in rows), "direct_checks": verified, "all_direct_checks_pass": all(item["verified"] for item in verified)}

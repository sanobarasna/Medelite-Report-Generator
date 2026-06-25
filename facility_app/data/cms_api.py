"""
CMS Provider Data Catalog API client.

Confirmed live (June 2026):
  - Metastore endpoint returns the FULL dataset catalog regardless of any
    keyword/theme query param -> we filter by title client-side in Python.
  - Datastore query endpoint pattern:
      {BASE}/datastore/query/{dataset_id}/0
        ?conditions[0][property]=...&conditions[0][value]=...&conditions[0][operator]=...
  - Dataset IDs are STABLE across monthly data refreshes (only the underlying
    CSV/distribution rotates) - so we resolve by title once per session
    (cached) rather than hardcoding, as a safety net against CMS ever
    reissuing a new ID, but we don't need to re-resolve on every call.

Confirmed dataset IDs (verified live June 2026):
    Provider Information            -> 4pq5-n9py
    Medicare Claims Quality Measures -> ijh5-nb2v

Confirmed field names (NH_Data_Dictionary.pdf, Feb 2026 edition):
    Provider Information (Table 2):
        "CMS Certification Number (CCN)"
        "Provider Name"
        "Location"                          (full address string)
        "Number of Certified Beds"
        "Overall Rating"
        "Health Inspection Rating"
        "Staffing Rating"
        "QM Rating"
        "State"

    Medicare Claims Quality Measures (Table 12):
        "CMS Certification Number (CCN)"
        "Measure Code"
        "Measure Description"
        "Resident type"           ("Short Stay" / "Long Stay")
        "Adjusted Score"
        "Observed Score"
        "Expected Score"
        "Footnote for the Measure Score"
"""

import requests
import streamlit as st

BASE = "https://data.cms.gov/provider-data/api/1"
METASTORE_URL = f"{BASE}/metastore/schemas/dataset/items"

# Confirmed stable dataset IDs - resolved live June 2026.
KNOWN_DATASET_IDS = {
    "Provider Information": "4pq5-n9py",
    "Medicare Claims Quality Measures": "ijh5-nb2v",
    "State US Averages": "xcdc-v8bm",
}

REQUEST_TIMEOUT = 20


# ---------------------------------------------------------------------------
# Dataset resolution
# ---------------------------------------------------------------------------

@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_full_catalog():
    """
    Fetch the entire CMS metastore catalog once per day (cached).
    The API does not honor server-side keyword filters, so we always
    pull everything and filter client-side.
    """
    resp = requests.get(METASTORE_URL, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


@st.cache_data(ttl=86400, show_spinner=False)
def resolve_dataset_id(title: str) -> str | None:
    """
    Resolve a dataset's current identifier by exact title match.
    Falls back to the known-good hardcoded ID if the live catalog
    lookup fails or doesn't find a match - this keeps the app working
    even if CMS's metastore is temporarily unreachable.
    """
    fallback = KNOWN_DATASET_IDS.get(title)
    try:
        catalog = _fetch_full_catalog()
    except Exception:
        return fallback

    for entry in catalog:
        if entry.get("title", "").strip().lower() == title.strip().lower():
            return entry.get("identifier", fallback)

    return fallback


# ---------------------------------------------------------------------------
# Generic datastore query helper
# ---------------------------------------------------------------------------

def _datastore_query(dataset_id: str, conditions: list[dict], limit: int = 500, offset: int = 0):
    """
    Query a CMS datastore resource with one or more conditions.
    conditions: list of {"property": ..., "value": ..., "operator": ...}
    """
    url = f"{BASE}/datastore/query/{dataset_id}/0"
    params = {"limit": limit, "offset": offset}
    for i, cond in enumerate(conditions):
        params[f"conditions[{i}][property]"] = cond["property"]
        params[f"conditions[{i}][value]"] = cond["value"]
        params[f"conditions[{i}][operator]"] = cond.get("operator", "=")

    resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Provider Information
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300, show_spinner=False)
def fetch_provider_info(ccn: str) -> dict | None:
    """
    Fetch core facility info for a given CCN from the Provider Information
    dataset. Returns None if no matching row is found, raises on
    network/API failure (caller should catch and show a friendly error).
    """
    ccn = ccn.strip()
    dataset_id = resolve_dataset_id("Provider Information")
    if not dataset_id:
        raise RuntimeError("Could not resolve the Provider Information dataset ID.")

    result = _datastore_query(
        dataset_id,
        conditions=[{"property": "cms_certification_number_ccn", "value": ccn, "operator": "="}],
        limit=5,
    )
    rows = result.get("results", [])
    if not rows:
        return None

    row = rows[0]

    def _num(key):
        val = row.get(key)
        if val in (None, "", "N/A"):
            return None
        try:
            return float(val) if "." in str(val) else int(val)
        except (ValueError, TypeError):
            return None

    return {
        "ccn": row.get("cms_certification_number_ccn", ccn),
        "provider_name": row.get("provider_name"),
        "state": row.get("state"),
        "location": row.get("location"),
        "census_capacity": _num("number_of_certified_beds"),
        "overall_rating": _num("overall_rating"),
        "health_inspection_rating": _num("health_inspection_rating"),
        "staffing_rating": _num("staffing_rating"),
        "quality_rating": _num("qm_rating"),
        "raw": row,
    }


# ---------------------------------------------------------------------------
# Medicare Claims Quality Measures (bonus: 12 hospitalization/ED metrics)
# ---------------------------------------------------------------------------

# Per the case study's hint: STR -> Short Stay, LT -> Long Stay.
# Per the data dictionary, "Measure Description" contains free text we match
# on keywords rather than a fixed numeric code, since measure codes can shift
# between releases (see Table 16 revision history) but description wording
# is stable enough to anchor on "hospitalization" / "emergency department".
def _classify_claims_row(row: dict) -> str | None:
    desc = (row.get("measure_description") or "").lower()
    resident_type = (row.get("resident_type") or "").lower()

    is_short = "short" in resident_type
    is_long = "long" in resident_type

    if "hospital" in desc:
        metric = "hospitalization"
    elif "emergency department" in desc or "ed visit" in desc or "outpatient emergency" in desc:
        metric = "ed_visit"
    else:
        return None

    if is_short:
        return f"str_{metric}"
    if is_long:
        return f"lt_{metric}"
    return None


@st.cache_data(ttl=300, show_spinner=False)
def fetch_claims_metrics(ccn: str) -> dict:
    """
    Fetch the facility-level Short-Stay / Long-Stay hospitalization and
    ED-visit measures from the Medicare Claims Quality Measures dataset.
    Returns a dict keyed like:
        str_hospitalization, str_ed_visit, lt_hospitalization, lt_ed_visit
    Each value is the "Observed Score" (facility's own rate), or None if
    that measure wasn't found/reported for this facility.
    """
    ccn = ccn.strip()
    dataset_id = resolve_dataset_id("Medicare Claims Quality Measures")
    if not dataset_id:
        raise RuntimeError("Could not resolve the Medicare Claims Quality Measures dataset ID.")

    result = _datastore_query(
        dataset_id,
        conditions=[{"property": "cms_certification_number_ccn", "value": ccn, "operator": "="}],
        limit=50,
    )
    rows = result.get("results", [])

    metrics: dict[str, float | None] = {
        "str_hospitalization": None,
        "str_ed_visit": None,
        "lt_hospitalization": None,
        "lt_ed_visit": None,
    }

    for row in rows:
        key = _classify_claims_row(row)
        if key is None:
            continue
        score = row.get("observed_score")
        try:
            metrics[key] = float(score) if score not in (None, "", "N/A") else None
        except (ValueError, TypeError):
            metrics[key] = None

    return metrics


@st.cache_data(ttl=300, show_spinner=False)
def fetch_state_national_averages(state: str) -> dict:
    """
    Fetch state and national averages for the 4 claims-based metrics from
    the State and US Averages dataset, filtered by state postal code and
    by 'NATION'.

    NOTE: the State/US Averages file (per the data dictionary, Table 3)
    does NOT carry the short/long-stay hospitalization & ED visit measures
    under the same names as the claims file - it has its own column set
    ("Number of hospitalizations per 1000 long-stay resident days", etc.)
    This function maps those specific column names directly.
    """
    dataset_id = resolve_dataset_id("State US Averages")
    if not dataset_id:
        raise RuntimeError("Could not resolve the State US Averages dataset ID.")

    averages = {
        "str_hospitalization_state": None,
        "str_hospitalization_national": None,
        "str_ed_visit_state": None,
        "str_ed_visit_national": None,
        "lt_hospitalization_state": None,
        "lt_hospitalization_national": None,
        "lt_ed_visit_state": None,
        "lt_ed_visit_national": None,
    }

    targets = {state.strip().upper(): "state", "NATION": "national"}

    for code, suffix in targets.items():
        result = _datastore_query(
            dataset_id,
            conditions=[{"property": "state_or_nation", "value": code, "operator": "="}],
            limit=5,
        )
        rows = result.get("results", [])
        if not rows:
            continue
        row = rows[0]

        def _num(key):
            val = row.get(key)
            try:
                return float(val) if val not in (None, "", "N/A") else None
            except (ValueError, TypeError):
                return None

        averages[f"str_hospitalization_{suffix}"] = _num(
            "percentage_of_short_stay_residents_who_were_rehospitalized_after_a_nursing_home_admission"
        )
        averages[f"str_ed_visit_{suffix}"] = _num(
            "percentage_of_short_stay_residents_who_had_an_outpatient_emergency_department_visit"
        )
        averages[f"lt_hospitalization_{suffix}"] = _num(
            "number_of_hospitalizations_per_1000_long_stay_resident_days"
        )
        averages[f"lt_ed_visit_{suffix}"] = _num(
            "number_of_outpatient_emergency_department_visits_per_1000_long_stay_resident_days"
        )

    return averages

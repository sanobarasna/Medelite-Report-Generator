"""
Mapping layer: translates raw CMS API data + manual inputs into the
exact field set/order/labels used by the Facility Assessment Snapshot
template (Facility_Assessment_Snapshot.docx).

Field-source rules confirmed from the case study's Data Mapping Reference
table (Section 4) - this is the authoritative source, overriding any
ambiguous placeholder text in the template docx itself:

    Name of Facility       -> CMS API, manual override replaces only this field
    Location                -> CMS API
    EMR                     -> Manual
    Census Capacity         -> CMS API ("Number of Certified Beds")
    Current Census          -> Manual (NOT from API)
    Type of Patient         -> Manual
    Previous Coverage       -> Manual (Yes/No)
    Previous Provider Perf. -> Manual
    Medical Coverage        -> Manual
    4 Star Ratings           -> CMS API
    12 hospitalization/ED    -> CMS API (claims-based), bonus
"""

FOOTNOTE_TEXT = {
    1: "Newly certified facility; insufficient data history.",
    2: "Not enough data available to calculate a star rating.",
    6: "Facility submitted data that did not meet staffing measure criteria.",
    7: "CMS determined data was not accurate, or suppressed for one or more quarters.",
    9: "Sample size too small to report.",
    10: "Data missing or not submitted.",
    13: "Results based on a shorter time period than required.",
    14: "Not required to submit data for this program.",
    18: "Not rated due to special focus facility status.",
    20: "Accuracy of this rating could not be validated by CMS.",
    21: "Accuracy of this measure could not be validated by CMS.",
    22: "Address could not be geocoded precisely; ZIP-level location used.",
    23: "Facility did not submit staffing data.",
    24: "Facility reported a high number of days without an RN onsite.",
    25: "Accuracy of staffing data could not be validated by CMS.",
    26: "Invalid/missing turnover data; minimum points applied.",
    27: "Turnover measure excluded from staffing rating; rescaled.",
    28: "Annual measure; quarterly data not available.",
}


def footnote_label(code) -> str | None:
    """Return a short human-readable footnote string, or None if no footnote."""
    if code in (None, "", 0):
        return None
    try:
        code = int(float(code))
    except (ValueError, TypeError):
        return None
    return FOOTNOTE_TEXT.get(code, f"See CMS footnote {code}.")


def display_value(value, footnote_code=None, suffix: str = "", na_text: str = "N/A"):
    """
    Format a value for display, appending a footnote marker if present.
    Returns na_text if value is missing.
    """
    if value is None or value == "":
        note = footnote_label(footnote_code)
        return f"{na_text}" + (f" ({note})" if note else "")
    return f"{value}{suffix}"


def build_snapshot_fields(
    provider_info: dict | None,
    claims_metrics: dict | None,
    state_national_averages: dict | None,
    manual_inputs: dict,
    facility_name_override: str = "",
) -> dict:
    """
    Combine all data sources into the exact 24-row field set used by the
    report template, in template order. Returns a dict with both raw
    values (for Supabase storage) and display-ready strings (for PDF/DOCX).

    manual_inputs expected keys:
        emr, current_census, type_of_patient, previous_coverage,
        previous_provider_performance, medical_coverage
    """
    provider_info = provider_info or {}
    claims_metrics = claims_metrics or {}
    state_national_averages = state_national_averages or {}

    api_name = provider_info.get("provider_name")
    facility_name_display = facility_name_override.strip() or api_name or "N/A"

    rows = [
        ("Name of Facility", facility_name_display),
        ("Location", provider_info.get("location") or "N/A"),
        ("EMR", manual_inputs.get("emr") or "N/A"),
        ("Census Capacity", display_value(provider_info.get("census_capacity"))),
        ("Current Census", display_value(manual_inputs.get("current_census"))),
        ("Type of Patient", manual_inputs.get("type_of_patient") or "N/A"),
        ("Previous Coverage from Medelite", manual_inputs.get("previous_coverage") or "N/A"),
        ("Previous Provider Performance from Medelite", manual_inputs.get("previous_provider_performance") or "N/A"),
        ("Medical Coverage", manual_inputs.get("medical_coverage") or "N/A"),
        ("Overall Star Rating", display_value(provider_info.get("overall_rating"))),
        ("Health Inspection", display_value(provider_info.get("health_inspection_rating"))),
        ("Staffing", display_value(provider_info.get("staffing_rating"))),
        ("Quality of Resident Care", display_value(provider_info.get("quality_rating"))),
        ("Short Term Hospitalization", display_value(claims_metrics.get("str_hospitalization"), suffix="%")),
        ("STR National Avg. for Hospitalization", display_value(state_national_averages.get("str_hospitalization_national"), suffix="%")),
        ("STR State National Avg. for Hospitalization", display_value(state_national_averages.get("str_hospitalization_state"), suffix="%")),
        ("STR ED Visit", display_value(claims_metrics.get("str_ed_visit"), suffix="%")),
        ("STR ED Visits National Avg.", display_value(state_national_averages.get("str_ed_visit_national"), suffix="%")),
        ("STR ED Visits State Avg.", display_value(state_national_averages.get("str_ed_visit_state"), suffix="%")),
        ("LT Hospitalization", display_value(claims_metrics.get("lt_hospitalization"))),
        ("LT National Avg. for Hospitalization", display_value(state_national_averages.get("lt_hospitalization_national"))),
        ("LT State National Avg. for Hospitalization", display_value(state_national_averages.get("lt_hospitalization_state"))),
        ("ED Visit", display_value(claims_metrics.get("lt_ed_visit"))),
        ("LT ED Visits National Avg.", display_value(state_national_averages.get("lt_ed_visit_national"))),
        ("LT ED Visits State Avg.", display_value(state_national_averages.get("lt_ed_visit_state"))),
    ]

    return {
        "facility_name_api": api_name,
        "facility_name_override": facility_name_override.strip() or None,
        "facility_name_display": facility_name_display,
        "state": provider_info.get("state"),
        "rows": rows,
    }

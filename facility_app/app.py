"""
Medelite Facility Assessment Snapshot Generator
-------------------------------------------------
Enter a CCN -> pull CMS public nursing-home data live -> layer on manual
operational inputs -> preview -> download PDF/DOCX -> persist to Supabase.

Test case: CCN 686123 -> Kendall Lakes Healthcare and Rehab Center, FL
"""

import streamlit as st
from pathlib import Path

from data.cms_api import fetch_provider_info, fetch_claims_metrics, fetch_state_national_averages
from data.mapping import build_snapshot_fields
from data.persistence import save_assessment, list_assessments, get_assessment
from exports.pdf_export import build_snapshot_pdf, medicare_url
from exports.docx_export import build_snapshot_docx

# Anchor all asset paths to this file's location, not the process's CWD -
# Streamlit Cloud doesn't guarantee CWD == the repo/app folder.
BASE_DIR = Path(__file__).resolve().parent
LOGO_PATH = BASE_DIR / "assets" / "infinite_medelite_logo.png"

st.set_page_config(page_title="Facility Assessment Snapshot", page_icon="🏥", layout="wide")


# ---------------------------------------------------------------------------
# Branding header - static, never overwritten by facility name
# ---------------------------------------------------------------------------

def render_brand_header(state: str = ""):
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.image(str(LOGO_PATH), width=320)
        st.markdown(
            "<h3 style='text-align:center; margin-bottom:0;'>FACILITY ASSESSMENT SNAPSHOT</h3>",
            unsafe_allow_html=True,
        )
        if state:
            st.markdown(
                f"<p style='text-align:center; font-weight:bold;'>{state}</p>",
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# Session state init
# ---------------------------------------------------------------------------

if "provider_info" not in st.session_state:
    st.session_state.provider_info = None
if "claims_metrics" not in st.session_state:
    st.session_state.claims_metrics = None
if "state_national_averages" not in st.session_state:
    st.session_state.state_national_averages = None
if "last_ccn" not in st.session_state:
    st.session_state.last_ccn = ""
if "fetch_error" not in st.session_state:
    st.session_state.fetch_error = None


# ---------------------------------------------------------------------------
# Sidebar: history / reopen past reports
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("📁 Past Lookups")
    st.caption("Reopen a previously generated assessment.")
    try:
        history = list_assessments(limit=25)
    except Exception:
        history = []
        st.info("Connect Supabase secrets to enable history.")

    if history:
        for record in history:
            label = f"{record.get('facility_name_display') or record['ccn']} ({record['ccn']})"
            if st.button(label, key=f"hist_{record['ccn']}", use_container_width=True):
                st.session_state.reopen_ccn = record["ccn"]
                st.rerun()
    elif history == []:
        st.caption("No saved assessments yet.")


# ---------------------------------------------------------------------------
# Main: CCN lookup
# ---------------------------------------------------------------------------

render_brand_header(st.session_state.provider_info.get("state") if st.session_state.provider_info else "")

st.divider()

reopen_ccn = st.session_state.pop("reopen_ccn", None)

col_a, col_b = st.columns([3, 1])
with col_a:
    ccn_input = st.text_input(
        "CMS Certification Number (CCN)",
        value=reopen_ccn or st.session_state.last_ccn,
        placeholder="e.g. 686123",
        max_chars=10,
    )
with col_b:
    st.write("")
    st.write("")
    fetch_clicked = st.button("🔍 Fetch Facility Data", use_container_width=True, type="primary")

if fetch_clicked and ccn_input.strip():
    ccn = ccn_input.strip()
    st.session_state.last_ccn = ccn
    st.session_state.fetch_error = None

    with st.spinner(f"Fetching CMS data for CCN {ccn}..."):
        try:
            provider_info = fetch_provider_info(ccn)
            if provider_info is None:
                st.session_state.provider_info = None
                st.session_state.fetch_error = (
                    f"No facility found for CCN '{ccn}'. Please double-check the number."
                )
            else:
                st.session_state.provider_info = provider_info
                try:
                    st.session_state.claims_metrics = fetch_claims_metrics(ccn)
                except Exception as e:
                    st.session_state.claims_metrics = {}
                    st.warning(f"Hospitalization/ED metrics unavailable: {e}")
                try:
                    st.session_state.state_national_averages = fetch_state_national_averages(
                        provider_info.get("state") or ""
                    )
                except Exception as e:
                    st.session_state.state_national_averages = {}
                    st.warning(f"State/national averages unavailable: {e}")
        except Exception as e:
            st.session_state.provider_info = None
            st.session_state.fetch_error = (
                f"Couldn't reach the CMS data API: {e}. Please try again in a moment."
            )

elif reopen_ccn:
    # Reopening a saved record: load from Supabase instead of re-fetching
    saved = get_assessment(reopen_ccn)
    if saved:
        st.session_state.last_ccn = reopen_ccn
        st.session_state.provider_info = {
            "ccn": saved["ccn"],
            "provider_name": saved.get("facility_name_api"),
            "state": saved.get("state"),
            "location": saved.get("location"),
            "census_capacity": saved.get("census_capacity"),
            "overall_rating": saved.get("overall_rating"),
            "health_inspection_rating": saved.get("health_inspection_rating"),
            "staffing_rating": saved.get("staffing_rating"),
            "quality_rating": saved.get("quality_rating"),
        }
        metrics_blob = saved.get("metrics") or {}
        st.session_state.claims_metrics = metrics_blob.get("claims", {})
        st.session_state.state_national_averages = metrics_blob.get("averages", {})
        st.session_state._reopened_manual = {
            "emr": saved.get("emr"),
            "current_census": saved.get("current_census"),
            "type_of_patient": saved.get("type_of_patient"),
            "previous_coverage": saved.get("previous_coverage"),
            "previous_provider_performance": saved.get("previous_provider_performance"),
            "medical_coverage": saved.get("medical_coverage"),
        }
        st.session_state._reopened_override = saved.get("facility_name_override") or ""

if st.session_state.fetch_error:
    st.error(st.session_state.fetch_error)


# ---------------------------------------------------------------------------
# Once we have provider info: show editable fields + preview + export
# ---------------------------------------------------------------------------

if st.session_state.provider_info:
    provider_info = st.session_state.provider_info
    ccn = provider_info["ccn"]
    reopened_manual = st.session_state.pop("_reopened_manual", {})
    reopened_override = st.session_state.pop("_reopened_override", "")

    st.success(
        f"Loaded: **{provider_info.get('provider_name', 'Unknown')}** "
        f"— {provider_info.get('state', '')} (CCN {ccn})"
    )

    st.subheader("Facility Name")
    name_override = st.text_input(
        "Optional name override (replaces only the 'Name of Facility' row — never the INFINITE banner)",
        value=reopened_override,
        placeholder=provider_info.get("provider_name") or "",
    )

    st.subheader("Manual Operational Inputs")
    m1, m2, m3 = st.columns(3)
    with m1:
        emr = st.text_input("EMR", value=reopened_manual.get("emr") or "", placeholder="e.g. PCC, MatrixCare")
        current_census = st.number_input(
            "Current Census",
            min_value=0,
            value=int(reopened_manual.get("current_census") or 0),
            step=1,
        )
    with m2:
        type_of_patient = st.text_input(
            "Type of Patient", value=reopened_manual.get("type_of_patient") or "",
            placeholder="e.g. Long-term & Short-term",
        )
        previous_coverage = st.selectbox(
            "Previous Coverage from Medelite", options=["Yes", "No"],
            index=0 if (reopened_manual.get("previous_coverage") or "Yes") == "Yes" else 1,
        )
    with m3:
        previous_provider_performance = st.text_input(
            "Previous Provider Performance from Medelite",
            value=reopened_manual.get("previous_provider_performance") or "",
            placeholder="e.g. About 30 patients/day",
        )
        medical_coverage = st.text_input(
            "Medical Coverage", value=reopened_manual.get("medical_coverage") or "",
            placeholder="e.g. Optometry, PCP, Podiatry",
        )

    manual_inputs = {
        "emr": emr,
        "current_census": current_census,
        "type_of_patient": type_of_patient,
        "previous_coverage": previous_coverage,
        "previous_provider_performance": previous_provider_performance,
        "medical_coverage": medical_coverage,
    }

    snapshot = build_snapshot_fields(
        provider_info=provider_info,
        claims_metrics=st.session_state.claims_metrics,
        state_national_averages=st.session_state.state_national_averages,
        manual_inputs=manual_inputs,
        facility_name_override=name_override,
    )

    st.divider()
    st.subheader("📋 Preview")
    st.table(snapshot["rows"])

    st.markdown(f"[🔗 View on Medicare Care Compare]({medicare_url(ccn, snapshot.get('state'))})")

    # ----- Charts (on-screen only, per architecture decision) -----
    claims = st.session_state.claims_metrics or {}
    averages = st.session_state.state_national_averages or {}
    if any(v is not None for v in claims.values()):
        st.divider()
        st.subheader("📊 Hospitalization & ED Visit Metrics")
        c1, c2 = st.columns(2)
        with c1:
            st.caption("Short-Stay Hospitalization (%)")
            st.bar_chart({
                "Facility": claims.get("str_hospitalization"),
                "State": averages.get("str_hospitalization_state"),
                "National": averages.get("str_hospitalization_national"),
            })
            st.caption("Short-Stay ED Visit (%)")
            st.bar_chart({
                "Facility": claims.get("str_ed_visit"),
                "State": averages.get("str_ed_visit_state"),
                "National": averages.get("str_ed_visit_national"),
            })
        with c2:
            st.caption("Long-Stay Hospitalization (per 1000 resident days)")
            st.bar_chart({
                "Facility": claims.get("lt_hospitalization"),
                "State": averages.get("lt_hospitalization_state"),
                "National": averages.get("lt_hospitalization_national"),
            })
            st.caption("Long-Stay ED Visit (per 1000 resident days)")
            st.bar_chart({
                "Facility": claims.get("lt_ed_visit"),
                "State": averages.get("lt_ed_visit_state"),
                "National": averages.get("lt_ed_visit_national"),
            })

    # ----- Exports -----
    st.divider()
    st.subheader("⬇️ Export")
    e1, e2, e3 = st.columns(3)

    with e1:
        try:
            pdf_bytes = build_snapshot_pdf(snapshot, ccn)
            st.download_button(
                "📄 Download PDF",
                data=pdf_bytes,
                file_name=f"Facility_Assessment_{ccn}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"PDF generation failed: {e}")

    with e2:
        try:
            docx_bytes = build_snapshot_docx(snapshot, ccn)
            st.download_button(
                "📝 Download DOCX",
                data=docx_bytes,
                file_name=f"Facility_Assessment_{ccn}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"DOCX generation failed: {e}")

    with e3:
        if st.button("💾 Save to History", use_container_width=True):
            record = {
                "ccn": ccn,
                "state": snapshot.get("state"),
                "facility_name_api": snapshot.get("facility_name_api"),
                "facility_name_override": snapshot.get("facility_name_override"),
                "facility_name_display": snapshot.get("facility_name_display"),
                "location": provider_info.get("location"),
                "census_capacity": provider_info.get("census_capacity"),
                "overall_rating": provider_info.get("overall_rating"),
                "health_inspection_rating": provider_info.get("health_inspection_rating"),
                "staffing_rating": provider_info.get("staffing_rating"),
                "quality_rating": provider_info.get("quality_rating"),
                "emr": manual_inputs["emr"],
                "current_census": manual_inputs["current_census"],
                "type_of_patient": manual_inputs["type_of_patient"],
                "previous_coverage": manual_inputs["previous_coverage"],
                "previous_provider_performance": manual_inputs["previous_provider_performance"],
                "medical_coverage": manual_inputs["medical_coverage"],
                "metrics": {"claims": claims, "averages": averages},
                "raw_api_snapshot": provider_info.get("raw", {}),
            }
            saved = save_assessment(record)
            if saved:
                st.success("Saved! This facility now appears in Past Lookups.")
                st.rerun()

else:
    st.info("Enter a CCN above and click **Fetch Facility Data** to get started. Try `686123` (Kendall Lakes, FL) as a test case.")

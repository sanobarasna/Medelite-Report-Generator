"""
Medelite Facility Assessment Snapshot Generator
-------------------------------------------------
Enter a CCN -> pull CMS public nursing-home data live -> layer on manual
operational inputs -> preview -> download PDF/DOCX.

Test case: CCN 686123 -> Kendall Lakes Healthcare and Rehab Center, FL
"""

import streamlit as st
from pathlib import Path

from data.cms_api import fetch_provider_info, fetch_claims_metrics, fetch_state_national_averages
from data.mapping import build_snapshot_fields
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
# Main: CCN lookup
# ---------------------------------------------------------------------------

render_brand_header(st.session_state.provider_info.get("state") if st.session_state.provider_info else "")

st.divider()

col_a, col_b = st.columns([3, 1])
with col_a:
    ccn_input = st.text_input(
        "CMS Certification Number (CCN)",
        value=st.session_state.last_ccn,
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

if st.session_state.fetch_error:
    st.error(st.session_state.fetch_error)


# ---------------------------------------------------------------------------
# Once we have provider info: show editable fields + preview + export
# ---------------------------------------------------------------------------

if st.session_state.provider_info:
    provider_info = st.session_state.provider_info
    ccn = provider_info["ccn"]

    st.success(
        f"Loaded: **{provider_info.get('provider_name', 'Unknown')}** "
        f"— {provider_info.get('state', '')} (CCN {ccn})"
    )

    st.subheader("Facility Name")
    name_override = st.text_input(
        "Optional name override (replaces only the 'Name of Facility' row — never the INFINITE banner)",
        value="",
        placeholder=provider_info.get("provider_name") or "",
    )

    st.subheader("Manual Operational Inputs")
    m1, m2, m3 = st.columns(3)
    with m1:
        emr = st.text_input("EMR", value="", placeholder="e.g. PCC, MatrixCare")
        current_census = st.number_input("Current Census", min_value=0, value=0, step=1)
    with m2:
        type_of_patient = st.text_input(
            "Type of Patient", value="", placeholder="e.g. Long-term & Short-term",
        )
        previous_coverage = st.selectbox("Previous Coverage from Medelite", options=["Yes", "No"])
    with m3:
        previous_provider_performance = st.text_input(
            "Previous Provider Performance from Medelite",
            value="", placeholder="e.g. About 30 patients/day",
        )
        medical_coverage = st.text_input(
            "Medical Coverage", value="", placeholder="e.g. Optometry, PCP, Podiatry",
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
    e1, e2 = st.columns(2)

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

else:
    st.info("Enter a CCN above and click **Fetch Facility Data** to get started. Try `686123` (Kendall Lakes, FL) as a test case.")

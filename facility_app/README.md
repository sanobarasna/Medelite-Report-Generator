# Facility Assessment Snapshot Generator

A Streamlit app for Medelite that looks up a nursing home by CMS Certification
Number (CCN), pulls live public CMS data, layers on manual operational inputs,
and generates a branded PDF/DOCX report.

**Test case:** CCN `686123` → Kendall Lakes Healthcare and Rehab Center, FL
(matches the sample `Facility Assessment Snapshot` PDF used as the validation
target for this project).

## Setup

```bash
pip install -r requirements.txt
streamlit run app.py
```

No external services or secrets are required to run the app — CMS's
Provider Data Catalog API is public and keyless.

## Project structure

```
app.py                     - main Streamlit entry point / UI
data/
  cms_api.py                - CMS Provider Data Catalog API client
  mapping.py                 - field mapping, STR/LT relabeling, footnotes
  persistence.py             - Supabase read/write helpers (UNUSED — see note below)
exports/
  pdf_export.py               - PDF generation (reportlab)
  docx_export.py              - DOCX generation (fills the approved template)
assets/
  infinite_medelite_logo.png   - extracted brand banner (static, never edited)
  snapshot_template.docx        - approved Word template, filled at export time
schema.sql                  - Supabase table + trigger definitions (UNUSED — see note below)
```

> **Note on `persistence.py` / `schema.sql`:** the app originally persisted
> every lookup to Supabase (one row per CCN, with automatic version history
> via a DB trigger) and offered a sidebar to reopen past reports. This
> feature was removed from `app.py` after the connected Supabase project
> hit its free-tier egress quota and started rejecting requests, breaking
> the "Past Lookups" sidebar in production. The Supabase client code and
> SQL schema are left in the repo, unreferenced, in case persistence is
> reinstated later (e.g. on a paid Supabase plan, or a different backend).
> To re-enable: re-wire `data/persistence.py`'s `save_assessment` /
> `list_assessments` / `get_assessment` back into `app.py`, restore a
> `.streamlit/secrets.toml` with valid Supabase credentials, and re-run
> `schema.sql` against an active project.

## Architecture notes

- **CMS data**: no API key required. Dataset IDs are resolved by title against
  the CMS metastore catalog (cached daily) with hardcoded fallbacks, since
  CMS dataset IDs are stable across monthly data refreshes but this guards
  against the rare case of a reissue.
  - Provider Information: `4pq5-n9py`
  - Medicare Claims Quality Measures: `ijh5-nb2v`
  - State US Averages: `xcdc-v8bm`
- **Field mapping**: `data/mapping.py` implements the exact field-source table
  from the technical case study (Section 4) — e.g. "Current Census" is a
  **manual** input, not pulled from the API, despite what the template's
  placeholder text might suggest at a glance.
- **STR/LT relabeling**: per the case study's hint, CMS's "Short Stay" /
  "Long Stay" resident-type values are mapped to the report's "STR" / "LT"
  shorthand. Claims rows are classified by parsing `Measure Description`
  text (matching on "hospital" / "emergency department") rather than a
  hardcoded numeric measure code, since CMS has reassigned measure codes
  across releases historically (see the data dictionary's revision table).
- **Branding guardrail**: the "INFINITE — Managed by MEDELITE" logo is a
  static image asset, rendered identically in the UI header, PDF, and DOCX
  exports. It is never replaced by the facility name (API or manual
  override) — the facility name only ever appears in the "Name of Facility"
  table row.
- **Exports**: charts are on-screen only (Streamlit `bar_chart`); PDF and
  DOCX exports stay table-only, matching the original template's plain
  layout. The PDF includes a clickable Medicare Care Compare hyperlink
  (required); the DOCX includes the same URL as plain text (python-docx
  hyperlinks require extra XML relationship work not worth it for a
  "bonus" export format).
- **Persistence**: none currently. Each session is stateless — lookups,
  manual inputs, and generated files exist only for the current browser
  session and are not saved anywhere. See the note above if you want to
  reinstate Supabase persistence.

## Known assumptions / engineering notes

Per the case study's own guidance ("you may make a reasonable engineering
assumption, document it clearly... we value resourcefulness over
perfection"), the following are documented here:

1. **CMS datastore column names** (e.g. `cms_certification_number_ccn`,
   `overall_rating`, `measure_description`, `observed_score`,
   `state_or_nation`) are CMS's standard snake_case transformations of the
   human-readable data dictionary labels. These were partially confirmed
   against third-party CMS API documentation but not all individually
   verified against a live response at build time. If a field renders as
   blank/"N/A" after a real fetch, the most likely cause is a column-name
   mismatch — add a quick `st.write(provider_info["raw"])` in `app.py`
   (right after a successful fetch) to inspect the actual keys CMS returns,
   and adjust `data/cms_api.py` accordingly.
2. **State US Averages claims-metric columns**: the State/US Averages file
   does not mirror the claims file's column names — it uses its own labels
   ("Number of hospitalizations per 1000 long-stay resident days", etc.).
   `fetch_state_national_averages()` maps these specific column names
   directly; double-check against a live row if averages don't populate.
3. **DOCX hyperlink**: rendered as plain text rather than a clickable link,
   since the case study's hyperlink requirement is explicitly scoped to the
   PDF export.

## Bonus features included

- ✅ All 12 hospitalization/ED metrics (STR/LT × facility/state/national)
- ✅ DOCX export
- ✅ On-screen charts (bar charts comparing facility vs. state vs. national)
- ✅ Error handling for invalid CCNs, missing fields, and partial API outages
- ⛔ Supabase persistence — built, then removed after a Supabase quota
  outage broke it in production; code retained but unwired (see note above)

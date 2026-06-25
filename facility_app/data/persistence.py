"""
Supabase persistence layer.

Schema (run schema.sql in your Supabase SQL editor before first use):
    facility_assessments          - one row per CCN, upserted on every fetch
    facility_assessments_history  - automatic snapshot of the prior row,
                                     written by a DB trigger on every update

This module only ever upserts to facility_assessments; the history table
is populated automatically by the trigger, so the app never writes to it
directly.
"""

import streamlit as st
from supabase import create_client, Client


@st.cache_resource
def get_client() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


def save_assessment(record: dict) -> dict | None:
    """
    Upsert a facility assessment record, keyed on ccn.
    record should contain all columns matching the facility_assessments
    table (see schema.sql). Returns the saved row, or None on failure.
    """
    client = get_client()
    try:
        result = client.table("facility_assessments").upsert(
            record, on_conflict="ccn"
        ).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        st.error(f"Could not save to Supabase: {e}")
        return None


def get_assessment(ccn: str) -> dict | None:
    """Fetch a single saved assessment by CCN, if it exists."""
    client = get_client()
    try:
        result = (
            client.table("facility_assessments")
            .select("*")
            .eq("ccn", ccn.strip())
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception as e:
        st.error(f"Could not read from Supabase: {e}")
        return None


def list_assessments(limit: int = 50) -> list[dict]:
    """
    Fetch the most recently updated assessments, for the in-app
    history/reopen view. One row per facility (CCN), most recent first.
    """
    client = get_client()
    try:
        result = (
            client.table("facility_assessments")
            .select("*")
            .order("updated_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception as e:
        st.error(f"Could not load history from Supabase: {e}")
        return []


def get_history_for_ccn(ccn: str, limit: int = 10) -> list[dict]:
    """Fetch prior archived versions of a CCN's assessment, most recent first."""
    client = get_client()
    try:
        result = (
            client.table("facility_assessments_history")
            .select("*")
            .eq("ccn", ccn.strip())
            .order("archived_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception as e:
        st.error(f"Could not load history from Supabase: {e}")
        return []

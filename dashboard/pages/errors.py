"""Errors page — Story 6.5."""

import streamlit as st

from tiktok_faceless.db.queries import get_resolved_errors, get_unresolved_errors

_ERROR_TYPE_LABELS: dict[str, str] = {
    "ElevenLabsError": "ElevenLabs TTS failure",
    "VideoAssemblyError": "Video assembly failure",
    "TikTokUploadError": "TikTok upload failure",
    "TikTokAuthError": "TikTok authentication error",
    "ProductResearchError": "Product research failure",
    "AnalyticsError": "Analytics fetch failure",
    "suppression_detected": "Suppression signal detected",
    "commission_discrepancy": "Commission discrepancy detected",
    "ScriptGenerationError": "Script generation failure",
    "MonetizationError": "Monetization check failure",
}


def _plain_message(error) -> str:
    """Return the plain-English version of error.message (already human-readable from agents)."""
    return error.message or error.error_type


def _render_error_row(error, resolved: bool = False) -> None:
    """Render a single error as a compact info block."""
    label = _ERROR_TYPE_LABELS.get(error.error_type, error.error_type.replace("_", " ").title())
    ts = error.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
    agent_display = error.agent.title()

    cols = st.columns([0.25, 0.25, 0.50])
    with cols[0]:
        st.markdown(f"**{agent_display}**  \n{ts}")
    with cols[1]:
        st.markdown(f"**{label}**")
    with cols[2]:
        st.markdown(_plain_message(error))
        if error.recovery_suggestion:
            st.caption(f"Suggestion: {error.recovery_suggestion}")

    if resolved and error.resolved_at:
        st.caption(f"Resolved: {error.resolved_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")

    st.divider()


def render_errors_page(session, account_id: str) -> None:
    st.header("Error Log")

    # --- Active errors ---
    try:
        active = get_unresolved_errors(session, account_id)
    except Exception as e:
        st.error(f"Failed to load active errors: {e}")
        active = []

    st.subheader("Active Errors")

    if not active:
        st.success("No active errors — all agents healthy.")
    else:
        for error in active:
            _render_error_row(error, resolved=False)

    # --- Resolved errors ---
    st.subheader("Resolved Errors")

    try:
        resolved = get_resolved_errors(session, account_id)
    except Exception as e:
        st.error(f"Failed to load resolved errors: {e}")
        resolved = []

    if not resolved:
        st.info("No resolved errors on record.")
    else:
        with st.expander(f"Resolved errors ({len(resolved)})"):
            for error in resolved:
                _render_error_row(error, resolved=True)

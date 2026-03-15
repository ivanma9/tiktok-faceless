"""
Milestone notification banners — Story 6.6.

Renders dismissible and persistent indigo milestone banners in the dashboard alert zone.
Suppression alert rendering is delegated to suppression_alert.py (Story 6.2).
"""

import streamlit as st

_INDIGO = "#6366f1"
_MILESTONE_1K_THRESHOLD = 1000.0

_FIRST_COMMISSION_SESSION_KEY = "first_commission_dismissed"
_PHASE_TRANSITION_SESSION_KEY = "phase_transition_shown"
_MILESTONE_1K_SESSION_KEY = "milestone_1k_dismissed"


def render_first_commission_banner(amount: float) -> None:
    """Render dismissible indigo first-commission banner.

    Only shows if not already dismissed this session.
    Sets st.session_state[_FIRST_COMMISSION_SESSION_KEY] = True on dismiss.
    """
    if st.session_state.get(_FIRST_COMMISSION_SESSION_KEY):
        return

    banner_html = (
        f'<div style="border-left: 4px solid {_INDIGO}; '
        f'background: #eef2ff; padding: 12px 16px; border-radius: 4px; margin-bottom: 8px;">'
        f"<strong>First affiliate commission earned — ${amount:,.2f}. "
        f"The thesis is proven.</strong>"
        f"</div>"
    )
    st.markdown(banner_html, unsafe_allow_html=True)
    if st.button("Dismiss", key="dismiss_first_commission"):
        st.session_state[_FIRST_COMMISSION_SESSION_KEY] = True
        st.rerun()


def render_phase_transition_banner(decision) -> None:
    """Render indigo phase-transition banner for a recent AgentDecision.

    Does not persist — shows on every load until the 24h window expires
    (controlled by get_latest_phase_transition query).
    Uses session_state to avoid re-rendering within the same autorefresh cycle.
    """
    # Key includes decision id so a new transition clears the "seen" state
    session_key = f"{_PHASE_TRANSITION_SESSION_KEY}_{decision.id}"
    if st.session_state.get(session_key):
        return

    from_phase = decision.from_value or "unknown"
    to_phase = decision.to_value or "unknown"

    # Extract niche from rationale if present — rationale is free-text so we surface it directly
    niche_suffix = f"  \n*{decision.rationale}*" if decision.rationale else ""

    banner_html = (
        f'<div style="border-left: 4px solid {_INDIGO}; '
        f'background: #eef2ff; padding: 12px 16px; border-radius: 4px; margin-bottom: 8px;">'
        f"<strong>Phase changed: {from_phase} → {to_phase}.</strong>{niche_suffix}"
        f"</div>"
    )
    st.markdown(banner_html, unsafe_allow_html=True)
    if st.button("Dismiss", key=f"dismiss_phase_{decision.id}"):
        st.session_state[session_key] = True
        st.rerun()


def render_milestone_1k_banner() -> None:
    """Render persistent $1K/month milestone banner until explicitly dismissed.

    Persists across autorefresh cycles until the operator clicks Dismiss.
    """
    if st.session_state.get(_MILESTONE_1K_SESSION_KEY):
        return

    banner_html = (
        f'<div style="border-left: 4px solid {_INDIGO}; '
        f'background: #eef2ff; padding: 12px 16px; border-radius: 4px; margin-bottom: 8px;">'
        f"<strong>$1,000/month milestone reached. System is confirmed working.</strong>"
        f"</div>"
    )
    st.markdown(banner_html, unsafe_allow_html=True)
    if st.button("Dismiss", key="dismiss_milestone_1k"):
        st.session_state[_MILESTONE_1K_SESSION_KEY] = True
        st.rerun()


def render_milestone_banners(
    phase_transition,
    first_commission: float | None,
    monthly_revenue: float,
) -> None:
    """Render milestone banners from pre-fetched data.

    Call order (highest to lowest priority):
    1. Phase transition banner
    2. First commission banner
    3. $1K/month milestone banner

    Suppression banner is NOT rendered here — it is handled in app.py via
    render_suppression_alert() from suppression_alert.py (Story 6.2).
    """
    if phase_transition is not None:
        render_phase_transition_banner(phase_transition)

    if first_commission is not None and not st.session_state.get(_FIRST_COMMISSION_SESSION_KEY):
        render_first_commission_banner(first_commission)

    if monthly_revenue >= _MILESTONE_1K_THRESHOLD and not st.session_state.get(
        _MILESTONE_1K_SESSION_KEY
    ):
        render_milestone_1k_banner()

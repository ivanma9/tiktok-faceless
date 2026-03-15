"""
Dashboard password gate via st.session_state.

Implementation: Story 6.1 — Dashboard Foundation & Auth
"""

import os

import streamlit as st


def check_password() -> bool:
    """Return True if the user is authenticated for this session.

    Reads DASHBOARD_PASSWORD from environment. Raises KeyError if unset (fail-fast).
    """
    if st.session_state.get("authenticated"):
        return True
    password = os.environ["DASHBOARD_PASSWORD"]
    entered = st.text_input("Dashboard Password", type="password")
    if st.button("Login"):
        if entered == password:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password")
    return False

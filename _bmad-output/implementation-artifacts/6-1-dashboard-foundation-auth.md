# Story 6.1: Dashboard Foundation & Auth

Status: ready-for-dev

## Story

As the operator,
I want a Streamlit dashboard running on the VPS behind a password gate with 60-second auto-refresh,
so that I can access live system data from any device without exposing it publicly.

## Acceptance Criteria

1. **Given** the Streamlit app is deployed
   **When** I navigate to the dashboard URL
   **Then** a password prompt is shown before any data is displayed
   **And** the password is validated against `DASHBOARD_PASSWORD` env var via `dashboard/auth.py`
   **And** on successful auth, `st.session_state["authenticated"] = True` persists for the session

2. **Given** the dashboard is authenticated
   **When** the page loads
   **Then** `streamlit-autorefresh` triggers a data reload every 60 seconds
   **And** the refresh is silent — no visible loading flash during auto-refresh
   **And** the last-updated timestamp in the top bar updates on each refresh

3. **Given** the dashboard connects to the database
   **When** `db/session.py` `get_session()` is called from `dashboard/`
   **Then** it connects to PostgreSQL (production) or SQLite (dev) based on env config
   **And** all queries are read-only — no dashboard code writes to the database
   **And** the dashboard loads current pipeline state within 5 seconds of page load

## Tasks / Subtasks

- [ ] Task 1: Create `dashboard/` directory structure
  - [ ] Create `dashboard/__init__.py` (empty)
  - [ ] Create `dashboard/pages/__init__.py` (empty)
  - [ ] Create `dashboard/components/__init__.py` (empty)
  - [ ] Create stub files: `dashboard/pages/overview.py`, `dashboard/pages/videos.py`, `dashboard/pages/decisions.py`, `dashboard/pages/errors.py`
  - [ ] Create stub files: `dashboard/components/phase_badge.py`, `dashboard/components/suppression_alert.py`, `dashboard/components/sparkline.py`

- [ ] Task 2: Implement `dashboard/auth.py` — password gate
  - [ ] Read `DASHBOARD_PASSWORD` from `os.environ` (no default — fail explicitly if unset)
  - [ ] `check_password() -> bool`: checks `st.session_state.get("authenticated")`, shows password input if not authenticated, validates against env var, sets `st.session_state["authenticated"] = True` on match, returns bool
  - [ ] On wrong password: show `st.error("Incorrect password")` and return False
  - [ ] No plaintext password in code — compare directly against env var value only

- [ ] Task 3: Implement `dashboard/app.py` — entry point
  - [ ] Import and call `check_password()` from `auth.py`; `st.stop()` if returns False (gate all content)
  - [ ] Add `streamlit-autorefresh` component: `st_autorefresh(interval=60_000, key="autorefresh")` — 60s in milliseconds
  - [ ] Add placeholder title: `st.title("TikTok Faceless Dashboard")`
  - [ ] Add `st.caption(f"Last updated: {datetime.utcnow().strftime('%H:%M:%S UTC')}")` for freshness display
  - [ ] Import `get_session` from `tiktok_faceless.db.session` — confirm DB connectivity (read-only ping)
  - [ ] No writes to DB from dashboard — read-only access only

- [ ] Task 4: Add `streamlit` and `streamlit-autorefresh` dependencies
  - [ ] Add `streamlit` and `streamlit-autorefresh` to `pyproject.toml` optional/dashboard group or main dependencies
  - [ ] Verify: `uv add streamlit streamlit-autorefresh` (or edit pyproject.toml directly)

- [ ] Task 5: Write tests in `tests/unit/dashboard/`
  - [ ] Create `tests/unit/dashboard/__init__.py`
  - [ ] Create `tests/unit/dashboard/test_auth.py`:
    - [ ] `test_check_password_returns_false_when_not_authenticated` — no session state → returns False
    - [ ] `test_check_password_returns_true_when_session_authenticated` — `st.session_state["authenticated"] = True` → returns True
    - [ ] `test_check_password_sets_session_on_correct_password` — correct password input → `session_state["authenticated"]` is True
    - [ ] `test_check_password_shows_error_on_wrong_password` — wrong password → `st.error` called

## Dev Notes

### Architecture Boundaries (MUST NOT VIOLATE)

- `dashboard/` ONLY imports from `tiktok_faceless.db.session` and `tiktok_faceless.db.queries`
- **NEVER** import from `tiktok_faceless.agents.*`, `tiktok_faceless.clients.*`, or `tiktok_faceless.graph`
- All DB access is read-only — dashboard is a consumer, not a writer

### Dashboard Directory Structure

```
dashboard/
├── __init__.py
├── app.py                        # Streamlit entry point
├── auth.py                       # password gate via st.session_state
├── pages/
│   ├── __init__.py
│   ├── overview.py               # phase indicator, pipeline health, revenue summary
│   ├── videos.py                 # per-video metrics table with sparklines
│   ├── decisions.py              # agent decision audit log
│   └── errors.py                 # error log with recovery guidance
└── components/
    ├── __init__.py
    ├── phase_badge.py            # Tournament/Commit/Scale visual indicator
    ├── suppression_alert.py      # FYP rate alert banner
    └── sparkline.py              # retention/CTR trend charts
```

### `auth.py` Implementation Pattern

```python
import os
import streamlit as st

def check_password() -> bool:
    """Return True if the user is authenticated."""
    if st.session_state.get("authenticated"):
        return True
    password = os.environ["DASHBOARD_PASSWORD"]  # Fail explicitly if unset
    entered = st.text_input("Dashboard Password", type="password")
    if st.button("Login"):
        if entered == password:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password")
    return False
```

### `app.py` Implementation Pattern

```python
import os
from datetime import datetime
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from dashboard.auth import check_password

if not check_password():
    st.stop()

st_autorefresh(interval=60_000, key="autorefresh")

st.title("TikTok Faceless Dashboard")
st.caption(f"Last updated: {datetime.utcnow().strftime('%H:%M:%S UTC')}")
```

### Testing Pattern for Streamlit

Streamlit functions require mocking `st.*` calls. Use `unittest.mock.patch` for each Streamlit function used:

```python
from unittest.mock import MagicMock, patch

def test_check_password_returns_true_when_session_authenticated():
    with patch("streamlit.session_state", {"authenticated": True}):
        from dashboard.auth import check_password
        assert check_password() is True
```

Or use `unittest.mock.MagicMock` for `st.session_state` dict access. Pattern from other tests:
- Patch `dashboard.auth.st.session_state` as a dict mock
- Patch `dashboard.auth.st.text_input` to return a string
- Patch `dashboard.auth.st.button` to return True/False
- Patch `dashboard.auth.st.error` to verify it's called

### Environment Variable Convention

```python
os.environ["DASHBOARD_PASSWORD"]  # KeyError if missing — GOOD (fail fast)
```

Do NOT use `os.environ.get("DASHBOARD_PASSWORD", "")` — empty default would allow any password to pass.

### Dependencies

Add to `pyproject.toml`:
```toml
streamlit = ">=1.35.0"
streamlit-autorefresh = ">=1.0.0"
```

Check current `pyproject.toml` for existing optional dependency groups before adding.

### `streamlit-autorefresh` Usage

```python
from streamlit_autorefresh import st_autorefresh
count = st_autorefresh(interval=60_000, key="autorefresh")  # interval in milliseconds
```

The `count` return value increments each refresh cycle — useful for triggering data reload.

### Project Conventions (from previous stories)

- Import sort: stdlib → third-party → local (ruff enforced)
- Line length ≤ 100 chars
- No bare `except Exception` — catch typed exceptions
- No function-level imports
- `datetime.utcnow()` for naive UTC timestamps
- Run `uv run pytest tests/unit/ -q` to verify no regressions (currently 325 passing)
- Run `uv run ruff check dashboard/ tests/unit/dashboard/` after implementation

### Previous Story Learnings (Stories 5.1–5.4)

- Explicit `session.commit()` inside each write helper (not in caller)
- Module-level imports only — no function-level imports
- `agent_health.get("agent") is False` for explicit False check (not just falsy)
- Patch at import site (e.g., `tiktok_faceless.main.resume_agent_queue`) not at module origin when modules are imported at module level
- Tests: mock only DB/network side effects in autouse; pure logic helpers patched per-test

### References

- Epic 6 spec: `_bmad-output/planning-artifacts/epics.md` — Story 6.1
- Architecture dashboard section: `_bmad-output/planning-artifacts/architecture.md` — Dashboard Boundary
- Architecture auth: `_bmad-output/planning-artifacts/architecture.md` — Authentication & Security
- Streamlit docs: https://docs.streamlit.io
- streamlit-autorefresh: https://github.com/kmcgrady/streamlit-autorefresh

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List

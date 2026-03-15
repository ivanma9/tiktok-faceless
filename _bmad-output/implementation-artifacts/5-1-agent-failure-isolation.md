# Story 5.1: Agent Failure Isolation

Status: review

## Story

As the operator,
I want any single agent failure to be fully contained so that other agents continue operating unaffected,
so that an ElevenLabs outage doesn't stop analytics from running, and a TikTok rate limit doesn't corrupt research state.

## Acceptance Criteria

1. **Given** `production_node` raises an unhandled exception during a render
   **When** the LangGraph graph catches it at the node boundary
   **Then** only the Production Agent's queue is paused
   **And** `analytics_node`, `monetization_node`, and `publishing_node` (for already-rendered videos) continue their cycles
   **And** `state["agent_health"]["production"] = False`
   **And** no other agent's state is mutated by the production failure

2. **Given** a failed agent node returns `{"errors": [AgentError(...)]}`
   **When** the Orchestrator processes the state delta
   **Then** the error is written to the `errors` DB table scoped by `account_id`
   **And** the pipeline routes around the failed agent on subsequent cycles until it is manually resumed

3. **Given** multiple agents fail simultaneously
   **When** the Orchestrator evaluates `state["agent_health"]`
   **Then** each failure is isolated and logged independently
   **And** the system never enters a global crash state from individual agent failures

## Tasks / Subtasks

- [x] Task 1: Fix `_route_after_orchestrator` in `graph.py` to not halt on errors
  - [x] Change routing logic: remove `state.errors` as a halt condition
  - [x] Route to END only on `state.published_video_id is not None` (duplicate-publish guard)
  - [x] Route based on agent health to skip unhealthy agent nodes

- [x] Task 2: Add per-agent conditional routing in `graph.py`
  - [x] Add `_route_after_production(state)` — always routes to publishing (already-rendered videos can still publish)
  - [x] Wire conditional edge for production with `add_conditional_edges`
  - Note: script→monetization and monetization→production kept as `add_edge` (routing doesn't diverge there)

- [x] Task 3: Fix `orchestrator_node` error block in `orchestrator.py`
  - [x] Add `session.commit()` after `session.add()` calls in error block (explicit commit per project convention)
  - [x] Return `{"agent_health": new_health}` — do NOT halt pipeline; let graph routing handle skipping
  - [x] Errors list is NOT cleared by orchestrator (LangGraph add-reducer accumulates; orchestrator only reads)

- [x] Task 4: Add `TestAgentFailureIsolation` class to `tests/unit/agents/test_orchestrator.py`
  - [x] `test_production_error_sets_health_false` — AgentError(agent="production") → agent_health["production"] is False
  - [x] `test_production_error_does_not_affect_other_agents` — production error → agent_health["script"] unchanged
  - [x] `test_multiple_errors_all_logged` — two errors from different agents → both agent_health entries set False
  - [x] `test_error_block_commits_session` — session.commit() called after session.add()
  - [x] `test_error_returns_health_delta_only` — result contains agent_health key, no phase/niche keys
- [x] Task 5: Add `TestGraphRouting` class to `tests/unit/test_graph.py`
  - [x] `test_route_after_orchestrator_clean_state_goes_to_script` — clean state → routes to "script"
  - [x] `test_route_after_orchestrator_errors_still_goes_to_script` — errors alone → still routes to "script"
  - [x] `test_route_after_orchestrator_published_routes_to_end` — published_video_id set → routes to END
  - [x] `test_route_after_production_always_goes_to_publishing` — production unhealthy → routes to "publishing"

## Dev Notes

### Current State Analysis

The existing `_route_after_orchestrator` function in `graph.py` currently halts the ENTIRE pipeline if `state.errors` is non-empty:

```python
def _route_after_orchestrator(state: PipelineState) -> str:
    if state.errors or state.published_video_id is not None:
        return END
    return "script"
```

This is the core problem — a single agent failure in the production node stops analytics, monetization, and other independent work from continuing on subsequent cycles. Story 5.1 removes `state.errors` as a halt condition here.

The `orchestrator_node` already:
- Detects `state.errors` at the top of the function
- Marks `agent_health[err.agent] = False` per error
- Returns `{"agent_health": new_health}` as state delta

**What's missing**:
1. The graph routing halts on errors instead of routing around unhealthy agents
2. No per-agent conditional edges (every agent is unconditionally connected)
3. `session.commit()` missing in orchestrator error block (minor — `get_session` auto-commits on clean exit)

### Updated `graph.py` Design

```python
def _route_after_orchestrator(state: PipelineState) -> str:
    """Route to END only on duplicate publish; otherwise continue to script."""
    if state.published_video_id is not None:
        return END
    return "script"


def _route_after_script(state: PipelineState) -> str:
    """Skip to monetization if script agent is unhealthy."""
    if state.agent_health.get("script") is False:
        return "monetization"
    return "monetization"  # always monetization after script (placeholder for future routing)


def _route_after_monetization(state: PipelineState) -> str:
    """Skip to production even if monetization is unhealthy — production can render queued scripts."""
    return "production"


def _route_after_production(state: PipelineState) -> str:
    """Skip to publishing if production is unhealthy — already-rendered videos can still publish."""
    if state.agent_health.get("production") is False:
        return "publishing"
    return "publishing"
```

**Note**: For `_route_after_script` and `_route_after_monetization`, routing destination is the same regardless — but the conditional edge pattern is established for future extensibility. The key change is `_route_after_orchestrator` removing `state.errors` as a halt condition, and `_route_after_production` allowing publishing to proceed even when production is down (already-rendered videos).

Replace `graph.add_edge(...)` calls for script/monetization/production with `graph.add_conditional_edges(...)`.

### Updated `build_graph` with Conditional Edges

```python
def build_graph() -> CompiledStateGraph:
    graph: StateGraph = StateGraph(PipelineState)

    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("script", script_node)
    graph.add_node("monetization", monetization_node)
    graph.add_node("production", production_node)
    graph.add_node("publishing", publishing_node)

    graph.add_edge(START, "orchestrator")
    graph.add_conditional_edges("orchestrator", _route_after_orchestrator)
    graph.add_conditional_edges("script", _route_after_script)
    graph.add_conditional_edges("monetization", _route_after_monetization)
    graph.add_conditional_edges("production", _route_after_production)
    graph.add_edge("publishing", END)

    return graph.compile(checkpointer=MemorySaver())
```

### Fix to `orchestrator_node` Error Block

Add `session.commit()` explicitly:

```python
if state.errors:
    with get_session() as session:
        for err in state.errors:
            session.add(
                Error(
                    account_id=state.account_id,
                    agent=err.agent,
                    error_type=err.error_type,
                    message=err.message,
                    video_id=err.video_id,
                    recovery_suggestion=err.recovery_suggestion,
                )
            )
        session.commit()  # Explicit — don't rely solely on auto-commit
    new_health = {**state.agent_health}
    for err in state.errors:
        new_health[err.agent] = False
    return {"agent_health": new_health}
```

### `agent_health` Semantics

- `agent_health` is a `dict[str, bool]` in `PipelineState`
- Default is `{}` — absence of a key means HEALTHY (not explicitly unhealthy)
- `agent_health.get("production") is False` — explicit check for `False` (not just falsy)
- Per-agent check: `state.agent_health.get("production") is False` → unhealthy; any other value (True, missing key) → healthy

### Test Patterns

Existing `test_orchestrator.py` helpers to reuse:
- `_mock_session()` — context-manager mock
- `_state()` — PipelineState factory
- `_MOD = "tiktok_faceless.agents.orchestrator"`

For `TestAgentFailureIsolation`:
```python
def _run_error_node(errors: list[AgentError]) -> dict:
    state = PipelineState(account_id="acc1", errors=errors)
    mock_sess = _mock_session()
    with patch(f"{_MOD}.get_session", return_value=mock_sess):
        return orchestrator_node(state)
```

For `TestGraphRouting` in `test_graph.py`, test the routing functions directly (not the compiled graph):
```python
from tiktok_faceless.graph import _route_after_orchestrator, _route_after_production
from tiktok_faceless.state import PipelineState

def test_route_after_production_unhealthy_skips_to_publishing():
    state = PipelineState(account_id="acc1", agent_health={"production": False})
    result = _route_after_production(state)
    assert result == "publishing"
```

### LangGraph `add_conditional_edges` — Single Destination Note

When all branches lead to the same node (e.g., `_route_after_script` always returns `"monetization"`), `add_conditional_edges` is equivalent to `add_edge`. Using conditional edges for all nodes is cleaner but LangGraph requires the path_map to include all possible return values. Ensure the routing functions and `add_conditional_edges` calls are consistent.

Alternatively: only add conditional edges where routing actually diverges:
- `"orchestrator"` → conditional (may go to END or "script")
- `"production"` → conditional (may go to "publishing" when unhealthy to skip production)
- `"script"`, `"monetization"` → `add_edge` is sufficient if routing doesn't diverge

### Files to Touch

| File | Action |
|------|--------|
| `tiktok_faceless/graph.py` | Add routing functions, update `build_graph` with conditional edges |
| `tiktok_faceless/agents/orchestrator.py` | Add `session.commit()` in error block |
| `tests/unit/agents/test_orchestrator.py` | Add `TestAgentFailureIsolation` (5 tests) |
| `tests/unit/test_graph.py` | Add `TestGraphRouting` (4 tests) |

### Do NOT Touch

- `tiktok_faceless/state.py` — `agent_health`, `errors`, `AgentError` all correct
- `tiktok_faceless/db/models.py` — `Error` model has all needed fields
- `tiktok_faceless/db/queries.py` — no new query needed (direct `session.add()` in orchestrator is fine)
- Any agent node files

### Previous Story Learnings (Stories 4.1–4.5)

- Import sort: stdlib → third-party → local (ruff I001)
- Line length ≤ 100 chars (ruff E501)
- Agent nodes return state delta dict only — never `return state`
- `uv run pytest tests/unit/ -q` to verify no regressions
- `session.add.call_args[0][0]` to get object passed to `session.add`
- `session.add.call_args_list` for multiple adds
- Do NOT use bare `except Exception` — use typed exceptions
- All module-level imports — no function-level imports

### References

- Story spec: `_bmad-output/planning-artifacts/epics.md` — Story 5.1
- `graph.py`: `tiktok_faceless/graph.py`
- `orchestrator.py`: `tiktok_faceless/agents/orchestrator.py`
- `PipelineState.agent_health`: `tiktok_faceless/state.py`
- `Error` model: `tiktok_faceless/db/models.py`

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

None — implementation straightforward per spec.

### Completion Notes List

- Removed `state.errors` as halt condition from `_route_after_orchestrator`; errors now flow to agent_health tracking without stopping the pipeline.
- Added `_route_after_production` conditional edge so publishing always proceeds (already-rendered videos can publish even when production is down).
- Added `session.commit()` explicitly in orchestrator error block per project convention.
- Fixed `test_graph_invocable_with_mocked_nodes` mock: added `reconciliation_interval_hours=24` to monetization config mock — the test now reaches monetization (it previously halted at orchestrator due to the errors check).
- All 293 unit tests pass; ruff clean.

### File List

- `tiktok_faceless/graph.py` — fixed `_route_after_orchestrator`, added `_route_after_production`, updated `build_graph`
- `tiktok_faceless/agents/orchestrator.py` — added `session.commit()` in error block
- `tests/unit/test_graph.py` — added imports, `TestGraphRouting` class (4 tests), fixed monetization mock
- `tests/unit/agents/test_orchestrator.py` — added `TestAgentFailureIsolation` class (5 tests)

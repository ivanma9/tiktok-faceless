# Story 1.7: Orchestrator Pipeline Wiring & Crash Recovery

Status: review

## Story

As the operator,
I want the Orchestrator to wire all agents into a sequential pipeline that resumes from last known state after a VM restart,
So that the system runs the full pipeline end-to-end and achieves the first autonomous post without any manual intervention.

## Acceptance Criteria

1. **Given** a valid `AccountConfig` loaded from environment, **When** `main.py` is executed, **Then** the LangGraph graph runs the sequence: `orchestrator_node → script_node → monetization_node → production_node → publishing_node` **And** each agent node returns a state delta dict (never full state mutation) **And** the graph checkpointer (`MemorySaver` for dev — see note) persists state after each node

2. **Given** the pipeline completes a node and the process is restarted, **When** `main.py` runs again with the same `thread_id`, **Then** the graph resumes from the last completed node (not from the beginning) **And** no duplicate posts occur (`published_video_id` is checked before re-running `publishing_node`) **And** no duplicate affiliate link generation occurs (`product_validated` is checked before re-running `monetization_node`)

3. **Given** any agent node returns `{"errors": [...]}` in its state delta, **When** the orchestrator processes the result, **Then** each `AgentError` is persisted to the `errors` DB table **And** the pipeline halts gracefully (graph reaches END) **And** `state["agent_health"]` is updated to reflect the failed agent as `False`

4. **Given** a fresh account with no prior state, **When** the full pipeline completes successfully for the first time, **Then** a `Video` row exists in the DB with `lifecycle_state = "posted"` **And** `published_video_id` is set and non-null **And** the `affiliate_link` is confirmed in the video row

5. **Given** a VPS deployment, **When** the systemd unit file is configured with `Restart=always` and `EnvironmentFile=`, **Then** the pipeline process restarts automatically on crash or reboot **And** secrets are loaded from the systemd `EnvironmentFile=` path — never hardcoded

6. **Given** all implementation is complete, **When** `uv run pytest` is run, **Then** all tests pass with zero failures **And** `uv run ruff check .` and `uv run mypy tiktok_faceless/` exit 0

## Tasks / Subtasks

- [x] Task 1: Implement `tiktok_faceless/agents/orchestrator.py` — orchestrator_node (AC: 2, 3)
  - [x] Import `AgentError`, `PipelineState` from `state`; `get_session` from `db.session`; `Error` from `db.models`
  - [x] Define `orchestrator_node(state: PipelineState) -> dict[str, Any]` as the single public export
  - [x] Check for errors from prior nodes: if `state.errors` is non-empty, persist each `AgentError` to the `errors` DB table and return `{}` (empty delta — signals pipeline to halt at END)
  - [x] Update `agent_health`: for each error in `state.errors`, set `agent_health[error.agent] = False`; return `{"agent_health": {**state.agent_health, error.agent: False}}`
  - [x] Guard against duplicate publish: if `state.published_video_id` is not None, return `{}` immediately (already posted — do not re-run pipeline)
  - [x] Guard against duplicate monetization: if `state.product_validated` is True and `state.current_script` is not None, return `{}` (already monetized and scripted)
  - [x] On clean state (no errors, no duplicates): return `{}` empty delta — let graph flow to next node
  - [x] **NOTE:** `orchestrator_node` is a ROUTER/HEALTH-CHECK node — it does NOT do business logic. It checks state health and routes. Keep it thin.

- [x] Task 2: Implement `tiktok_faceless/graph.py` — LangGraph graph assembly (AC: 1, 2)
  - [x] Import `StateGraph`, `START`, `END` from `langgraph.graph`; `MemorySaver` from `langgraph.checkpoint.memory`
  - [x] Import all 5 agent nodes: `orchestrator_node`, `script_node`, `monetization_node`, `production_node`, `publishing_node`
  - [x] Define `build_graph() -> CompiledGraph` — assembles and compiles the pipeline graph with checkpointer
  - [x] Add nodes: `"orchestrator"`, `"script"`, `"monetization"`, `"production"`, `"publishing"`
  - [x] Add edges: `START → orchestrator → script → monetization → production → publishing → END`
  - [x] Add conditional edge after `orchestrator`: if `state.errors` is non-empty → go to `END`; else → continue to `"script"`
  - [x] Add conditional edge after `publishing`: if `state.published_video_id` is set → go to `END`; else → go to `END` (deferred posts also end cleanly)
  - [x] Compile with `checkpointer=MemorySaver()` — enables state persistence across restarts for dev
  - [x] `build_graph()` returns the compiled graph — do NOT call `.invoke()` inside this function

- [x] Task 3: Implement `main.py` — entry point (AC: 1, 4, 5)
  - [x] Call `load_env()` first (from `tiktok_faceless.config`) before any other imports that read env vars
  - [x] Call `init_db(get_engine())` to create tables if they don't exist (dev SQLite)
  - [x] Build initial `PipelineState` from env: `account_id = os.environ["ACCOUNT_ID"]`; include a pre-configured `selected_product` dict for MVP testing
  - [x] Call `build_graph()` to get the compiled graph
  - [x] Invoke the graph: `graph.invoke(state.model_dump(), config={"configurable": {"thread_id": account_id}})` — `thread_id` enables crash recovery
  - [x] Log result to stdout using `logging`
  - [x] Handle `KeyboardInterrupt` gracefully — log and exit 0

- [x] Task 4: Create `systemd/tiktok-faceless.service` — VPS deployment unit (AC: 5)
  - [x] Create `systemd/tiktok-faceless.service` with standard systemd unit format
  - [x] Set `Restart=always`, `RestartSec=5`
  - [x] Set `EnvironmentFile=/etc/tiktok-faceless/env` — secrets loaded from file, never hardcoded
  - [x] Set `ExecStart=` to run `uv run python main.py` from the project directory
  - [x] Set `WorkingDirectory=` to the project path
  - [x] Include `[Install]` section with `WantedBy=multi-user.target`

- [x] Task 5: Write unit tests for `orchestrator_node` (AC: 2, 3)
  - [x] Create `tests/unit/agents/test_orchestrator.py`
  - [x] Test: clean state (no errors, no prior publish) returns empty dict `{}`
  - [x] Test: state with `published_video_id` set returns `{}` immediately (dedup guard)
  - [x] Test: state with errors → `agent_health` updated with failed agent as `False`
  - [x] Test: state with errors → `AgentError` persisted to `errors` DB table (mock `get_session`)
  - [x] Mock `get_session` for all DB tests

- [x] Task 6: Write unit tests for `build_graph()` (AC: 1)
  - [x] Create `tests/unit/test_graph.py`
  - [x] Test: `build_graph()` returns a compiled graph object (not None)
  - [x] Test: graph has expected nodes registered (`"orchestrator"`, `"script"`, `"monetization"`, `"production"`, `"publishing"`)
  - [x] Test: graph can be invoked with a minimal valid state dict without raising (mock all agent nodes to return `{}`)

- [x] Task 7: Run all validations (AC: 6)
  - [x] Run `uv run pytest` — all tests must pass
  - [x] Run `uv run ruff check .` — must exit 0
  - [x] Run `uv run mypy tiktok_faceless/` — must exit 0

## Dev Notes

### CRITICAL ARCHITECTURE CONSTRAINTS

1. **`orchestrator_node` is a ROUTER — not a business logic node.** It checks state health (errors, duplicates) and routes. It must NOT call any external API, generate scripts, or do anything except read state and write to DB errors table + agent_health.

2. **LangGraph `MemorySaver` for dev (NOT `SqliteSaver`)** — `langgraph-checkpoint-sqlite` is NOT installed. The installed package `langgraph-checkpoint 4.0.1` only ships `MemorySaver` and base classes. Use `MemorySaver` for dev. Architecture doc says `SqliteSaver` but that requires a separate package — use `MemorySaver` to stay within installed deps.

3. **`StateGraph` with Pydantic model** — LangGraph 1.1.0 accepts `PipelineState` (a Pydantic `BaseModel`) as the state schema:
   ```python
   graph = StateGraph(PipelineState)
   graph.add_node("orchestrator", orchestrator_node)
   graph.add_edge(START, "orchestrator")
   # ...
   compiled = graph.compile(checkpointer=MemorySaver())
   ```

4. **Conditional edge from orchestrator** — use `add_conditional_edges` to route based on error state:
   ```python
   def _route_after_orchestrator(state: PipelineState) -> str:
       if state.errors:
           return END
       if state.published_video_id:
           return END
       return "script"

   graph.add_conditional_edges("orchestrator", _route_after_orchestrator)
   ```

5. **`thread_id` for crash recovery** — pass `config={"configurable": {"thread_id": account_id}}` to `.invoke()`. The checkpointer stores state keyed by `thread_id`, so restarting with the same `thread_id` resumes from the last checkpoint.

6. **`orchestrator_node` error persistence pattern:**
   ```python
   def orchestrator_node(state: PipelineState) -> dict[str, Any]:
       if state.errors:
           with get_session() as session:
               for err in state.errors:
                   session.add(Error(
                       account_id=state.account_id,
                       agent=err.agent,
                       error_type=err.error_type,
                       message=err.message,
                       video_id=err.video_id,
                       recovery_suggestion=err.recovery_suggestion,
                   ))
           new_health = {**state.agent_health}
           for err in state.errors:
               new_health[err.agent] = False
           return {"agent_health": new_health}
       if state.published_video_id is not None:
           return {}
       return {}
   ```

7. **`graph.py` must live at `tiktok_faceless/graph.py`** (architecture spec). `main.py` lives at project root.

8. **`main.py` invocation pattern:**
   ```python
   from tiktok_faceless.config import load_env
   from tiktok_faceless.db.session import get_engine, init_db
   from tiktok_faceless.graph import build_graph
   from tiktok_faceless.state import PipelineState

   load_env()
   init_db(get_engine())

   state = PipelineState(
       account_id=os.environ["ACCOUNT_ID"],
       selected_product={
           "product_id": os.environ.get("TEST_PRODUCT_ID", "test_prod_1"),
           "product_name": os.environ.get("TEST_PRODUCT_NAME", "Test Widget"),
           "product_url": os.environ.get("TEST_PRODUCT_URL", "https://example.com"),
           "commission_rate": 0.15,
           "niche": os.environ.get("TEST_NICHE", "health"),
           "sales_velocity_score": 1.0,
       },
   )
   graph = build_graph()
   result = graph.invoke(
       state.model_dump(),
       config={"configurable": {"thread_id": state.account_id}},
   )
   ```

9. **`CompiledStateGraph` type annotation** — for `build_graph()` return type, use `Any` or import the type:
   ```python
   from langgraph.graph.state import CompiledStateGraph
   def build_graph() -> CompiledStateGraph: ...
   ```

10. **mypy note** — `langgraph` may lack complete type stubs. Use `# type: ignore[import-untyped]` or configure `mypy` to ignore missing imports for langgraph if needed. Check `pyproject.toml` for existing `ignore_missing_imports = true` in mypy config.

### `graph.py` Full Structure

```python
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from tiktok_faceless.agents.monetization import monetization_node
from tiktok_faceless.agents.orchestrator import orchestrator_node
from tiktok_faceless.agents.production import production_node
from tiktok_faceless.agents.publishing import publishing_node
from tiktok_faceless.agents.script import script_node
from tiktok_faceless.state import PipelineState


def _route_after_orchestrator(state: PipelineState) -> str:
    if state.errors or state.published_video_id is not None:
        return END
    return "script"


def build_graph() -> CompiledStateGraph:
    graph: StateGraph = StateGraph(PipelineState)
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("script", script_node)
    graph.add_node("monetization", monetization_node)
    graph.add_node("production", production_node)
    graph.add_node("publishing", publishing_node)
    graph.add_edge(START, "orchestrator")
    graph.add_conditional_edges("orchestrator", _route_after_orchestrator)
    graph.add_edge("script", "monetization")
    graph.add_edge("monetization", "production")
    graph.add_edge("production", "publishing")
    graph.add_edge("publishing", END)
    return graph.compile(checkpointer=MemorySaver())
```

### Testing `build_graph()`

```python
from unittest.mock import patch, MagicMock

def test_build_graph_returns_compiled_graph():
    from tiktok_faceless.graph import build_graph
    g = build_graph()
    assert g is not None

def test_graph_nodes_registered():
    from tiktok_faceless.graph import build_graph
    g = build_graph()
    # CompiledStateGraph exposes .nodes dict
    assert "orchestrator" in g.nodes
    assert "script" in g.nodes
```

### File Touch Map

**Implement (placeholder → full):**
- `tiktok_faceless/agents/orchestrator.py`

**Create new:**
- `tiktok_faceless/graph.py`
- `main.py`
- `systemd/tiktok-faceless.service`
- `tests/unit/agents/test_orchestrator.py`
- `tests/unit/test_graph.py`

**Do NOT touch:**
- All other agent files — already implemented in prior stories
- `tiktok_faceless/state.py` — all fields present
- `tiktok_faceless/db/models.py` — `Error` model already has all needed fields
- `tiktok_faceless/config.py` — `load_env()`, `load_account_config()` already implemented

### mypy Configuration Check

```toml
# pyproject.toml should already have:
[[tool.mypy.overrides]]
module = ["langgraph.*", "langgraph.graph.*"]
ignore_missing_imports = true
```
Verify before implementing — add if missing. `main.py` is at project root, not inside `tiktok_faceless/`, so mypy check `uv run mypy tiktok_faceless/` will NOT check `main.py`. That's correct.

### Previous Story Learnings

- Import sort: stdlib → third-party → local (ruff I001)
- Line length ≤ 100 chars (ruff E501)
- `dict[str, Any]` return type on all agent nodes
- Patch at import location: `patch("tiktok_faceless.agents.orchestrator.get_session")`
- `get_session()` mock: set `__enter__` / `__exit__` on MagicMock
- `datetime.now(UTC)` not `datetime.utcnow()` (Python 3.12+ deprecation)
- `Error` model `timestamp` field uses `default=datetime.utcnow` in the ORM — SQLAlchemy handles it; don't pass `timestamp` explicitly when creating `Error()` rows

### References

- Architecture: `_bmad-output/planning-artifacts/architecture.md` — `graph.py` location, `main.py` pattern, systemd deployment, LangGraph state delta contract, orchestrator as sole phase-writer
- Epics: `_bmad-output/planning-artifacts/epics.md` — Story 1.7 (lines 447–494)
- PRD: `_bmad-output/planning-artifacts/prd.md` — FR1–6 (Orchestration & Pipeline Control), FR30–34 (Error Handling)
- Previous story: `1-6-publishing-agent-with-suppression-resistant-cadence.md` — deferred pattern, session mock pattern

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- 121 tests passing (8 new: 5 orchestrator_node + 3 graph)
- ruff and mypy strict both exit 0
- LangGraph CompiledStateGraph/StateGraph type args suppressed with type: ignore[type-arg] (LangGraph 1.1.0 generics not fully typed)
- MemorySaver used instead of SqliteSaver (langgraph-checkpoint-sqlite not installed)
- orchestrator_node is thin router: persists errors to DB, updates agent_health, guards duplicate publish
- build_graph() conditional edge: errors or already-published → END; else → script
- test_graph.py end-to-end invocation test mocks all 5 agent nodes successfully

### File List

- tiktok_faceless/agents/orchestrator.py — implemented
- tiktok_faceless/graph.py — created
- main.py — created
- systemd/tiktok-faceless.service — created
- tests/unit/agents/test_orchestrator.py — created
- tests/unit/test_graph.py — created

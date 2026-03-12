# Story 1.5: Basic Script & Affiliate Link Generation

Status: review

## Story

As the operator,
I want the Script Agent to generate a basic video script and the Monetization Agent to attach a valid TikTok Shop affiliate link,
So that every video produced has monetization built in before it ever reaches the Production Agent — and no video is ever posted without one.

## Acceptance Criteria

1. **Given** a `PipelineState` with `selected_product` populated, **When** `script_node(state)` is called, **Then** `LLMClient.generate_script()` is called with the product details **And** `state["current_script"]` is set to a non-empty script string **And** `state["hook_archetype"]` is set to one of the 4 valid hook types

2. **Given** a `PipelineState` with `selected_product` populated, **When** `monetization_node(state)` is called, **Then** `TikTokAPIClient.generate_affiliate_link()` is called with the product_id extracted from `selected_product` **And** the affiliate link is stored in the `videos` DB table row for this video **And** `state["product_validated"]` is set to `True` confirming the link was successfully generated

3. **Given** affiliate link generation fails with a `TikTokAPIError`, `TikTokRateLimitError`, or `TikTokAuthError`, **When** `monetization_node` catches the error, **Then** it returns `{"errors": [AgentError(agent="monetization", error_type="...", ...)]}` **And** `state["product_validated"]` remains `False` — pipeline halts before production (NFR12)

4. **Given** `LLMClient.generate_script()` raises `LLMError`, **When** `script_node` catches the error, **Then** it returns `{"errors": [AgentError(agent="script", error_type="LLMError", ...)]}` **And** `current_script` and `hook_archetype` remain unset

5. **Given** a `PipelineState` with `selected_product` equal to `None`, **When** `script_node(state)` is called, **Then** it returns `{"errors": [AgentError(agent="script", error_type="MissingProduct", ...)]}` immediately

6. **Given** a successfully generated script and affiliate link, **When** the video DB row is inspected, **Then** `affiliate_link` is populated, `script_text` is populated, and `lifecycle_state` is `queued`

7. **Given** all implementation is complete, **When** `uv run pytest` is run, **Then** all tests pass with zero failures **And** `uv run ruff check .` and `uv run mypy tiktok_faceless/` exit 0

## Tasks / Subtasks

- [x] Task 1: Implement `tiktok_faceless/agents/script.py` — script_node (AC: 1, 4, 5)
  - [x] Import `LLMClient` from `clients.llm`, `LLMError` from `clients`, `AgentError` + `PipelineState` from `state`, `load_account_config` from `config`
  - [x] Define `VALID_HOOK_ARCHETYPES: list[str] = ["curiosity_gap", "social_proof", "controversy", "demonstration"]`
  - [x] Define `script_node(state: PipelineState) -> dict[str, Any]` as the single public export
  - [x] Guard: if `state.selected_product is None`, return `{"errors": [AgentError(agent="script", error_type="MissingProduct", message="selected_product is None — cannot generate script without a product")]}` immediately
  - [x] Build LLM prompt from `state.selected_product` (include product_name, product_url, niche, commission_rate from dict keys)
  - [x] Use `random.choice(VALID_HOOK_ARCHETYPES)` to select hook_archetype before calling LLM
  - [x] Include the chosen `hook_archetype` in the prompt so the script style matches the archetype
  - [x] Call `LLMClient(api_key=config.anthropic_api_key).generate_script(prompt=prompt)` with try/except `LLMError`
  - [x] Validate response is non-empty string; raise `LLMError` if blank
  - [x] Return `{"current_script": script_text, "hook_archetype": hook_archetype}` on success
  - [x] Wrap in try/except `LLMError` → return `AgentError` delta, exit early

- [x] Task 2: Implement `tiktok_faceless/agents/monetization.py` — monetization_node (AC: 2, 3, 6)
  - [x] Import `TikTokAPIClient` from `clients.tiktok`, `TikTokAPIError`, `TikTokRateLimitError`, `TikTokAuthError` from `clients`, `AgentError` + `PipelineState` from `state`, `load_account_config` from `config`, `get_session` from `db.session`, `Video` from `db.models`
  - [x] Define `monetization_node(state: PipelineState) -> dict[str, Any]` as the single public export
  - [x] Guard: if `state.selected_product is None`, return `{"errors": [AgentError(agent="monetization", error_type="MissingProduct", message="selected_product is None — cannot generate affiliate link without a product")]}` immediately
  - [x] Extract `product_id` from `state.selected_product["product_id"]`
  - [x] Build `TikTokAPIClient(access_token=config.tiktok_access_token, open_id=config.tiktok_open_id)`
  - [x] Call `client.generate_affiliate_link(account_id=state.account_id, product_id=product_id)` with try/except `(TikTokAPIError, TikTokRateLimitError, TikTokAuthError)`
  - [x] On success: open DB session with `get_session()`, find or create a `Video` row for the current pipeline run, set `affiliate_link` and `product_id`, commit
  - [x] Return `{"product_validated": True}` on success
  - [x] On exception: map to appropriate `error_type` string (`"TikTokAPIError"`, `"TikTokRateLimitError"`, `"TikTokAuthError"`), return `{"errors": [AgentError(...)]}` with `product_validated` remaining `False`
  - [x] **NOTE:** For MVP, Video row lookup uses `state.account_id` + most-recently-created `lifecycle_state == "queued"` row. Create if none exists (with placeholder `niche=state.committed_niche or "unknown"`)

- [x] Task 3: Write unit tests for `script_node` (AC: 1, 4, 5)
  - [x] Create `tests/unit/agents/test_script.py`
  - [x] Test: `selected_product=None` returns `AgentError` with `error_type="MissingProduct"` immediately
  - [x] Test: successful call returns `{"current_script": <non-empty str>, "hook_archetype": <valid str>}`
  - [x] Test: `hook_archetype` returned is one of `VALID_HOOK_ARCHETYPES`
  - [x] Test: `LLMError` from `generate_script` returns `AgentError` delta with `error_type="LLMError"`, no `current_script` key
  - [x] Mock `load_account_config` and `LLMClient` in all tests — no real API calls

- [x] Task 4: Write unit tests for `monetization_node` (AC: 2, 3)
  - [x] Create `tests/unit/agents/test_monetization.py`
  - [x] Test: `selected_product=None` returns `AgentError` with `error_type="MissingProduct"`
  - [x] Test: successful call returns `{"product_validated": True}`
  - [x] Test: `TikTokAPIError` → returns `AgentError` with `error_type="TikTokAPIError"`, no `product_validated: True`
  - [x] Test: `TikTokRateLimitError` → returns `AgentError` with `error_type="TikTokRateLimitError"`
  - [x] Test: `TikTokAuthError` → returns `AgentError` with `error_type="TikTokAuthError"`
  - [x] Mock `load_account_config`, `TikTokAPIClient`, and `get_session` in all tests — no real DB or API calls

- [x] Task 5: Run all validations (AC: 7)
  - [x] Run `uv run pytest` — all tests must pass
  - [x] Run `uv run ruff check .` — must exit 0
  - [x] Run `uv run mypy tiktok_faceless/` — must exit 0

## Dev Notes

### CRITICAL ARCHITECTURE CONSTRAINTS

1. **`script_node` and `monetization_node` are the ONLY public exports** from their respective files. No other functions are public.

2. **Return state DELTA only** — never return or mutate the full `PipelineState`. Only return the keys that changed:
   ```python
   # CORRECT
   return {"current_script": "Hook: Did you know...", "hook_archetype": "curiosity_gap"}

   # WRONG
   return state.model_dump()
   ```

3. **`selected_product` is a `dict | None`** in `PipelineState`. Access fields via dict keys (`state.selected_product["product_id"]`), not attribute access. The dict shape matches `AffiliateProduct` fields: `product_id`, `product_name`, `product_url`, `commission_rate`, `sales_velocity_score`, `niche`.

4. **NFR12 is critical:** No video ever proceeds to Production without `product_validated = True`. `monetization_node` must run before `production_node` in the pipeline. The agent must not silently swallow errors — always return `AgentError` delta on failure.

5. **LLMClient API:** `generate_script(prompt: str, max_tokens: int = 1024) -> str`. The method takes a raw string prompt — you must build the prompt from product details and hook_archetype. Use the existing `anthropic_api_key` from `AccountConfig`.

6. **Hook archetype selection is random per video** (ensures A/B testing variety for FR12). Use `random.choice(VALID_HOOK_ARCHETYPES)` before the LLM call.

7. **`VALID_HOOK_ARCHETYPES`** — defined at module level as a constant (not hardcoded inline):
   ```python
   VALID_HOOK_ARCHETYPES: list[str] = ["curiosity_gap", "social_proof", "controversy", "demonstration"]
   ```
   Source: PRD FR12 — "3 distinct hook archetype variants per product (e.g., curiosity gap, social proof, controversy, demonstration)". We implement 4 for variety.

8. **DB write in `monetization_node`** — use `get_session()` context manager from `db.session`. The `Video` ORM model has these relevant fields: `id` (UUID str), `account_id`, `niche`, `hook_archetype`, `lifecycle_state` (default `"queued"`), `script_text`, `affiliate_link`, `product_id`. For MVP, query for `Video` with matching `account_id` and `lifecycle_state == "queued"` ordered by `created_at DESC`, take first. Create if none exists.

### `script_node` Prompt Pattern

```python
def _build_script_prompt(product: dict, hook_archetype: str) -> str:
    return (
        f"You are a viral TikTok creator. Generate a short (<60s) video script "
        f"for a {hook_archetype.replace('_', ' ')} style hook.\n\n"
        f"Product: {product.get('product_name', 'Unknown Product')}\n"
        f"Niche: {product.get('niche', 'general')}\n"
        f"URL: {product.get('product_url', '')}\n"
        f"Commission: {product.get('commission_rate', 0):.0%}\n\n"
        f"Script (60 words max, no hashtags, end with clear CTA):"
    )
```
This is a suggested pattern — adapt as needed, but keep prompts focused and include the product URL for authenticity.

### `monetization_node` DB Pattern

```python
from tiktok_faceless.db.session import get_session
from tiktok_faceless.db.models import Video
import uuid

with get_session() as session:
    video = (
        session.query(Video)
        .filter_by(account_id=state.account_id, lifecycle_state="queued")
        .order_by(Video.created_at.desc())
        .first()
    )
    if video is None:
        video = Video(
            id=str(uuid.uuid4()),
            account_id=state.account_id,
            niche=state.committed_niche or "unknown",
        )
        session.add(video)
    video.affiliate_link = affiliate_link
    video.product_id = product_id
    # session.commit() handled by get_session() context manager
```

### Error Mapping Pattern

```python
except TikTokRateLimitError as e:
    return {"errors": [AgentError(agent="monetization", error_type="TikTokRateLimitError", message=str(e))]}
except TikTokAuthError as e:
    return {"errors": [AgentError(agent="monetization", error_type="TikTokAuthError", message=str(e))]}
except TikTokAPIError as e:
    return {"errors": [AgentError(agent="monetization", error_type="TikTokAPIError", message=str(e))]}
```
Catch from most-specific to least-specific (RateLimit before Auth before generic API).

### Testing Mocking Pattern

```python
# script_node test
def test_llm_error_returns_agent_error() -> None:
    state = PipelineState(
        account_id="acc1",
        selected_product={"product_id": "p1", "product_name": "Widget", "product_url": "https://example.com", "commission_rate": 0.15, "niche": "health"},
    )
    with patch("tiktok_faceless.agents.script.load_account_config", return_value=_mock_config()):
        with patch("tiktok_faceless.agents.script.LLMClient") as mock_llm_cls:
            mock_llm_cls.return_value.generate_script.side_effect = LLMError("Timeout")
            result = script_node(state)
    assert "errors" in result
    assert result["errors"][0].error_type == "LLMError"
    assert "current_script" not in result

# monetization_node test
def test_tiktok_api_error_returns_agent_error() -> None:
    state = PipelineState(account_id="acc1", selected_product={"product_id": "p1", ...})
    with patch("tiktok_faceless.agents.monetization.load_account_config", return_value=_mock_config()):
        with patch("tiktok_faceless.agents.monetization.TikTokAPIClient") as mock_tk:
            mock_tk.return_value.generate_affiliate_link.side_effect = TikTokAPIError("500")
            with patch("tiktok_faceless.agents.monetization.get_session"):
                result = monetization_node(state)
    assert result["errors"][0].error_type == "TikTokAPIError"
```

### File Touch Map

**Implement (placeholder → full):**
- `tiktok_faceless/agents/script.py`
- `tiktok_faceless/agents/monetization.py`

**Create new:**
- `tests/unit/agents/test_script.py`
- `tests/unit/agents/test_monetization.py`

**Do NOT touch:**
- `tiktok_faceless/state.py` — already has all required fields (`selected_product`, `product_validated`, `current_script`, `hook_archetype`)
- `tiktok_faceless/clients/llm.py` — `generate_script` already implemented
- `tiktok_faceless/clients/tiktok.py` — `generate_affiliate_link` already implemented
- `tiktok_faceless/db/models.py` — `Video` model already has `affiliate_link`, `product_id`, `script_text`
- Any other agent files

### Previous Story Learnings

- Import sort order is enforced by ruff I001 — always put stdlib first, then third-party, then local imports separated by blank lines
- Remove unused imports immediately (ruff F401)
- `dict[str, Any]` return type is the correct annotation for agent nodes
- Patch at the import location, not the definition location: `patch("tiktok_faceless.agents.script.LLMClient")` not `patch("tiktok_faceless.clients.llm.LLMClient")`
- `get_session()` is a context manager — always use with `with get_session() as session:`
- SQLAlchemy 2.0: use `session.query(Model).filter_by(...)` for simple queries in agent nodes (full 2.0 `select()` syntax is fine too)
- When mocking `get_session`, use `patch("tiktok_faceless.agents.monetization.get_session")` and configure as context manager mock: `mock_session.__enter__.return_value = mock_session_obj`

### References

- Architecture: `_bmad-output/planning-artifacts/architecture.md` — "Requirements to Structure Mapping" (FR11–13, FR27–29), pipeline flow diagram, `PipelineState` field definitions
- Epics: `_bmad-output/planning-artifacts/epics.md` — Story 1.5 (lines 380–411)
- PRD: `_bmad-output/planning-artifacts/prd.md` — FR11–13 (Script), FR27–29 (Monetization), NFR12
- Previous story: `1-4-video-production-agent.md` — error contract pattern, state delta pattern, mocking approach

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- All 96 tests passing (9 new for this story: 4 script_node + 5 monetization_node)
- ruff and mypy strict both exit 0
- `VALID_HOOK_ARCHETYPES` constant defined at module level in `script.py`; random selection per call ensures A/B variety
- `monetization_node` DB write uses `get_session()` context manager; creates new `Video` row if none queued
- NFR12 enforced: error returns do NOT set `product_validated=True`; pipeline halts before production
- Line-length E501 fixes applied to both test files and monetization.py

### File List

- `tiktok_faceless/agents/script.py` — implemented
- `tiktok_faceless/agents/monetization.py` — implemented
- `tests/unit/agents/test_script.py` — created
- `tests/unit/agents/test_monetization.py` — created

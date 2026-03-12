# Story 2.4: Full Script Generation with Hook Archetypes & Persona

Status: ready-for-dev

## Story

As the operator,
I want the Script Agent to generate 3 distinct hook archetype variants per product using buyer language, with the account persona applied consistently,
so that the system produces high-conversion scripts that A/B test hook effectiveness and maintain a recognizable account voice.

## Acceptance Criteria

1. **Given** a `PipelineState` with `selected_product` including `buyer_language`
   **When** `script_node(state)` is called
   **Then** `LLMClient.generate_script()` is called exactly 3 times — once per archetype in `THREE_HOOK_ARCHETYPES`
   **And** each call's prompt incorporates buyer-language phrases from `state["selected_product"]["buyer_language"]`
   **And** each call's prompt includes the account persona's name, catchphrases, and tone from `AccountConfig`

2. **Given** 3 script variants are generated
   **When** the returned state delta is inspected
   **Then** `state["current_script"]` is the script from the first variant (`curiosity_gap`)
   **And** `state["hook_archetype"]` is `"curiosity_gap"` (first archetype)
   **And** `state["hook_variants"]` is a list of 3 dicts, each with `archetype` and `script` keys

3. **Given** the LLM API returns an error on ANY of the 3 variant calls
   **When** `script_node` catches it
   **Then** an `AgentError` with `error_type="LLMError"` is returned
   **And** `current_script` is not set in the delta — pipeline halts before production
   **And** no partial `hook_variants` are returned

4. **Given** `selected_product` does not have a `buyer_language` key (older state)
   **When** `script_node` builds the prompt
   **Then** `buyer_language` is treated as an empty list — no `KeyError` raised
   **And** script generation proceeds normally with product details only

5. **Given** `selected_product` is `None`
   **When** `script_node` is called
   **Then** a `MissingProduct` `AgentError` is returned (unchanged behavior from Story 1.5)

## Tasks / Subtasks

- [ ] Task 7: Upgrade `script_node` to 3 hook variants with buyer language and persona (All ACs)
  - [ ] Replace `VALID_HOOK_ARCHETYPES` with `THREE_HOOK_ARCHETYPES = ["curiosity_gap", "social_proof", "controversy"]`
  - [ ] Add `hook_variants: list[dict] = Field(default_factory=list)` to `PipelineState` in `state.py`
  - [ ] Add persona fields to `AccountConfig` in `config.py` (see Schema Changes below)
  - [ ] Update `load_account_config()` to read persona env vars with safe defaults
  - [ ] Update `_build_script_prompt` to include buyer_language phrases and persona fields
  - [ ] Refactor `script_node` to loop over `THREE_HOOK_ARCHETYPES`, calling LLM once per archetype
  - [ ] On any `LLMError`, return `AgentError` immediately (all-or-nothing — no partial variants)
  - [ ] Return delta: `{"current_script": ..., "hook_archetype": "curiosity_gap", "hook_variants": [...]}`
  - [ ] Add `hook_variants` column to `videos` DB table (see DB Change below)
  - [ ] Tests in `tests/unit/agents/test_script.py` — new class `TestScriptNodeHookVariants`

## Dev Notes

### Critical Architecture Rules

- **Agent node returns state delta dict only** — never `return state`, never mutate `state` in place
- **Never call external APIs directly** — always through `LLMClient`
- **All fatal errors returned as `AgentError`** in `{"errors": [AgentError(...)]}` delta
- **All-or-nothing on variant generation** — if any of the 3 LLM calls fails, the entire node fails
- **No `random.choice`** — hook archetype selection is now deterministic: always `THREE_HOOK_ARCHETYPES[0]` as primary

### Schema Changes

#### `tiktok_faceless/state.py` — Add `hook_variants`

```python
hook_variants: list[dict] = Field(default_factory=list)  # type: ignore[type-arg]
```

Add after the existing `hook_archetype` field (line 56). The field is not annotated with `add` reducer — it is replaced wholesale each run, not appended.

#### `tiktok_faceless/config.py` — Add persona fields to `AccountConfig`

Add the following three fields to `AccountConfig`:

```python
persona_name: str = ""
persona_catchphrase: str = ""
persona_tone: str = "casual"
```

These fields intentionally have safe empty/default values so no existing deployments break — all are optional from the operator's perspective for MVP. When empty, the prompt omits persona instructions.

Update `load_account_config()` to read from environment with fallback:

```python
persona_name=os.environ.get("PERSONA_NAME", ""),
persona_catchphrase=os.environ.get("PERSONA_CATCHPHRASE", ""),
persona_tone=os.environ.get("PERSONA_TONE", "casual"),
```

#### `videos` DB row — Add `hook_variants` column

Add a JSON column `hook_variants` to the `videos` table in the SQLAlchemy model (file to locate: `tiktok_faceless/db/models.py` or equivalent). Store as JSON/Text. This column is populated when the `script_node` writes its result via `db/queries.py`.

If a DB migration framework is in use, add a new migration. If not, document the ALTER TABLE statement:

```sql
ALTER TABLE videos ADD COLUMN hook_variants JSON;
```

### `THREE_HOOK_ARCHETYPES` constant

```python
THREE_HOOK_ARCHETYPES: list[str] = ["curiosity_gap", "social_proof", "controversy"]
```

This replaces `VALID_HOOK_ARCHETYPES` for the 3 fixed generation archetypes. The old `VALID_HOOK_ARCHETYPES` list (which included `"demonstration"`) is removed. If any other code imports `VALID_HOOK_ARCHETYPES` from `script.py`, update those imports to `THREE_HOOK_ARCHETYPES`.

The existing test `test_hook_archetype_is_valid` asserts `result["hook_archetype"] in VALID_HOOK_ARCHETYPES` — this import must be updated to `THREE_HOOK_ARCHETYPES` (see Existing Test Updates below).

### Updated `_build_script_prompt`

```python
def _build_script_prompt(
    product: dict[str, Any],
    hook_archetype: str,
    buyer_language: list[str],
    persona_name: str,
    persona_catchphrase: str,
    persona_tone: str,
) -> str:
    buyer_phrases = (
        "\nBuyer language to incorporate: " + ", ".join(f'"{p}"' for p in buyer_language)
        if buyer_language
        else ""
    )
    persona_block = ""
    if persona_name or persona_catchphrase:
        parts = []
        if persona_name:
            parts.append(f"Your creator name is {persona_name}.")
        if persona_catchphrase:
            parts.append(f"Use your catchphrase: \"{persona_catchphrase}\".")
        persona_block = "\nPersona: " + " ".join(parts)

    return (
        f"You are a viral TikTok creator with a {persona_tone} tone.{persona_block} "
        f"Generate a short (<60s) video script "
        f"for a {hook_archetype.replace('_', ' ')} style hook.\n\n"
        f"Product: {product.get('product_name', 'Unknown Product')}\n"
        f"Niche: {product.get('niche', 'general')}\n"
        f"URL: {product.get('product_url', '')}\n"
        f"Commission: {product.get('commission_rate', 0):.0%}\n"
        f"{buyer_phrases}\n"
        f"Script (60 words max, no hashtags, end with clear CTA):"
    )
```

### Refactored `script_node` — Full Implementation Pattern

```python
def script_node(state: PipelineState) -> dict[str, Any]:
    """
    Generate 3 hook variant scripts from state.selected_product.

    Calls LLM once per archetype in THREE_HOOK_ARCHETYPES.
    If any LLM call fails, returns AgentError (all-or-nothing).
    Incorporates buyer_language phrases and account persona from AccountConfig.

    Returns state delta dict with current_script, hook_archetype, and hook_variants
    on success, or errors list on failure. Never returns full PipelineState.
    """
    if state.selected_product is None:
        return {
            "errors": [
                AgentError(
                    agent="script",
                    error_type="MissingProduct",
                    message="selected_product is None — cannot generate script without a product",
                )
            ]
        }

    config = load_account_config(state.account_id)
    buyer_language: list[str] = state.selected_product.get("buyer_language") or []

    llm = LLMClient(api_key=config.anthropic_api_key)
    variants: list[dict[str, Any]] = []

    for archetype in THREE_HOOK_ARCHETYPES:
        prompt = _build_script_prompt(
            product=state.selected_product,
            hook_archetype=archetype,
            buyer_language=buyer_language,
            persona_name=config.persona_name,
            persona_catchphrase=config.persona_catchphrase,
            persona_tone=config.persona_tone,
        )
        try:
            script_text = llm.generate_script(prompt=prompt)
            if not script_text or not script_text.strip():
                raise LLMError("LLM returned empty script")
        except LLMError as e:
            return {
                "errors": [
                    AgentError(
                        agent="script",
                        error_type="LLMError",
                        message=str(e),
                        recovery_suggestion=(
                            "Check Anthropic API key and rate limits. "
                            "Retry after a short backoff."
                        ),
                    )
                ]
            }
        variants.append({"archetype": archetype, "script": script_text})

    # First variant (curiosity_gap) is the primary selected script
    return {
        "current_script": variants[0]["script"],
        "hook_archetype": variants[0]["archetype"],
        "hook_variants": variants,
    }
```

Key points:
- `LLMClient` is instantiated once before the loop — not per archetype
- `buyer_language` uses `.get("buyer_language") or []` — handles missing key AND `None` value
- Any `LLMError` (including empty script) causes immediate return with `AgentError`; no partial `hook_variants` are emitted
- `hook_archetype` is always `"curiosity_gap"` on success (deterministic, not random)
- The old `random.choice` call is removed entirely

### Files to Touch

| File | Action |
|------|--------|
| `tiktok_faceless/agents/script.py` | Replace `VALID_HOOK_ARCHETYPES` with `THREE_HOOK_ARCHETYPES`; update `_build_script_prompt` signature; refactor `script_node` to loop |
| `tiktok_faceless/state.py` | Add `hook_variants: list[dict] = Field(default_factory=list)` field |
| `tiktok_faceless/config.py` | Add `persona_name`, `persona_catchphrase`, `persona_tone` fields + `load_account_config` reads |
| `tests/unit/agents/test_script.py` | Add `TestScriptNodeHookVariants` class; update `VALID_HOOK_ARCHETYPES` import |
| DB model file (locate `videos` table) | Add `hook_variants` JSON column |

### Do NOT Touch

- `tiktok_faceless/clients/llm.py` — `LLMClient.generate_script()` interface is unchanged
- `tiktok_faceless/agents/research.py` — no changes needed
- `tiktok_faceless/orchestrator.py` — no changes needed
- Any other agent files

### Required Test Cases — Task 7: `TestScriptNodeHookVariants`

Add to `tests/unit/agents/test_script.py`. Use the existing `_PRODUCT` and `_mock_config()` helpers. Extend `_mock_config()` usage by patching persona fields inline on the returned mock where needed.

The module-level `_MOD` constant should be added if not present:

```python
_MOD = "tiktok_faceless.agents.script"
```

#### Fixture additions

```python
_PRODUCT_WITH_BUYER_LANGUAGE = {
    **_PRODUCT,
    "buyer_language": ["literally changed my life", "why did I wait so long"],
}
```

#### `TestScriptNodeHookVariants` test cases

```python
class TestScriptNodeHookVariants:

    def test_llm_called_exactly_three_times(self) -> None:
        """script_node calls LLM once per archetype — exactly 3 calls total."""
        state = PipelineState(account_id="acc1", selected_product=_PRODUCT_WITH_BUYER_LANGUAGE)

        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.LLMClient") as mock_llm_cls,
        ):
            mock_llm = MagicMock()
            mock_llm.generate_script.return_value = "Great script."
            mock_llm_cls.return_value = mock_llm

            result = script_node(state)

        assert mock_llm.generate_script.call_count == 3

    def test_buyer_language_phrases_appear_in_prompts(self) -> None:
        """Each LLM prompt contains buyer-language phrases from selected_product."""
        state = PipelineState(account_id="acc1", selected_product=_PRODUCT_WITH_BUYER_LANGUAGE)
        captured_prompts: list[str] = []

        def capture_prompt(prompt: str) -> str:
            captured_prompts.append(prompt)
            return "Script text."

        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.LLMClient") as mock_llm_cls,
        ):
            mock_llm = MagicMock()
            mock_llm.generate_script.side_effect = capture_prompt
            mock_llm_cls.return_value = mock_llm

            script_node(state)

        assert len(captured_prompts) == 3
        for prompt in captured_prompts:
            assert "literally changed my life" in prompt
            assert "why did I wait so long" in prompt

    def test_all_three_variants_stored_in_hook_variants(self) -> None:
        """hook_variants contains 3 entries, each with archetype and script keys."""
        state = PipelineState(account_id="acc1", selected_product=_PRODUCT)

        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.LLMClient") as mock_llm_cls,
        ):
            mock_llm = MagicMock()
            mock_llm.generate_script.side_effect = [
                "Script A.", "Script B.", "Script C."
            ]
            mock_llm_cls.return_value = mock_llm

            result = script_node(state)

        assert "hook_variants" in result
        assert len(result["hook_variants"]) == 3
        for variant in result["hook_variants"]:
            assert "archetype" in variant
            assert "script" in variant

    def test_current_script_equals_first_variant_script(self) -> None:
        """current_script is the script from the first variant (curiosity_gap)."""
        state = PipelineState(account_id="acc1", selected_product=_PRODUCT)

        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.LLMClient") as mock_llm_cls,
        ):
            mock_llm = MagicMock()
            mock_llm.generate_script.side_effect = [
                "First script.", "Second script.", "Third script."
            ]
            mock_llm_cls.return_value = mock_llm

            result = script_node(state)

        assert result["current_script"] == "First script."

    def test_hook_archetype_is_curiosity_gap(self) -> None:
        """hook_archetype is always 'curiosity_gap' — the first archetype."""
        state = PipelineState(account_id="acc1", selected_product=_PRODUCT)

        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.LLMClient") as mock_llm_cls,
        ):
            mock_llm = MagicMock()
            mock_llm.generate_script.return_value = "Script."
            mock_llm_cls.return_value = mock_llm

            result = script_node(state)

        assert result["hook_archetype"] == "curiosity_gap"

    def test_llm_error_on_any_variant_returns_agent_error(self) -> None:
        """LLM failure on the second variant → AgentError, no hook_variants or current_script."""
        state = PipelineState(account_id="acc1", selected_product=_PRODUCT)

        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.LLMClient") as mock_llm_cls,
        ):
            mock_llm = MagicMock()
            mock_llm.generate_script.side_effect = [
                "First script.",
                LLMError("API timeout on second variant"),
                "Third script.",
            ]
            mock_llm_cls.return_value = mock_llm

            result = script_node(state)

        assert "errors" in result
        assert result["errors"][0].error_type == "LLMError"
        assert "current_script" not in result
        assert "hook_variants" not in result

    def test_missing_buyer_language_key_handled_gracefully(self) -> None:
        """selected_product without buyer_language key does not raise KeyError."""
        product_without_buyer_language = {
            k: v for k, v in _PRODUCT.items() if k != "buyer_language"
        }
        state = PipelineState(
            account_id="acc1", selected_product=product_without_buyer_language
        )

        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.LLMClient") as mock_llm_cls,
        ):
            mock_llm = MagicMock()
            mock_llm.generate_script.return_value = "Script."
            mock_llm_cls.return_value = mock_llm

            result = script_node(state)

        assert "current_script" in result
        assert "errors" not in result
```

### Existing Test Updates

The following changes to existing tests are required:

1. **`test_hook_archetype_is_valid`** — currently imports and checks `VALID_HOOK_ARCHETYPES`. Update the import and assertion:

   ```python
   # Change import line (line 5 of test file):
   from tiktok_faceless.agents.script import THREE_HOOK_ARCHETYPES, script_node

   # Change assertion in test_hook_archetype_is_valid:
   assert result["hook_archetype"] in THREE_HOOK_ARCHETYPES
   ```

2. **`test_returns_script_and_hook_archetype`** — currently mocks one `generate_script` call. After refactor, the LLM is called 3 times. Update the mock to return a value for all 3 calls:

   ```python
   mock_llm.generate_script.return_value = "Widget changes everything! Click now."
   # return_value is reused on every call — no change needed if using return_value (not side_effect)
   ```

   This test should still pass without modification if `return_value` (not `side_effect`) is used, since `return_value` applies to every call. Verify and leave as-is if so.

3. **`test_llm_error_returns_agent_error`** in `TestScriptNodeErrors` — currently uses `side_effect = LLMError("Timeout")` which raises on every call. This remains correct — the first LLM call fails and `AgentError` is returned. No change needed.

4. **`test_missing_product_returns_agent_error`** in `TestScriptNodeGuards` — no LLM calls are made; this test is unaffected.

5. **`test_hook_variants_present_in_result`** — add a check for `hook_variants` in the existing success test or rely on the new `TestScriptNodeHookVariants` class. No forced change to the existing class, but consider adding:

   ```python
   assert "hook_variants" in result
   assert len(result["hook_variants"]) == 3
   ```

   to `test_returns_script_and_hook_archetype` for completeness.

### Previous Story Learnings (from Stories 1.5, 2.1–2.3)

- `_MOD = "tiktok_faceless.agents.script"` — add at module level if not present
- Mock pattern for `LLMClient`: `patch(f"{_MOD}.LLMClient") as mock_llm_cls` then `mock_llm_cls.return_value = mock_llm`
- `LLMError` imported from `tiktok_faceless.clients` — already in test file
- Import sort: stdlib → third-party → local (ruff I001 enforced)
- Line length ≤ 100 chars (ruff E501 enforced)
- `dict[str, Any]` return type on `script_node`
- `AgentError` and `PipelineState` imported from `tiktok_faceless.state`

### References

- Architecture patterns: `_bmad-output/planning-artifacts/architecture.md` — Agent Boundary, State Delta pattern, Error Contract
- Epic 2.4 story spec: `_bmad-output/planning-artifacts/epics.md` — Story 2.4 (lines 570–595)
- Previous story: `_bmad-output/implementation-artifacts/2-3-multi-niche-product-scanning.md`
- `script_node` current implementation: `tiktok_faceless/agents/script.py`
- `PipelineState` / `AgentError`: `tiktok_faceless/state.py`
- `AccountConfig` / `load_account_config`: `tiktok_faceless/config.py`
- Existing script tests: `tests/unit/agents/test_script.py`

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

### File List

- `tiktok_faceless/agents/script.py` — replace `VALID_HOOK_ARCHETYPES` with `THREE_HOOK_ARCHETYPES`; update `_build_script_prompt`; refactor `script_node` to 3-variant loop
- `tiktok_faceless/state.py` — add `hook_variants: list[dict]` field
- `tiktok_faceless/config.py` — add `persona_name`, `persona_catchphrase`, `persona_tone` fields
- `tests/unit/agents/test_script.py` — update `VALID_HOOK_ARCHETYPES` import; add `TestScriptNodeHookVariants` class (7 test cases) + `_PRODUCT_WITH_BUYER_LANGUAGE` fixture
- DB model file (locate `videos` table) — add `hook_variants` JSON column

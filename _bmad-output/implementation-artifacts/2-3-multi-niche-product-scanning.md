# Story 2.3: Multi-Niche Product Scanning

Status: ready-for-dev

## Story

As the operator,
I want the Research Agent to scan all niches in the configured niche pool during Tournament Phase,
so that the Tournament can evaluate multiple niches and select the best product overall without one niche failure blocking others.

## Acceptance Criteria

1. **Given** a `PipelineState` with `phase = "tournament"` and `candidate_niches` populated
   **When** `research_node` runs
   **Then** each niche in `candidate_niches` is scanned sequentially (one `get_validated_products` call per niche)
   **And** one niche's API failure does not block subsequent niches from being scanned
   **And** the product with the highest `sales_velocity_score` across all niches is stored as `selected_product`

2. **Given** tournament mode scanning completes
   **When** the results are inspected
   **Then** `state["selected_product"]` is the top product across all scanned niches
   **And** `product_validated` is `True`

3. **Given** `phase = "commit"` (or any non-tournament phase)
   **When** `research_node` runs
   **Then** only `committed_niche` is scanned — `candidate_niches` is ignored
   **And** behavior is identical to the pre-Story-2.3 implementation

4. **Given** `phase = "tournament"` and `candidate_niches` is empty
   **When** `research_node` runs
   **Then** a `MissingNiche` `AgentError` is returned and the pipeline halts

5. **Given** all niches in `candidate_niches` fail with API errors during tournament mode
   **When** `research_node` finishes iterating
   **Then** an `AgentError` is returned (pipeline halts) — not a silent empty result

6. **Given** some niches succeed and some fail in tournament mode
   **When** `research_node` finishes
   **Then** failures are logged (printed) but do not appear as `AgentError` entries in state
   **And** the best product from the successful niches is returned

## Tasks / Subtasks

- [ ] Task 6: Refactor `research_node` to be phase-aware (All ACs)
  - [ ] Add phase check: `if state.phase == "tournament"` → use `candidate_niches`; else → use `[state.committed_niche]`
  - [ ] Guard: empty `candidate_niches` in tournament mode → return `MissingNiche` `AgentError`
  - [ ] Loop over target niches sequentially; collect best product per niche
  - [ ] Per-niche cache check still applies (same TTL logic, scoped by niche)
  - [ ] API errors on a single niche are caught, logged, and skipped — do NOT add `AgentError`, do NOT halt
  - [ ] After loop: if no products collected across all niches → return `AgentError`
  - [ ] Pick overall winner: `max(all_best_products, key=lambda p: p.sales_velocity_score)`
  - [ ] Call `get_video_comments` on winner (same non-fatal pattern from Story 2.2)
  - [ ] Return `{"selected_product": product_dict, "product_validated": True}`
  - [ ] Tests in `tests/unit/agents/test_research.py` — new class `TestResearchNodeTournament`

## Dev Notes

### Critical Architecture Rules

- **Agent node returns state delta dict only** — never `return state`, never mutate `state` in place
- **Never call external APIs directly** — always through `TikTokAPIClient`
- **All DB access through `db/queries.py`** — agents never touch SQLAlchemy sessions directly
- **`account_id` as first scope parameter** — every DB query and API call is scoped by `account_id`
- **All fatal errors returned as `AgentError`** in `{"errors": [AgentError(...)]}` delta
- **Phase does NOT change in `research_node`** — `orchestrator.py` is the ONLY file that writes `state["phase"]`
- **No hardcoded thresholds** — `min_commission_rate` and `min_sales_velocity` come from `AccountConfig`

### Files to Touch

| File | Action |
|------|--------|
| `tiktok_faceless/agents/research.py` | Refactor `research_node` to be phase-aware |
| `tests/unit/agents/test_research.py` | Add `TestResearchNodeTournament` class |

### Do NOT Touch

- `tiktok_faceless/state.py` — `candidate_niches: list[str]` and `phase` fields already correct; no schema change
- `tiktok_faceless/clients/tiktok.py` — `get_validated_products` and `get_video_comments` already implemented
- `tiktok_faceless/db/queries.py` — no new queries needed
- `tiktok_faceless/config.py` — `min_commission_rate` and `min_sales_velocity` already present
- Any other agent files

### Design Decision: Sequential Loop vs. LangGraph `Send` API

The Epic 2.3 spec mentions LangGraph `Send` API for fan-out across niches in parallel. For this MVP story scope, a **sequential loop** is used instead. Trade-off rationale:

- **`Send` API** fans out graph nodes in parallel, requiring sub-graph node definitions, a reducer on the receiving node, and coordination across separate graph invocations. This is significant additional scope — closer to a Story 2.x.5 level refactor.
- **Sequential loop** keeps the entire change within `research_node` as a single self-contained function, which matches this story's single-task scope (Task 6 only).
- Performance impact is acceptable for MVP: tournament mode scans O(5–10) niches, each with a cache check first. Most scans hit cache.
- The sequential loop is a correct implementation of all ACs. If true parallelism becomes a bottleneck at scale, the `Send` API refactor can be a future story with no AC change.

Document this decision in code comments so the next developer understands the intent.

### Refactored `research_node` — Full Implementation Pattern

```python
def research_node(state: PipelineState) -> dict[str, Any]:
    """
    Validate products for the target niche(s) via TikTok Shop buyer intent signals.

    Tournament phase: scans all candidate_niches sequentially, picks the best product
    across all niches by sales_velocity_score. One niche failure does not block others.
    All other phases: scans committed_niche only (pre-2.3 behavior).

    Note: Sequential loop used instead of LangGraph Send API for MVP simplicity.
    Fan-out parallelism can be added in a future story without changing ACs.

    Returns state delta dict with selected_product + product_validated=True on success,
    or errors list on failure. Never returns full PipelineState.
    """
    config = load_account_config(state.account_id)
    client = TikTokAPIClient(
        access_token=config.tiktok_access_token,
        open_id=config.tiktok_open_id,
    )

    # --- Determine which niches to scan ---
    if state.phase == "tournament":
        if not state.candidate_niches:
            return {
                "errors": [
                    AgentError(
                        agent="research",
                        error_type="MissingNiche",
                        message=(
                            "phase is 'tournament' but candidate_niches is empty — "
                            "cannot scan without target niches"
                        ),
                        recovery_suggestion=(
                            "Populate candidate_niches in AccountConfig before entering "
                            "tournament phase."
                        ),
                    )
                ]
            }
        target_niches = state.candidate_niches
    else:
        niche = state.committed_niche
        if not niche:
            return {
                "errors": [
                    AgentError(
                        agent="research",
                        error_type="MissingNiche",
                        message=(
                            "committed_niche is not set — cannot validate products "
                            "without a target niche"
                        ),
                        recovery_suggestion=(
                            "Set committed_niche in state before calling research_node."
                        ),
                    )
                ]
            }
        target_niches = [niche]

    # --- Scan each niche; collect the best product per niche ---
    all_best: list[AffiliateProduct] = []

    for niche in target_niches:
        with get_session() as session:
            cached = get_cached_products(session, account_id=state.account_id, niche=niche)

        if cached:
            all_best.append(max(cached, key=lambda p: p.sales_velocity_score))
            continue

        # Live API fetch for this niche
        try:
            products = client.get_validated_products(
                account_id=state.account_id,
                niche=niche,
                min_commission_rate=config.min_commission_rate,
                min_sales_velocity=config.min_sales_velocity,
            )
        except (TikTokRateLimitError, TikTokAPIError) as e:
            # Non-fatal in tournament multi-niche context — log and continue
            print(f"[research_node] niche '{niche}' API error (skipping): {e}")
            continue

        if not products:
            # No products in this niche — skip silently
            continue

        # Cache results for this niche
        with get_session() as session:
            for product in products:
                cache_product(session, account_id=state.account_id, product=product)

        all_best.append(products[0])  # already sorted by sales_velocity_score descending

    # --- Guard: all niches failed ---
    if not all_best:
        niche_list = ", ".join(f"'{n}'" for n in target_niches)
        return {
            "errors": [
                AgentError(
                    agent="research",
                    error_type="NoValidatedProducts",
                    message=(
                        f"No validated products found across niches: {niche_list}. "
                        f"All niches either returned no products or encountered API errors."
                    ),
                    recovery_suggestion=(
                        "Check TikTok API credentials, rate limits, and niche configurations. "
                        "Try adjusting min_commission_rate or min_sales_velocity thresholds."
                    ),
                )
            ]
        }

    # --- Pick overall winner across all niches ---
    best = max(all_best, key=lambda p: p.sales_velocity_score)

    # --- Mine buyer-language comments (non-fatal — never blocks pipeline) ---
    try:
        comments = client.get_video_comments(video_id=best.product_id, max_count=20)
    except (TikTokRateLimitError, TikTokAPIError):
        comments = []

    product_dict = best.model_dump()
    product_dict["buyer_language"] = comments
    return {
        "selected_product": product_dict,
        "product_validated": True,
    }
```

Key points:
- `AffiliateProduct` must be imported from `tiktok_faceless.models.shop` (add to imports if not already present)
- `config` and `client` are instantiated once before the loop — not per niche
- The `continue` on API error skips to the next niche; no `AgentError` is emitted
- The final `max()` over `all_best` picks the winner across all niches by `sales_velocity_score`
- Comment mining happens on the overall winner only — not per niche

### Import Addition

Add `AffiliateProduct` to the imports in `tiktok_faceless/agents/research.py` if it is not already imported:

```python
from tiktok_faceless.models.shop import AffiliateProduct
```

### Required Test Cases — Task 6: `TestResearchNodeTournament`

Add to `tests/unit/agents/test_research.py`. Use the existing `_MOD`, `_PRODUCT`, `_STATE`, `_mock_config()`, and `_mock_session_ctx()` helpers.

Define a second product fixture and a tournament-mode state fixture at module level alongside the existing `_PRODUCT` and `_STATE`:

```python
# Second product with lower score for cross-niche comparison
_PRODUCT_B = AffiliateProduct(
    product_id="p2",
    name="Product B",
    niche="fitness",
    commission_rate=0.15,
    sales_velocity_score=0.6,  # lower than _PRODUCT (assume _PRODUCT has 0.85)
    affiliate_signal=True,
    buyer_language=[],
)

_TOURNAMENT_STATE = PipelineState(
    account_id="acc1",
    phase="tournament",
    candidate_niches=["beauty", "fitness"],
)
```

```python
class TestResearchNodeTournament:

    def test_tournament_scans_all_candidate_niches(self) -> None:
        """get_validated_products called once per niche in tournament mode."""
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
            patch(f"{_MOD}.get_session", return_value=_mock_session_ctx()),
            patch(f"{_MOD}.get_cached_products", return_value=[]),
            patch(f"{_MOD}.cache_product"),
        ):
            mock_client = MagicMock()
            mock_client.get_validated_products.side_effect = [
                [_PRODUCT],    # beauty niche
                [_PRODUCT_B],  # fitness niche
            ]
            mock_client.get_video_comments.return_value = []
            mock_client_cls.return_value = mock_client

            result = research_node(_TOURNAMENT_STATE)

        assert result["product_validated"] is True
        assert mock_client.get_validated_products.call_count == 2
        # Verify both niches were requested
        calls = mock_client.get_validated_products.call_args_list
        niches_called = [c.kwargs["niche"] for c in calls]
        assert "beauty" in niches_called
        assert "fitness" in niches_called

    def test_tournament_picks_highest_sales_velocity_across_niches(self) -> None:
        """Winner is the product with the highest sales_velocity_score, regardless of niche."""
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
            patch(f"{_MOD}.get_session", return_value=_mock_session_ctx()),
            patch(f"{_MOD}.get_cached_products", return_value=[]),
            patch(f"{_MOD}.cache_product"),
        ):
            mock_client = MagicMock()
            mock_client.get_validated_products.side_effect = [
                [_PRODUCT_B],  # beauty niche — lower score
                [_PRODUCT],    # fitness niche — higher score
            ]
            mock_client.get_video_comments.return_value = []
            mock_client_cls.return_value = mock_client

            result = research_node(_TOURNAMENT_STATE)

        assert result["selected_product"]["product_id"] == _PRODUCT.product_id

    def test_commit_mode_ignores_candidate_niches_uses_committed_niche(self) -> None:
        """Non-tournament phase uses committed_niche only; candidate_niches is ignored."""
        commit_state = PipelineState(
            account_id="acc1",
            phase="commit",
            candidate_niches=["beauty", "fitness"],  # should be ignored
            committed_niche="beauty",
        )
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
            patch(f"{_MOD}.get_session", return_value=_mock_session_ctx()),
            patch(f"{_MOD}.get_cached_products", return_value=[]),
            patch(f"{_MOD}.cache_product"),
        ):
            mock_client = MagicMock()
            mock_client.get_validated_products.return_value = [_PRODUCT]
            mock_client.get_video_comments.return_value = []
            mock_client_cls.return_value = mock_client

            result = research_node(commit_state)

        assert result["product_validated"] is True
        assert mock_client.get_validated_products.call_count == 1
        call_kwargs = mock_client.get_validated_products.call_args.kwargs
        assert call_kwargs["niche"] == "beauty"

    def test_empty_candidate_niches_in_tournament_returns_error(self) -> None:
        """tournament phase with no candidate_niches returns MissingNiche AgentError."""
        empty_tournament = PipelineState(
            account_id="acc1",
            phase="tournament",
            candidate_niches=[],
        )
        with patch(f"{_MOD}.load_account_config", return_value=_mock_config()):
            result = research_node(empty_tournament)

        assert "errors" in result
        assert result["errors"][0].error_type == "MissingNiche"
        assert "product_validated" not in result

    def test_one_niche_api_failure_does_not_block_other_niches(self) -> None:
        """An API error on one niche is caught and skipped; remaining niches still run."""
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
            patch(f"{_MOD}.get_session", return_value=_mock_session_ctx()),
            patch(f"{_MOD}.get_cached_products", return_value=[]),
            patch(f"{_MOD}.cache_product"),
        ):
            mock_client = MagicMock()
            mock_client.get_validated_products.side_effect = [
                TikTokAPIError("500: server error"),  # beauty fails
                [_PRODUCT_B],                          # fitness succeeds
            ]
            mock_client.get_video_comments.return_value = []
            mock_client_cls.return_value = mock_client

            result = research_node(_TOURNAMENT_STATE)

        assert result["product_validated"] is True
        assert result["selected_product"]["product_id"] == _PRODUCT_B.product_id
        # No AgentError for the partial niche failure
        assert "errors" not in result

    def test_all_niches_fail_returns_agent_error(self) -> None:
        """If every niche fails with API errors, return AgentError to halt pipeline."""
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
            patch(f"{_MOD}.get_session", return_value=_mock_session_ctx()),
            patch(f"{_MOD}.get_cached_products", return_value=[]),
            patch(f"{_MOD}.cache_product"),
        ):
            mock_client = MagicMock()
            mock_client.get_validated_products.side_effect = TikTokAPIError("500: server error")
            mock_client_cls.return_value = mock_client

            result = research_node(_TOURNAMENT_STATE)

        assert "errors" in result
        assert result["errors"][0].error_type == "NoValidatedProducts"

    def test_tournament_cache_hit_per_niche_skips_api(self) -> None:
        """Cache hits in tournament mode are respected — no live API call for cached niches."""
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
            patch(f"{_MOD}.get_session", return_value=_mock_session_ctx()),
            patch(f"{_MOD}.get_cached_products", return_value=[_PRODUCT]),  # always cache hit
            patch(f"{_MOD}.cache_product"),
        ):
            mock_client = MagicMock()
            mock_client.get_video_comments.return_value = []
            mock_client_cls.return_value = mock_client

            result = research_node(_TOURNAMENT_STATE)

        assert result["product_validated"] is True
        mock_client.get_validated_products.assert_not_called()
```

### Existing Test Updates

Existing tests in `TestResearchNodeSuccess` and `TestResearchNodeCommentMining` do not need changes — they use `_STATE` which has `phase="warmup"` (default) and `committed_niche` set, so they exercise the non-tournament path and remain valid.

If `_STATE` does not have a `committed_niche` set, add it:

```python
_STATE = PipelineState(
    account_id="acc1",
    committed_niche="beauty",  # ensure this is set
)
```

### `_PRODUCT` Score Assumption

The test fixtures assume `_PRODUCT.sales_velocity_score > _PRODUCT_B.sales_velocity_score`. Verify the existing `_PRODUCT` fixture's score value. If `_PRODUCT` is already defined with a known score (e.g. `0.85`), define `_PRODUCT_B` with a lower score (e.g. `0.6`). If `_PRODUCT` uses a different field name or construction pattern, match it.

### Previous Story Learnings (from Stories 2.1 and 2.2)

- `_MOD = "tiktok_faceless.agents.research"` constant already in test file — do not redefine
- `_mock_config()` helper already in test file — do not redefine
- `_mock_session_ctx()` helper already in test file — do not redefine
- Mock config patch: `patch(f"{_MOD}.load_account_config", return_value=_mock_config())`
- `TikTokAPIClient` patched at import location: `patch(f"{_MOD}.TikTokAPIClient")`
- Import sort: stdlib → third-party → local (ruff I001 enforced)
- Line length ≤ 100 chars (ruff E501 enforced)
- `dict[str, Any]` return type on `research_node`
- `get_session()` mock pattern: `ctx.__enter__ = MagicMock(return_value=MagicMock()); ctx.__exit__ = MagicMock(return_value=False)` — use `_mock_session_ctx()` helper
- `TikTokAPIError` imported from `tiktok_faceless.clients` (already in test file from Story 2.2)

### References

- Architecture patterns: `_bmad-output/planning-artifacts/architecture.md` — Agent Boundary, State Delta pattern, Error Contract
- Epic 2.3 story spec: `_bmad-output/planning-artifacts/epics.md` — Story 2.3 (lines 544–567)
- Previous stories: `_bmad-output/implementation-artifacts/2-1-product-validation-via-buyer-intent-signals.md`, `_bmad-output/implementation-artifacts/2-2-comment-mining-for-buyer-language.md`
- `AffiliateProduct` model: `tiktok_faceless/models/shop.py`
- `TikTokAPIClient` current implementation: `tiktok_faceless/clients/tiktok.py`
- `research_node` current implementation: `tiktok_faceless/agents/research.py`
- `PipelineState` / `AgentError`: `tiktok_faceless/state.py`

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

### File List

- `tiktok_faceless/agents/research.py` — refactor `research_node` to be phase-aware (tournament vs. commit/other)
- `tests/unit/agents/test_research.py` — add `TestResearchNodeTournament` class (7 test cases) + add `_PRODUCT_B` and `_TOURNAMENT_STATE` fixtures

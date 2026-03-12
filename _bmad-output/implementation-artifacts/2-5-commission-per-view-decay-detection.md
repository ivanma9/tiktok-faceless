# Story 2.5: Commission-Per-View Decay Detection

Status: ready-for-dev

## Story

As the operator,
I want the Research Agent to continuously monitor commission-per-view for the committed niche and surface a decay alert when it drops,
so that niche saturation is detected automatically and a re-tournament is triggered before revenue plateaus.

## Acceptance Criteria

1. **Given** `phase = "commit"` and an active `committed_niche`
   **When** `research_node` runs on its polling schedule
   **Then** commission-per-view is calculated as `total_affiliate_orders / total_view_count` over the last 7 days, scoped by `account_id` and `committed_niche`
   **And** the result is compared against `config.decay_threshold`

2. **Given** commission-per-view drops below `decay_threshold` for 2 consecutive polling intervals
   **When** the decay condition is confirmed
   **Then** `state["niche_decay_alert"]` is set to `True`
   **And** `state["consecutive_decay_count"]` is `>= 2`

3. **Given** commission-per-view is above `decay_threshold` on any polling interval
   **When** the research node runs
   **Then** `consecutive_decay_count` is reset to `0`
   **And** `niche_decay_alert` remains `False`

4. **Given** `phase != "commit"` (e.g., `"tournament"`)
   **When** `research_node` runs
   **Then** decay detection logic is skipped entirely — no DB query for commission-per-view

5. **Given** no commission data exists in the DB for the niche over the last 7 days (cpv == 0.0)
   **When** decay detection runs
   **Then** the counter is NOT incremented and no alert is set — zero data is not a decay signal

6. **Given** a decay alert is raised
   **When** the Orchestrator reads it on the next cycle (Epic 3)
   **Then** a re-tournament is triggered — `state["phase"]` is reset to `"tournament"` by the Orchestrator only
   **And** the committed niche's existing videos remain live for passive affiliate earning

## Tasks / Subtasks

- [ ] Task 8: Commission-per-view decay detection (bundled: state + config + DB query + research_node extension)
  - [ ] Add `niche_decay_alert: bool = False` and `consecutive_decay_count: int = 0` to `PipelineState` in `state.py`
  - [ ] Add `decay_threshold: float = Field(default=0.001, ge=0.0)` to `AccountConfig` in `config.py`
  - [ ] Add `get_commission_per_view(session, account_id, niche, days=7) -> float` to `db/queries.py`
  - [ ] Add decay detection block at the END of `research_node` in `agents/research.py` (commit phase only, after selecting product)
  - [ ] Tests in `tests/unit/agents/test_research.py` — new class `TestDecayDetection`
  - [ ] Tests in `tests/unit/db/test_queries.py` — new class `TestGetCommissionPerView`

## Dev Notes

### Critical Architecture Rules

- **Agent node returns state delta dict only** — never `return state`, never mutate `state` in place
- **Decay detection is non-fatal** — always returns `selected_product` alongside decay delta; never blocks the pipeline
- **Zero cpv is not decay** — only increment counter when `cpv > 0 and cpv < decay_threshold`
- **Phase guard first** — decay block must be skipped entirely outside commit phase (no DB query)
- **No new external API calls** — decay detection reads only from DB (`VideoMetric` + `Video`)

### Schema Changes

#### `tiktok_faceless/state.py` — Add decay fields

Add after the existing `suppression_alert` field (line 63):

```python
niche_decay_alert: bool = False
consecutive_decay_count: int = 0
```

These fields use plain replacement semantics (no LangGraph `add` reducer) — each research_node run overwrites them wholesale.

#### `tiktok_faceless/config.py` — Add `decay_threshold` to `AccountConfig`

Add after `min_sales_velocity`:

```python
decay_threshold: float = Field(default=0.001, ge=0.0)
```

Default `0.001` means 1 affiliate order per 1,000 views. The `ge=0.0` constraint prevents negative values. No env var read is required — this is config-file / code-driven only at MVP. If an env var is needed later, add `DECAY_THRESHOLD` to `load_account_config`.

### `get_commission_per_view` — Full Implementation

Add to `tiktok_faceless/db/queries.py`:

```python
from tiktok_faceless.db.models import Video, VideoMetric

def get_commission_per_view(
    session: Session,
    account_id: str,
    niche: str,
    days: int = 7,
) -> float:
    """
    Return total_affiliate_orders / total_view_count for account+niche over the last `days` days.

    Joins VideoMetric on VideoMetric.video_id == Video.tiktok_video_id, filtering by
    account_id and niche on the Video side and by recorded_at cutoff on the VideoMetric side.

    Returns 0.0 if no matching rows exist or total view_count is zero.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    result = (
        session.query(
            func.sum(VideoMetric.affiliate_orders),
            func.sum(VideoMetric.view_count),
        )
        .join(Video, VideoMetric.video_id == Video.tiktok_video_id)
        .filter(
            Video.account_id == account_id,
            Video.niche == niche,
            VideoMetric.recorded_at >= cutoff,
        )
        .one()
    )
    total_orders, total_views = result
    if not total_views:
        return 0.0
    return float(total_orders) / float(total_views)
```

Required additional imports at top of `db/queries.py`:

```python
from sqlalchemy import func
from tiktok_faceless.db.models import Product, Video, VideoMetric
```

(`Video` and `VideoMetric` are new additions; `Product` was already imported.)

### Decay Detection Block in `research_node` — Full Implementation

Add at the END of `research_node`, after the `buyer_language` comment mining block and before the final `return`. The block merges a `decay_delta` into the return dict:

```python
    # --- Decay detection (commit phase only) ---
    decay_delta: dict[str, Any] = {}
    if state.phase == "commit" and state.committed_niche:
        with get_session() as session:
            cpv = get_commission_per_view(
                session,
                account_id=state.account_id,
                niche=state.committed_niche,
            )
        if cpv > 0 and cpv < config.decay_threshold:
            new_count = state.consecutive_decay_count + 1
            decay_delta = {
                "consecutive_decay_count": new_count,
                "niche_decay_alert": new_count >= 2,
            }
        elif cpv > 0:
            # Above threshold — reset counter
            decay_delta = {
                "consecutive_decay_count": 0,
                "niche_decay_alert": False,
            }
        # cpv == 0.0: no data — do not increment or reset; leave state unchanged

    return {
        "selected_product": product_dict,
        "product_validated": True,
        **decay_delta,
    }
```

The updated import block for `research.py` gains:

```python
from tiktok_faceless.db.queries import cache_product, get_cached_products, get_commission_per_view
```

### Updated `research_node` — Full Function (for reference)

```python
def research_node(state: PipelineState) -> dict[str, Any]:
    """
    Validate products for the configured niche(s) via TikTok Shop buyer intent signals.

    In tournament phase: scans all candidate_niches and picks the best product overall.
    In other phases: scans only committed_niche.

    In commit phase: after selecting a product, runs commission-per-view decay detection
    against the last 7 days of VideoMetric data. Sets niche_decay_alert=True after 2
    consecutive intervals below config.decay_threshold. Decay detection is non-fatal.

    Returns state delta dict with selected_product + product_validated=True on success,
    or errors list on failure. Never returns full PipelineState.
    """
    # Determine niches to scan based on phase
    if state.phase == "tournament":
        niches = state.candidate_niches
    else:
        niches = [state.committed_niche] if state.committed_niche else []

    if not niches:
        return {
            "errors": [
                AgentError(
                    agent="research",
                    error_type="MissingNiche",
                    message=(
                        "No niches to scan. Set committed_niche (commit/other phases) "
                        "or candidate_niches (tournament phase)."
                    ),
                    recovery_suggestion=(
                        "Populate committed_niche or candidate_niches in state before "
                        "calling research_node."
                    ),
                )
            ]
        }

    config = load_account_config(state.account_id)
    client = TikTokAPIClient(
        access_token=config.tiktok_access_token,
        open_id=config.tiktok_open_id,
    )

    # Collect best product per niche
    all_best: list[AffiliateProduct] = []

    for niche in niches:
        with get_session() as session:
            cached = get_cached_products(session, account_id=state.account_id, niche=niche)

        if cached:
            all_best.append(max(cached, key=lambda p: p.sales_velocity_score))
            continue

        try:
            products = client.get_validated_products(
                account_id=state.account_id,
                niche=niche,
                min_commission_rate=config.min_commission_rate,
                min_sales_velocity=config.min_sales_velocity,
            )
        except (TikTokRateLimitError, TikTokAPIError):
            continue

        if products:
            with get_session() as session:
                for product in products:
                    cache_product(session, account_id=state.account_id, product=product)
            all_best.append(products[0])

    if not all_best:
        return {
            "product_validated": False,
            "errors": [
                AgentError(
                    agent="research",
                    error_type="NoValidatedProducts",
                    message=f"No products in niches {niches} met the validation thresholds.",
                    recovery_suggestion="Try different niches or lower thresholds.",
                )
            ],
        }

    best = max(all_best, key=lambda p: p.sales_velocity_score)

    try:
        comments = client.get_video_comments(video_id=best.product_id, max_count=20)
    except (TikTokRateLimitError, TikTokAPIError):
        comments = []

    product_dict = best.model_dump()
    product_dict["buyer_language"] = comments

    # --- Decay detection (commit phase only) ---
    decay_delta: dict[str, Any] = {}
    if state.phase == "commit" and state.committed_niche:
        with get_session() as session:
            cpv = get_commission_per_view(
                session,
                account_id=state.account_id,
                niche=state.committed_niche,
            )
        if cpv > 0 and cpv < config.decay_threshold:
            new_count = state.consecutive_decay_count + 1
            decay_delta = {
                "consecutive_decay_count": new_count,
                "niche_decay_alert": new_count >= 2,
            }
        elif cpv > 0:
            decay_delta = {
                "consecutive_decay_count": 0,
                "niche_decay_alert": False,
            }

    return {
        "selected_product": product_dict,
        "product_validated": True,
        **decay_delta,
    }
```

### Files to Touch

| File | Action |
|------|--------|
| `tiktok_faceless/state.py` | Add `niche_decay_alert: bool = False` and `consecutive_decay_count: int = 0` |
| `tiktok_faceless/config.py` | Add `decay_threshold: float = Field(default=0.001, ge=0.0)` |
| `tiktok_faceless/db/queries.py` | Add `get_commission_per_view`; add `func` import from sqlalchemy; add `Video`, `VideoMetric` to model imports |
| `tiktok_faceless/agents/research.py` | Add decay detection block at end of `research_node`; import `get_commission_per_view` |
| `tests/unit/agents/test_research.py` | Add `TestDecayDetection` class (7 test cases) |
| `tests/unit/db/test_queries.py` | Add `TestGetCommissionPerView` class (2 test cases) |

### Do NOT Touch

- `tiktok_faceless/agents/script.py` — no changes needed
- `tiktok_faceless/orchestrator.py` — re-tournament trigger is Epic 3 work
- `tiktok_faceless/db/models.py` — no schema changes needed; `VideoMetric` and `Video` already have required columns
- `tiktok_faceless/db/session.py` — no changes needed

### Required Test Cases

#### `TestGetCommissionPerView` in `tests/unit/db/test_queries.py`

Use in-memory SQLite via the existing session fixture pattern.

```python
class TestGetCommissionPerView:

    def test_returns_correct_ratio_from_db(self, session: Session) -> None:
        """Returns sum(affiliate_orders) / sum(view_count) for matching rows."""
        # Insert a Video with tiktok_video_id set
        video = Video(
            id="v1",
            account_id="acc1",
            niche="fitness",
            lifecycle_state="posted",
            tiktok_video_id="tiktok-v1",
            created_at=datetime.utcnow(),
        )
        session.add(video)
        # Insert two VideoMetric rows within 7 days
        now = datetime.utcnow()
        session.add(VideoMetric(
            video_id="tiktok-v1",
            account_id="acc1",
            recorded_at=now - timedelta(days=1),
            view_count=1000,
            affiliate_orders=2,
        ))
        session.add(VideoMetric(
            video_id="tiktok-v1",
            account_id="acc1",
            recorded_at=now - timedelta(days=3),
            view_count=500,
            affiliate_orders=1,
        ))
        session.commit()

        cpv = get_commission_per_view(session, account_id="acc1", niche="fitness")

        # total_orders=3, total_views=1500 → 0.002
        assert cpv == pytest.approx(3 / 1500)

    def test_returns_zero_when_no_data(self, session: Session) -> None:
        """Returns 0.0 when no VideoMetric rows match account+niche."""
        cpv = get_commission_per_view(session, account_id="acc1", niche="fitness")
        assert cpv == 0.0
```

#### `TestDecayDetection` in `tests/unit/agents/test_research.py`

Use `_MOD = "tiktok_faceless.agents.research"` and the existing `_mock_config()` helper. Mock both `load_account_config` and `get_commission_per_view` (patched at the research module level). The product-selection path is patched via `get_cached_products` returning a product.

```python
_MOD = "tiktok_faceless.agents.research"

_CACHED_PRODUCT = AffiliateProduct(
    product_id="p1",
    product_name="Widget",
    product_url="https://example.com/widget",
    commission_rate=0.10,
    sales_velocity_score=0.8,
    niche="fitness",
)

def _commit_state(**kwargs: Any) -> PipelineState:
    return PipelineState(
        account_id="acc1",
        phase="commit",
        committed_niche="fitness",
        **kwargs,
    )


class TestDecayDetection:

    def _run_with_cpv(
        self,
        cpv: float,
        state: PipelineState,
    ) -> dict[str, Any]:
        """Helper: run research_node with mocked cpv and cached product."""
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.get_cached_products", return_value=[_CACHED_PRODUCT]),
            patch(f"{_MOD}.get_commission_per_view", return_value=cpv),
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
        ):
            mock_client = MagicMock()
            mock_client.get_video_comments.return_value = []
            mock_client_cls.return_value = mock_client
            return research_node(state)

    def test_alert_set_after_two_consecutive_intervals(self) -> None:
        """niche_decay_alert becomes True when consecutive_decay_count reaches 2."""
        # consecutive_decay_count=1 already in state (first detection happened last run)
        state = _commit_state(consecutive_decay_count=1)
        result = self._run_with_cpv(cpv=0.0005, state=state)

        assert result["niche_decay_alert"] is True
        assert result["consecutive_decay_count"] == 2

    def test_no_alert_on_first_detection(self) -> None:
        """Counter increments to 1 on first below-threshold detection — no alert yet."""
        state = _commit_state(consecutive_decay_count=0)
        result = self._run_with_cpv(cpv=0.0005, state=state)

        assert result["niche_decay_alert"] is False
        assert result["consecutive_decay_count"] == 1

    def test_counter_resets_when_cpv_above_threshold(self) -> None:
        """consecutive_decay_count resets to 0 and alert cleared when cpv >= threshold."""
        state = _commit_state(consecutive_decay_count=1, niche_decay_alert=False)
        result = self._run_with_cpv(cpv=0.005, state=state)  # above default 0.001

        assert result["consecutive_decay_count"] == 0
        assert result["niche_decay_alert"] is False

    def test_decay_detection_skipped_in_tournament_phase(self) -> None:
        """No decay_delta keys in result when phase == 'tournament'."""
        state = PipelineState(
            account_id="acc1",
            phase="tournament",
            candidate_niches=["fitness"],
        )
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.get_cached_products", return_value=[_CACHED_PRODUCT]),
            patch(f"{_MOD}.get_commission_per_view") as mock_cpv,
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
        ):
            mock_client = MagicMock()
            mock_client.get_video_comments.return_value = []
            mock_client_cls.return_value = mock_client
            result = research_node(state)

        mock_cpv.assert_not_called()
        assert "niche_decay_alert" not in result
        assert "consecutive_decay_count" not in result

    def test_decay_detection_skipped_when_cpv_is_zero(self) -> None:
        """cpv == 0.0 (no data) — counter not incremented, no keys in delta."""
        state = _commit_state(consecutive_decay_count=0)
        result = self._run_with_cpv(cpv=0.0, state=state)

        assert "niche_decay_alert" not in result
        assert "consecutive_decay_count" not in result

    def test_selected_product_always_returned_with_decay_delta(self) -> None:
        """Decay detection is non-fatal — selected_product always present in result."""
        state = _commit_state(consecutive_decay_count=0)
        result = self._run_with_cpv(cpv=0.0005, state=state)

        assert "selected_product" in result
        assert result["product_validated"] is True

    def test_decay_detection_skipped_when_no_committed_niche(self) -> None:
        """No committed_niche in commit phase — decay block is skipped gracefully."""
        state = PipelineState(
            account_id="acc1",
            phase="commit",
            committed_niche=None,
        )
        # No niches → MissingNiche error, but decay is irrelevant here.
        # Verify get_commission_per_view is not called.
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.get_commission_per_view") as mock_cpv,
        ):
            result = research_node(state)

        mock_cpv.assert_not_called()
        assert "errors" in result
```

### Key Design Decisions

1. **`cpv == 0.0` is not decay** — The system cannot distinguish "niche is dead" from "no videos posted yet / reporting lag." Zero data is treated as no signal. The counter is left unchanged.

2. **`consecutive_decay_count` is state, not DB** — The count persists in `PipelineState` across polling cycles via LangGraph's state persistence. No separate DB table is needed.

3. **Decay alert does not halt the pipeline** — `selected_product` is always included in the return dict alongside any `decay_delta`. The Orchestrator (Epic 3) decides what to do with `niche_decay_alert=True`.

4. **`decay_threshold` default = 0.001** — 1 order per 1,000 views. This is a conservative floor; operators can tune it lower for high-volume niches.

5. **7-day window is fixed in the query, not in config** — At MVP, 7 days is hardcoded as the `days` parameter default. Making this configurable is deferred to a future story.

6. **Join is `VideoMetric.video_id == Video.tiktok_video_id`** — `VideoMetric.video_id` stores the TikTok-side video ID (not the internal UUID), matching `Video.tiktok_video_id`. The `account_id` filter is applied on the `Video` side (which has `niche`).

### Previous Story Learnings (from Stories 2.1–2.4)

- `_MOD = "tiktok_faceless.agents.research"` — use at module level in test file
- Patch `get_session` or individual query functions at the research module level — do NOT patch at `db.queries` module level
- `AgentError` and `PipelineState` imported from `tiktok_faceless.state`
- Import sort: stdlib → third-party → local (ruff I001 enforced)
- Line length ≤ 100 chars (ruff E501 enforced)
- `dict[str, Any]` return type on `research_node`
- `get_session()` used as context manager (`with get_session() as session:`)

### References

- Epic 2.5 story spec: `_bmad-output/planning-artifacts/epics.md` — Story 2.5 (lines 597–619)
- Previous story: `_bmad-output/implementation-artifacts/2-4-full-script-generation-hook-archetypes-persona.md`
- `research_node` current implementation: `tiktok_faceless/agents/research.py`
- `PipelineState` / `AgentError`: `tiktok_faceless/state.py`
- `AccountConfig` / `load_account_config`: `tiktok_faceless/config.py`
- `VideoMetric`, `Video` ORM models: `tiktok_faceless/db/models.py`
- Existing DB queries: `tiktok_faceless/db/queries.py`

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

### File List

- `tiktok_faceless/state.py` — add `niche_decay_alert: bool = False` and `consecutive_decay_count: int = 0`
- `tiktok_faceless/config.py` — add `decay_threshold: float = Field(default=0.001, ge=0.0)`
- `tiktok_faceless/db/queries.py` — add `get_commission_per_view`; add `func` sqlalchemy import; add `Video`, `VideoMetric` model imports
- `tiktok_faceless/agents/research.py` — add decay detection block at end of `research_node`; import `get_commission_per_view`
- `tests/unit/agents/test_research.py` — add `TestDecayDetection` class (7 test cases)
- `tests/unit/db/test_queries.py` — add `TestGetCommissionPerView` class (2 test cases)

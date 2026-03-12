"""
Orchestrator agent: phase routing, transitions, and pipeline health checks.

This is the ONLY file that writes state["phase"].
Implementation: Story 1.7 — Orchestrator Pipeline Wiring & Crash Recovery
"""

from typing import Any

from tiktok_faceless.db.models import Error
from tiktok_faceless.db.session import get_session
from tiktok_faceless.state import PipelineState


def orchestrator_node(state: PipelineState) -> dict[str, Any]:
    """
    Route the pipeline based on health state and duplicate guards.

    - If errors exist from prior nodes: persist to DB, update agent_health, halt.
    - If already published: return empty delta (no-op, pipeline ends).
    - Otherwise: return empty delta, graph continues to script_node.

    This node does NOT perform business logic — it is a thin router/health-check.
    """
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
        new_health = {**state.agent_health}
        for err in state.errors:
            new_health[err.agent] = False
        return {"agent_health": new_health}

    if state.published_video_id is not None:
        return {}

    return {}

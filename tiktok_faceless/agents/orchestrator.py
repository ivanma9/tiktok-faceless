"""
Orchestrator agent: phase routing, transitions, and pipeline health checks.

This is the ONLY file that writes state["phase"].
Implementation: Story 1.7 — Orchestrator Pipeline Wiring & Crash Recovery
"""

import json
import time
from typing import Any

from tiktok_faceless.config import load_account_config
from tiktok_faceless.db.models import AgentDecision
from tiktok_faceless.db.queries import (
    get_commission_per_view,
    get_niche_scores,
    get_paused_agents,
    pause_agent_queue,
    write_agent_errors,
)
from tiktok_faceless.db.session import get_session
from tiktok_faceless.state import PipelineState
from tiktok_faceless.utils.alerts import send_phase_alert


def _tournament_elapsed_days(started_at: float) -> float:
    """Return days elapsed since tournament_started_at timestamp."""
    return (time.time() - started_at) / 86400.0


def _build_supporting_data(scores: list[tuple[str, float]]) -> str:
    """Serialize niche score list to JSON string for AgentDecision.supporting_data."""
    return json.dumps([{"niche": n, "score": round(s, 6)} for n, s in scores])


def orchestrator_node(state: PipelineState) -> dict[str, Any]:
    """
    Route the pipeline, detect phase transitions, and persist audit decisions.

    - If errors exist from prior nodes: persist to DB, update agent_health, halt.
    - If already published: return empty delta (no-op, pipeline ends).
    - If phase=tournament and duration elapsed: detect winner or extend tournament.
    - If phase=commit and niche_decay_alert: reset to tournament (re-tournament).
    - Otherwise: return empty delta, graph continues to script_node.

    This is the ONLY node that writes state["phase"].
    """
    with get_session() as session:
        paused = get_paused_agents(session, state.account_id)
    merged_health = {**state.agent_health}
    for agent_name in paused:
        merged_health[agent_name] = False

    if state.errors:
        with get_session() as session:
            write_agent_errors(session, state.account_id, state.errors)
        for err in state.errors:
            with get_session() as session:
                pause_agent_queue(session, state.account_id, err.agent)
        new_health = {**merged_health}
        for err in state.errors:
            new_health[err.agent] = False
        return {"agent_health": new_health}

    if merged_health != state.agent_health:
        return {"agent_health": merged_health}

    if state.published_video_id is not None:
        return {}

    # Tournament completion detection — only orchestrator writes phase
    if state.phase == "tournament" and state.tournament_started_at > 0:
        config = load_account_config(state.account_id)
        elapsed_days = _tournament_elapsed_days(state.tournament_started_at)
        if elapsed_days >= config.tournament_duration_days:
            with get_session() as session:
                scores = get_niche_scores(
                    session,
                    account_id=state.account_id,
                    days=config.tournament_duration_days,
                    min_video_count=config.tournament_min_video_count,
                )
                if scores:
                    winner_niche, winner_score = scores[0]
                    session.add(
                        AgentDecision(
                            account_id=state.account_id,
                            agent="orchestrator",
                            decision_type="tournament_commit",
                            from_value="tournament",
                            to_value=winner_niche,
                            rationale=(
                                f"Tournament complete after {elapsed_days:.1f} days. "
                                f"Winner: {winner_niche} score={winner_score:.4f}"
                            ),
                            supporting_data=_build_supporting_data(scores),
                        )
                    )
                    session.commit()
                    send_phase_alert(
                        bot_token=config.telegram_bot_token,
                        chat_id=config.telegram_chat_id,
                        from_phase="tournament",
                        to_phase="commit",
                        committed_niche=winner_niche,
                        timestamp=time.time(),
                    )
                    return {"phase": "commit", "committed_niche": winner_niche}
                else:
                    session.add(
                        AgentDecision(
                            account_id=state.account_id,
                            agent="orchestrator",
                            decision_type="tournament_extended",
                            from_value="tournament",
                            to_value="tournament",
                            rationale=(
                                f"Tournament extended by {config.tournament_extension_days} days — "
                                f"no niche met min_video_count={config.tournament_min_video_count}"
                            ),
                            supporting_data=None,
                        )
                    )
                    session.commit()
                    return {
                        "tournament_started_at": (
                            state.tournament_started_at
                            + config.tournament_extension_days * 86400.0
                        )
                    }

    # Niche decay re-tournament — commit→tournament reset on confirmed decay
    if state.phase == "commit" and state.niche_decay_alert and state.committed_niche:
        config = load_account_config(state.account_id)
        decayed_niche = state.committed_niche
        with get_session() as session:
            cpv = get_commission_per_view(
                session, account_id=state.account_id, niche=decayed_niche
            )
            session.add(
                AgentDecision(
                    account_id=state.account_id,
                    agent="orchestrator",
                    decision_type="niche_decay_retriggered_tournament",
                    from_value="commit",
                    to_value="tournament",
                    rationale=(
                        f"Niche decay confirmed for '{decayed_niche}' "
                        f"(commission_per_view={cpv:.6f}). Re-triggering tournament."
                    ),
                    supporting_data=json.dumps({
                        "decayed_niche": decayed_niche,
                        "commission_per_view": round(cpv, 6),
                        "consecutive_decay_count": state.consecutive_decay_count,
                    }),
                )
            )
            session.commit()
        send_phase_alert(
            bot_token=config.telegram_bot_token,
            chat_id=config.telegram_chat_id,
            from_phase="commit",
            to_phase="tournament",
            committed_niche=None,
            timestamp=time.time(),
        )
        candidate_niches = [n for n in config.niche_pool if n != decayed_niche]
        return {
            "phase": "tournament",
            "committed_niche": None,
            "candidate_niches": candidate_niches,
            "niche_decay_alert": False,
            "consecutive_decay_count": 0,
            "tournament_started_at": time.time(),
        }

    return {}

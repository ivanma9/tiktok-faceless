"""
LangGraph graph assembly: pipeline wiring and checkpointer setup.

Call build_graph() to get a compiled graph ready for invocation.
Implementation: Story 1.7 — Orchestrator Pipeline Wiring & Crash Recovery
"""

import os
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from tiktok_faceless.agents.monetization import monetization_node
from tiktok_faceless.agents.orchestrator import orchestrator_node
from tiktok_faceless.agents.production import production_node
from tiktok_faceless.agents.publishing import publishing_node
from tiktok_faceless.agents.research import research_node
from tiktok_faceless.agents.script import script_node
from tiktok_faceless.db.queries import get_pending_video
from tiktok_faceless.db.session import get_session
from tiktok_faceless.state import PipelineState


def _route_after_orchestrator(state: PipelineState) -> str:
    """Route to END only when a video has already been published (duplicate-publish guard).

    Short-circuits to 'production' (skipping research/script/monetization) when a
    rendered-but-unposted video already exists in the DB — saves API quota.
    """
    if state.published_video_id is not None:
        return END
    with get_session() as session:
        pending = get_pending_video(session, state.account_id)
    if pending is not None:
        return "production"
    return "research"


def build_graph() -> CompiledStateGraph:  # type: ignore[type-arg]
    """
    Assemble and compile the 5-node pipeline graph with SqliteSaver checkpointer.

    Node order: orchestrator → script → monetization → production → publishing
    """
    graph: StateGraph = StateGraph(PipelineState)  # type: ignore[type-arg]

    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("research", research_node)
    graph.add_node("script", script_node)
    graph.add_node("monetization", monetization_node)
    graph.add_node("production", production_node)
    graph.add_node("publishing", publishing_node)

    graph.add_edge(START, "orchestrator")
    graph.add_conditional_edges("orchestrator", _route_after_orchestrator)
    graph.add_edge("research", "script")
    graph.add_edge("script", "monetization")
    graph.add_edge("monetization", "production")
    graph.add_edge("production", "publishing")
    graph.add_edge("publishing", END)

    checkpoint_db = os.environ.get("CHECKPOINT_DB_PATH", "./checkpoints.db")
    conn = sqlite3.connect(checkpoint_db, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    return graph.compile(checkpointer=checkpointer)

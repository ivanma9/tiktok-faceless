"""
LangGraph graph assembly: pipeline wiring and checkpointer setup.

Call build_graph() to get a compiled graph ready for invocation.
Implementation: Story 1.7 — Orchestrator Pipeline Wiring & Crash Recovery
"""

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
    """Route to END on errors or duplicate publish; otherwise continue to script."""
    if state.errors or state.published_video_id is not None:
        return END
    return "script"


def build_graph() -> CompiledStateGraph:  # type: ignore[type-arg]
    """
    Assemble and compile the 5-node pipeline graph with MemorySaver checkpointer.

    Node order: orchestrator → script → monetization → production → publishing
    """
    graph: StateGraph = StateGraph(PipelineState)  # type: ignore[type-arg]

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

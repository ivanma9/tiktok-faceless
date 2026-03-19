"""
Entry point for the tiktok-faceless pipeline.

Implementation: Story 1.7 — Orchestrator Pipeline Wiring & Crash Recovery
Implementation: Story 5.3 — Agent Queue Pause & Manual Resume
Implementation: Story 7.1 — Isolated Multi-Account Pipeline Execution
Implementation: Story 7.2 — Account Provisioning with Config Clone
"""

import argparse
import logging
import logging.config
import sys
import time

from langgraph.graph.state import CompiledStateGraph

from tiktok_faceless.config import load_account_config, load_env
from tiktok_faceless.db.queries import (
    get_active_accounts,
    provision_account,
    resolve_agent_errors,
    resume_agent_queue,
)
from tiktok_faceless.db.session import get_session
from tiktok_faceless.graph import build_graph
from tiktok_faceless.state import PipelineState
from tiktok_faceless.utils.alerts import send_resume_alert

logger = logging.getLogger("tiktok_faceless.main")


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="tiktok_faceless.main")
    parser.add_argument("--resume-agent", metavar="AGENT")
    parser.add_argument("--account-id", metavar="ACCOUNT_ID")
    parser.add_argument("--provision-account", metavar="ACCOUNT_ID")
    return parser.parse_args()


def _run_provision(account_id: str) -> None:
    load_account_config(account_id)  # raises KeyError if env vars missing
    with get_session() as session:
        created = provision_account(session, account_id)
    if created:
        logger.info("Provisioned account %s", account_id)


def _run_resume(account_id: str, agent: str) -> None:
    config = load_account_config(account_id)
    with get_session() as session:
        resume_agent_queue(session, account_id, agent)
        resolve_agent_errors(session, account_id, agent)
    send_resume_alert(account_id=account_id, agent=agent, config=config)


def run_pipeline_for_account(account_id: str, graph: CompiledStateGraph) -> None:
    """Run the pipeline for a single account using an isolated thread_id."""
    config = load_account_config(account_id)
    initial_state = PipelineState(
        account_id=account_id,
        phase="tournament",
        candidate_niches=config.niche_pool,
    )
    try:
        thread_id = f"{account_id}-{int(time.time())}"
        graph.invoke(
            initial_state.model_dump(),
            config={"configurable": {"thread_id": thread_id}},
        )
    except Exception as e:  # noqa: BLE001 — intentional catch-all: cross-account safety boundary
        logger.error("Pipeline failed for account %s: %s", account_id, e)


def run_all_accounts(graph: CompiledStateGraph) -> None:
    """Fetch all active accounts and run the pipeline for each serially."""
    with get_session() as session:
        account_ids = [a.account_id for a in get_active_accounts(session)]
    if not account_ids:
        logger.warning("No active accounts found — nothing to run")
        return
    logger.info("Running pipeline for %d active accounts", len(account_ids))
    for account_id in account_ids:
        run_pipeline_for_account(account_id, graph)
        logger.info("Completed pipeline run for account %s", account_id)


def _run_pipeline() -> None:
    graph = build_graph()
    run_all_accounts(graph)


def main() -> None:
    _setup_logging()
    load_env()
    args = parse_args()
    if args.provision_account:
        _run_provision(args.provision_account)
        return
    if bool(args.resume_agent) != bool(args.account_id):
        print(
            "Error: --resume-agent and --account-id must be provided together",
            file=sys.stderr,
        )
        sys.exit(1)
    if args.resume_agent and args.account_id:
        _run_resume(args.account_id, args.resume_agent)
    else:
        _run_pipeline()


if __name__ == "__main__":
    main()

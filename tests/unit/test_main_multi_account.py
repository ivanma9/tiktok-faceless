"""Tests for multi-account pipeline execution in tiktok_faceless.main."""

import sys
from unittest.mock import MagicMock, call, patch

from tiktok_faceless.main import run_all_accounts, run_pipeline_for_account


class TestRunPipelineForAccount:
    def test_run_pipeline_for_account_uses_correct_thread_id(self):
        """graph.invoke is called with thread_id matching account_id."""
        graph = MagicMock()
        mock_state = MagicMock()
        mock_state.model_dump.return_value = {"account_id": "acc-123"}

        with (
            patch("tiktok_faceless.main.load_account_config"),
            patch("tiktok_faceless.main.PipelineState", return_value=mock_state) as mock_ps,
        ):
            run_pipeline_for_account("acc-123", graph)
            mock_ps.assert_called_once_with(account_id="acc-123")

        graph.invoke.assert_called_once_with(
            mock_state.model_dump(), config={"configurable": {"thread_id": "acc-123"}}
        )

    def test_run_pipeline_for_account_isolates_state(self):
        """Two calls with different account_ids use distinct thread_ids."""
        graph = MagicMock()

        def make_state(account_id):
            s = MagicMock()
            s.model_dump.return_value = {"account_id": account_id}
            return s

        with (
            patch("tiktok_faceless.main.load_account_config"),
            patch("tiktok_faceless.main.PipelineState", side_effect=make_state),
        ):
            run_pipeline_for_account("acc-A", graph)
            run_pipeline_for_account("acc-B", graph)

        assert graph.invoke.call_count == 2
        calls = graph.invoke.call_args_list
        thread_ids = [c.kwargs["config"]["configurable"]["thread_id"] for c in calls]
        assert thread_ids[0] == "acc-A"
        assert thread_ids[1] == "acc-B"
        assert thread_ids[0] != thread_ids[1]

    def test_run_pipeline_for_account_catches_exception(self):
        """RuntimeError from graph.invoke is caught; function returns without re-raising."""
        graph = MagicMock()
        graph.invoke.side_effect = RuntimeError("boom")

        mock_state = MagicMock()
        mock_state.model_dump.return_value = {"account_id": "acc-err"}

        with (
            patch("tiktok_faceless.main.load_account_config"),
            patch("tiktok_faceless.main.PipelineState", return_value=mock_state),
        ):
            # Should not raise
            run_pipeline_for_account("acc-err", graph)


class TestRunAllAccounts:
    def test_run_all_accounts_calls_each_serially(self):
        """run_pipeline_for_account is called once per active account, in order."""
        accounts = [MagicMock(account_id=f"acc-{i}") for i in range(3)]
        graph = MagicMock()

        with (
            patch("tiktok_faceless.main.get_session") as mock_get_session,
            patch("tiktok_faceless.main.get_active_accounts", return_value=accounts),
            patch("tiktok_faceless.main.run_pipeline_for_account") as mock_run,
        ):
            mock_get_session.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_get_session.return_value.__exit__ = MagicMock(return_value=False)
            with patch("tiktok_faceless.main.logger") as mock_logger:
                run_all_accounts(graph)

        assert mock_run.call_count == 3
        expected_calls = [call(f"acc-{i}", graph) for i in range(3)]
        mock_run.assert_has_calls(expected_calls, any_order=False)
        # Verify completion log emitted after each account
        completion_calls = [
            c for c in mock_logger.info.call_args_list if "Completed pipeline run" in str(c)
        ]
        assert len(completion_calls) == 3

    def test_run_all_accounts_empty_list(self):
        """No graph.invoke calls when get_active_accounts returns []."""
        graph = MagicMock()

        with (
            patch("tiktok_faceless.main.get_session") as mock_get_session,
            patch("tiktok_faceless.main.get_active_accounts", return_value=[]),
            patch("tiktok_faceless.main.run_pipeline_for_account") as mock_run,
        ):
            mock_get_session.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_get_session.return_value.__exit__ = MagicMock(return_value=False)
            with patch("tiktok_faceless.main.logger") as mock_logger:
                run_all_accounts(graph)

        mock_run.assert_not_called()
        graph.invoke.assert_not_called()
        # Verify warning log emitted
        mock_logger.warning.assert_called_once_with("No active accounts found — nothing to run")


class TestRunPipelineDefaultCliPath:
    def test_run_pipeline_default_cli_path(self):
        """With no CLI flags, main() calls _run_pipeline (not _run_resume)."""
        from tiktok_faceless.main import main

        with (
            patch.object(sys, "argv", ["main"]),
            patch("tiktok_faceless.main._run_pipeline") as mock_pipeline,
            patch("tiktok_faceless.main._run_resume") as mock_resume,
        ):
            main()

        mock_pipeline.assert_called_once()
        mock_resume.assert_not_called()

"""Tests for tiktok_faceless/graph.py — build_graph."""

from unittest.mock import MagicMock, patch

from tiktok_faceless.graph import build_graph


class TestBuildGraph:
    def test_returns_compiled_graph(self) -> None:
        graph = build_graph()
        assert graph is not None

    def test_expected_nodes_registered(self) -> None:
        graph = build_graph()
        node_names = set(graph.nodes.keys())
        for expected in ("orchestrator", "script", "monetization", "production", "publishing"):
            assert expected in node_names, f"Missing node: {expected}"

    def test_graph_invocable_with_mocked_nodes(self) -> None:
        """Graph can be invoked end-to-end when all agent nodes are mocked to return {}."""
        empty: dict = {}
        with patch("tiktok_faceless.agents.orchestrator.get_session") as mock_gs:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=MagicMock())
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_gs.return_value = mock_ctx

            with patch("tiktok_faceless.agents.script.load_account_config") as mock_cfg:
                mock_cfg.return_value = MagicMock(anthropic_api_key="key")
                with patch("tiktok_faceless.agents.script.LLMClient") as mock_llm:
                    mock_llm.return_value.generate_script.return_value = "script text"

                    with patch(
                        "tiktok_faceless.agents.monetization.load_account_config"
                    ) as mock_cfg2:
                        mock_cfg2.return_value = MagicMock(
                            tiktok_access_token="tok", tiktok_open_id="oid"
                        )
                        with patch(
                            "tiktok_faceless.agents.monetization.TikTokAPIClient"
                        ) as mock_tk:
                            mock_tk.return_value.generate_affiliate_link.return_value = (
                                "https://aff.link"
                            )
                            with patch(
                                "tiktok_faceless.agents.monetization.get_session"
                            ) as mock_gs2:
                                mock_gs2.return_value = mock_ctx

                                with patch(
                                    "tiktok_faceless.agents.production.load_account_config"
                                ) as mock_cfg3:
                                    mock_cfg3.return_value = MagicMock(
                                        elevenlabs_api_key="el",
                                        elevenlabs_voice_id="v",
                                        creatomate_api_key="cr",
                                        creatomate_template_id="t",
                                    )
                                    with patch(
                                        "tiktok_faceless.agents.production.ElevenLabsClient"
                                    ) as mock_el:
                                        mock_el.return_value.generate_voiceover.return_value = (
                                            b"audio"
                                        )
                                        with patch(
                                            "tiktok_faceless.agents.production.CreatomateClient"
                                        ) as mock_cr:
                                            mock_cr.return_value.submit_render.return_value = (
                                                "job1"
                                            )
                                            mock_cr.return_value.poll_status.return_value = (
                                                "https://cdn.example.com/v.mp4"
                                            )
                                            with patch(
                                                "tiktok_faceless.agents.production.Path"
                                            ) as mock_path:
                                                mock_path.return_value.__truediv__ = (
                                                    MagicMock(return_value=MagicMock())
                                                )
                                                mock_path.return_value.__str__ = MagicMock(
                                                    return_value="/out/vid.mp4"
                                                )

                                                with patch(
                                                    "tiktok_faceless.agents.publishing"
                                                    ".load_account_config"
                                                ) as mock_cfg4:
                                                    mock_cfg4.return_value = MagicMock(
                                                        tiktok_access_token="tok",
                                                        tiktok_open_id="oid",
                                                        posting_window_start=0,
                                                        posting_window_end=23,
                                                        max_posts_per_day=3,
                                                        tournament_posts_per_day=3,
                                                        commit_posts_per_day=3,
                                                        scale_posts_per_day=3,
                                                    )
                                                    with patch(
                                                        "tiktok_faceless.agents.publishing"
                                                        ".is_within_posting_window",
                                                        return_value=True,
                                                    ):
                                                        with patch(
                                                            "tiktok_faceless.agents.publishing"
                                                            ".time"
                                                        ) as mock_time:
                                                            mock_time.time.return_value = (
                                                                9_999_999.0
                                                            )
                                                            with patch(
                                                                "tiktok_faceless.agents"
                                                                ".publishing.get_session"
                                                            ) as mock_gs3:
                                                                mock_gs3.return_value = mock_ctx
                                                                with patch(
                                                                    "tiktok_faceless.agents"
                                                                    ".publishing.TikTokAPIClient"
                                                                ) as mock_tk2:
                                                                    mock_resp = MagicMock()
                                                                    mock_resp.video_id = "v1"
                                                                    mock_tk2.return_value\
                                                                        .post_video\
                                                                        .return_value = mock_resp

                                                                    graph = build_graph()
                                                                    state_dict = {
                                                                        "account_id": "acc1",
                                                                        "selected_product": {
                                                                            "product_id": "p1",
                                                                            "product_name": "W",
                                                                            "product_url": "u",
                                                                            "commission_rate": 0.1,
                                                                            "niche": "health",
                                                                            "sales_velocity_score": 1.0,  # noqa: E501
                                                                        },
                                                                    }
                                                                    result = graph.invoke(
                                                                        state_dict,
                                                                        config={
                                                                            "configurable": {
                                                                                "thread_id": "t1"
                                                                            }
                                                                        },
                                                                    )
                                                                    assert result is not None
        _ = empty  # suppress unused variable

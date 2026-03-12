"""Tests for Pydantic response/request models in tiktok_faceless/models/."""

import time

from tiktok_faceless.models.elevenlabs import ElevenLabsVoiceConfig
from tiktok_faceless.models.shop import AffiliateProduct, CommissionRecord
from tiktok_faceless.models.tiktok import TikTokPostResponse, TikTokVideoMetrics


class TestTikTokVideoMetrics:
    def test_instantiation(self) -> None:
        m = TikTokVideoMetrics(
            video_id="vid_1",
            view_count=1000,
            like_count=50,
            comment_count=10,
            share_count=5,
            average_time_watched=12.5,
            traffic_source_type={"FOR_YOU": 0.8, "FOLLOW": 0.2},
        )
        assert m.video_id == "vid_1"
        assert m.view_count == 1000
        assert m.traffic_source_type["FOR_YOU"] == 0.8

    def test_post_response_optional_share_url(self) -> None:
        r = TikTokPostResponse(video_id="vid_2")
        assert r.video_id == "vid_2"
        assert r.share_url is None


class TestElevenLabsVoiceConfig:
    def test_defaults(self) -> None:
        cfg = ElevenLabsVoiceConfig(voice_id="voice_abc")
        assert cfg.stability == 0.5
        assert cfg.similarity_boost == 0.75
        assert cfg.style == 0.0

    def test_custom_values(self) -> None:
        cfg = ElevenLabsVoiceConfig(voice_id="v1", stability=0.9, similarity_boost=0.6)
        assert cfg.stability == 0.9


class TestShopModels:
    def test_affiliate_product(self) -> None:
        p = AffiliateProduct(
            product_id="p1",
            product_name="Widget",
            product_url="https://example.com",
            commission_rate=0.15,
            niche="tech",
        )
        assert p.sales_velocity_score == 0.0
        assert p.commission_rate == 0.15

    def test_commission_record_timestamp_auto(self) -> None:
        before = time.time()
        r = CommissionRecord(
            order_id="ord_1",
            product_id="p1",
            commission_amount=4.50,
        )
        after = time.time()
        assert before <= r.recorded_at <= after

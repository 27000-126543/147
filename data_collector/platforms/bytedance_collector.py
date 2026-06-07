from datetime import date
from typing import List, Optional
from models import AdPerformanceData, PlatformType, TouchPoint
from ..base_collector import BasePlatformCollector
from ..sample_data_generator import SampleDataGenerator


class BytedanceCollector(BasePlatformCollector):
    def __init__(self, platform: PlatformType = PlatformType.BYTEDANCE):
        super().__init__(platform)
        self.sample_gen = SampleDataGenerator()
        self.channels = ["bytedance_douyin", "bytedance_toutiao"]
        self.campaigns = ["douyin_live", "douyin_short", "toutiao_feed", "toutiao_search"]
        self.audiences = ["18-24", "25-34", "35-44", "45+"]

    async def fetch_data(
        self,
        start_date: date,
        end_date: date,
        channels: Optional[List[str]] = None,
        hourly: bool = False
    ) -> List[AdPerformanceData]:
        target_channels = channels or self.channels
        return self.sample_gen.generate_platform_data(
            platform=PlatformType.BYTEDANCE,
            channels=target_channels,
            start_date=start_date,
            end_date=end_date,
            campaigns=self.campaigns,
            audiences=self.audiences,
            base_impressions=100000,
            base_clicks=5000,
            base_conversions=250,
            base_cost=10000,
            base_revenue=30000,
            hourly=hourly
        )

    async def fetch_touchpoints(
        self,
        start_date: date,
        end_date: date,
        conversion_ids: Optional[List[str]] = None
    ) -> List[TouchPoint]:
        return self.sample_gen.generate_platform_touchpoints(
            platform=PlatformType.BYTEDANCE,
            channels=self.channels,
            start_date=start_date,
            end_date=end_date,
            campaigns=self.campaigns,
            audiences=self.audiences,
            num_touchpoints=1000
        )

    async def _fetch_daily_data(
        self,
        start_date: date,
        end_date: date,
        channels: Optional[List[str]] = None,
        hour: Optional[int] = None
    ) -> List[AdPerformanceData]:
        target_channels = channels or self.channels
        return self.sample_gen.generate_platform_data(
            platform=PlatformType.BYTEDANCE,
            channels=target_channels,
            start_date=start_date,
            end_date=end_date,
            campaigns=self.campaigns,
            audiences=self.audiences,
            base_impressions=100000,
            base_clicks=5000,
            base_conversions=250,
            base_cost=10000,
            base_revenue=30000,
            hourly=False,
            specific_hour=hour
        )

from datetime import date
from typing import List, Optional
from models import AdPerformanceData, PlatformType, TouchPoint
from ..base_collector import BasePlatformCollector
from ..sample_data_generator import SampleDataGenerator


class XiaohongshuCollector(BasePlatformCollector):
    def __init__(self, platform: PlatformType = PlatformType.XIAOHONGSHU):
        super().__init__(platform)
        self.sample_gen = SampleDataGenerator()
        self.channels = ["xiaohongshu"]
        self.campaigns = ["xhs_note", "xhs_live", "xhs_search", "xhs_feed"]
        self.audiences = ["18-24_female", "25-34_female", "35-44_female", "25-34_male"]

    async def fetch_data(
        self,
        start_date: date,
        end_date: date,
        channels: Optional[List[str]] = None,
        hourly: bool = False
    ) -> List[AdPerformanceData]:
        target_channels = channels or self.channels
        return self.sample_gen.generate_platform_data(
            platform=PlatformType.XIAOHONGSHU,
            channels=target_channels,
            start_date=start_date,
            end_date=end_date,
            campaigns=self.campaigns,
            audiences=self.audiences,
            base_impressions=30000,
            base_clicks=1500,
            base_conversions=60,
            base_cost=3000,
            base_revenue=9000,
            hourly=hourly
        )

    async def fetch_touchpoints(
        self,
        start_date: date,
        end_date: date,
        conversion_ids: Optional[List[str]] = None
    ) -> List[TouchPoint]:
        return self.sample_gen.generate_platform_touchpoints(
            platform=PlatformType.XIAOHONGSHU,
            channels=self.channels,
            start_date=start_date,
            end_date=end_date,
            campaigns=self.campaigns,
            audiences=self.audiences,
            num_touchpoints=300
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
            platform=PlatformType.XIAOHONGSHU,
            channels=target_channels,
            start_date=start_date,
            end_date=end_date,
            campaigns=self.campaigns,
            audiences=self.audiences,
            base_impressions=30000,
            base_clicks=1500,
            base_conversions=60,
            base_cost=3000,
            base_revenue=9000,
            hourly=False,
            specific_hour=hour
        )

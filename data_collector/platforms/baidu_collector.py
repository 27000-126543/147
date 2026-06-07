from datetime import date, timedelta
from typing import List, Optional
import numpy as np
from models import AdPerformanceData, PlatformType, TouchPoint
from utils import generate_id
from ..base_collector import BasePlatformCollector
from ..sample_data_generator import SampleDataGenerator


class BaiduCollector(BasePlatformCollector):
    def __init__(self, platform: PlatformType = PlatformType.BAIDU):
        super().__init__(platform)
        self.sample_gen = SampleDataGenerator()
        self.channels = ["baidu_search", "baidu_feed"]
        self.campaigns = ["brand_campaign", "performance_campaign", "retargeting"]
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
            platform=PlatformType.BAIDU,
            channels=target_channels,
            start_date=start_date,
            end_date=end_date,
            campaigns=self.campaigns,
            audiences=self.audiences,
            base_impressions=50000,
            base_clicks=2500,
            base_conversions=100,
            base_cost=5000,
            base_revenue=15000,
            hourly=hourly
        )

    async def fetch_touchpoints(
        self,
        start_date: date,
        end_date: date,
        conversion_ids: Optional[List[str]] = None
    ) -> List[TouchPoint]:
        return self.sample_gen.generate_platform_touchpoints(
            platform=PlatformType.BAIDU,
            channels=self.channels,
            start_date=start_date,
            end_date=end_date,
            campaigns=self.campaigns,
            audiences=self.audiences,
            num_touchpoints=500
        )

    async def _fetch_daily_data(
        self,
        start_date: date,
        end_date: date,
        channels: Optional[List[str]] = None,
        hour: Optional[int] = None
    ) -> List[AdPerformanceData]:
        target_channels = channels or self.channels
        data = self.sample_gen.generate_platform_data(
            platform=PlatformType.BAIDU,
            channels=target_channels,
            start_date=start_date,
            end_date=end_date,
            campaigns=self.campaigns,
            audiences=self.audiences,
            base_impressions=50000,
            base_clicks=2500,
            base_conversions=100,
            base_cost=5000,
            base_revenue=15000,
            hourly=False,
            specific_hour=hour
        )
        return data

from datetime import date
from typing import List, Optional
from models import AdPerformanceData, PlatformType, TouchPoint
from ..base_collector import BasePlatformCollector
from ..sample_data_generator import SampleDataGenerator


class AliyunCollector(BasePlatformCollector):
    def __init__(self, platform: PlatformType = PlatformType.ALIYUN):
        super().__init__(platform)
        self.sample_gen = SampleDataGenerator()
        self.channels = ["aliyun_zhima"]
        self.campaigns = ["zhima_credit", "zhima_marketing", "ali_pay"]
        self.audiences = ["18-24", "25-34", "35-44", "45+", "high_income"]

    async def fetch_data(
        self,
        start_date: date,
        end_date: date,
        channels: Optional[List[str]] = None,
        hourly: bool = False
    ) -> List[AdPerformanceData]:
        target_channels = channels or self.channels
        return self.sample_gen.generate_platform_data(
            platform=PlatformType.ALIYUN,
            channels=target_channels,
            start_date=start_date,
            end_date=end_date,
            campaigns=self.campaigns,
            audiences=self.audiences,
            base_impressions=60000,
            base_clicks=3000,
            base_conversions=150,
            base_cost=6000,
            base_revenue=18000,
            hourly=hourly
        )

    async def fetch_touchpoints(
        self,
        start_date: date,
        end_date: date,
        conversion_ids: Optional[List[str]] = None
    ) -> List[TouchPoint]:
        return self.sample_gen.generate_platform_touchpoints(
            platform=PlatformType.ALIYUN,
            channels=self.channels,
            start_date=start_date,
            end_date=end_date,
            campaigns=self.campaigns,
            audiences=self.audiences,
            num_touchpoints=600
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
            platform=PlatformType.ALIYUN,
            channels=target_channels,
            start_date=start_date,
            end_date=end_date,
            campaigns=self.campaigns,
            audiences=self.audiences,
            base_impressions=60000,
            base_clicks=3000,
            base_conversions=150,
            base_cost=6000,
            base_revenue=18000,
            hourly=False,
            specific_hour=hour
        )

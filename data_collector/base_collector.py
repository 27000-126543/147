import asyncio
import aiohttp
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional
from models import AdPerformanceData, PlatformType, TouchPoint
from utils import get_logger, generate_id, retry
from config import settings

logger = get_logger(__name__)


class BasePlatformCollector(ABC):
    def __init__(self, platform: PlatformType):
        self.platform = platform
        self.config = settings.PLATFORM_API_CONFIGS.get(platform.value, {})
        self.api_url = self.config.get("api_url", "")
        self.timeout = self.config.get("timeout", 30)
        self.retry_times = self.config.get("retry_times", 3)
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.session:
            await self.session.close()

    @abstractmethod
    async def fetch_data(
        self,
        start_date: date,
        end_date: date,
        channels: Optional[List[str]] = None,
        hourly: bool = False
    ) -> List[AdPerformanceData]:
        pass

    @abstractmethod
    async def fetch_touchpoints(
        self,
        start_date: date,
        end_date: date,
        conversion_ids: Optional[List[str]] = None
    ) -> List[TouchPoint]:
        pass

    @retry(max_retries=3, delay=1.0)
    async def _make_request(
        self,
        endpoint: str,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if not self.session:
            raise RuntimeError("Session not initialized")

        url = f"{self.api_url}/{endpoint.lstrip('/')}"
        headers = self._get_auth_headers()

        logger.debug(f"Making {method} request to {url}")

        async with self.session.request(method, url, params=params, json=data, headers=headers) as response:
            if response.status != 200:
                error_text = await response.text()
                logger.error(f"API request failed: {response.status} - {error_text}")
                raise Exception(f"API request failed: {response.status}")

            response_data = await response.json()
            return response_data

    def _get_auth_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json"
        }

    def _get_access_token(self) -> str:
        return f"demo_token_{self.platform.value}"

    def _generate_touchpoints(
        self,
        channel: str,
        campaign: str,
        audience: str,
        date_val: date,
        clicks: int
    ) -> List[TouchPoint]:
        touchpoints = []
        for i in range(min(clicks, 50)):
            hour = (i * 24 // max(clicks, 1)) % 24
            minute = (i * 60 // max(clicks, 1)) % 60
            timestamp = datetime.combine(date_val, datetime.min.time()) + timedelta(hours=hour, minutes=minute)
            
            touchpoints.append(TouchPoint(
                touchpoint_id=generate_id("tp"),
                channel=channel,
                timestamp=timestamp,
                campaign=campaign,
                audience=audience,
                interaction_type="click",
                metadata={
                    "platform": self.platform.value,
                    "position": i + 1,
                    "hour": hour
                }
            ))
        return touchpoints

    async def _fetch_hourly_data(
        self,
        start_date: date,
        end_date: date,
        channels: Optional[List[str]] = None
    ) -> List[AdPerformanceData]:
        all_data = []
        current_date = start_date
        
        while current_date <= end_date:
            for hour in range(24):
                daily_data = await self._fetch_daily_data(current_date, current_date, channels, hour)
                all_data.extend(daily_data)
            current_date += timedelta(days=1)
            
        return all_data

    @abstractmethod
    async def _fetch_daily_data(
        self,
        start_date: date,
        end_date: date,
        channels: Optional[List[str]] = None,
        hour: Optional[int] = None
    ) -> List[AdPerformanceData]:
        pass

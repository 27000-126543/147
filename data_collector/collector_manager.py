import asyncio
from datetime import date, timedelta
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd
import os
from config import settings
from models import AdPerformanceData, PlatformType, TouchPoint
from utils import get_logger, generate_id, parallel_process, batch_iterator
from .base_collector import BasePlatformCollector
from .platforms.baidu_collector import BaiduCollector
from .platforms.tencent_collector import TencentCollector
from .platforms.bytedance_collector import BytedanceCollector
from .platforms.aliyun_collector import AliyunCollector
from .platforms.kuaishou_collector import KuaishouCollector
from .platforms.xiaohongshu_collector import XiaohongshuCollector
from .sample_data_generator import SampleDataGenerator

logger = get_logger(__name__)


class DataCollectorManager:
    def __init__(self, use_sample_data: bool = True):
        self.use_sample_data = use_sample_data
        self.collectors: Dict[PlatformType, BasePlatformCollector] = {}
        self._init_collectors()
        self.sample_generator = SampleDataGenerator()

    def _init_collectors(self):
        collector_map = {
            PlatformType.BAIDU: BaiduCollector,
            PlatformType.TENCENT: TencentCollector,
            PlatformType.BYTEDANCE: BytedanceCollector,
            PlatformType.ALIYUN: AliyunCollector,
            PlatformType.KUAISHOU: KuaishouCollector,
            PlatformType.XIAOHONGSHU: XiaohongshuCollector,
        }

        for platform, collector_class in collector_map.items():
            if platform.value in settings.AD_PLATFORMS:
                self.collectors[platform] = collector_class(platform)

    async def collect_all_platforms(
        self,
        start_date: date,
        end_date: date,
        platforms: Optional[List[PlatformType]] = None,
        channels: Optional[List[str]] = None,
        hourly: bool = False
    ) -> List[AdPerformanceData]:
        logger.info(f"Starting data collection from {start_date} to {end_date}")
        
        if self.use_sample_data:
            logger.info("Using sample data generation mode")
            return await self._collect_sample_data(start_date, end_date, hourly)

        target_platforms = platforms or list(self.collectors.keys())
        all_data = []

        tasks = []
        for platform in target_platforms:
            if platform in self.collectors:
                collector = self.collectors[platform]
                task = self._collect_from_platform(
                    collector, start_date, end_date, channels, hourly
                )
                tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                platform = target_platforms[i]
                logger.error(f"Failed to collect from {platform}: {str(result)}")
            else:
                all_data.extend(result)

        logger.info(f"Collected {len(all_data)} records from {len(target_platforms)} platforms")
        await self._save_data(all_data, start_date, end_date)
        return all_data

    async def _collect_from_platform(
        self,
        collector: BasePlatformCollector,
        start_date: date,
        end_date: date,
        channels: Optional[List[str]] = None,
        hourly: bool = False
    ) -> List[AdPerformanceData]:
        async with collector:
            return await collector.fetch_data(start_date, end_date, channels, hourly)

    async def _collect_sample_data(
        self,
        start_date: date,
        end_date: date,
        hourly: bool = False
    ) -> List[AdPerformanceData]:
        data = self.sample_generator.generate_performance_data(
            start_date, end_date, hourly=hourly
        )
        await self._save_data(data, start_date, end_date)
        return data

    async def collect_touchpoints(
        self,
        start_date: date,
        end_date: date,
        platforms: Optional[List[PlatformType]] = None
    ) -> List[TouchPoint]:
        logger.info(f"Collecting touchpoints from {start_date} to {end_date}")
        
        if self.use_sample_data:
            return self.sample_generator.generate_touchpoints(start_date, end_date)

        target_platforms = platforms or list(self.collectors.keys())
        all_touchpoints = []

        for platform in target_platforms:
            if platform in self.collectors:
                collector = self.collectors[platform]
                try:
                    async with collector:
                        touchpoints = await collector.fetch_touchpoints(start_date, end_date)
                        all_touchpoints.extend(touchpoints)
                        logger.info(f"Collected {len(touchpoints)} touchpoints from {platform}")
                except Exception as e:
                    logger.error(f"Failed to collect touchpoints from {platform}: {str(e)}")

        return all_touchpoints

    async def _save_data(
        self,
        data: List[AdPerformanceData],
        start_date: date,
        end_date: date
    ):
        if not data:
            return

        try:
            df = pd.DataFrame([d.model_dump() for d in data])
            
            if 'touchpoints' in df.columns:
                df = df.drop(columns=['touchpoints'])
            
            filename = f"performance_data_{start_date}_{end_date}_{generate_id()}.parquet"
            filepath = os.path.join(settings.DATA_DIR, filename)
            
            df.to_parquet(filepath, index=False)
            logger.info(f"Saved {len(data)} records to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save data: {str(e)}")

    def load_saved_data(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> pd.DataFrame:
        all_files = []
        for f in os.listdir(settings.DATA_DIR):
            if f.startswith("performance_data_") and f.endswith(".parquet"):
                all_files.append(os.path.join(settings.DATA_DIR, f))

        if not all_files:
            return pd.DataFrame()

        dfs = []
        for filepath in sorted(all_files):
            try:
                df = pd.read_parquet(filepath)
                if start_date or end_date:
                    if 'date' in df.columns:
                        df['date'] = pd.to_datetime(df['date']).dt.date
                        if start_date:
                            df = df[df['date'] >= start_date]
                        if end_date:
                            df = df[df['date'] <= end_date]
                dfs.append(df)
            except Exception as e:
                logger.error(f"Failed to load {filepath}: {str(e)}")

        if not dfs:
            return pd.DataFrame()

        result = pd.concat(dfs, ignore_index=True)
        logger.info(f"Loaded {len(result)} records from saved data")
        return result

    async def collect_in_batches(
        self,
        start_date: date,
        end_date: date,
        batch_days: int = 7,
        **kwargs
    ) -> List[AdPerformanceData]:
        all_data = []
        current_start = start_date

        while current_start <= end_date:
            current_end = min(current_start + timedelta(days=batch_days - 1), end_date)
            logger.info(f"Collecting batch: {current_start} to {current_end}")
            
            batch_data = await self.collect_all_platforms(
                current_start, current_end, **kwargs
            )
            all_data.extend(batch_data)
            
            current_start = current_end + timedelta(days=1)

        return all_data

    def process_high_volume_data(
        self,
        data: List[AdPerformanceData]
    ) -> pd.DataFrame:
        logger.info(f"Processing {len(data)} records with high-volume engine")
        
        import dask.dataframe as dd
        from dask.diagnostics import ProgressBar

        df = pd.DataFrame([d.model_dump() for d in data])
        if 'touchpoints' in df.columns:
            df = df.drop(columns=['touchpoints'])

        ddf = dd.from_pandas(df, npartitions=settings.DATA_PROCESSING_PARTITIONS)
        
        with ProgressBar():
            result = ddf.compute()

        logger.info(f"High-volume processing complete: {len(result)} records")
        return result

    def get_collection_summary(
        self,
        data: List[AdPerformanceData]
    ) -> Dict[str, Any]:
        df = pd.DataFrame([d.model_dump() for d in data])
        
        summary = {
            "total_records": len(data),
            "date_range": {
                "start": df['date'].min().isoformat() if 'date' in df.columns else None,
                "end": df['date'].max().isoformat() if 'date' in df.columns else None
            },
            "platforms": df['platform'].value_counts().to_dict() if 'platform' in df.columns else {},
            "channels": df['channel'].nunique() if 'channel' in df.columns else 0,
            "total_impressions": int(df['impressions'].sum()) if 'impressions' in df.columns else 0,
            "total_clicks": int(df['clicks'].sum()) if 'clicks' in df.columns else 0,
            "total_conversions": int(df['conversions'].sum()) if 'conversions' in df.columns else 0,
            "total_cost": float(df['cost'].sum()) if 'cost' in df.columns else 0,
            "total_revenue": float(df['revenue'].sum()) if 'revenue' in df.columns else 0,
        }
        
        return summary

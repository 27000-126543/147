import numpy as np
import pandas as pd
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional
from models import AdPerformanceData, PlatformType, TouchPoint
from utils import generate_id, get_logger

logger = get_logger(__name__)


class SampleDataGenerator:
    def __init__(self, seed: int = 42):
        np.random.seed(seed)
        self.seasonality_factors = {
            1: 0.8, 2: 0.85, 3: 1.0, 4: 1.1, 5: 1.2, 6: 1.3,
            7: 1.25, 8: 1.15, 9: 1.1, 10: 1.05, 11: 0.95, 12: 0.9
        }
        self.day_of_week_factors = {
            0: 1.0, 1: 1.05, 2: 1.1, 3: 1.08, 4: 1.02,
            5: 0.85, 6: 0.8
        }
        self.hour_factors = {
            h: 0.3 + 0.7 * np.sin(np.pi * (h - 6) / 12) if 6 <= h <= 22 else 0.1
            for h in range(24)
        }
        self.hour_factors[12] = 1.2
        self.hour_factors[20] = 1.3
        self.hour_factors[21] = 1.25

    def _get_multiplier(self, date_val: date, hour: Optional[int] = None) -> float:
        month_factor = self.seasonality_factors.get(date_val.month, 1.0)
        dow_factor = self.day_of_week_factors.get(date_val.weekday(), 1.0)
        hour_factor = self.hour_factors.get(hour, 1.0) if hour is not None else 1.0
        random_factor = np.random.normal(1.0, 0.15)
        return max(0.1, month_factor * dow_factor * hour_factor * random_factor)

    def generate_performance_data(
        self,
        start_date: date,
        end_date: date,
        hourly: bool = False
    ) -> List[AdPerformanceData]:
        logger.info(f"Generating sample performance data from {start_date} to {end_date}")
        
        all_data = []
        platform_configs = [
            {
                'platform': PlatformType.BAIDU,
                'channels': ['baidu_search', 'baidu_feed'],
                'campaigns': ['brand', 'performance', 'retargeting'],
                'audiences': ['18-24', '25-34', '35-44', '45+'],
                'base_impressions': 50000,
                'base_clicks': 2500,
                'base_conversions': 100,
                'base_cost': 5000,
                'base_revenue': 15000
            },
            {
                'platform': PlatformType.TENCENT,
                'channels': ['tencent_wechat', 'tencent_qq'],
                'campaigns': ['moments', 'official', 'feed'],
                'audiences': ['18-24', '25-34', '35-44', '45+'],
                'base_impressions': 80000,
                'base_clicks': 4000,
                'base_conversions': 200,
                'base_cost': 8000,
                'base_revenue': 24000
            },
            {
                'platform': PlatformType.BYTEDANCE,
                'channels': ['bytedance_douyin', 'bytedance_toutiao'],
                'campaigns': ['live', 'short_video', 'feed'],
                'audiences': ['18-24', '25-34', '35-44', '45+'],
                'base_impressions': 100000,
                'base_clicks': 5000,
                'base_conversions': 250,
                'base_cost': 10000,
                'base_revenue': 30000
            },
            {
                'platform': PlatformType.ALIYUN,
                'channels': ['aliyun_zhima'],
                'campaigns': ['credit_marketing', 'pay_promotion'],
                'audiences': ['25-34', '35-44', '45+', 'high_income'],
                'base_impressions': 60000,
                'base_clicks': 3000,
                'base_conversions': 150,
                'base_cost': 6000,
                'base_revenue': 18000
            },
            {
                'platform': PlatformType.KUAISHOU,
                'channels': ['kuaishou'],
                'campaigns': ['short_video', 'live_streaming'],
                'audiences': ['18-24', '25-34', '35-44', 'lower_tier'],
                'base_impressions': 40000,
                'base_clicks': 2000,
                'base_conversions': 80,
                'base_cost': 4000,
                'base_revenue': 10000
            },
            {
                'platform': PlatformType.XIAOHONGSHU,
                'channels': ['xiaohongshu'],
                'campaigns': ['notes', 'search', 'live'],
                'audiences': ['18-24_f', '25-34_f', '35-44_f', '25-34_m'],
                'base_impressions': 30000,
                'base_clicks': 1500,
                'base_conversions': 60,
                'base_cost': 3000,
                'base_revenue': 9000
            }
        ]

        for config in platform_configs:
            platform_data = self.generate_platform_data(
                platform=config['platform'],
                channels=config['channels'],
                start_date=start_date,
                end_date=end_date,
                campaigns=config['campaigns'],
                audiences=config['audiences'],
                base_impressions=config['base_impressions'],
                base_clicks=config['base_clicks'],
                base_conversions=config['base_conversions'],
                base_cost=config['base_cost'],
                base_revenue=config['base_revenue'],
                hourly=hourly
            )
            all_data.extend(platform_data)

        logger.info(f"Generated {len(all_data)} sample performance records")
        return all_data

    def generate_platform_data(
        self,
        platform: PlatformType,
        channels: List[str],
        start_date: date,
        end_date: date,
        campaigns: List[str],
        audiences: List[str],
        base_impressions: int,
        base_clicks: int,
        base_conversions: int,
        base_cost: float,
        base_revenue: float,
        hourly: bool = False,
        specific_hour: Optional[int] = None
    ) -> List[AdPerformanceData]:
        data = []
        current_date = start_date
        channel_count = len(channels)
        campaign_count = len(campaigns)
        audience_count = len(audiences)
        
        while current_date <= end_date:
            hours = [specific_hour] if specific_hour is not None else (range(24) if hourly else [None])
            
            for hour in hours:
                for channel_idx, channel in enumerate(channels):
                    for campaign in campaigns:
                        for audience in audiences:
                            multiplier = self._get_multiplier(current_date, hour)
                            
                            channel_weight = 1.0 - (channel_idx * 0.2 / max(channel_count - 1, 1))
                            
                            impressions = int(base_impressions * multiplier * channel_weight 
                                            / (campaign_count * audience_count * (24 if hourly else 1)))
                            impressions = max(0, impressions + np.random.randint(-100, 100))
                            
                            ctr = base_clicks / base_impressions
                            clicks = int(impressions * ctr * np.random.normal(1.0, 0.1))
                            clicks = max(0, min(clicks, impressions))
                            
                            cvr = base_conversions / base_clicks
                            conversions = int(clicks * cvr * np.random.normal(1.0, 0.15))
                            conversions = max(0, min(conversions, clicks))
                            
                            cpc = base_cost / base_clicks
                            cost = round(clicks * cpc * np.random.normal(1.0, 0.05), 2)
                            cost = max(0, cost)
                            
                            rpconv = base_revenue / base_conversions
                            revenue = round(conversions * rpconv * np.random.normal(1.0, 0.2), 2)
                            revenue = max(0, revenue)
                            
                            data.append(AdPerformanceData(
                                platform=platform,
                                channel=channel,
                                campaign=campaign,
                                audience=audience,
                                date=current_date,
                                hour=hour,
                                impressions=impressions,
                                clicks=clicks,
                                conversions=conversions,
                                cost=cost,
                                revenue=revenue,
                                touchpoints=[],
                                metadata={
                                    'generator': 'sample',
                                    'multiplier': round(multiplier, 4),
                                    'channel_weight': round(channel_weight, 4)
                                }
                            ))
            
            current_date += timedelta(days=1)
        
        return data

    def generate_touchpoints(
        self,
        start_date: date,
        end_date: date,
        num_conversions: int = 1000
    ) -> List[TouchPoint]:
        logger.info(f"Generating sample touchpoints for {num_conversions} conversions")
        
        all_touchpoints = []
        channels = list(settings.CHANNEL_CONFIG.keys())
        campaigns = ["brand", "performance", "retargeting", "awareness"]
        audiences = ["18-24", "25-34", "35-44", "45+"]
        
        for i in range(num_conversions):
            conv_date = start_date + timedelta(
                days=np.random.randint(0, (end_date - start_date).days + 1)
            )
            
            path_length = np.random.randint(2, 8)
            channel_sequence = np.random.choice(
                channels, size=path_length, replace=True,
                p=[0.2, 0.15, 0.25, 0.1, 0.1, 0.1, 0.05, 0.03, 0.02]
            )
            
            base_time = datetime.combine(conv_date, datetime.min.time()) + timedelta(
                hours=np.random.randint(8, 23),
                minutes=np.random.randint(0, 60)
            )
            
            for pos, channel in enumerate(channel_sequence):
                tp_time = base_time - timedelta(
                    days=np.random.randint(0, 3),
                    hours=np.random.randint(0, 24)
                )
                tp_time = max(tp_time, datetime.combine(start_date, datetime.min.time()))
                
                all_touchpoints.append(TouchPoint(
                    touchpoint_id=generate_id("tp"),
                    channel=channel,
                    timestamp=tp_time,
                    campaign=np.random.choice(campaigns),
                    audience=np.random.choice(audiences),
                    interaction_type=np.random.choice(
                        ["click", "impression", "view"],
                        p=[0.6, 0.3, 0.1]
                    ),
                    metadata={
                        'conversion_num': i,
                        'position_in_path': pos + 1,
                        'path_length': path_length,
                        'is_last_touch': pos == path_length - 1,
                        'is_first_touch': pos == 0
                    }
                ))
        
        logger.info(f"Generated {len(all_touchpoints)} touchpoints")
        return all_touchpoints

    def generate_platform_touchpoints(
        self,
        platform: PlatformType,
        channels: List[str],
        start_date: date,
        end_date: date,
        campaigns: List[str],
        audiences: List[str],
        num_touchpoints: int = 500
    ) -> List[TouchPoint]:
        touchpoints = []
        
        for i in range(num_touchpoints):
            rand_date = start_date + timedelta(
                days=np.random.randint(0, (end_date - start_date).days + 1)
            )
            hour = np.random.randint(8, 23)
            minute = np.random.randint(0, 60)
            timestamp = datetime.combine(rand_date, datetime.min.time()) + timedelta(hours=hour, minutes=minute)
            
            touchpoints.append(TouchPoint(
                touchpoint_id=generate_id("tp"),
                channel=np.random.choice(channels),
                timestamp=timestamp,
                campaign=np.random.choice(campaigns),
                audience=np.random.choice(audiences),
                interaction_type=np.random.choice(
                    ["click", "impression"], p=[0.7, 0.3]
                ),
                metadata={
                    'platform': platform.value,
                    'hour': hour,
                    'minute': minute
                }
            ))
        
        return touchpoints

    def generate_conversion_paths(
        self,
        start_date: date,
        end_date: date,
        num_paths: int = 500
    ) -> List[Dict]:
        paths = []
        channels = list(settings.CHANNEL_CONFIG.keys())
        
        for i in range(num_paths):
            path_length = np.random.randint(2, 7)
            selected_channels = np.random.choice(
                channels, size=path_length, replace=True
            )
            conv_date = start_date + timedelta(
                days=np.random.randint(0, (end_date - start_date).days + 1)
            )
            conv_time = datetime.combine(conv_date, datetime.min.time()) + timedelta(
                hours=np.random.randint(10, 22)
            )
            
            touchpoints = []
            for pos, ch in enumerate(selected_channels):
                tp_time = conv_time - timedelta(
                    hours=np.random.randint(1, 72) * (path_length - pos)
                )
                touchpoints.append({
                    'channel': ch,
                    'timestamp': tp_time,
                    'position': pos + 1
                })
            
            paths.append({
                'path_id': generate_id("path"),
                'touchpoints': sorted(touchpoints, key=lambda x: x['timestamp']),
                'conversion_value': np.random.uniform(50, 500),
                'conversion_timestamp': conv_time,
                'channel_sequence': [tp['channel'] for tp in sorted(touchpoints, key=lambda x: x['timestamp'])]
            })
        
        return paths

    def generate_million_records(
        self,
        start_date: date,
        end_date: date
    ) -> pd.DataFrame:
        logger.info("Generating 1M+ records for high-volume testing")
        
        days = (end_date - start_date).days + 1
        channels = list(settings.CHANNEL_CONFIG.keys())
        platforms = [p.value for p in PlatformType]
        
        records_per_day = 1000000 // days + 1
        
        all_records = []
        for day in range(days):
            current_date = start_date + timedelta(days=day)
            
            data = {
                'date': [current_date] * records_per_day,
                'platform': np.random.choice(platforms, records_per_day),
                'channel': np.random.choice(channels, records_per_day),
                'hour': np.random.randint(0, 24, records_per_day),
                'impressions': np.random.poisson(500, records_per_day),
                'clicks': np.random.poisson(25, records_per_day),
                'conversions': np.random.poisson(2, records_per_day),
                'cost': np.random.uniform(10, 500, records_per_day).round(2),
                'revenue': np.random.uniform(30, 1500, records_per_day).round(2),
                'audience': np.random.choice(['18-24', '25-34', '35-44', '45+'], records_per_day),
                'campaign': np.random.choice(['brand', 'performance', 'retargeting'], records_per_day)
            }
            
            all_records.append(pd.DataFrame(data))
        
        result = pd.concat(all_records, ignore_index=True)
        logger.info(f"Generated {len(result)} records")
        return result

    def generate_daily_data(self, target_date: date) -> List[AdPerformanceData]:
        return self.generate_performance_data(target_date, target_date, hourly=True)

    def generate_massive_data(self, num_days: int = 7, records_per_day: int = 1000, start_date: date = None) -> pd.DataFrame:
        if start_date is None:
            end_date = date.today()
            start_date = end_date - timedelta(days=num_days - 1)
        else:
            end_date = start_date + timedelta(days=num_days - 1)
        perf_data = self.generate_performance_data(start_date, end_date, hourly=False)
        df = pd.DataFrame([d.model_dump() for d in perf_data])
        if len(df) > num_days * records_per_day:
            df = df.sample(n=num_days * records_per_day, random_state=42)
        return df

    def generate_sample_dataframe(self, num_days: int = 7) -> pd.DataFrame:
        return self.generate_massive_data(num_days=num_days)

from config import settings

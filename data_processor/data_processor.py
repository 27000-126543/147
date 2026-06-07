import pandas as pd
import numpy as np
import dask.dataframe as dd
from dask.diagnostics import ProgressBar
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import os
from config import settings
from models import AdPerformanceData
from utils import get_logger, safe_divide, round_float, batch_iterator, parallel_process

logger = get_logger(__name__)


class DataProcessor:
    def __init__(self, use_dask: bool = True):
        self.use_dask = use_dask
        self.df: Optional[pd.DataFrame] = None
        self.ddf: Optional[dd.DataFrame] = None

    def load_data(self, data: List[AdPerformanceData] = None, df: pd.DataFrame = None) -> 'DataProcessor':
        if data is not None:
            logger.info(f"Loading {len(data)} records from AdPerformanceData list")
            self.df = pd.DataFrame([d.model_dump() for d in data])
            if 'touchpoints' in self.df.columns:
                self.df = self.df.drop(columns=['touchpoints'])
        elif df is not None:
            logger.info(f"Loading {len(df)} records from DataFrame")
            self.df = df.copy()
        else:
            raise ValueError("Either data or df must be provided")
        
        self._preprocess()
        return self

    def load_parquet(self, filepath: str) -> 'DataProcessor':
        logger.info(f"Loading data from {filepath}")
        if self.use_dask and os.path.isdir(filepath):
            self.ddf = dd.read_parquet(filepath)
            with ProgressBar():
                self.df = self.ddf.compute()
        else:
            self.df = pd.read_parquet(filepath)
        
        self._preprocess()
        return self

    def load_saved_data(self, start_date: date = None, end_date: date = None) -> 'DataProcessor':
        all_files = []
        for f in os.listdir(settings.DATA_DIR):
            if f.startswith("performance_data_") and f.endswith(".parquet"):
                all_files.append(os.path.join(settings.DATA_DIR, f))

        if not all_files:
            logger.warning("No saved data found")
            self.df = pd.DataFrame()
            return self

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

        if dfs:
            self.df = pd.concat(dfs, ignore_index=True)
            self._preprocess()
            logger.info(f"Loaded {len(self.df)} records from saved data")
        else:
            self.df = pd.DataFrame()
        
        return self

    def _preprocess(self):
        if self.df is None or self.df.empty:
            return

        logger.info("Preprocessing data")
        
        if 'date' in self.df.columns:
            self.df['date'] = pd.to_datetime(self.df['date'])
        
        if 'platform' in self.df.columns:
            self.df['platform'] = self.df['platform'].astype(str)
        
        numeric_cols = ['impressions', 'clicks', 'conversions', 'cost', 'revenue']
        for col in numeric_cols:
            if col in self.df.columns:
                self.df[col] = pd.to_numeric(self.df[col], errors='coerce').fillna(0)
        
        if 'hour' in self.df.columns:
            self.df['hour'] = self.df['hour'].fillna(-1).astype(int)
        
        self.df['date'] = pd.to_datetime(self.df['date'])
        
        if 'clicks' in self.df.columns and 'impressions' in self.df.columns:
            self.df['ctr'] = self.df.apply(
                lambda row: safe_divide(row['clicks'], row['impressions']), axis=1
            )
        
        if 'conversions' in self.df.columns and 'clicks' in self.df.columns:
            self.df['cvr'] = self.df.apply(
                lambda row: safe_divide(row['conversions'], row['clicks']), axis=1
            )
        
        if 'cost' in self.df.columns and 'conversions' in self.df.columns:
            self.df['cpa'] = self.df.apply(
                lambda row: safe_divide(row['cost'], row['conversions']), axis=1
            )
        
        if 'revenue' in self.df.columns and 'cost' in self.df.columns:
            self.df['roas'] = self.df.apply(
                lambda row: safe_divide(row['revenue'], row['cost']), axis=1
            )
        
        if 'revenue' in self.df.columns and 'cost' in self.df.columns:
            self.df['roi_raw'] = self.df.apply(
                lambda row: safe_divide(row['revenue'] - row['cost'], row['cost']), axis=1
            )
        
        if 'date' in self.df.columns:
            self.df['week'] = self.df['date'].dt.isocalendar().week.astype(int)
            self.df['month'] = self.df['date'].dt.month
            self.df['day_of_week'] = self.df['date'].dt.dayofweek
        
        if 'hour' in self.df.columns:
            self.df['time_slot'] = self.df['hour'].apply(self._classify_time_slot)

    def _classify_time_slot(self, hour: int) -> str:
        if hour < 0:
            return 'unknown'
        elif 0 <= hour < 6:
            return 'early_morning'
        elif 6 <= hour < 12:
            return 'morning'
        elif 12 <= hour < 14:
            return 'lunch'
        elif 14 <= hour < 18:
            return 'afternoon'
        elif 18 <= hour < 22:
            return 'evening'
        else:
            return 'night'

    def clean_and_validate(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()

        logger.info("Cleaning and validating data")
        
        clean_df = df.copy()
        
        for col in clean_df.columns:
            if clean_df[col].apply(lambda x: isinstance(x, (dict, list))).any():
                clean_df = clean_df.drop(columns=[col])
        
        if 'date' in clean_df.columns:
            clean_df['date'] = pd.to_datetime(clean_df['date'], errors='coerce')
            clean_df = clean_df.dropna(subset=['date'])
        
        numeric_cols = ['impressions', 'clicks', 'conversions', 'cost', 'revenue']
        for col in numeric_cols:
            if col in clean_df.columns:
                clean_df[col] = pd.to_numeric(clean_df[col], errors='coerce').fillna(0)
                clean_df = clean_df[clean_df[col] >= 0]
        
        if 'channel' in clean_df.columns:
            clean_df['channel'] = clean_df['channel'].astype(str).str.strip()
        
        if 'clicks' in clean_df.columns and 'impressions' in clean_df.columns:
            clean_df.loc[clean_df['clicks'] > clean_df['impressions'], 'clicks'] = clean_df['impressions']
        
        if 'conversions' in clean_df.columns and 'clicks' in clean_df.columns:
            clean_df.loc[clean_df['conversions'] > clean_df['clicks'], 'conversions'] = clean_df['clicks']
        
        if len(clean_df.columns) > 0:
            try:
                clean_df = clean_df.drop_duplicates()
            except Exception as e:
                logger.warning(f"Could not drop duplicates: {str(e)}")
        
        logger.info(f"Cleaned data: {len(clean_df)} records")
        return clean_df

    def process_data(self, data) -> pd.DataFrame:
        if isinstance(data, pd.DataFrame):
            logger.info(f"Processing {len(data)} records from DataFrame")
            df = data.copy()
        elif isinstance(data, list) and len(data) > 0:
            if hasattr(data[0], 'model_dump'):
                logger.info(f"Processing {len(data)} records from AdPerformanceData list")
                df = pd.DataFrame([d.model_dump() for d in data])
            else:
                logger.info(f"Processing {len(data)} records from list")
                df = pd.DataFrame(data)
        else:
            raise ValueError("Data must be a DataFrame or list of AdPerformanceData")
        
        if 'touchpoints' in df.columns:
            df = df.drop(columns=['touchpoints'])
        
        self.df = self.clean_and_validate(df)
        self._preprocess()
        return self.df

    def process_high_volume(self, data: List[AdPerformanceData]) -> pd.DataFrame:
        logger.info(f"Processing {len(data)} records with Dask for high volume")
        
        batches = list(batch_iterator(data, batch_size=settings.BATCH_SIZE))
        
        def process_batch(batch):
            df = pd.DataFrame([d.model_dump() for d in batch])
            if 'touchpoints' in df.columns:
                df = df.drop(columns=['touchpoints'])
            return df
        
        results = parallel_process(
            process_batch, batches, max_workers=settings.MAX_WORKERS
        )
        
        valid_dfs = [r for r in results if isinstance(r, pd.DataFrame)]
        
        if not valid_dfs:
            return pd.DataFrame()
        
        self.df = pd.concat(valid_dfs, ignore_index=True)
        self.ddf = dd.from_pandas(self.df, npartitions=settings.DATA_PROCESSING_PARTITIONS)
        
        with ProgressBar():
            result = self.ddf.compute()
        
        self.df = result
        self._preprocess()
        return self.df

    def aggregate_by_channel(self, start_date: date = None, end_date: date = None) -> pd.DataFrame:
        if self.df is None or self.df.empty:
            return pd.DataFrame()
        
        df = self.df.copy()
        
        if start_date and 'date' in df.columns:
            df = df[df['date'].dt.date >= start_date]
        if end_date and 'date' in df.columns:
            df = df[df['date'].dt.date <= end_date]
        
        if 'channel' not in df.columns:
            return pd.DataFrame()
        
        agg_dict = {
            'impressions': 'sum',
            'clicks': 'sum',
            'conversions': 'sum',
            'cost': 'sum',
            'revenue': 'sum'
        }
        
        grouped = df.groupby('channel').agg(agg_dict).reset_index()
        
        grouped['ctr'] = grouped.apply(lambda r: safe_divide(r['clicks'], r['impressions']), axis=1)
        grouped['cvr'] = grouped.apply(lambda r: safe_divide(r['conversions'], r['clicks']), axis=1)
        grouped['cpa'] = grouped.apply(lambda r: safe_divide(r['cost'], r['conversions']), axis=1)
        grouped['roas'] = grouped.apply(lambda r: safe_divide(r['revenue'], r['cost']), axis=1)
        grouped['roi'] = grouped.apply(lambda r: safe_divide(r['revenue'] - r['cost'], r['cost']), axis=1)
        
        return grouped.sort_values('roi', ascending=False)

    def aggregate_by_audience(self) -> pd.DataFrame:
        if self.df is None or self.df.empty or 'audience' not in self.df.columns:
            return pd.DataFrame()
        
        agg_dict = {
            'impressions': 'sum',
            'clicks': 'sum',
            'conversions': 'sum',
            'cost': 'sum',
            'revenue': 'sum'
        }
        
        grouped = self.df.groupby('audience').agg(agg_dict).reset_index()
        
        grouped['ctr'] = grouped.apply(lambda r: safe_divide(r['clicks'], r['impressions']), axis=1)
        grouped['cvr'] = grouped.apply(lambda r: safe_divide(r['conversions'], r['clicks']), axis=1)
        grouped['cpa'] = grouped.apply(lambda r: safe_divide(r['cost'], r['conversions']), axis=1)
        grouped['roas'] = grouped.apply(lambda r: safe_divide(r['revenue'], r['cost']), axis=1)
        grouped['roi'] = grouped.apply(lambda r: safe_divide(r['revenue'] - r['cost'], r['cost']), axis=1)
        
        return grouped.sort_values('roi', ascending=False)

    def aggregate_by_time_slot(self) -> pd.DataFrame:
        if self.df is None or self.df.empty or 'time_slot' not in self.df.columns:
            return pd.DataFrame()
        
        agg_dict = {
            'impressions': 'sum',
            'clicks': 'sum',
            'conversions': 'sum',
            'cost': 'sum',
            'revenue': 'sum'
        }
        
        grouped = self.df.groupby('time_slot').agg(agg_dict).reset_index()
        
        grouped['ctr'] = grouped.apply(lambda r: safe_divide(r['clicks'], r['impressions']), axis=1)
        grouped['cvr'] = grouped.apply(lambda r: safe_divide(r['conversions'], r['clicks']), axis=1)
        grouped['cpa'] = grouped.apply(lambda r: safe_divide(r['cost'], r['conversions']), axis=1)
        grouped['roas'] = grouped.apply(lambda r: safe_divide(r['revenue'], r['cost']), axis=1)
        grouped['roi'] = grouped.apply(lambda r: safe_divide(r['revenue'] - r['cost'], r['cost']), axis=1)
        
        return grouped.sort_values('roi', ascending=False)

    def aggregate_by_hour(self) -> pd.DataFrame:
        if self.df is None or self.df.empty or 'hour' not in self.df.columns:
            return pd.DataFrame()
        
        df = self.df[self.df['hour'] >= 0].copy()
        
        agg_dict = {
            'impressions': 'sum',
            'clicks': 'sum',
            'conversions': 'sum',
            'cost': 'sum',
            'revenue': 'sum'
        }
        
        grouped = df.groupby('hour').agg(agg_dict).reset_index()
        
        grouped['ctr'] = grouped.apply(lambda r: safe_divide(r['clicks'], r['impressions']), axis=1)
        grouped['cvr'] = grouped.apply(lambda r: safe_divide(r['conversions'], r['clicks']), axis=1)
        grouped['cpa'] = grouped.apply(lambda r: safe_divide(r['cost'], r['conversions']), axis=1)
        grouped['roas'] = grouped.apply(lambda r: safe_divide(r['revenue'], r['cost']), axis=1)
        grouped['roi'] = grouped.apply(lambda r: safe_divide(r['revenue'] - r['cost'], r['cost']), axis=1)
        
        return grouped.sort_values('hour')

    def aggregate_by_date(self, start_date: date = None, end_date: date = None) -> pd.DataFrame:
        if self.df is None or self.df.empty or 'date' not in self.df.columns:
            return pd.DataFrame()
        
        df = self.df.copy()
        if start_date:
            df = df[df['date'].dt.date >= start_date]
        if end_date:
            df = df[df['date'].dt.date <= end_date]
        
        df['date'] = df['date'].dt.date
        
        agg_dict = {
            'impressions': 'sum',
            'clicks': 'sum',
            'conversions': 'sum',
            'cost': 'sum',
            'revenue': 'sum'
        }
        
        grouped = df.groupby('date').agg(agg_dict).reset_index()
        
        grouped['ctr'] = grouped.apply(lambda r: safe_divide(r['clicks'], r['impressions']), axis=1)
        grouped['cvr'] = grouped.apply(lambda r: safe_divide(r['conversions'], r['clicks']), axis=1)
        grouped['cpa'] = grouped.apply(lambda r: safe_divide(r['cost'], r['conversions']), axis=1)
        grouped['roas'] = grouped.apply(lambda r: safe_divide(r['revenue'], r['cost']), axis=1)
        grouped['roi'] = grouped.apply(lambda r: safe_divide(r['revenue'] - r['cost'], r['cost']), axis=1)
        
        return grouped.sort_values('date')

    def aggregate_multi_dimension(self, dimensions: List[str]) -> pd.DataFrame:
        if self.df is None or self.df.empty:
            return pd.DataFrame()
        
        valid_dims = [d for d in dimensions if d in self.df.columns]
        if not valid_dims:
            return pd.DataFrame()
        
        agg_dict = {
            'impressions': 'sum',
            'clicks': 'sum',
            'conversions': 'sum',
            'cost': 'sum',
            'revenue': 'sum'
        }
        
        grouped = self.df.groupby(valid_dims).agg(agg_dict).reset_index()
        
        grouped['ctr'] = grouped.apply(lambda r: safe_divide(r['clicks'], r['impressions']), axis=1)
        grouped['cvr'] = grouped.apply(lambda r: safe_divide(r['conversions'], r['clicks']), axis=1)
        grouped['cpa'] = grouped.apply(lambda r: safe_divide(r['cost'], r['conversions']), axis=1)
        grouped['roas'] = grouped.apply(lambda r: safe_divide(r['revenue'], r['cost']), axis=1)
        grouped['roi'] = grouped.apply(lambda r: safe_divide(r['revenue'] - r['cost'], r['cost']), axis=1)
        
        return grouped

    def get_channel_daily_trend(self, channel: str) -> pd.DataFrame:
        if self.df is None or self.df.empty:
            return pd.DataFrame()
        
        df = self.df[self.df['channel'] == channel].copy()
        if df.empty:
            return pd.DataFrame()
        
        df['date'] = df['date'].dt.date
        
        agg_dict = {
            'impressions': 'sum',
            'clicks': 'sum',
            'conversions': 'sum',
            'cost': 'sum',
            'revenue': 'sum'
        }
        
        grouped = df.groupby('date').agg(agg_dict).reset_index()
        grouped['roi'] = grouped.apply(lambda r: safe_divide(r['revenue'] - r['cost'], r['cost']), axis=1)
        grouped['roas'] = grouped.apply(lambda r: safe_divide(r['revenue'], r['cost']), axis=1)
        grouped['cvr'] = grouped.apply(lambda r: safe_divide(r['conversions'], r['clicks']), axis=1)
        grouped['cpa'] = grouped.apply(lambda r: safe_divide(r['cost'], r['conversions']), axis=1)
        
        return grouped.sort_values('date')

    def detect_anomalies(self, threshold: float = 3.0) -> pd.DataFrame:
        if self.df is None or self.df.empty:
            return pd.DataFrame()
        
        df = self.df.copy()
        anomalies = []
        
        for channel in df['channel'].unique():
            channel_df = df[df['channel'] == channel]
            
            for metric in ['roi_raw', 'ctr', 'cvr']:
                if metric in channel_df.columns:
                    mean = channel_df[metric].mean()
                    std = channel_df[metric].std()
                    
                    if std > 0:
                        z_scores = (channel_df[metric] - mean) / std
                        anomaly_mask = abs(z_scores) > threshold
                        anomaly_rows = channel_df[anomaly_mask].copy()
                        if not anomaly_rows.empty:
                            anomaly_rows['anomaly_metric'] = metric
                            anomaly_rows['anomaly_score'] = z_scores[anomaly_mask]
                            anomalies.append(anomaly_rows)
        
        if anomalies:
            return pd.concat(anomalies, ignore_index=True)
        return pd.DataFrame()

    def get_summary(self) -> Dict[str, Any]:
        if self.df is None or self.df.empty:
            return {}
        
        summary = {
            'total_records': len(self.df),
            'date_range': {
                'start': self.df['date'].min().strftime('%Y-%m-%d') if 'date' in self.df.columns else None,
                'end': self.df['date'].max().strftime('%Y-%m-%d') if 'date' in self.df.columns else None
            },
            'platforms': self.df['platform'].nunique() if 'platform' in self.df.columns else 0,
            'channels': self.df['channel'].nunique() if 'channel' in self.df.columns else 0,
            'audiences': self.df['audience'].nunique() if 'audience' in self.df.columns else 0,
            'totals': {
                'impressions': int(self.df['impressions'].sum()),
                'clicks': int(self.df['clicks'].sum()),
                'conversions': int(self.df['conversions'].sum()),
                'cost': round_float(self.df['cost'].sum()),
                'revenue': round_float(self.df['revenue'].sum())
            },
            'average_metrics': {
                'ctr': round_float(self.df['ctr'].mean()),
                'cvr': round_float(self.df['cvr'].mean()),
                'cpa': round_float(self.df['cpa'].mean()),
                'roas': round_float(self.df['roas'].mean()),
                'roi': round_float(self.df['roi_raw'].mean())
            }
        }
        
        return summary

    def extract_touchpoints(self, df: pd.DataFrame) -> pd.DataFrame:
        from data_collector import SampleDataGenerator
        from datetime import date
        
        logger.info("Extracting touchpoints from data")
        
        if df is None or df.empty:
            return pd.DataFrame()
        
        start_date = df['date'].min().date() if 'date' in df.columns else date.today() - timedelta(days=7)
        end_date = df['date'].max().date() if 'date' in df.columns else date.today()
        
        num_conversions = max(100, min(len(df) // 10, 1000))
        
        generator = SampleDataGenerator()
        touchpoints = generator.generate_touchpoints(
            start_date=start_date,
            end_date=end_date,
            num_conversions=num_conversions
        )
        
        tp_df = pd.DataFrame([tp.model_dump() for tp in touchpoints])
        logger.info(f"Extracted {len(tp_df)} touchpoints")
        return tp_df

    def save_processed_data(self, filepath: str) -> None:
        if self.df is None:
            raise ValueError("No data to save")
        
        logger.info(f"Saving processed data to {filepath}")
        self.df.to_parquet(filepath, index=False)

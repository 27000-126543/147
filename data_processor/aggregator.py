import pandas as pd
import numpy as np
from datetime import date, timedelta
from typing import List, Dict, Any, Optional
import dask.dataframe as dd
from dask.diagnostics import ProgressBar
from config import settings
from utils import get_logger, safe_divide, round_float, parallel_process

logger = get_logger(__name__)


class DataAggregator:
    def __init__(self, use_dask: bool = True):
        self.use_dask = use_dask

    def aggregate_channel_metrics(
        self,
        df: pd.DataFrame,
        group_by: List[str] = None
    ) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame()
        
        group_cols = group_by or ['channel']
        valid_cols = [c for c in group_cols if c in df.columns]
        
        if not valid_cols:
            valid_cols = ['channel']
        
        agg_dict = {
            'impressions': 'sum',
            'clicks': 'sum',
            'conversions': 'sum',
            'cost': 'sum',
            'revenue': 'sum'
        }
        
        if self.use_dask and len(df) > 100000:
            return self._aggregate_dask(df, valid_cols, agg_dict)
        else:
            return self._aggregate_pandas(df, valid_cols, agg_dict)

    def _aggregate_pandas(
        self,
        df: pd.DataFrame,
        group_cols: List[str],
        agg_dict: Dict[str, str]
    ) -> pd.DataFrame:
        grouped = df.groupby(group_cols).agg(agg_dict).reset_index()
        return self._compute_derived_metrics(grouped)

    def _aggregate_dask(
        self,
        df: pd.DataFrame,
        group_cols: List[str],
        agg_dict: Dict[str, str]
    ) -> pd.DataFrame:
        logger.info("Using Dask for high-volume aggregation")
        
        ddf = dd.from_pandas(df, npartitions=settings.DATA_PROCESSING_PARTITIONS)
        
        with ProgressBar():
            grouped = ddf.groupby(group_cols).agg(agg_dict).compute()
        
        grouped = grouped.reset_index()
        return self._compute_derived_metrics(grouped)

    def _compute_derived_metrics(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        df['ctr'] = df.apply(lambda r: safe_divide(r['clicks'], r['impressions']), axis=1)
        df['cvr'] = df.apply(lambda r: safe_divide(r['conversions'], r['clicks']), axis=1)
        df['cpa'] = df.apply(lambda r: safe_divide(r['cost'], r['conversions']), axis=1)
        df['roas'] = df.apply(lambda r: safe_divide(r['revenue'], r['cost']), axis=1)
        df['roi'] = df.apply(lambda r: safe_divide(r['revenue'] - r['cost'], r['cost']), axis=1)
        
        for col in ['ctr', 'cvr', 'cpa', 'roas', 'roi']:
            df[col] = df[col].apply(lambda x: round_float(x))
        
        return df

    def aggregate_hourly_by_channel(
        self,
        df: pd.DataFrame
    ) -> pd.DataFrame:
        if df.empty or 'hour' not in df.columns:
            return pd.DataFrame()
        
        df_filtered = df[df['hour'] >= 0].copy()
        
        agg_dict = {
            'impressions': 'sum',
            'clicks': 'sum',
            'conversions': 'sum',
            'cost': 'sum',
            'revenue': 'sum'
        }
        
        grouped = df_filtered.groupby(['channel', 'hour']).agg(agg_dict).reset_index()
        return self._compute_derived_metrics(grouped)

    def aggregate_daily_by_channel(
        self,
        df: pd.DataFrame,
        start_date: date = None,
        end_date: date = None
    ) -> pd.DataFrame:
        if df.empty or 'date' not in df.columns:
            return pd.DataFrame()
        
        df_filtered = df.copy()
        df_filtered['date'] = pd.to_datetime(df_filtered['date']).dt.date
        
        if start_date:
            df_filtered = df_filtered[df_filtered['date'] >= start_date]
        if end_date:
            df_filtered = df_filtered[df_filtered['date'] <= end_date]
        
        agg_dict = {
            'impressions': 'sum',
            'clicks': 'sum',
            'conversions': 'sum',
            'cost': 'sum',
            'revenue': 'sum'
        }
        
        grouped = df_filtered.groupby(['channel', 'date']).agg(agg_dict).reset_index()
        result = self._compute_derived_metrics(grouped)
        return result.sort_values(['channel', 'date'])

    def aggregate_by_audience_channel(
        self,
        df: pd.DataFrame
    ) -> pd.DataFrame:
        if df.empty or 'audience' not in df.columns:
            return pd.DataFrame()
        
        agg_dict = {
            'impressions': 'sum',
            'clicks': 'sum',
            'conversions': 'sum',
            'cost': 'sum',
            'revenue': 'sum'
        }
        
        grouped = df.groupby(['channel', 'audience']).agg(agg_dict).reset_index()
        return self._compute_derived_metrics(grouped)

    def aggregate_weekly_trend(
        self,
        df: pd.DataFrame
    ) -> pd.DataFrame:
        if df.empty or 'date' not in df.columns:
            return pd.DataFrame()
        
        df_copy = df.copy()
        df_copy['date'] = pd.to_datetime(df_copy['date'])
        df_copy['week_start'] = df_copy['date'] - pd.to_timedelta(df_copy['date'].dt.dayofweek, unit='D')
        df_copy['week_start'] = df_copy['week_start'].dt.date
        
        agg_dict = {
            'impressions': 'sum',
            'clicks': 'sum',
            'conversions': 'sum',
            'cost': 'sum',
            'revenue': 'sum'
        }
        
        grouped = df_copy.groupby(['week_start']).agg(agg_dict).reset_index()
        return self._compute_derived_metrics(grouped)

    def compute_rolling_metrics(
        self,
        df: pd.DataFrame,
        window: int = 7,
        group_by: str = 'channel'
    ) -> pd.DataFrame:
        if df.empty or 'date' not in df.columns:
            return pd.DataFrame()
        
        df_copy = df.copy()
        df_copy['date'] = pd.to_datetime(df_copy['date'])
        df_copy = df_copy.sort_values([group_by, 'date'])
        
        metrics = ['impressions', 'clicks', 'conversions', 'cost', 'revenue']
        
        result_dfs = []
        for group in df_copy[group_by].unique():
            group_df = df_copy[df_copy[group_by] == group].copy()
            
            for metric in metrics:
                group_df[f'{metric}_{window}d_rolling'] = group_df[metric].rolling(window=window).sum()
                group_df[f'{metric}_{window}d_avg'] = group_df[metric].rolling(window=window).mean()
            
            group_df[f'roi_{window}d_rolling'] = group_df.apply(
                lambda r: safe_divide(
                    r[f'revenue_{window}d_rolling'] - r[f'cost_{window}d_rolling'],
                    r[f'cost_{window}d_rolling']
                ), axis=1
            )
            
            result_dfs.append(group_df)
        
        return pd.concat(result_dfs, ignore_index=True)

    def compute_channel_comparison(
        self,
        df: pd.DataFrame,
        base_channel: str
    ) -> pd.DataFrame:
        if df.empty or 'channel' not in df.columns:
            return pd.DataFrame()
        
        channel_agg = self.aggregate_channel_metrics(df)
        
        if base_channel not in channel_agg['channel'].values:
            logger.warning(f"Base channel {base_channel} not found in data")
            return channel_agg
        
        base_metrics = channel_agg[channel_agg['channel'] == base_channel].iloc[0]
        
        comparison_cols = ['ctr', 'cvr', 'cpa', 'roas', 'roi']
        for col in comparison_cols:
            channel_agg[f'{col}_vs_{base_channel}'] = channel_agg.apply(
                lambda r: round_float(safe_divide(r[col], base_metrics[col]) - 1), axis=1
            )
        
        return channel_agg

    def parallel_aggregate(
        self,
        df: pd.DataFrame,
        aggregation_configs: List[Dict[str, Any]]
    ) -> Dict[str, pd.DataFrame]:
        def aggregate_single(config):
            try:
                group_by = config.get('group_by', ['channel'])
                name = config.get('name', '_'.join(group_by))
                
                result = self.aggregate_channel_metrics(df, group_by=group_by)
                return name, result
            except Exception as e:
                logger.error(f"Aggregation failed for {config}: {e}")
                return config.get('name', 'error'), pd.DataFrame()
        
        results = parallel_process(aggregate_single, aggregation_configs)
        return {name: df for name, df in results}

    def pivot_for_report(
        self,
        df: pd.DataFrame,
        rows: str = 'channel',
        columns: str = 'date',
        values: str = 'roi'
    ) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame()
        
        pivot = pd.pivot_table(
            df,
            index=rows,
            columns=columns,
            values=values,
            aggfunc='mean'
        )
        
        return pivot.round(4)

    def compute_percentiles(
        self,
        df: pd.DataFrame,
        metric: str,
        percentiles: List[float] = None
    ) -> Dict[str, float]:
        if df.empty or metric not in df.columns:
            return {}
        
        pcts = percentiles or [0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99]
        
        result = {}
        for p in pcts:
            result[f'p{int(p*100)}'] = round_float(np.percentile(df[metric].dropna(), p * 100))
        
        return result

    def get_top_performers(
        self,
        df: pd.DataFrame,
        metric: str = 'roi',
        n: int = 5,
        group_by: str = None
    ) -> pd.DataFrame:
        if df.empty or metric not in df.columns:
            return pd.DataFrame()
        
        if group_by and group_by in df.columns:
            result = df.groupby(group_by).apply(
                lambda x: x.nlargest(n, metric)
            ).reset_index(drop=True)
        else:
            result = df.nlargest(n, metric)
        
        return result

    def get_bottom_performers(
        self,
        df: pd.DataFrame,
        metric: str = 'roi',
        n: int = 5,
        group_by: str = None
    ) -> pd.DataFrame:
        if df.empty or metric not in df.columns:
            return pd.DataFrame()
        
        if group_by and group_by in df.columns:
            result = df.groupby(group_by).apply(
                lambda x: x.nsmallest(n, metric)
            ).reset_index(drop=True)
        else:
            result = df.nsmallest(n, metric)
        
        return result

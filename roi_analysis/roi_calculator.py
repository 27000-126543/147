import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from config import settings
from models import ChannelROI, AttributionModelType, AttributionResult
from utils import get_logger, safe_divide, round_float
from data_processor import DataAggregator

logger = get_logger(__name__)


class ROICalculator:
    def __init__(self, channel_config: Dict[str, Dict] = None):
        self.channel_config = channel_config or settings.CHANNEL_CONFIG
        self.aggregator = DataAggregator()

    def calculate_channel_roi(
        self,
        performance_data: pd.DataFrame,
        attributed_revenue: Dict[str, float] = None,
        attribution_model: AttributionModelType = None,
        date_val: date = None
    ) -> pd.DataFrame:
        if performance_data.empty:
            return pd.DataFrame()

        attribution_model = attribution_model or AttributionModelType(settings.DEFAULT_ATTRIBUTION_MODEL)
        date_val = date_val or date.today()

        channel_metrics = self.aggregator.aggregate_channel_metrics(performance_data)

        roi_data = []
        for _, row in channel_metrics.iterrows():
            channel = row['channel']
            
            if attributed_revenue and channel in attributed_revenue:
                attrib_rev = attributed_revenue[channel]
            else:
                attrib_rev = row['revenue']
            
            total_cost = row['cost']
            total_revenue = row['revenue']
            
            roi = safe_divide(attrib_rev - total_cost, total_cost)
            cpa = safe_divide(total_cost, row['conversions'])
            cvr = safe_divide(row['conversions'], row['clicks'])
            roas = safe_divide(attrib_rev, total_cost)
            
            channel_weight = self.channel_config.get(channel, {}).get('weight', 1.0)
            weighted_roi = roi * channel_weight

            roi_data.append({
                'channel': channel,
                'date': date_val,
                'total_cost': round_float(total_cost),
                'total_revenue': round_float(total_revenue),
                'attributed_revenue': round_float(attrib_rev),
                'roi': round_float(roi),
                'weighted_roi': round_float(weighted_roi),
                'cpa': round_float(cpa),
                'cvr': round_float(cvr),
                'roas': round_float(roas),
                'attribution_model': attribution_model.value,
                'impressions': int(row['impressions']),
                'clicks': int(row['clicks']),
                'conversions': int(row['conversions']),
                'weight': channel_weight
            })

        df = pd.DataFrame(roi_data)
        if not df.empty:
            df = df.sort_values('weighted_roi', ascending=False)
            df['rank'] = range(1, len(df) + 1)

        return df

    def calculate_daily_roi_trend(
        self,
        performance_data: pd.DataFrame,
        channel: str = None
    ) -> pd.DataFrame:
        if performance_data.empty or 'date' not in performance_data.columns:
            return pd.DataFrame()

        df_filtered = performance_data.copy()
        if channel:
            df_filtered = df_filtered[df_filtered['channel'] == channel]

        daily_agg = self.aggregator.aggregate_daily_by_channel(df_filtered)

        if daily_agg.empty:
            return pd.DataFrame()

        trends = []
        for (ch, date_val), group in daily_agg.groupby(['channel', 'date']):
            total_cost = group['cost'].sum()
            total_revenue = group['revenue'].sum()
            
            trends.append({
                'channel': ch,
                'date': date_val,
                'cost': round_float(total_cost),
                'revenue': round_float(total_revenue),
                'roi': round_float(safe_divide(total_revenue - total_cost, total_cost)),
                'roas': round_float(safe_divide(total_revenue, total_cost)),
                'conversions': int(group['conversions'].sum())
            })

        return pd.DataFrame(trends).sort_values(['channel', 'date'])

    def calculate_rolling_roi(
        self,
        performance_data: pd.DataFrame,
        window: int = 7,
        channel: str = None
    ) -> pd.DataFrame:
        daily_trend = self.calculate_daily_roi_trend(performance_data, channel)
        if daily_trend.empty:
            return pd.DataFrame()

        result_dfs = []
        for ch in daily_trend['channel'].unique():
            ch_df = daily_trend[daily_trend['channel'] == ch].copy().sort_values('date')
            
            ch_df[f'roi_{window}d_rolling'] = ch_df['roi'].rolling(window=window).mean()
            ch_df[f'revenue_{window}d_rolling'] = ch_df['revenue'].rolling(window=window).sum()
            ch_df[f'cost_{window}d_rolling'] = ch_df['cost'].rolling(window=window).sum()
            ch_df[f'roi_{window}d_std'] = ch_df['roi'].rolling(window=window).std()
            
            result_dfs.append(ch_df)

        return pd.concat(result_dfs, ignore_index=True)

    def identify_roi_outliers(
        self,
        performance_data: pd.DataFrame,
        threshold: float = 2.0
    ) -> pd.DataFrame:
        roi_df = self.calculate_channel_roi(performance_data)
        if roi_df.empty:
            return pd.DataFrame()

        mean_roi = roi_df['roi'].mean()
        std_roi = roi_df['roi'].std()

        if std_roi == 0:
            return pd.DataFrame()

        roi_df['z_score'] = (roi_df['roi'] - mean_roi) / std_roi
        outliers = roi_df[abs(roi_df['z_score']) > threshold]

        return outliers

    def calculate_roi_forecast(
        self,
        performance_data: pd.DataFrame,
        channel: str,
        forecast_days: int = 7
    ) -> Dict[str, Any]:
        daily_trend = self.calculate_daily_roi_trend(performance_data, channel)
        if daily_trend.empty:
            return {}

        channel_df = daily_trend[daily_trend['channel'] == channel].sort_values('date')
        if len(channel_df) < 7:
            return {'error': 'Insufficient data for forecasting'}

        recent_roi = channel_df['roi'].tail(14).values
        
        if len(recent_roi) >= 2:
            slope, intercept = np.polyfit(range(len(recent_roi)), recent_roi, 1)
        else:
            slope = 0
            intercept = np.mean(recent_roi) if len(recent_roi) > 0 else 0

        forecast = []
        for i in range(forecast_days):
            predicted_roi = intercept + slope * (len(recent_roi) + i)
            forecast.append({
                'day': i + 1,
                'predicted_roi': round_float(max(predicted_roi, 0)),
                'trend': 'increasing' if slope > 0.01 else 'decreasing' if slope < -0.01 else 'stable'
            })

        return {
            'channel': channel,
            'current_roi': round_float(recent_roi[-1]) if len(recent_roi) > 0 else 0,
            'avg_roi_7d': round_float(np.mean(recent_roi[-7:])) if len(recent_roi) >= 7 else 0,
            'avg_roi_14d': round_float(np.mean(recent_roi)) if len(recent_roi) >= 14 else 0,
            'trend_slope': round_float(slope),
            'volatility': round_float(np.std(recent_roi)),
            'forecast': forecast
        }

    def calculate_daily_roi(
        self,
        performance_data: pd.DataFrame,
        attribution_results: List[AttributionResult] = None,
        attribution_model: AttributionModelType = None
    ) -> List[ChannelROI]:
        if performance_data.empty or 'date' not in performance_data.columns:
            return []

        attribution_model = attribution_model or AttributionModelType(settings.DEFAULT_ATTRIBUTION_MODEL)
        
        attributed_revenue_by_channel = {}
        if attribution_results:
            for result in attribution_results:
                for tp_id, contribution in result.contributions.items():
                    channel = None
                    for tp in result.touchpoints:
                        if tp.touchpoint_id == tp_id:
                            channel = tp.channel
                            break
                    if channel:
                        attributed_revenue_by_channel[channel] = attributed_revenue_by_channel.get(channel, 0) + contribution

        daily_data = []
        df = performance_data.copy()
        df['date'] = pd.to_datetime(df['date']).dt.date
        
        for date_val, day_group in df.groupby('date'):
            day_attributed = {}
            if attributed_revenue_by_channel:
                day_attributed = attributed_revenue_by_channel
            
            daily_roi_df = self.calculate_channel_roi(
                day_group,
                attributed_revenue=day_attributed if day_attributed else None,
                attribution_model=attribution_model,
                date_val=date_val
            )
            if not daily_roi_df.empty:
                for _, row in daily_roi_df.iterrows():
                    channel_roi = ChannelROI(
                        channel=row['channel'],
                        date=row['date'],
                        total_cost=float(row['total_cost']),
                        total_revenue=float(row['total_revenue']),
                        attributed_revenue=float(row['attributed_revenue']),
                        roi=float(row['roi']),
                        weighted_roi=float(row['weighted_roi']),
                        rank=int(row['rank']),
                        cpa=float(row['cpa']),
                        cvr=float(row['cvr']),
                        roas=float(row['roas']),
                        attribution_model=attribution_model,
                        impressions=int(row['impressions']),
                        clicks=int(row['clicks']),
                        conversions=int(row['conversions'])
                    )
                    daily_data.append(channel_roi)
        
        logger.info(f"Calculated daily ROI for {len(daily_data)} records")
        return daily_data

    def calculate_weighted_roi(
        self,
        roi_data: List[ChannelROI],
        custom_weights: Dict[str, float] = None
    ) -> List[ChannelROI]:
        if not roi_data:
            return []

        updated_rois = []
        for roi in roi_data:
            channel = roi.channel
            if custom_weights and channel in custom_weights:
                weight = custom_weights[channel]
            else:
                weight = self.channel_config.get(channel, {}).get('weight', 1.0)
            
            new_weighted_roi = max(0, round_float(roi.roi * weight))
            updated_roi = ChannelROI(
                channel=roi.channel,
                date=roi.date,
                total_cost=roi.total_cost,
                total_revenue=roi.total_revenue,
                attributed_revenue=roi.attributed_revenue,
                roi=roi.roi,
                weighted_roi=new_weighted_roi,
                rank=roi.rank,
                cpa=roi.cpa,
                cvr=roi.cvr,
                roas=roi.roas,
                attribution_model=roi.attribution_model,
                impressions=roi.impressions,
                clicks=roi.clicks,
                conversions=roi.conversions
            )
            updated_rois.append(updated_roi)

        updated_rois.sort(key=lambda x: x.weighted_roi, reverse=True)
        for i, roi in enumerate(updated_rois):
            roi.rank = i + 1

        return updated_rois

    def compare_roi_across_models(
        self,
        performance_data: pd.DataFrame,
        model_attributions: Dict[AttributionModelType, Dict[str, float]]
    ) -> pd.DataFrame:
        if performance_data.empty or not model_attributions:
            return pd.DataFrame()

        comparison_data = []
        for model_type, attrib_rev in model_attributions.items():
            roi_df = self.calculate_channel_roi(
                performance_data,
                attributed_revenue=attrib_rev,
                attribution_model=model_type
            )

            if not roi_df.empty:
                roi_df['attribution_model'] = model_type.value
                comparison_data.append(roi_df[['channel', 'roi', 'weighted_roi', 'rank', 'attribution_model']])

        if not comparison_data:
            return pd.DataFrame()

        combined = pd.concat(comparison_data, ignore_index=True)

        pivot = pd.pivot_table(
            combined,
            index='channel',
            columns='attribution_model',
            values='roi',
            aggfunc='first'
        ).reset_index()

        return pivot

    def calculate_roi_by_segment(
        self,
        performance_data: pd.DataFrame,
        segment_by: str = 'audience'
    ) -> pd.DataFrame:
        if performance_data.empty or segment_by not in performance_data.columns:
            return pd.DataFrame()

        agg = self.aggregator.aggregate_channel_metrics(
            performance_data,
            group_by=['channel', segment_by]
        )

        return agg.sort_values(['channel', 'roi'], ascending=[True, False])

    def get_roi_summary(
        self,
        performance_data: pd.DataFrame
    ) -> Dict[str, Any]:
        roi_df = self.calculate_channel_roi(performance_data)
        if roi_df.empty:
            return {}

        summary = {
            'total_channels': len(roi_df),
            'avg_roi': round_float(roi_df['roi'].mean()),
            'weighted_avg_roi': round_float(
                safe_divide(
                    (roi_df['roi'] * roi_df['weight']).sum(),
                    roi_df['weight'].sum()
                )
            ),
            'median_roi': round_float(roi_df['roi'].median()),
            'max_roi': round_float(roi_df['roi'].max()),
            'min_roi': round_float(roi_df['roi'].min()),
            'roi_std': round_float(roi_df['roi'].std()),
            'channels_above_threshold': int((roi_df['roi'] >= settings.ROI_THRESHOLD).sum()),
            'channels_below_threshold': int((roi_df['roi'] < settings.ROI_THRESHOLD).sum()),
            'top_channels': roi_df.head(3)[['channel', 'roi', 'weighted_roi']].to_dict('records'),
            'bottom_channels': roi_df.tail(3)[['channel', 'roi', 'weighted_roi']].to_dict('records')
        }

        return summary

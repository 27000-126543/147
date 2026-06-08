import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
from config import settings
from models import (
    TouchPoint,
    AttributionResult,
    AttributionModelType,
    AdPerformanceData
)
from utils import get_logger, generate_id, round_float, parallel_process
from .attribution_models import (
    BaseAttributionModel,
    get_attribution_model
)

logger = get_logger(__name__)


class AttributionEngine:
    def __init__(self, default_model: AttributionModelType = None):
        self.default_model = default_model or AttributionModelType(settings.DEFAULT_ATTRIBUTION_MODEL)
        self.models: Dict[AttributionModelType, BaseAttributionModel] = {}
        self._init_models()

    def _init_models(self):
        for model_type in AttributionModelType:
            if model_type.value in settings.ATTRIBUTION_MODELS:
                self.models[model_type] = get_attribution_model(model_type)

    def run_attribution(
        self,
        touchpoints: List[TouchPoint],
        conversion_value: float,
        conversion_timestamp: datetime = None,
        model_type: AttributionModelType = None
    ) -> AttributionResult:
        model_type = model_type or self.default_model
        model = self.models.get(model_type)

        if not model:
            raise ValueError(f"Model {model_type} not initialized")

        conversion_timestamp = conversion_timestamp or datetime.now()

        return model.attribute(
            touchpoints=touchpoints,
            conversion_value=conversion_value,
            conversion_timestamp=conversion_timestamp
        )

    def run_batch_attribution(
        self,
        conversion_paths: List[Dict[str, Any]],
        model_type: AttributionModelType = None,
        parallel: bool = True
    ) -> List[AttributionResult]:
        logger.info(f"Running batch attribution for {len(conversion_paths)} paths")

        model_type = model_type or self.default_model
        model = self.models.get(model_type)

        if not model:
            raise ValueError(f"Model {model_type} not initialized")

        def attribute_path(path: Dict) -> AttributionResult:
            try:
                return model.attribute(
                    touchpoints=path.get('touchpoints', []),
                    conversion_value=path.get('conversion_value', 0.0),
                    conversion_timestamp=path.get('conversion_timestamp', datetime.now()),
                    conversion_id=path.get('conversion_id')
                )
            except Exception as e:
                logger.error(f"Attribution failed for path: {e}")
                return AttributionResult(
                    conversion_id=path.get('conversion_id', generate_id("conv")),
                    touchpoints=[],
                    model_type=model_type,
                    contributions={},
                    conversion_value=path.get('conversion_value', 0.0),
                    conversion_timestamp=path.get('conversion_timestamp', datetime.now()),
                    total_touchpoints=0,
                    conversion_path_length=0
                )

        if parallel and len(conversion_paths) > 100:
            results = parallel_process(
                attribute_path, conversion_paths,
                max_workers=settings.MAX_WORKERS
            )
        else:
            results = [attribute_path(p) for p in conversion_paths]

        valid_results = [r for r in results if isinstance(r, AttributionResult)]
        logger.info(f"Completed attribution for {len(valid_results)} paths")
        return valid_results

    def run_all_models(
        self,
        conversion_paths: List[Dict[str, Any]]
    ) -> Dict[AttributionModelType, List[AttributionResult]]:
        logger.info(f"Running all attribution models for {len(conversion_paths)} paths")

        all_results = {}
        for model_type in self.models:
            logger.info(f"Running {model_type} attribution")
            all_results[model_type] = self.run_batch_attribution(
                conversion_paths, model_type=model_type
            )

        return all_results

    def aggregate_channel_contributions(
        self,
        attribution_results: List[AttributionResult]
    ) -> pd.DataFrame:
        if not attribution_results:
            return pd.DataFrame()

        channel_contributions = defaultdict(lambda: {
            'total_contribution': 0.0,
            'conversion_count': 0,
            'touchpoint_count': 0
        })

        for result in attribution_results:
            for tp in result.touchpoints:
                contribution = result.contributions.get(tp.touchpoint_id, 0.0)
                channel_contributions[tp.channel]['total_contribution'] += contribution
                channel_contributions[tp.channel]['touchpoint_count'] += 1

            for channel in set(tp.channel for tp in result.touchpoints):
                channel_contributions[channel]['conversion_count'] += 1

        data = []
        for channel, metrics in channel_contributions.items():
            data.append({
                'channel': channel,
                'attributed_revenue': round_float(metrics['total_contribution']),
                'conversion_count': metrics['conversion_count'],
                'touchpoint_count': metrics['touchpoint_count'],
                'avg_revenue_per_conversion': round_float(
                    metrics['total_contribution'] / max(metrics['conversion_count'], 1)
                )
            })

        df = pd.DataFrame(data)
        if not df.empty:
            df = df.sort_values('attributed_revenue', ascending=False)

        return df

    def calculate_model_channel_attributions(
        self,
        performance_data: pd.DataFrame,
        conversion_paths: List[Dict[str, Any]]
    ) -> Dict[AttributionModelType, pd.DataFrame]:
        if performance_data.empty or not conversion_paths:
            return {}

        all_attributions = self.run_all_models(conversion_paths)

        results = {}
        for model_type, attributions in all_attributions.items():
            channel_contrib = self.aggregate_channel_contributions(attributions)

            if not channel_contrib.empty and 'channel' in performance_data.columns:
                channel_costs = performance_data.groupby('channel')['cost'].sum().reset_index()
                channel_revenue = performance_data.groupby('channel')['revenue'].sum().reset_index()

                merged = channel_contrib.merge(channel_costs, on='channel', how='left')
                merged = merged.merge(channel_revenue, on='channel', how='left')

                merged['roi'] = merged.apply(
                    lambda r: round_float((r['attributed_revenue'] - r['cost']) / max(r['cost'], 1)),
                    axis=1
                )
                merged['roas'] = merged.apply(
                    lambda r: round_float(r['attributed_revenue'] / max(r['cost'], 1)),
                    axis=1
                )
                merged['attribution_model'] = model_type.value

                results[model_type] = merged

        return results

    def compare_models(
        self,
        conversion_paths: List[Dict[str, Any]]
    ) -> pd.DataFrame:
        all_attributions = self.run_all_models(conversion_paths)

        comparison_data = []
        for model_type, attributions in all_attributions.items():
            channel_df = self.aggregate_channel_contributions(attributions)

            if not channel_df.empty:
                total_revenue = channel_df['attributed_revenue'].sum()
                top_channel = channel_df.iloc[0]['channel'] if len(channel_df) > 0 else None
                top_contribution = channel_df.iloc[0]['attributed_revenue'] if len(channel_df) > 0 else 0

                comparison_data.append({
                    'model': model_type.value,
                    'total_paths': len(attributions),
                    'total_attributed_revenue': round_float(total_revenue),
                    'top_channel': top_channel,
                    'top_channel_revenue': round_float(top_contribution),
                    'top_channel_share': round_float(top_contribution / max(total_revenue, 1)),
                    'unique_channels': len(channel_df),
                    'concentration_ratio': self._calculate_concentration_ratio(channel_df)
                })

        return pd.DataFrame(comparison_data)

    def _calculate_concentration_ratio(self, channel_df: pd.DataFrame) -> float:
        if channel_df.empty:
            return 0.0

        total = channel_df['attributed_revenue'].sum()
        if total == 0:
            return 0.0

        top3 = channel_df.head(3)['attributed_revenue'].sum()
        return round_float(top3 / total)

    def get_channel_attribution_summary(
        self,
        performance_data: pd.DataFrame,
        conversion_paths: List[Dict[str, Any]]
    ) -> pd.DataFrame:
        model_attributions = self.calculate_model_channel_attributions(
            performance_data, conversion_paths
        )

        if not model_attributions:
            return pd.DataFrame()

        all_dfs = []
        for model_type, df in model_attributions.items():
            df['model'] = model_type.value
            all_dfs.append(df)

        combined = pd.concat(all_dfs, ignore_index=True)

        pivot = pd.pivot_table(
            combined,
            index='channel',
            columns='model',
            values='attributed_revenue',
            aggfunc='first'
        ).reset_index()

        return pivot

    def create_conversion_paths_from_touchpoints(
        self,
        touchpoints: List[TouchPoint],
        lookback_window_days: int = 30
    ) -> List[Dict[str, Any]]:
        if not touchpoints:
            return []

        sorted_tps = sorted(touchpoints, key=lambda x: x.timestamp)

        conversion_user_map = defaultdict(list)
        for tp in sorted_tps:
            user_id = tp.metadata.get('user_id', tp.audience)
            conversion_user_map[user_id].append(tp)

        paths = []
        for user_id, user_tps in conversion_user_map.items():
            if len(user_tps) >= 2:
                sorted_user_tps = sorted(user_tps, key=lambda x: x.timestamp)

                window_start = sorted_user_tps[0].timestamp
                current_path_tps = []

                for tp in sorted_user_tps:
                    time_since_start = (tp.timestamp - window_start).total_seconds() / (24 * 3600)

                    if time_since_start > lookback_window_days and current_path_tps:
                        if len(current_path_tps) >= 2:
                            paths.append({
                                'conversion_id': generate_id("conv"),
                                'touchpoints': current_path_tps,
                                'conversion_value': self._estimate_conversion_value(current_path_tps),
                                'conversion_timestamp': current_path_tps[-1].timestamp
                            })
                        window_start = tp.timestamp
                        current_path_tps = [tp]
                    else:
                        current_path_tps.append(tp)

                if len(current_path_tps) >= 2:
                    paths.append({
                        'conversion_id': generate_id("conv"),
                        'touchpoints': current_path_tps,
                        'conversion_value': self._estimate_conversion_value(current_path_tps),
                        'conversion_timestamp': current_path_tps[-1].timestamp
                    })

        logger.info(f"Created {len(paths)} conversion paths from {len(touchpoints)} touchpoints")
        return paths

    def build_conversion_paths(self, touchpoints_df: pd.DataFrame):
        from models import TouchPoint
        
        logger.info("Building conversion paths from touchpoints DataFrame")
        
        if touchpoints_df is None or touchpoints_df.empty:
            return []
        
        touchpoints = []
        for _, row in touchpoints_df.iterrows():
            tp_dict = row.to_dict()
            if 'metadata' in tp_dict and isinstance(tp_dict['metadata'], str):
                try:
                    import json
                    tp_dict['metadata'] = json.loads(tp_dict['metadata'])
                except:
                    tp_dict['metadata'] = {}
            touchpoints.append(TouchPoint(**tp_dict))
        
        paths = self.create_conversion_paths_from_touchpoints(touchpoints)
        logger.info(f"Built {len(paths)} conversion paths")
        return paths

    def summarize_channel_contributions(
        self,
        attribution_results: List[AttributionResult]
    ) -> Dict[str, Any]:
        if not attribution_results:
            return {}

        channel_totals = defaultdict(float)
        channel_counts = defaultdict(int)

        for result in attribution_results:
            for channel, contribution in result.contributions.items():
                channel_totals[channel] += contribution
                channel_counts[channel] += 1

        total_contribution = sum(channel_totals.values())
        summary = {
            'channel_contributions': {},
            'channel_share': {},
            'channel_interaction_count': dict(channel_counts),
            'total_contribution': round_float(total_contribution),
            'total_conversions': len(attribution_results)
        }

        for channel, total in channel_totals.items():
            summary['channel_contributions'][channel] = round_float(total)
            summary['channel_share'][channel] = round_float(total / total_contribution) if total_contribution > 0 else 0.0

        return summary

    def _estimate_conversion_value(self, touchpoints: List[TouchPoint]) -> float:
        if not touchpoints:
            return 0.0

        base_value = np.random.uniform(50, 500)
        path_length = len(touchpoints)
        channel_diversity = len(set(tp.channel for tp in touchpoints))

        multiplier = 1.0 + (path_length * 0.1) + (channel_diversity * 0.15)

        return round_float(base_value * multiplier)

    def get_attribution_insights(
        self,
        attribution_results: List[AttributionResult]
    ) -> Dict[str, Any]:
        if not attribution_results:
            return {}

        total_conversions = len(attribution_results)
        total_value = sum(r.conversion_value for r in attribution_results)
        avg_path_length = np.mean([r.conversion_path_length for r in attribution_results])

        channel_first_touches = defaultdict(int)
        channel_last_touches = defaultdict(int)

        for result in attribution_results:
            if result.touchpoints:
                channel_first_touches[result.touchpoints[0].channel] += 1
                channel_last_touches[result.touchpoints[-1].channel] += 1

        insights = {
            'total_conversions': total_conversions,
            'total_attributed_value': round_float(total_value),
            'avg_path_length': round_float(avg_path_length),
            'avg_conversion_value': round_float(total_value / max(total_conversions, 1)),
            'top_first_touch_channels': dict(sorted(
                channel_first_touches.items(), key=lambda x: x[1], reverse=True
            )[:5]),
            'top_last_touch_channels': dict(sorted(
                channel_last_touches.items(), key=lambda x: x[1], reverse=True
            )[:5]),
            'path_length_distribution': self._get_path_length_distribution(attribution_results)
        }

        return insights

    def _get_path_length_distribution(
        self,
        attribution_results: List[AttributionResult]
    ) -> Dict[str, int]:
        dist = defaultdict(int)
        for result in attribution_results:
            length = result.conversion_path_length
            if length == 1:
                dist['1 touchpoint'] += 1
            elif 2 <= length <= 3:
                dist['2-3 touchpoints'] += 1
            elif 4 <= length <= 6:
                dist['4-6 touchpoints'] += 1
            else:
                dist['7+ touchpoints'] += 1
        return dict(dist)

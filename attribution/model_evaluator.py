import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
from config import settings
from models import AttributionResult, AttributionModelType, TouchPoint
from utils import get_logger, round_float, safe_divide
from .attribution_engine import AttributionEngine

logger = get_logger(__name__)


class AttributionModelEvaluator:
    def __init__(self, attribution_engine: AttributionEngine):
        self.engine = attribution_engine

    def evaluate_models(
        self,
        conversion_paths: List[Dict[str, Any]],
        holdout_ratio: float = 0.2,
        random_seed: int = 42
    ) -> pd.DataFrame:
        logger.info(f"Evaluating attribution models with {len(conversion_paths)} paths")

        np.random.seed(random_seed)
        n_paths = len(conversion_paths)
        indices = np.random.permutation(n_paths)
        split_idx = int(n_paths * (1 - holdout_ratio))

        train_paths = [conversion_paths[i] for i in indices[:split_idx]]
        test_paths = [conversion_paths[i] for i in indices[split_idx:]]

        train_attributions = self.engine.run_all_models(train_paths)
        test_attributions = self.engine.run_all_models(test_paths)

        evaluation_results = []
        for model_type in self.engine.models:
            train_results = train_attributions.get(model_type, [])
            test_results = test_attributions.get(model_type, [])

            metrics = self._calculate_model_metrics(
                train_results, test_results, train_paths, test_paths
            )
            metrics['model'] = model_type.value
            evaluation_results.append(metrics)

        return pd.DataFrame(evaluation_results)

    def _calculate_model_metrics(
        self,
        train_results: List[AttributionResult],
        test_results: List[AttributionResult],
        train_paths: List[Dict],
        test_paths: List[Dict]
    ) -> Dict[str, Any]:
        train_contrib = self.engine.aggregate_channel_contributions(train_results)
        test_contrib = self.engine.aggregate_channel_contributions(test_results)

        metrics = {}

        metrics['train_conversions'] = len(train_results)
        metrics['test_conversions'] = len(test_results)

        train_total = train_contrib['attributed_revenue'].sum() if not train_contrib.empty else 0
        test_total = test_contrib['attributed_revenue'].sum() if not test_contrib.empty else 0

        actual_train = sum(p.get('conversion_value', 0) for p in train_paths)
        actual_test = sum(p.get('conversion_value', 0) for p in test_paths)

        metrics['train_revenue_error'] = round_float(abs(train_total - actual_train) / max(actual_train, 1))
        metrics['test_revenue_error'] = round_float(abs(test_total - actual_test) / max(actual_test, 1))

        if not train_contrib.empty and not test_contrib.empty:
            merged = train_contrib.merge(
                test_contrib, on='channel',
                suffixes=('_train', '_test'), how='outer'
            ).fillna(0)

            if len(merged) > 1:
                correlation = merged['attributed_revenue_train'].corr(merged['attributed_revenue_test'])
                metrics['train_test_correlation'] = round_float(correlation if not pd.isna(correlation) else 0)
            else:
                metrics['train_test_correlation'] = 1.0

            rank_correlation = self._calculate_rank_correlation(train_contrib, test_contrib)
            metrics['rank_stability'] = round_float(rank_correlation)

            gini = self._calculate_gini_coefficient(train_contrib['attributed_revenue'])
            metrics['gini_coefficient'] = round_float(gini)

            metrics['channel_coverage'] = round_float(
                len(train_contrib[train_contrib['attributed_revenue'] > 0]) / max(len(train_contrib), 1)
            )

            metrics['top_channel_share'] = round_float(
                train_contrib.iloc[0]['attributed_revenue'] / max(train_total, 1)
                if not train_contrib.empty else 0
            )

        metrics['avg_path_length'] = round_float(np.mean(
            [r.conversion_path_length for r in train_results]
        )) if train_results else 0

        return metrics

    def _calculate_rank_correlation(
        self,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame
    ) -> float:
        if train_df.empty or test_df.empty:
            return 0.0

        train_ranks = train_df.sort_values('attributed_revenue', ascending=False).reset_index()
        train_ranks['train_rank'] = train_ranks.index + 1

        test_ranks = test_df.sort_values('attributed_revenue', ascending=False).reset_index()
        test_ranks['test_rank'] = test_ranks.index + 1

        merged = train_ranks[['channel', 'train_rank']].merge(
            test_ranks[['channel', 'test_rank']], on='channel', how='inner'
        )

        if len(merged) < 2:
            return 1.0

        n = len(merged)
        d_squared = ((merged['train_rank'] - merged['test_rank']) ** 2).sum()
        spearman = 1 - (6 * d_squared) / (n * (n ** 2 - 1))

        return max(-1, min(1, spearman))

    def _calculate_gini_coefficient(self, values: np.ndarray) -> float:
        if len(values) == 0:
            return 0.0

        arr = np.array(values, dtype=float)
        arr = np.sort(arr)
        n = len(arr)

        if n == 0 or np.sum(arr) == 0:
            return 0.0

        index = np.arange(1, n + 1)
        return (2 * np.sum(index * arr) - (n + 1) * np.sum(arr)) / (n * np.sum(arr))

    def recommend_best_model(
        self,
        evaluation_results: pd.DataFrame,
        weights: Dict[str, float] = None
    ) -> Dict[str, Any]:
        if evaluation_results.empty:
            return {'recommended_model': AttributionModelType.LAST_CLICK.value, 'score': 0}

        default_weights = {
            'test_revenue_error': -0.3,
            'train_test_correlation': 0.25,
            'rank_stability': 0.2,
            'gini_coefficient': 0.15,
            'channel_coverage': 0.1
        }

        weights = weights or default_weights

        normalized = evaluation_results.copy()
        for metric in weights:
            if metric in normalized.columns:
                min_val = normalized[metric].min()
                max_val = normalized[metric].max()
                if max_val != min_val:
                    normalized[metric] = (normalized[metric] - min_val) / (max_val - min_val)
                else:
                    normalized[metric] = 0.5

        normalized['total_score'] = 0
        for metric, weight in weights.items():
            if metric in normalized.columns:
                normalized['total_score'] += normalized[metric] * weight

        best_idx = normalized['total_score'].idxmax()
        best_model = normalized.loc[best_idx, 'model']
        best_score = normalized.loc[best_idx, 'total_score']

        scores = normalized[['model', 'total_score']].set_index('model')['total_score'].to_dict()
        scores = {k: round_float(v) for k, v in scores.items()}

        return {
            'recommended_model': best_model,
            'confidence_score': round_float(best_score),
            'all_scores': scores,
            'evaluation_details': evaluation_results.to_dict('records')
        }

    def generate_evaluation_report(
        self,
        conversion_paths: List[Dict[str, Any]],
        performance_data: pd.DataFrame
    ) -> Dict[str, Any]:
        logger.info("Generating attribution model evaluation report")

        model_comparison = self.engine.compare_models(conversion_paths)
        evaluation_results = self.evaluate_models(conversion_paths)
        recommendation = self.recommend_best_model(evaluation_results)

        recommended_model = AttributionModelType(recommendation['recommended_model'])

        recommended_attributions = self.engine.run_batch_attribution(
            conversion_paths, model_type=recommended_model
        )

        channel_contributions = self.engine.aggregate_channel_contributions(
            recommended_attributions
        )

        insights = self.engine.get_attribution_insights(recommended_attributions)

        report = {
            'report_date': datetime.now().isoformat(),
            'period_analyzed': {
                'path_count': len(conversion_paths),
                'total_conversion_value': round_float(sum(p.get('conversion_value', 0) for p in conversion_paths))
            },
            'model_comparison': model_comparison.to_dict('records') if not model_comparison.empty else [],
            'model_evaluation': evaluation_results.to_dict('records') if not evaluation_results.empty else [],
            'recommendation': recommendation,
            'recommended_model_channel_contributions': channel_contributions.to_dict('records') if not channel_contributions.empty else [],
            'attribution_insights': insights,
            'performance_vs_attribution': self._compare_performance_attribution(
                performance_data, channel_contributions
            )
        }

        return report

    def _compare_performance_attribution(
        self,
        performance_data: pd.DataFrame,
        channel_contributions: pd.DataFrame
    ) -> List[Dict[str, Any]]:
        if performance_data.empty or channel_contributions.empty:
            return []

        if 'channel' not in performance_data.columns:
            return []

        actual_perf = performance_data.groupby('channel').agg({
            'cost': 'sum',
            'revenue': 'sum',
            'conversions': 'sum'
        }).reset_index()

        merged = actual_perf.merge(channel_contributions, on='channel', how='left').fillna(0)

        comparison = []
        for _, row in merged.iterrows():
            actual_roi = safe_divide(row['revenue'] - row['cost'], row['cost'])
            attributed_roi = safe_divide(row['attributed_revenue'] - row['cost'], row['cost'])

            comparison.append({
                'channel': row['channel'],
                'actual_cost': round_float(row['cost']),
                'actual_revenue': round_float(row['revenue']),
                'actual_roi': round_float(actual_roi),
                'attributed_revenue': round_float(row['attributed_revenue']),
                'attributed_roi': round_float(attributed_roi),
                'revenue_difference': round_float(row['attributed_revenue'] - row['revenue']),
                'roi_difference': round_float(attributed_roi - actual_roi)
            })

        return comparison

    def track_model_stability(
        self,
        historical_evaluations: List[Dict[str, Any]]
    ) -> pd.DataFrame:
        if not historical_evaluations:
            return pd.DataFrame()

        stability_data = []
        for i, eval_result in enumerate(historical_evaluations):
            for model_result in eval_result.get('evaluation_details', []):
                stability_data.append({
                    'period': i + 1,
                    'model': model_result.get('model'),
                    'test_error': model_result.get('test_revenue_error'),
                    'correlation': model_result.get('train_test_correlation'),
                    'rank_stability': model_result.get('rank_stability')
                })

        return pd.DataFrame(stability_data)

    def get_conversion_path_analysis(
        self,
        conversion_paths: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        if not conversion_paths:
            return {}

        path_lengths = [len(p.get('touchpoints', [])) for p in conversion_paths]
        channels_in_path = [
            len(set(tp.channel for tp in p.get('touchpoints', [])))
            for p in conversion_paths
        ]

        channel_sequences = defaultdict(int)
        for path in conversion_paths:
            tps = sorted(path.get('touchpoints', []), key=lambda x: x.timestamp)
            sequence = tuple(tp.channel for tp in tps)
            if len(sequence) >= 2:
                channel_sequences[sequence] += 1

        analysis = {
            'total_paths': len(conversion_paths),
            'avg_path_length': round_float(np.mean(path_lengths)),
            'median_path_length': np.median(path_lengths),
            'max_path_length': max(path_lengths) if path_lengths else 0,
            'avg_unique_channels': round_float(np.mean(channels_in_path)),
            'most_common_paths': [
                {
                    'path': list(seq),
                    'frequency': freq,
                    'percentage': round_float(freq / max(len(conversion_paths), 1))
                }
                for seq, freq in sorted(channel_sequences.items(), key=lambda x: x[1], reverse=True)[:10]
            ],
            'path_length_distribution': dict(pd.Series(path_lengths).value_counts().sort_index())
        }

        return analysis

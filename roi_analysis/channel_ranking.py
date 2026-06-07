import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from config import settings
from models import ChannelROI, AttributionModelType
from utils import get_logger, safe_divide, round_float

logger = get_logger(__name__)


class ChannelRanker:
    def __init__(self):
        self.channel_config = settings.CHANNEL_CONFIG

    def rank_channels(
        self,
        roi_data,
        ranking_criteria: List[str] = None,
        weights: Dict[str, float] = None
    ):
        if isinstance(roi_data, pd.DataFrame):
            if roi_data.empty:
                return roi_data
        elif isinstance(roi_data, list):
            if not roi_data:
                return roi_data
        else:
            return roi_data

        default_criteria = ['weighted_roi', 'roas', 'cvr', 'conversions']
        default_weights = {'weighted_roi': 0.4, 'roas': 0.3, 'cvr': 0.2, 'conversions': 0.1}

        criteria = ranking_criteria or default_criteria
        weights = weights or default_weights

        if isinstance(roi_data, list):
            df = pd.DataFrame([roi.model_dump() for roi in roi_data])
        else:
            df = roi_data.copy()
        
        df['composite_score'] = 0.0

        for criterion in criteria:
            if criterion in df.columns:
                min_val = df[criterion].min()
                max_val = df[criterion].max()

                if max_val != min_val:
                    if criterion in ['cpa']:
                        normalized = 1 - (df[criterion] - min_val) / (max_val - min_val)
                    else:
                        normalized = (df[criterion] - min_val) / (max_val - min_val)
                else:
                    normalized = 0.5

                weight = weights.get(criterion, 0.25)
                df['composite_score'] += normalized * weight
            else:
                logger.warning(f"Ranking criterion '{criterion}' not found in data")

        df['composite_score'] = df['composite_score'].apply(lambda x: round_float(x, 4))
        df = df.sort_values('composite_score', ascending=False)
        df['rank'] = range(1, len(df) + 1)
        df['tier'] = df['composite_score'].apply(self._assign_tier)

        if isinstance(roi_data, list):
            result = []
            for _, row in df.iterrows():
                channel_roi = ChannelROI(
                    channel=row['channel'],
                    date=row['date'],
                    total_cost=float(row['total_cost']),
                    total_revenue=float(row['total_revenue']),
                    attributed_revenue=float(row['attributed_revenue']),
                    roi=float(row['roi']),
                    weighted_roi=max(0, float(row['weighted_roi'])),
                    rank=int(row['rank']),
                    tier=str(row['tier']) if 'tier' in row and pd.notna(row['tier']) else None,
                    cpa=float(row['cpa']),
                    cvr=float(row['cvr']),
                    roas=float(row['roas']),
                    attribution_model=AttributionModelType(row['attribution_model']) if isinstance(row['attribution_model'], str) else row['attribution_model'],
                    impressions=int(row['impressions']),
                    clicks=int(row['clicks']),
                    conversions=int(row['conversions'])
                )
                result.append(channel_roi)
            return result
        
        return df

    def _assign_tier(self, score: float) -> str:
        if score >= 0.8:
            return 'S'
        elif score >= 0.6:
            return 'A'
        elif score >= 0.4:
            return 'B'
        elif score >= 0.2:
            return 'C'
        else:
            return 'D'

    def generate_ranking_report(
        self,
        ranked_data: pd.DataFrame
    ) -> Dict[str, Any]:
        if ranked_data.empty:
            return {}

        report = {
            'generated_at': datetime.now().isoformat(),
            'total_channels': len(ranked_data),
            'tier_distribution': self._get_tier_distribution(ranked_data),
            'top_performers': ranked_data.head(5)[
                ['rank', 'channel', 'composite_score', 'tier', 'roi', 'weighted_roi', 'roas']
            ].to_dict('records'),
            'bottom_performers': ranked_data.tail(5)[
                ['rank', 'channel', 'composite_score', 'tier', 'roi', 'weighted_roi', 'roas']
            ].to_dict('records'),
            'average_scores': {
                'composite_score': round_float(ranked_data['composite_score'].mean()),
                'roi': round_float(ranked_data['roi'].mean()),
                'weighted_roi': round_float(ranked_data['weighted_roi'].mean()),
                'roas': round_float(ranked_data['roas'].mean())
            },
            'channel_budget_allocation': self._recommend_budget_allocation(ranked_data)
        }

        return report

    def _get_tier_distribution(self, df: pd.DataFrame) -> Dict[str, int]:
        tier_order = ['S', 'A', 'B', 'C', 'D']
        dist = df['tier'].value_counts().to_dict()
        return {tier: dist.get(tier, 0) for tier in tier_order}

    def _recommend_budget_allocation(self, ranked_data: pd.DataFrame) -> List[Dict[str, Any]]:
        total_budget = settings.TOTAL_DAILY_BUDGET
        total_score = ranked_data['composite_score'].sum()

        if total_score == 0:
            return []

        allocations = []
        for _, row in ranked_data.iterrows():
            channel = row['channel']
            config = self.channel_config.get(channel, {})
            min_budget = config.get('min_budget', 0)
            max_budget = config.get('max_budget', total_budget)

            recommended = (row['composite_score'] / total_score) * total_budget
            recommended = max(min_budget, min(max_budget, recommended))

            allocations.append({
                'channel': channel,
                'rank': row['rank'],
                'tier': row['tier'],
                'composite_score': row['composite_score'],
                'recommended_budget': round_float(recommended),
                'min_budget': min_budget,
                'max_budget': max_budget,
                'budget_share': round_float(recommended / total_budget)
            })

        return allocations

    def track_ranking_changes(
        self,
        current_ranking: pd.DataFrame,
        previous_ranking: pd.DataFrame
    ) -> pd.DataFrame:
        if current_ranking.empty or previous_ranking.empty:
            return pd.DataFrame()

        merged = current_ranking[['channel', 'rank', 'composite_score', 'tier']].merge(
            previous_ranking[['channel', 'rank', 'composite_score', 'tier']],
            on='channel',
            suffixes=('_current', '_previous'),
            how='outer'
        ).fillna({'rank_current': 999, 'rank_previous': 999})

        merged['rank_change'] = merged['rank_previous'] - merged['rank_current']
        merged['score_change'] = merged['composite_score_current'] - merged['composite_score_previous']
        merged['tier_changed'] = merged['tier_current'] != merged['tier_previous']

        merged['trend'] = merged['rank_change'].apply(
            lambda x: 'up' if x > 0 else 'down' if x < 0 else 'stable'
        )

        return merged.sort_values('rank_current')

    def get_channel_rank_history(
        self,
        historical_roi: List[pd.DataFrame],
        channel: str
    ) -> pd.DataFrame:
        if not historical_roi:
            return pd.DataFrame()

        history = []
        for i, roi_df in enumerate(historical_roi):
            ranked = self.rank_channels(roi_df)
            channel_data = ranked[ranked['channel'] == channel]

            if not channel_data.empty:
                history.append({
                    'period': i + 1,
                    'rank': channel_data.iloc[0]['rank'],
                    'composite_score': channel_data.iloc[0]['composite_score'],
                    'roi': channel_data.iloc[0]['roi'],
                    'tier': channel_data.iloc[0]['tier']
                })

        return pd.DataFrame(history)

    def identify_rising_channels(
        self,
        ranking_history: pd.DataFrame,
        threshold: int = 3
    ) -> List[Dict[str, Any]]:
        if ranking_history.empty or 'rank_change' not in ranking_history.columns:
            return []

        rising = ranking_history[ranking_history['rank_change'] >= threshold]
        return rising[['channel', 'rank_current', 'rank_change', 'trend']].to_dict('records')

    def identify_declining_channels(
        self,
        ranking_history: pd.DataFrame,
        threshold: int = -3
    ) -> List[Dict[str, Any]]:
        if ranking_history.empty or 'rank_change' not in ranking_history.columns:
            return []

        declining = ranking_history[ranking_history['rank_change'] <= threshold]
        return declining[['channel', 'rank_current', 'rank_change', 'trend']].to_dict('records')

    def calculate_rank_stability(
        self,
        historical_rankings: List[pd.DataFrame]
    ) -> Dict[str, float]:
        if len(historical_rankings) < 2:
            return {}

        channels = historical_rankings[0]['channel'].unique()
        stability_scores = {}

        for channel in channels:
            ranks = []
            for ranking in historical_rankings:
                ch_rank = ranking[ranking['channel'] == channel]['rank']
                if not ch_rank.empty:
                    ranks.append(ch_rank.iloc[0])

            if len(ranks) >= 2:
                stability = 1 - (np.std(ranks) / max(np.mean(ranks), 1))
                stability_scores[channel] = round_float(max(0, min(1, stability)))

        return stability_scores

    def create_roi_contribution_chart_data(
        self,
        ranked_data: pd.DataFrame
    ) -> Dict[str, Any]:
        if ranked_data.empty:
            return {}

        total_cost = ranked_data['total_cost'].sum()
        total_revenue = ranked_data['total_revenue'].sum()
        total_profit = total_revenue - total_cost

        channels = []
        for _, row in ranked_data.iterrows():
            channels.append({
                'channel': row['channel'],
                'cost': row['total_cost'],
                'revenue': row['total_revenue'],
                'profit': row['total_revenue'] - row['total_cost'],
                'roi': row['roi'],
                'cost_share': round_float(row['total_cost'] / max(total_cost, 1)),
                'revenue_share': round_float(row['total_revenue'] / max(total_revenue, 1)),
                'profit_share': round_float((row['total_revenue'] - row['total_cost']) / max(total_profit, 1))
            })

        return {
            'total_cost': round_float(total_cost),
            'total_revenue': round_float(total_revenue),
            'total_profit': round_float(total_profit),
            'total_roi': round_float(safe_divide(total_profit, total_cost)),
            'channels': channels
        }

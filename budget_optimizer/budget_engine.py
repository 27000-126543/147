import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from config import settings
from models import (
    BudgetAdjustmentSuggestion,
    BudgetAdjustmentRecord,
    BudgetAdjustmentStatus,
    AttributionModelType
)
from utils import get_logger, generate_id, safe_divide, round_float
from roi_analysis import ROICalculator, ChannelRanker

logger = get_logger(__name__)


class BudgetOptimizer:
    def __init__(self):
        self.roi_calculator = ROICalculator()
        self.channel_ranker = ChannelRanker()
        self.channel_config = settings.CHANNEL_CONFIG
        self.threshold = settings.ROI_THRESHOLD
        self.consecutive_days = settings.CONSECUTIVE_DAYS_FOR_BUDGET_ADJUSTMENT

    def generate_adjustment_suggestions(
        self,
        roi_data,
        current_budgets: Dict[str, float],
        total_budget: float = None,
        attribution_model: AttributionModelType = None
    ):
        if isinstance(roi_data, list):
            daily_roi_df = pd.DataFrame([roi.model_dump() for roi in roi_data])
        else:
            daily_roi_df = roi_data

        underperforming = self.identify_underperforming_channels(daily_roi_df)
        
        if isinstance(roi_data, list):
            ranked_channels = self.channel_ranker.rank_channels(roi_data)
            ranked_df = pd.DataFrame([r.model_dump() for r in ranked_channels])
        else:
            ranked_df = self.channel_ranker.rank_channels(roi_data)

        return self.generate_budget_suggestions(
            underperforming_channels=underperforming,
            ranked_channels=ranked_df,
            current_budgets=current_budgets,
            attribution_model=attribution_model
        )

    def identify_underperforming_channels(
        self,
        daily_roi_data: pd.DataFrame,
        threshold: float = None,
        consecutive_days: int = None
    ) -> List[Dict[str, Any]]:
        if daily_roi_data.empty or 'date' not in daily_roi_data.columns:
            return []

        threshold = threshold or self.threshold
        consecutive_days = consecutive_days or self.consecutive_days

        underperforming = []

        for channel in daily_roi_data['channel'].unique():
            ch_data = daily_roi_data[daily_roi_data['channel'] == channel].copy()
            ch_data = ch_data.sort_values('date', ascending=False).head(consecutive_days)

            if len(ch_data) < consecutive_days:
                continue

            all_below_threshold = (ch_data['roi'] < threshold).all()
            if all_below_threshold:
                avg_roi = ch_data['roi'].mean()
                trend = self._calculate_roi_trend(ch_data)
                
                cost_col = 'cost' if 'cost' in ch_data.columns else 'total_cost'
                revenue_col = 'revenue' if 'revenue' in ch_data.columns else 'total_revenue'
                daily_data = ch_data[['date', 'roi', cost_col, revenue_col]].rename(
                    columns={cost_col: 'cost', revenue_col: 'revenue'}
                ).to_dict('records')

                underperforming.append({
                    'channel': channel,
                    'consecutive_days': consecutive_days,
                    'avg_roi': round_float(avg_roi),
                    'threshold': threshold,
                    'roi_vs_threshold': round_float(avg_roi - threshold),
                    'trend': trend,
                    'daily_data': daily_data
                })

        logger.info(f"Identified {len(underperforming)} underperforming channels")
        return underperforming

    def _calculate_roi_trend(self, channel_data: pd.DataFrame) -> str:
        if len(channel_data) < 2:
            return 'stable'

        sorted_data = channel_data.sort_values('date')
        rois = sorted_data['roi'].values

        slope, _ = np.polyfit(range(len(rois)), rois, 1)

        if slope > 0.01:
            return 'improving'
        elif slope < -0.01:
            return 'deteriorating'
        else:
            return 'stable'

    def generate_budget_suggestions(
        self,
        underperforming_channels: List[Dict[str, Any]],
        ranked_channels: pd.DataFrame,
        current_budgets: Dict[str, float],
        attribution_model: AttributionModelType = None
    ) -> List[BudgetAdjustmentSuggestion]:
        if not underperforming_channels or ranked_channels.empty:
            return []

        attribution_model = attribution_model or AttributionModelType(settings.DEFAULT_ATTRIBUTION_MODEL)
        total_budget = sum(current_budgets.values())
        suggestions = []

        total_available_budget = 0.0
        channel_suggestions = []

        for under in underperforming_channels:
            channel = under['channel']
            current_budget = current_budgets.get(channel, 0)

            if current_budget == 0:
                continue

            channel_rank = ranked_channels[ranked_channels['channel'] == channel]
            if channel_rank.empty:
                continue

            rank = channel_rank.iloc[0]['rank']
            tier = channel_rank.iloc[0]['tier']
            current_roi = under['avg_roi']

            config = self.channel_config.get(channel, {})
            min_budget = config.get('min_budget', 0)

            if tier in ['C', 'D']:
                reduction_percent = 0.3
            elif tier == 'B':
                reduction_percent = 0.2
            else:
                reduction_percent = 0.1

            suggested_budget = max(min_budget, current_budget * (1 - reduction_percent))
            adjustment_amount = current_budget - suggested_budget
            adjustment_percent = -reduction_percent

            total_available_budget += adjustment_amount

            expected_improvement = self._predict_roi_improvement(
                channel, current_roi, reduction_percent, ranked_channels
            )

            risk_level = self._assess_risk_level(under, tier)

            reason = self._generate_adjustment_reason(
                channel, current_roi, self.threshold, under['consecutive_days'],
                under['trend'], tier, adjustment_percent
            )

            suggestion = BudgetAdjustmentSuggestion(
                suggestion_id=generate_id("sug"),
                channel=channel,
                current_budget=round_float(current_budget),
                suggested_budget=round_float(suggested_budget),
                adjustment_percent=round_float(adjustment_percent),
                reason=reason,
                current_roi=round_float(current_roi),
                threshold=self.threshold,
                consecutive_days_below_threshold=under['consecutive_days'],
                expected_roi_improvement=round_float(expected_improvement['roi']),
                expected_revenue_change=round_float(expected_improvement['revenue']),
                risk_level=risk_level,
                generated_at=datetime.now(),
                model_attribution=attribution_model
            )

            channel_suggestions.append({
                'suggestion': suggestion,
                'adjustment_amount': adjustment_amount
            })

        if total_available_budget > 0:
            suggestions = self._allocate_reclaimed_budget(
                channel_suggestions,
                total_available_budget,
                ranked_channels,
                current_budgets,
                attribution_model
            )
        else:
            suggestions = [s['suggestion'] for s in channel_suggestions]

        logger.info(f"Generated {len(suggestions)} budget adjustment suggestions")
        return suggestions

    def _predict_roi_improvement(
        self,
        channel: str,
        current_roi: float,
        reduction_percent: float,
        ranked_channels: pd.DataFrame
    ) -> Dict[str, float]:
        channel_data = ranked_channels[ranked_channels['channel'] == channel]
        if channel_data.empty:
            return {'roi': 0, 'revenue': 0}

        ch = channel_data.iloc[0]
        current_cost = ch['total_cost']
        current_revenue = ch['total_revenue']

        new_cost = current_cost * (1 - reduction_percent)

        efficiency_factor = max(0.5, 1 + (current_roi - self.threshold) * 0.1)
        expected_revenue = new_cost * (1 + current_roi) * efficiency_factor

        expected_roi = safe_divide(expected_revenue - new_cost, new_cost)
        roi_improvement = expected_roi - current_roi
        revenue_change = expected_revenue - current_revenue

        return {
            'roi': roi_improvement,
            'revenue': revenue_change,
            'expected_roi': expected_roi,
            'expected_revenue': expected_revenue
        }

    def _assess_risk_level(
        self,
        underperforming: Dict[str, Any],
        tier: str
    ) -> str:
        avg_roi = underperforming['avg_roi']
        threshold = underperforming['threshold']
        roi_gap = threshold - avg_roi
        trend = underperforming['trend']

        if roi_gap > 1.0 and trend == 'deteriorating':
            return 'high'
        elif roi_gap > 0.5 or tier in ['C', 'D']:
            return 'medium'
        else:
            return 'low'

    def _generate_adjustment_reason(
        self,
        channel: str,
        current_roi: float,
        threshold: float,
        consecutive_days: int,
        trend: str,
        tier: str,
        adjustment_percent: float
    ) -> str:
        parts = [
            f"Channel {channel} has ROI below threshold ({current_roi:.2f} < {threshold:.2f})",
            f"for {consecutive_days} consecutive days",
            f"with {trend} trend",
            f"and current tier {tier}.",
            f"Proposed {abs(adjustment_percent)*100:.0f}% budget reduction",
            f"to improve overall portfolio efficiency."
        ]
        return " ".join(parts)

    def _allocate_reclaimed_budget(
        self,
        reduction_suggestions: List[Dict],
        total_available_budget: float,
        ranked_channels: pd.DataFrame,
        current_budgets: Dict[str, float],
        attribution_model: AttributionModelType
    ) -> List[BudgetAdjustmentSuggestion]:
        suggestions = [s['suggestion'] for s in reduction_suggestions]
        reduced_channels = set(s.channel for s in suggestions)

        top_performers = ranked_channels[
            (~ranked_channels['channel'].isin(reduced_channels)) &
            (ranked_channels['roi'] >= self.threshold)
        ].head(3)

        if top_performers.empty:
            return suggestions

        total_score = top_performers['composite_score'].sum()

        for _, row in top_performers.iterrows():
            channel = row['channel']
            current_budget = current_budgets.get(channel, 0)
            config = self.channel_config.get(channel, {})
            max_budget = config.get('max_budget', settings.TOTAL_DAILY_BUDGET)

            allocation_share = row['composite_score'] / total_score
            additional_budget = total_available_budget * allocation_share
            new_budget = min(max_budget, current_budget + additional_budget)
            actual_increase = new_budget - current_budget

            if actual_increase > 0:
                increase_percent = actual_increase / current_budget if current_budget > 0 else 1.0

                expected_impact = self._predict_growth_impact(
                    channel, row['roi'], actual_increase, ranked_channels
                )

                reason = (
                    f"Reallocate budget from underperforming channels to top performer {channel}. "
                    f"Current ROI: {row['roi']:.2f}, Tier: {row['tier']}. "
                    f"Expected to drive additional revenue of ¥{expected_impact['revenue']:,.2f}"
                )

                suggestion = BudgetAdjustmentSuggestion(
                    suggestion_id=generate_id("sug"),
                    channel=channel,
                    current_budget=round_float(current_budget),
                    suggested_budget=round_float(new_budget),
                    adjustment_percent=round_float(increase_percent),
                    reason=reason,
                    current_roi=round_float(row['roi']),
                    threshold=self.threshold,
                    consecutive_days_below_threshold=0,
                    expected_roi_improvement=round_float(expected_impact['roi']),
                    expected_revenue_change=round_float(expected_impact['revenue']),
                    risk_level='low',
                    generated_at=datetime.now(),
                    model_attribution=attribution_model
                )

                suggestions.append(suggestion)

        return suggestions

    def _predict_growth_impact(
        self,
        channel: str,
        current_roi: float,
        budget_increase: float,
        ranked_channels: pd.DataFrame
    ) -> Dict[str, float]:
        channel_data = ranked_channels[ranked_channels['channel'] == channel]
        if channel_data.empty:
            return {'roi': 0, 'revenue': 0}

        ch = channel_data.iloc[0]
        marginal_roi = max(0, current_roi * 0.8)

        expected_revenue_increase = budget_increase * (1 + marginal_roi)
        expected_roi_change = marginal_roi - current_roi

        return {
            'roi': expected_roi_change,
            'revenue': expected_revenue_increase
        }

    def calculate_new_budget_allocation(
        self,
        approved_suggestions: List[BudgetAdjustmentSuggestion],
        current_budgets: Dict[str, float]
    ) -> Dict[str, float]:
        new_budgets = current_budgets.copy()

        for suggestion in approved_suggestions:
            channel = suggestion.channel
            new_budgets[channel] = suggestion.suggested_budget

        total_new = sum(new_budgets.values())
        total_current = sum(current_budgets.values())

        if abs(total_new - total_current) > 1:
            logger.warning(
                f"Budget total mismatch: ¥{total_current:,.2f} → ¥{total_new:,.2f}"
            )

        return new_budgets

    def validate_budget_allocation(
        self,
        budget_allocation: Dict[str, float]
    ) -> Tuple[bool, List[str]]:
        errors = []
        total_budget = sum(budget_allocation.values())
        expected_total = settings.TOTAL_DAILY_BUDGET

        if abs(total_budget - expected_total) / expected_total > 0.05:
            errors.append(
                f"Total budget ({total_budget:,.2f}) differs from expected ({expected_total:,.2f}) by >5%"
            )

        for channel, budget in budget_allocation.items():
            config = self.channel_config.get(channel, {})
            min_budget = config.get('min_budget', 0)
            max_budget = config.get('max_budget', float('inf'))

            if budget < min_budget:
                errors.append(
                    f"Channel {channel} budget ({budget:,.2f}) below minimum ({min_budget:,.2f})"
                )
            if budget > max_budget:
                errors.append(
                    f"Channel {channel} budget ({budget:,.2f}) above maximum ({max_budget:,.2f})"
                )

        return len(errors) == 0, errors

    def create_adjustment_record(
        self,
        suggestion: BudgetAdjustmentSuggestion,
        status: BudgetAdjustmentStatus = BudgetAdjustmentStatus.PENDING,
        approver: str = None
    ) -> BudgetAdjustmentRecord:
        return BudgetAdjustmentRecord(
            adjustment_id=generate_id("adj"),
            suggestion_id=suggestion.suggestion_id,
            channel=suggestion.channel,
            old_budget=suggestion.current_budget,
            new_budget=suggestion.suggested_budget,
            status=status,
            approver=approver,
            approved_at=datetime.now() if status in [
                BudgetAdjustmentStatus.APPROVED, BudgetAdjustmentStatus.EXECUTED
            ] else None,
            performance_metrics={
                'current_roi': suggestion.current_roi,
                'expected_roi_improvement': suggestion.expected_roi_improvement,
                'expected_revenue_change': suggestion.expected_revenue_change
            }
        )

    def get_current_budgets(
        self,
        performance_data: pd.DataFrame
    ) -> Dict[str, float]:
        if performance_data.empty or 'channel' not in performance_data.columns:
            return {ch: config.get('weight', 0) * settings.TOTAL_DAILY_BUDGET
                    for ch, config in self.channel_config.items()}

        channel_costs = performance_data.groupby('channel')['cost'].sum()
        total_cost = channel_costs.sum()

        if total_cost == 0:
            return {ch: config.get('weight', 0) * settings.TOTAL_DAILY_BUDGET
                    for ch, config in self.channel_config.items()}

        budgets = {}
        for channel, config in self.channel_config.items():
            if channel in channel_costs:
                share = channel_costs[channel] / total_cost
            else:
                share = config.get('weight', 0)

            budgets[channel] = round_float(share * settings.TOTAL_DAILY_BUDGET)

        return budgets

    def optimize_budgets(
        self,
        performance_data: pd.DataFrame,
        daily_roi_data: pd.DataFrame,
        attribution_model: AttributionModelType = None
    ) -> Dict[str, Any]:
        if performance_data.empty or daily_roi_data.empty:
            return {'error': 'Insufficient data for budget optimization'}

        roi_df = self.roi_calculator.calculate_channel_roi(
            performance_data, attribution_model=attribution_model
        )

        ranked = self.channel_ranker.rank_channels(roi_df)

        underperforming = self.identify_underperforming_channels(daily_roi_data)

        current_budgets = self.get_current_budgets(performance_data)

        suggestions = self.generate_budget_suggestions(
            underperforming, ranked, current_budgets, attribution_model
        )

        return {
            'roi_data': roi_df,
            'ranked_channels': ranked,
            'underperforming_channels': underperforming,
            'current_budgets': current_budgets,
            'suggestions': suggestions,
            'ranking_report': self.channel_ranker.generate_ranking_report(ranked)
        }

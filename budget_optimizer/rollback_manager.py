import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional
from config import settings
from models import BudgetAdjustmentRecord, BudgetAdjustmentStatus
from utils import get_logger, safe_divide, round_float
from roi_analysis import ROICalculator

logger = get_logger(__name__)


class RollbackManager:
    def __init__(self):
        self.roi_calculator = ROICalculator()
        self.monitoring_hours = settings.ROLLBACK_MONITORING_HOURS
        self.threshold = settings.ROI_THRESHOLD

    def start_monitoring(
        self,
        adjustment: BudgetAdjustmentRecord,
        baseline_data: pd.DataFrame
    ) -> BudgetAdjustmentRecord:
        adjustment.status = BudgetAdjustmentStatus.MONITORING
        adjustment.monitoring_start = datetime.now()
        adjustment.monitoring_end = adjustment.monitoring_start + timedelta(hours=self.monitoring_hours)

        baseline_metrics = self._calculate_baseline_metrics(
            baseline_data, adjustment.channel
        )
        adjustment.performance_metrics['baseline'] = baseline_metrics

        logger.info(
            f"Started monitoring for {adjustment.channel} "
            f"until {adjustment.monitoring_end}"
        )
        return adjustment

    def _calculate_baseline_metrics(
        self,
        baseline_data: pd.DataFrame,
        channel: str
    ) -> Dict[str, float]:
        if baseline_data.empty or 'channel' not in baseline_data.columns:
            return {}

        ch_data = baseline_data[baseline_data['channel'] == channel]
        if ch_data.empty:
            return {}

        metrics = {
            'avg_roi': round_float(ch_data['roi'].mean() if 'roi' in ch_data.columns else 0),
            'avg_roas': round_float(ch_data['roas'].mean() if 'roas' in ch_data.columns else 0),
            'avg_cvr': round_float(ch_data['cvr'].mean() if 'cvr' in ch_data.columns else 0),
            'daily_cost': round_float(ch_data['cost'].mean() if 'cost' in ch_data.columns else 0),
            'daily_revenue': round_float(ch_data['revenue'].mean() if 'revenue' in ch_data.columns else 0),
            'daily_conversions': round_float(ch_data['conversions'].mean() if 'conversions' in ch_data.columns else 0)
        }

        return metrics

    def monitor_performance(
        self,
        adjustment: BudgetAdjustmentRecord,
        current_data: pd.DataFrame,
        check_interval_hours: int = 6
    ) -> Dict[str, Any]:
        if adjustment.monitoring_start is None:
            return {'status': 'error', 'message': 'Monitoring not started'}

        now = datetime.now()
        elapsed_hours = (now - adjustment.monitoring_start).total_seconds() / 3600

        channel = adjustment.channel
        ch_data = current_data[current_data['channel'] == channel]

        if ch_data.empty:
            return {
                'status': 'no_data',
                'elapsed_hours': elapsed_hours,
                'remaining_hours': max(0, self.monitoring_hours - elapsed_hours)
            }

        current_metrics = self._calculate_current_metrics(ch_data, adjustment.monitoring_start)
        baseline = adjustment.performance_metrics.get('baseline', {})

        comparison = self._compare_performance(current_metrics, baseline)

        should_rollback = self._should_rollback(comparison)

        check_result = {
            'adjustment_id': adjustment.adjustment_id,
            'channel': channel,
            'elapsed_hours': round_float(elapsed_hours),
            'remaining_hours': round_float(max(0, self.monitoring_hours - elapsed_hours)),
            'current_metrics': current_metrics,
            'baseline_metrics': baseline,
            'comparison': comparison,
            'should_rollback': should_rollback,
            'monitoring_complete': elapsed_hours >= self.monitoring_hours
        }

        return check_result

    def _calculate_current_metrics(
        self,
        channel_data: pd.DataFrame,
        monitoring_start: datetime
    ) -> Dict[str, float]:
        if channel_data.empty:
            return {}

        if 'date' in channel_data.columns:
            channel_data['date'] = pd.to_datetime(channel_data['date'])
            recent_data = channel_data[
                channel_data['date'] >= monitoring_start.date()
            ]
        else:
            recent_data = channel_data

        if recent_data.empty:
            recent_data = channel_data.tail(100)

        metrics = {
            'avg_roi': round_float(recent_data['roi'].mean() if 'roi' in recent_data.columns else 0),
            'avg_roas': round_float(recent_data['roas'].mean() if 'roas' in recent_data.columns else 0),
            'avg_cvr': round_float(recent_data['cvr'].mean() if 'cvr' in recent_data.columns else 0),
            'total_cost': round_float(recent_data['cost'].sum() if 'cost' in recent_data.columns else 0),
            'total_revenue': round_float(recent_data['revenue'].sum() if 'revenue' in recent_data.columns else 0),
            'total_conversions': int(recent_data['conversions'].sum() if 'conversions' in recent_data.columns else 0)
        }

        hours_elapsed = max(1, (datetime.now() - monitoring_start).total_seconds() / 3600)
        metrics['daily_cost'] = round_float(metrics['total_cost'] * 24 / hours_elapsed)
        metrics['daily_revenue'] = round_float(metrics['total_revenue'] * 24 / hours_elapsed)
        metrics['daily_conversions'] = round_float(metrics['total_conversions'] * 24 / hours_elapsed)

        return metrics

    def _compare_performance(
        self,
        current: Dict[str, float],
        baseline: Dict[str, float]
    ) -> Dict[str, Any]:
        comparison = {}

        for metric in ['avg_roi', 'avg_roas', 'avg_cvr', 'daily_revenue']:
            curr_val = current.get(metric, 0)
            base_val = baseline.get(metric, 0)

            if base_val != 0:
                change_pct = safe_divide(curr_val - base_val, base_val)
            else:
                change_pct = 0

            comparison[metric] = {
                'baseline': base_val,
                'current': curr_val,
                'change_absolute': round_float(curr_val - base_val),
                'change_percent': round_float(change_pct),
                'improved': curr_val > base_val
            }

        return comparison

    def _should_rollback(self, comparison: Dict[str, Any]) -> bool:
        roi_comp = comparison.get('avg_roi', {})
        current_roi = roi_comp.get('current', 0)
        base_roi = roi_comp.get('baseline', 0)

        if current_roi < self.threshold and current_roi < base_roi * 0.9:
            logger.warning(f"ROI below threshold and 10% below baseline: {current_roi:.2f} < {base_roi:.2f}")
            return True

        roi_change = roi_comp.get('change_percent', 0)
        if roi_change < -0.15:
            logger.warning(f"ROI dropped by more than 15%: {roi_change:.2%}")
            return True

        revenue_comp = comparison.get('daily_revenue', {})
        revenue_change = revenue_comp.get('change_percent', 0)
        if revenue_change < -0.2:
            logger.warning(f"Revenue dropped by more than 20%: {revenue_change:.2%}")
            return True

        return False

    def execute_rollback(
        self,
        adjustment: BudgetAdjustmentRecord,
        trigger_reason: str
    ) -> BudgetAdjustmentRecord:
        adjustment.status = BudgetAdjustmentStatus.ROLLED_BACK
        adjustment.rollback_at = datetime.now()
        adjustment.rollback_trigger = trigger_reason

        logger.warning(
            f"Rolled back budget adjustment for {adjustment.channel}: "
            f"¥{adjustment.new_budget:,.2f} → ¥{adjustment.old_budget:,.2f}. "
            f"Reason: {trigger_reason}"
        )

        return adjustment

    def complete_monitoring(
        self,
        adjustment: BudgetAdjustmentRecord,
        final_data: pd.DataFrame
    ) -> BudgetAdjustmentRecord:
        adjustment.status = BudgetAdjustmentStatus.EXECUTED
        adjustment.executed_at = adjustment.monitoring_start
        adjustment.monitoring_end = datetime.now()

        final_metrics = self._calculate_baseline_metrics(
            final_data, adjustment.channel
        )
        adjustment.performance_metrics['final'] = final_metrics

        baseline = adjustment.performance_metrics.get('baseline', {})
        comparison = self._compare_performance(final_metrics, baseline)
        adjustment.performance_metrics['monitoring_comparison'] = comparison

        improvement = comparison.get('avg_roi', {}).get('improved', False)

        logger.info(
            f"Completed monitoring for {adjustment.channel}. "
            f"Performance {'improved' if improvement else 'did not improve'}. "
            f"Final ROI: {final_metrics.get('avg_roi', 0):.2f}"
        )

        return adjustment

    def get_monitoring_summary(
        self,
        adjustments: List[BudgetAdjustmentRecord],
        current_data: pd.DataFrame
    ) -> List[Dict[str, Any]]:
        summary = []

        for adj in adjustments:
            if adj.status == BudgetAdjustmentStatus.MONITORING:
                status = self.monitor_performance(adj, current_data)
                summary.append({
                    'adjustment_id': adj.adjustment_id,
                    'channel': adj.channel,
                    'status': adj.status.value,
                    'monitoring_start': adj.monitoring_start.isoformat() if adj.monitoring_start else None,
                    'monitoring_end': adj.monitoring_end.isoformat() if adj.monitoring_end else None,
                    'elapsed_hours': status.get('elapsed_hours', 0),
                    'remaining_hours': status.get('remaining_hours', 0),
                    'should_rollback': status.get('should_rollback', False),
                    'current_roi': status.get('current_metrics', {}).get('avg_roi', 0),
                    'baseline_roi': status.get('baseline_metrics', {}).get('avg_roi', 0),
                    'old_budget': adj.old_budget,
                    'new_budget': adj.new_budget
                })

        return summary

    def check_all_monitoring(
        self,
        active_adjustments: List[BudgetAdjustmentRecord],
        current_data: pd.DataFrame
    ) -> Dict[str, Any]:
        results = {
            'need_rollback': [],
            'monitoring_complete': [],
            'still_monitoring': []
        }

        for adj in active_adjustments:
            if adj.status != BudgetAdjustmentStatus.MONITORING:
                continue

            status = self.monitor_performance(adj, current_data)

            if status.get('should_rollback'):
                results['need_rollback'].append({
                    'adjustment': adj,
                    'reason': self._get_rollback_reason(status)
                })
            elif status.get('monitoring_complete'):
                results['monitoring_complete'].append({
                    'adjustment': adj,
                    'final_status': 'success' if not status.get('should_rollback') else 'failed'
                })
            else:
                results['still_monitoring'].append(adj)

        return results

    def _get_rollback_reason(self, status: Dict[str, Any]) -> str:
        comparison = status.get('comparison', {})

        reasons = []
        roi_comp = comparison.get('avg_roi', {})

        if roi_comp.get('change_percent', 0) < -0.15:
            reasons.append(
                f"ROI dropped by {abs(roi_comp['change_percent'])*100:.1f}% "
                f"(from {roi_comp['baseline']:.2f} to {roi_comp['current']:.2f})"
            )

        revenue_comp = comparison.get('daily_revenue', {})
        if revenue_comp.get('change_percent', 0) < -0.2:
            reasons.append(
                f"Revenue dropped by {abs(revenue_comp['change_percent'])*100:.1f}%"
            )

        current_roi = roi_comp.get('current', 0)
        if current_roi < self.threshold:
            reasons.append(
                f"ROI ({current_roi:.2f}) below threshold ({self.threshold:.2f})"
            )

        return "; ".join(reasons) if reasons else "Performance degradation detected"

    def generate_rollback_notification(
        self,
        adjustment: BudgetAdjustmentRecord,
        reason: str
    ) -> Dict[str, Any]:
        return {
            'type': 'budget_rollback',
            'priority': 'high',
            'recipients': settings.NOTIFICATION_EMAILS,
            'subject': f"URGENT: Budget rolled back for {adjustment.channel}",
            'body': f"""
Budget adjustment has been rolled back for channel: {adjustment.channel}

Reason: {reason}

Adjustment Details:
- Old Budget: ¥{adjustment.old_budget:,.2f}
- New Budget: ¥{adjustment.new_budget:,.2f}
- Rollback to: ¥{adjustment.old_budget:,.2f}
- Monitoring Start: {adjustment.monitoring_start}
- Rollback Time: {adjustment.rollback_at}

Performance Metrics:
{self._format_performance_metrics(adjustment.performance_metrics)}

Please review and take appropriate action.
            """.strip(),
            'timestamp': datetime.now().isoformat(),
            'adjustment_id': adjustment.adjustment_id
        }

    def _format_performance_metrics(self, metrics: Dict[str, Any]) -> str:
        baseline = metrics.get('baseline', {})
        final = metrics.get('final', {})

        lines = [
            "Metric | Baseline | Current | Change",
            "--- | --- | --- | ---",
            f"ROI | {baseline.get('avg_roi', 'N/A')} | {final.get('avg_roi', 'N/A')} | "
            f"{round_float(final.get('avg_roi', 0) - baseline.get('avg_roi', 0), signed=True)}"
        ]

        return "\n".join(lines)

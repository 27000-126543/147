import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from config import settings
from models import (
    BudgetAdjustmentSuggestion,
    BudgetAdjustmentRecord,
    BudgetAdjustmentStatus
)
from utils import get_logger, generate_id, round_float

logger = get_logger(__name__)


class ApprovalWorkflow:
    def __init__(self):
        self.pending_approvals: List[BudgetAdjustmentRecord] = []
        self.approval_history: List[BudgetAdjustmentRecord] = []

    def submit_for_approval(
        self,
        suggestions: List[BudgetAdjustmentSuggestion],
        submitter: str = "system"
    ) -> List[BudgetAdjustmentRecord]:
        if not suggestions:
            return []

        records = []
        for suggestion in suggestions:
            record = BudgetAdjustmentRecord(
                adjustment_id=generate_id("adj"),
                suggestion_id=suggestion.suggestion_id,
                channel=suggestion.channel,
                old_budget=suggestion.current_budget,
                new_budget=suggestion.suggested_budget,
                status=BudgetAdjustmentStatus.PENDING,
                performance_metrics={
                    'suggestion': suggestion.model_dump(),
                    'submitted_by': submitter,
                    'submitted_at': datetime.now().isoformat()
                }
            )

            self.pending_approvals.append(record)
            records.append(record)

            logger.info(
                f"Submitted budget adjustment for approval: "
                f"{suggestion.channel} "
                f"¥{suggestion.current_budget:,.2f} → ¥{suggestion.suggested_budget:,.2f}"
            )

        self._send_notification(records)
        return records

    def approve(
        self,
        adjustment_id: str,
        approver: str,
        comments: str = None
    ) -> Optional[BudgetAdjustmentRecord]:
        record = self._find_pending_adjustment(adjustment_id)
        if not record:
            logger.error(f"Adjustment {adjustment_id} not found or not pending")
            return None

        record.status = BudgetAdjustmentStatus.APPROVED
        record.approver = approver
        record.approved_at = datetime.now()

        if 'performance_metrics' not in record.performance_metrics:
            record.performance_metrics['performance_metrics'] = {}
        record.performance_metrics['approver'] = approver
        record.performance_metrics['approval_comments'] = comments
        record.performance_metrics['approved_at'] = record.approved_at.isoformat()

        self.pending_approvals = [
            a for a in self.pending_approvals if a.adjustment_id != adjustment_id
        ]
        self.approval_history.append(record)

        logger.info(
            f"Adjustment {adjustment_id} approved by {approver}: "
            f"{record.channel} "
            f"¥{record.old_budget:,.2f} → ¥{record.new_budget:,.2f}"
        )

        return record

    def reject(
        self,
        adjustment_id: str,
        approver: str,
        reason: str
    ) -> Optional[BudgetAdjustmentRecord]:
        record = self._find_pending_adjustment(adjustment_id)
        if not record:
            logger.error(f"Adjustment {adjustment_id} not found or not pending")
            return None

        record.status = BudgetAdjustmentStatus.REJECTED
        record.approver = approver

        record.performance_metrics['approver'] = approver
        record.performance_metrics['rejection_reason'] = reason
        record.performance_metrics['rejected_at'] = datetime.now().isoformat()

        self.pending_approvals = [
            a for a in self.pending_approvals if a.adjustment_id != adjustment_id
        ]
        self.approval_history.append(record)

        logger.info(
            f"Adjustment {adjustment_id} rejected by {approver}: {reason}"
        )

        return record

    def batch_approve(
        self,
        adjustment_ids: List[str],
        approver: str,
        comments: str = None
    ) -> List[BudgetAdjustmentRecord]:
        results = []
        for adj_id in adjustment_ids:
            result = self.approve(adj_id, approver, comments)
            if result:
                results.append(result)
        return results

    def batch_reject(
        self,
        adjustment_ids: List[str],
        approver: str,
        reason: str
    ) -> List[BudgetAdjustmentRecord]:
        results = []
        for adj_id in adjustment_ids:
            result = self.reject(adj_id, approver, reason)
            if result:
                results.append(result)
        return results

    def get_pending_approvals(
        self,
        channel: str = None,
        min_adjustment: float = None
    ) -> List[Dict[str, Any]]:
        pending = self.pending_approvals

        if channel:
            pending = [a for a in pending if a.channel == channel]

        if min_adjustment:
            pending = [
                a for a in pending
                if abs(a.new_budget - a.old_budget) >= min_adjustment
            ]

        return [self._format_approval_for_display(a) for a in pending]

    def get_approval_history(
        self,
        start_date: datetime = None,
        end_date: datetime = None,
        status: BudgetAdjustmentStatus = None,
        channel: str = None
    ) -> List[Dict[str, Any]]:
        history = self.approval_history

        if start_date:
            history = [
                a for a in history
                if a.approved_at and a.approved_at >= start_date
            ]

        if end_date:
            history = [
                a for a in history
                if a.approved_at and a.approved_at <= end_date
            ]

        if status:
            history = [a for a in history if a.status == status]

        if channel:
            history = [a for a in history if a.channel == channel]

        return [self._format_approval_for_display(a) for a in history]

    def get_approved_adjustments(
        self,
        status: BudgetAdjustmentStatus = BudgetAdjustmentStatus.APPROVED
    ) -> List[BudgetAdjustmentRecord]:
        return [
            a for a in self.approval_history
            if a.status == status
        ]

    def execute_adjustments(
        self,
        approved_adjustments: List[BudgetAdjustmentRecord],
        current_budgets: Dict[str, float]
    ) -> Dict[str, float]:
        new_budgets = current_budgets.copy()

        for adjustment in approved_adjustments:
            if adjustment.status != BudgetAdjustmentStatus.APPROVED:
                logger.warning(
                    f"Skipping adjustment {adjustment.adjustment_id}: "
                    f"status is {adjustment.status.value}, not APPROVED"
                )
                continue

            adjustment.status = BudgetAdjustmentStatus.EXECUTED
            adjustment.executed_at = datetime.now()
            adjustment.performance_metrics['executed_at'] = adjustment.executed_at.isoformat()

            channel = adjustment.channel
            new_budgets[channel] = adjustment.new_budget

            logger.info(
                f"Executed budget adjustment for {channel}: "
                f"¥{adjustment.old_budget:,.2f} → ¥{adjustment.new_budget:,.2f}"
            )

        return new_budgets

    def get_approval_summary(self) -> Dict[str, Any]:
        pending_count = len(self.pending_approvals)
        approved_count = sum(
            1 for a in self.approval_history
            if a.status == BudgetAdjustmentStatus.APPROVED
        )
        rejected_count = sum(
            1 for a in self.approval_history
            if a.status == BudgetAdjustmentStatus.REJECTED
        )
        executed_count = sum(
            1 for a in self.approval_history
            if a.status == BudgetAdjustmentStatus.EXECUTED
        )
        rolled_back_count = sum(
            1 for a in self.approval_history
            if a.status == BudgetAdjustmentStatus.ROLLED_BACK
        )

        total_adjustment_amount = sum(
            abs(a.new_budget - a.old_budget)
            for a in self.pending_approvals
        )

        return {
            'pending_count': pending_count,
            'approved_count': approved_count,
            'rejected_count': rejected_count,
            'executed_count': executed_count,
            'rolled_back_count': rolled_back_count,
            'total_pending_adjustment_amount': round_float(total_adjustment_amount),
            'pending_channels': list(set(a.channel for a in self.pending_approvals))
        }

    def escalate_pending_approvals(
        self,
        hours_pending: int = 24
    ) -> List[Dict[str, Any]]:
        now = datetime.now()
        escalated = []

        for record in self.pending_approvals:
            submitted_at = record.performance_metrics.get('submitted_at')
            if submitted_at:
                submitted_dt = datetime.fromisoformat(submitted_at)
                if (now - submitted_dt) > timedelta(hours=hours_pending):
                    escalated.append(self._format_approval_for_display(record))

        if escalated:
            logger.warning(
                f"Escalating {len(escalated)} pending approvals "
                f"that have been pending for >{hours_pending} hours"
            )
            self._send_escalation_notification(escalated)

        return escalated

    def auto_approve_low_risk(
        self,
        max_adjustment_percent: float = 0.1,
        max_total_amount: float = 10000.0
    ) -> List[BudgetAdjustmentRecord]:
        auto_approved = []
        total_auto_adjustment = 0.0

        for record in self.pending_approvals:
            suggestion_data = record.performance_metrics.get('suggestion', {})
            risk_level = suggestion_data.get('risk_level', 'high')
            adjustment_percent = abs(record.performance_metrics.get('suggestion', {}).get('adjustment_percent', 1))
            adjustment_amount = abs(record.new_budget - record.old_budget)

            if (risk_level == 'low' and
                adjustment_percent <= max_adjustment_percent and
                total_auto_adjustment + adjustment_amount <= max_total_amount):

                approved = self.approve(
                    record.adjustment_id,
                    approver="auto_approval_system",
                    comments=f"Auto-approved: low risk adjustment within limits"
                )

                if approved:
                    auto_approved.append(approved)
                    total_auto_adjustment += adjustment_amount

        logger.info(
            f"Auto-approved {len(auto_approved)} low-risk adjustments "
            f"totaling ¥{total_auto_adjustment:,.2f}"
        )

        return auto_approved

    def _find_pending_adjustment(
        self,
        adjustment_id: str
    ) -> Optional[BudgetAdjustmentRecord]:
        for record in self.pending_approvals:
            if record.adjustment_id == adjustment_id:
                return record
        return None

    def _format_approval_for_display(
        self,
        record: BudgetAdjustmentRecord
    ) -> Dict[str, Any]:
        suggestion = record.performance_metrics.get('suggestion', {})

        return {
            'adjustment_id': record.adjustment_id,
            'suggestion_id': record.suggestion_id,
            'channel': record.channel,
            'old_budget': record.old_budget,
            'new_budget': record.new_budget,
            'adjustment_amount': round_float(record.new_budget - record.old_budget),
            'adjustment_percent': round_float(
                (record.new_budget - record.old_budget) / max(record.old_budget, 1)
            ),
            'status': record.status.value,
            'approver': record.approver,
            'approved_at': record.approved_at.isoformat() if record.approved_at else None,
            'executed_at': record.executed_at.isoformat() if record.executed_at else None,
            'current_roi': suggestion.get('current_roi'),
            'expected_roi_improvement': suggestion.get('expected_roi_improvement'),
            'expected_revenue_change': suggestion.get('expected_revenue_change'),
            'risk_level': suggestion.get('risk_level'),
            'reason': suggestion.get('reason'),
            'submitted_at': record.performance_metrics.get('submitted_at')
        }

    def _send_notification(self, records: List[BudgetAdjustmentRecord]):
        if not records:
            return

        summary = []
        for record in records:
            suggestion = record.performance_metrics.get('suggestion', {})
            summary.append(
                f"- {record.channel}: "
                f"¥{record.old_budget:,.2f} → ¥{record.new_budget:,.2f} "
                f"(ROI: {suggestion.get('current_roi', 0):.2f})"
            )

        notification = {
            'type': 'budget_approval_pending',
            'priority': 'medium',
            'recipients': settings.NOTIFICATION_EMAILS,
            'subject': f"Pending Budget Approvals: {len(records)} adjustments need review",
            'body': f"""
The following budget adjustments require your approval:

{chr(10).join(summary)}

Please review and approve/reject at your earliest convenience.
            """.strip(),
            'timestamp': datetime.now().isoformat(),
            'adjustment_ids': [r.adjustment_id for r in records]
        }

        logger.info(
            f"Notification sent for {len(records)} pending approvals"
        )
        return notification

    def _send_escalation_notification(self, escalated: List[Dict[str, Any]]):
        if not escalated:
            return

        summary = []
        for item in escalated:
            summary.append(
                f"- {item['channel']}: "
                f"¥{item['old_budget']:,.2f} → ¥{item['new_budget']:,.2f}, "
                f"pending since {item['submitted_at']}"
            )

        notification = {
            'type': 'budget_approval_escalation',
            'priority': 'high',
            'recipients': settings.NOTIFICATION_EMAILS + ["director@company.com"],
            'subject': f"ESCALATION: {len(escalated)} budget approvals overdue",
            'body': f"""
URGENT: The following budget adjustments have been pending for more than 24 hours:

{chr(10).join(summary)}

Please review immediately to avoid disruption to marketing campaigns.
            """.strip(),
            'timestamp': datetime.now().isoformat()
        }

        logger.warning(
            f"Escalation notification sent for {len(escalated)} overdue approvals"
        )
        return notification

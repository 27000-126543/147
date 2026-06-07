from datetime import datetime, date
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, field_validator


class PlatformType(str, Enum):
    BAIDU = "baidu"
    TENCENT = "tencent"
    ALIYUN = "aliyun"
    BYTEDANCE = "bytedance"
    KUAISHOU = "kuaishou"
    XIAOHONGSHU = "xiaohongshu"


class AttributionModelType(str, Enum):
    FIRST_CLICK = "first_click"
    LAST_CLICK = "last_click"
    LINEAR = "linear"
    TIME_DECAY = "time_decay"
    POSITION_BASED = "position_based"


class BudgetAdjustmentStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    ROLLED_BACK = "rolled_back"
    MONITORING = "monitoring"


class TouchPoint(BaseModel):
    touchpoint_id: str
    channel: str
    timestamp: datetime
    campaign: str
    audience: str
    interaction_type: str = Field(default="click")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AdPerformanceData(BaseModel):
    platform: PlatformType
    channel: str
    campaign: str
    audience: str
    date: date
    hour: Optional[int] = Field(default=None, ge=0, le=23)
    impressions: int = Field(ge=0)
    clicks: int = Field(ge=0)
    conversions: int = Field(ge=0)
    cost: float = Field(ge=0)
    revenue: float = Field(ge=0)
    touchpoints: List[TouchPoint] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    collected_at: datetime = Field(default_factory=datetime.now)

    @field_validator('hour')
    def validate_hour(cls, v):
        if v is not None and (v < 0 or v > 23):
            raise ValueError('Hour must be between 0 and 23')
        return v


class AttributionResult(BaseModel):
    conversion_id: str
    touchpoints: List[TouchPoint]
    model_type: AttributionModelType
    contributions: Dict[str, float]
    conversion_value: float
    conversion_timestamp: datetime
    total_touchpoints: int
    conversion_path_length: int


class ChannelROI(BaseModel):
    channel: str
    date: date
    total_cost: float
    total_revenue: float
    attributed_revenue: float
    roi: float
    weighted_roi: float
    rank: int
    tier: Optional[str] = None
    cpa: float
    cvr: float
    roas: float
    attribution_model: AttributionModelType
    impressions: int
    clicks: int
    conversions: int


class BudgetAdjustmentSuggestion(BaseModel):
    suggestion_id: str
    channel: str
    current_budget: float
    suggested_budget: float
    adjustment_percent: float
    reason: str
    current_roi: float
    threshold: float
    consecutive_days_below_threshold: int
    expected_roi_improvement: float
    expected_revenue_change: float
    risk_level: str
    generated_at: datetime
    model_attribution: AttributionModelType


class BudgetAdjustmentRecord(BaseModel):
    adjustment_id: str
    suggestion_id: str
    channel: str
    old_budget: float
    new_budget: float
    status: BudgetAdjustmentStatus
    approver: Optional[str] = None
    approved_at: Optional[datetime] = None
    executed_at: Optional[datetime] = None
    monitoring_start: Optional[datetime] = None
    monitoring_end: Optional[datetime] = None
    rollback_trigger: Optional[str] = None
    rollback_at: Optional[datetime] = None
    performance_metrics: Dict[str, Any] = Field(default_factory=dict)


class ReportConfig(BaseModel):
    report_id: str
    report_type: str
    start_date: date
    end_date: date
    channels: Optional[List[str]] = None
    metrics: List[str] = Field(default_factory=lambda: ["cpa", "cvr", "roas", "roi"])
    attribution_model: AttributionModelType
    include_charts: bool = True
    export_formats: List[str] = Field(default_factory=lambda: ["pdf", "xlsx"])
    scheduled: bool = False


class SimulationConfig(BaseModel):
    simulation_id: str
    name: str
    description: Optional[str] = None
    base_date: date
    budget_adjustments: Dict[str, float]
    attribution_model: AttributionModelType
    simulation_runs: int = 1000
    confidence_level: float = 0.95


class SimulationResult(BaseModel):
    simulation_id: str
    base_total_revenue: float
    simulated_total_revenue: float
    revenue_change_percent: float
    base_total_roi: float
    simulated_total_roi: float
    roi_change_percent: float
    channel_results: Dict[str, Dict[str, float]]
    confidence_interval: Dict[str, float]
    recommendation: str
    charts_data: Dict[str, Any] = Field(default_factory=dict)


class LogEntry(BaseModel):
    log_id: str
    timestamp: datetime
    operation_type: str
    operator: Optional[str] = None
    module: str
    status: str
    details: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    duration_ms: Optional[float] = None


class ConversionPath(BaseModel):
    path_id: str
    touchpoints: List[TouchPoint]
    conversion_value: float
    conversion_timestamp: datetime
    channel_sequence: List[str]

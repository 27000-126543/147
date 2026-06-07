import numpy as np
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Any, Tuple
from models import TouchPoint, AttributionResult, AttributionModelType
from utils import get_logger, generate_id, safe_divide, round_float

logger = get_logger(__name__)


class BaseAttributionModel(ABC):
    def __init__(self, model_type: AttributionModelType):
        self.model_type = model_type

    @abstractmethod
    def calculate_contributions(
        self,
        touchpoints: List[TouchPoint],
        conversion_value: float,
        conversion_timestamp: datetime = None
    ) -> Dict[str, float]:
        pass

    def attribute(
        self,
        touchpoints: List[TouchPoint],
        conversion_value: float,
        conversion_timestamp: datetime = None,
        conversion_id: str = None
    ) -> AttributionResult:
        if conversion_timestamp is None and touchpoints:
            conversion_timestamp = max(tp.timestamp for tp in touchpoints)
        elif conversion_timestamp is None:
            conversion_timestamp = datetime.now()
        if not touchpoints:
            return AttributionResult(
                conversion_id=conversion_id or generate_id("conv"),
                touchpoints=[],
                model_type=self.model_type,
                contributions={},
                conversion_value=conversion_value,
                conversion_timestamp=conversion_timestamp,
                total_touchpoints=0,
                conversion_path_length=0
            )

        sorted_touchpoints = sorted(touchpoints, key=lambda x: x.timestamp)
        contributions = self.calculate_contributions(
            sorted_touchpoints, conversion_value, conversion_timestamp
        )

        total_contribution = sum(contributions.values())
        if total_contribution > 0:
            keys = list(contributions.keys())
            for i, key in enumerate(keys):
                if i < len(keys) - 1:
                    contributions[key] = round_float(
                        contributions[key] * conversion_value / total_contribution
                    )
                else:
                    allocated = sum(contributions[k] for k in keys[:-1])
                    contributions[key] = round_float(conversion_value - allocated)

        return AttributionResult(
            conversion_id=conversion_id or generate_id("conv"),
            touchpoints=sorted_touchpoints,
            model_type=self.model_type,
            contributions=contributions,
            conversion_value=conversion_value,
            conversion_timestamp=conversion_timestamp,
            total_touchpoints=len(sorted_touchpoints),
            conversion_path_length=len(set(tp.channel for tp in sorted_touchpoints))
        )


class FirstClickAttribution(BaseAttributionModel):
    def __init__(self):
        super().__init__(AttributionModelType.FIRST_CLICK)

    def calculate_contributions(
        self,
        touchpoints: List[TouchPoint],
        conversion_value: float,
        conversion_timestamp: datetime = None
    ) -> Dict[str, float]:
        if not touchpoints:
            return {}

        sorted_tps = sorted(touchpoints, key=lambda x: x.timestamp)
        first_tp = sorted_tps[0]

        contributions = {}
        for tp in sorted_tps:
            if tp.touchpoint_id == first_tp.touchpoint_id:
                contributions[tp.touchpoint_id] = conversion_value
            else:
                contributions[tp.touchpoint_id] = 0.0

        return contributions


class LastClickAttribution(BaseAttributionModel):
    def __init__(self):
        super().__init__(AttributionModelType.LAST_CLICK)

    def calculate_contributions(
        self,
        touchpoints: List[TouchPoint],
        conversion_value: float,
        conversion_timestamp: datetime = None
    ) -> Dict[str, float]:
        if not touchpoints:
            return {}

        sorted_tps = sorted(touchpoints, key=lambda x: x.timestamp)
        last_tp = sorted_tps[-1]

        contributions = {}
        for tp in sorted_tps:
            if tp.touchpoint_id == last_tp.touchpoint_id:
                contributions[tp.touchpoint_id] = conversion_value
            else:
                contributions[tp.touchpoint_id] = 0.0

        return contributions


class LinearAttribution(BaseAttributionModel):
    def __init__(self):
        super().__init__(AttributionModelType.LINEAR)

    def calculate_contributions(
        self,
        touchpoints: List[TouchPoint],
        conversion_value: float,
        conversion_timestamp: datetime = None
    ) -> Dict[str, float]:
        if not touchpoints:
            return {}

        equal_weight = conversion_value / len(touchpoints)
        contributions = {
            tp.touchpoint_id: round_float(equal_weight) for tp in touchpoints
        }

        return contributions


class TimeDecayAttribution(BaseAttributionModel):
    def __init__(self, decay_half_life: float = 7.0):
        super().__init__(AttributionModelType.TIME_DECAY)
        self.decay_half_life = decay_half_life
        self.decay_constant = np.log(2) / decay_half_life

    def calculate_contributions(
        self,
        touchpoints: List[TouchPoint],
        conversion_value: float,
        conversion_timestamp: datetime = None
    ) -> Dict[str, float]:
        if not touchpoints:
            return {}

        sorted_tps = sorted(touchpoints, key=lambda x: x.timestamp)
        weights = []

        for tp in sorted_tps:
            time_diff = (conversion_timestamp - tp.timestamp).total_seconds() / (24 * 3600)
            weight = np.exp(-self.decay_constant * max(time_diff, 0))
            weights.append(max(weight, 0.01))

        total_weight = sum(weights)
        contributions = {}
        for i, tp in enumerate(sorted_tps):
            normalized_weight = safe_divide(weights[i], total_weight)
            contributions[tp.touchpoint_id] = round_float(conversion_value * normalized_weight)

        return contributions


class PositionBasedAttribution(BaseAttributionModel):
    def __init__(self, first_weight: float = 0.4, last_weight: float = 0.4):
        super().__init__(AttributionModelType.POSITION_BASED)
        self.first_weight = first_weight
        self.last_weight = last_weight
        self.middle_weight = 1.0 - first_weight - last_weight

        if self.middle_weight < 0:
            raise ValueError("First and last weights must sum to <= 1.0")

    def calculate_contributions(
        self,
        touchpoints: List[TouchPoint],
        conversion_value: float,
        conversion_timestamp: datetime = None
    ) -> Dict[str, float]:
        if not touchpoints:
            return {}

        sorted_tps = sorted(touchpoints, key=lambda x: x.timestamp)
        n = len(sorted_tps)
        contributions = {}

        if n == 1:
            contributions[sorted_tps[0].touchpoint_id] = conversion_value
        elif n == 2:
            half_value = conversion_value / 2
            contributions[sorted_tps[0].touchpoint_id] = round_float(half_value)
            contributions[sorted_tps[1].touchpoint_id] = round_float(half_value)
        else:
            middle_count = n - 2
            middle_weight_per_tp = safe_divide(self.middle_weight, middle_count) if middle_count > 0 else 0

            for i, tp in enumerate(sorted_tps):
                if i == 0:
                    weight = self.first_weight
                elif i == n - 1:
                    weight = self.last_weight
                else:
                    weight = middle_weight_per_tp

                contributions[tp.touchpoint_id] = round_float(conversion_value * weight)

        return contributions


def get_attribution_model(model_type: AttributionModelType) -> BaseAttributionModel:
    model_map = {
        AttributionModelType.FIRST_CLICK: FirstClickAttribution,
        AttributionModelType.LAST_CLICK: LastClickAttribution,
        AttributionModelType.LINEAR: LinearAttribution,
        AttributionModelType.TIME_DECAY: TimeDecayAttribution,
        AttributionModelType.POSITION_BASED: PositionBasedAttribution,
    }

    model_class = model_map.get(model_type)
    if not model_class:
        raise ValueError(f"Unknown attribution model: {model_type}")

    return model_class()

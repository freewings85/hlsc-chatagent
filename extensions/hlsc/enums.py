"""Shared enums and precision mappings for HLSC tools."""

from __future__ import annotations

from typing import Final, Literal


CarPrecision = Literal["none", "L1", "L2", "L3"]
ProjectRequiredPrecision = Literal["none", "basic", "exact_model", "vin"]
RequiredCarPrecision = Literal["exact_model", "vin"]

CAR_PRECISION_NONE: Final[str] = "none"
CAR_PRECISION_L1: Final[str] = "L1"
CAR_PRECISION_L2: Final[str] = "L2"
CAR_PRECISION_L3: Final[str] = "L3"

REQUIRED_PRECISION_EXACT_MODEL: Final[str] = "exact_model"
REQUIRED_PRECISION_VIN: Final[str] = "vin"
PROJECT_REQUIRED_PRECISION_NONE: Final[str] = "none"
PROJECT_REQUIRED_PRECISION_BASIC: Final[str] = "basic"

CAR_PRECISION_TO_REQUIRED: Final[dict[str, RequiredCarPrecision]] = {
    CAR_PRECISION_L2: REQUIRED_PRECISION_EXACT_MODEL,
    CAR_PRECISION_L3: REQUIRED_PRECISION_VIN,
}

CAR_PRECISION_TO_PROJECT_REQUIRED: Final[dict[str, ProjectRequiredPrecision]] = {
    CAR_PRECISION_NONE: PROJECT_REQUIRED_PRECISION_NONE,
    CAR_PRECISION_L1: PROJECT_REQUIRED_PRECISION_BASIC,
    CAR_PRECISION_L2: REQUIRED_PRECISION_EXACT_MODEL,
    CAR_PRECISION_L3: REQUIRED_PRECISION_VIN,
}

PROJECT_REQUIRED_PRECISION_LABELS: Final[dict[str, str]] = {
    PROJECT_REQUIRED_PRECISION_NONE: "无需车型信息",
    PROJECT_REQUIRED_PRECISION_BASIC: "需要基础车型信息",
    REQUIRED_PRECISION_EXACT_MODEL: "需要精确车型",
    REQUIRED_PRECISION_VIN: "VIN",
}


def to_required_precision(car_precision: str) -> RequiredCarPrecision | None:
    """Convert internal car precision to ask_user_car_info precision."""
    return CAR_PRECISION_TO_REQUIRED.get(car_precision)


def to_project_required_precision(car_precision: str) -> ProjectRequiredPrecision:
    """Convert internal car precision to model-facing required precision."""
    return CAR_PRECISION_TO_PROJECT_REQUIRED.get(car_precision, PROJECT_REQUIRED_PRECISION_NONE)

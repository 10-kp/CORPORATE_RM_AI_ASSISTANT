# src/domain/deal_summary.py
"""
Canonical domain objects for the Corporate RM AI Assistant.

This file defines the single source of truth for the Deal Summary that powers:
- API responses
- UI rendering
- AI summary generation
- Natural-language Q&A
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Any, Dict, List, Literal, Optional


StrategicSector = Literal[
    "Manufacturing",
    "Advanced Technology",
    "Healthcare",
    "Food Security",
    "Renewables",
    "Other",
]

Trend3Y = Literal["Improving", "Stable", "Declining"]
Signal3 = Literal["Strong", "Adequate", "Weak"]
SignalLeverage = Literal["Low", "Moderate", "Elevated"]
SignalVolatility = Literal["Low", "Moderate", "High"]
SignalInvestment = Literal["High", "Moderate", "Low"]

DealReadinessStatus = Literal["Strong", "Conditional", "Weak"]


@dataclass(frozen=True)
class RatingAnchor:
    system: str
    grade: str
    outlook: Optional[str] = None
    as_of: Optional[date] = None


@dataclass(frozen=True)
class Eligibility:
    score: float
    drivers: List[str] = field(default_factory=list)
    breakdown: Dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class FinancialSignals:
    revenue_trend_3y: Trend3Y
    margin_trend_3y: Literal["Improving", "Stable", "Under Pressure"]
    leverage_position: SignalLeverage
    cashflow_quality: Signal3
    earnings_volatility: SignalVolatility
    capex_growth_investment: SignalInvestment
    financial_transparency: Signal3


@dataclass(frozen=True)
class DealReadiness:
    status: DealReadinessStatus
    strengths: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class DealSummary:
    client_name: str
    group_name: Optional[str]
    sector: StrategicSector

    rating_anchor: RatingAnchor
    eligibility: Eligibility
    financial_signals: FinancialSignals

    deal_readiness: DealReadiness
    mandate_fit_summary: str
    rm_actions: List[str] = field(default_factory=list)
    talking_points: List[str] = field(default_factory=list)

    created_at: Optional[date] = None
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)

        def _convert(obj: Any) -> Any:
            if isinstance(obj, date):
                return obj.isoformat()
            if isinstance(obj, dict):
                return {k: _convert(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_convert(v) for v in obj]
            return obj

        return _convert(d)

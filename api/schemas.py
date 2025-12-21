# api/schemas.py
from __future__ import annotations

from datetime import date
from typing import Dict, List, Literal, Optional, Any

from pydantic import BaseModel, Field, field_validator

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


class RatingAnchorIn(BaseModel):
    system: str = Field(..., description="Source system for rating (Credit Lens / Moody's).")
    grade: str = Field(..., description="Rating grade as provided by the source system.")
    outlook: Optional[str] = Field(None, description="Stable/Negative/Positive (if available).")
    as_of: Optional[date] = Field(None, description="Rating date (if available).")


class EligibilityIn(BaseModel):
    score: float = Field(..., ge=0.0, le=6.0, description="Eligibility score (0.0 to 6.0).")
    drivers: List[str] = Field(default_factory=list, description="Short bullets explaining the score.")
    breakdown: Dict[str, float] = Field(default_factory=dict, description="Optional component scores.")


class FinancialSignalsIn(BaseModel):
    revenue_trend_3y: Trend3Y
    margin_trend_3y: Literal["Improving", "Stable", "Under Pressure"]
    leverage_position: SignalLeverage
    cashflow_quality: Signal3
    earnings_volatility: SignalVolatility
    capex_growth_investment: SignalInvestment
    financial_transparency: Signal3


class DealInputRequest(BaseModel):
    client_name: str
    group_name: Optional[str] = None
    sector: StrategicSector

    rating_anchor: RatingAnchorIn
    eligibility: EligibilityIn
    financial_signals: FinancialSignalsIn

    notes: Optional[str] = Field(None, description="Optional RM notes.")

    @field_validator("client_name")
    @classmethod
    def client_name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("client_name must not be empty.")
        return v


class DealReadinessOut(BaseModel):
    status: DealReadinessStatus
    strengths: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)


class DealSummaryResponse(BaseModel):
    client_name: str
    group_name: Optional[str] = None
    sector: StrategicSector

    rating_anchor: RatingAnchorIn
    eligibility: EligibilityIn
    financial_signals: FinancialSignalsIn

    deal_readiness: DealReadinessOut
    mandate_fit_summary: str

    rm_actions: List[str] = Field(default_factory=list)
    talking_points: List[str] = Field(default_factory=list)

    created_at: Optional[date] = None
    notes: Optional[str] = None


# ===============================
# AI schemas (Explain + Q&A)
# ===============================

class AIQARequest(BaseModel):
    question: str = Field(..., description="User question about the deal summary.")
    # Frontend should pass the /assess response here so AI can be grounded
    deal_summary: Optional[DealSummaryResponse] = None


class AIQAResponse(BaseModel):
    answer: str
    disclaimer: str


class AIExplainRequest(BaseModel):
    # Frontend should pass the /assess response here
    deal_summary: DealSummaryResponse


class AIExplainResponse(BaseModel):
    executive_summary: str
    key_risks_explained: List[str] = Field(default_factory=list)
    rm_talking_points: List[str] = Field(default_factory=list)
    disclaimer: str

# api/schemas.py
from __future__ import annotations

from datetime import date
from typing import Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field, field_validator

StrategicSector = Literal[
    "Manufacturing",
    "Advanced Technology",
    "Healthcare",
    "Food Security",
    "Renewables",
    "Other",
]

DealReadinessStatus = Literal["Strong", "Conditional", "Weak"]
Decision = Literal["Proceed", "Restructure", "Decline", "N/A"]

ConfidenceLevel = Literal["Low", "Medium", "High"]


class RatingAnchorIn(BaseModel):
    system: str = Field(..., description="Source system for rating (Credit Lens / Moody's).")
    grade: str = Field(..., description="Rating grade as provided by the source system.")
    outlook: Optional[str] = Field(None, description="Stable/Negative/Positive (if available).")
    as_of: Optional[date] = Field(None, description="Rating date (if available).")


class EligibilityIn(BaseModel):
    score: float = Field(..., ge=0.0, le=6.0, description="Eligibility score (0.0 to 6.0).")
    drivers: List[str] = Field(default_factory=list, description="Short bullets explaining the score.")
    breakdown: Dict[str, float] = Field(default_factory=dict, description="Optional component scores.")


class Financials2YIn(BaseModel):
    """
    MVP: two-year financial snapshot extracted from uploaded PDF (or manually entered).

    period_labels: exactly 2 labels (e.g., ("FY-1", "FY-2"))
    Each metric: exactly 2 values aligned to period_labels; None allowed if not found.

    NOTE:
    - For DSCR support, we explicitly include DSCR drivers:
        ebitda (P&L), interest_on_loans (P&L), cpltd (B/S)
      so that:
        DSCR = EBITDA / (CPLTD + Interest on loans)
      can be computed deterministically (backend and/or frontend).
    """

    period_labels: Tuple[str, str] = Field(..., description='Two periods, e.g. ("FY-1","FY-2").')
    currency: Optional[str] = Field(None, description="Currency if known (e.g., AED, USD).")
    confidence: ConfidenceLevel = Field("Low", description="Extraction confidence (MVP heuristic).")

    # Core wholesale-banking metrics (2 years)
    revenue: Tuple[Optional[float], Optional[float]] = Field(
        (None, None), description="Revenue for the two periods (absolute)."
    )
    ebitda_margin_pct: Tuple[Optional[float], Optional[float]] = Field(
        (None, None), description="EBITDA margin (%) for the two periods."
    )
    leverage_netdebt_to_ebitda: Tuple[Optional[float], Optional[float]] = Field(
        (None, None), description="Net Debt / EBITDA for the two periods."
    )

    # DSCR drivers (explicit; do not hide in debug)
    ebitda: Tuple[Optional[float], Optional[float]] = Field(
        (None, None), description="EBITDA amount for the two periods."
    )
    interest_on_loans: Tuple[Optional[float], Optional[float]] = Field(
        (None, None), description="Interest on loans / borrowing-related finance cost for the two periods."
    )
    cpltd: Tuple[Optional[float], Optional[float]] = Field(
        (None, None), description="Current portion of long-term debt / current maturities for the two periods."
    )

    dscr: Tuple[Optional[float], Optional[float]] = Field(
        (None, None),
        description=(
            "DSCR for the two periods. If inputs are available, DSCR should be computed "
            "deterministically as EBITDA/(CPLTD+Interest)."
        ),
    )

    operating_cashflow: Tuple[Optional[float], Optional[float]] = Field(
        (None, None), description="Net cash from operating activities for the two periods."
    )

    # ------------------------------
    # Minimal banker-grade additions
    # ------------------------------

    # P&L
    net_profit: Tuple[Optional[float], Optional[float]] = Field(
        (None, None), description="Net profit after tax (PAT) for the two periods."
    )
    interest_expense_total: Tuple[Optional[float], Optional[float]] = Field(
        (None, None), description="Total finance costs / interest expense for the two periods (if available)."
    )

    # Balance Sheet
    total_assets: Tuple[Optional[float], Optional[float]] = Field(
        (None, None), description="Total assets for the two periods."
    )
    total_equity: Tuple[Optional[float], Optional[float]] = Field(
        (None, None), description="Total equity for the two periods."
    )
    total_debt: Tuple[Optional[float], Optional[float]] = Field(
        (None, None), description="Total debt (short-term + long-term borrowings) for the two periods."
    )
    current_assets: Tuple[Optional[float], Optional[float]] = Field(
        (None, None), description="Current assets for the two periods."
    )
    current_liabilities: Tuple[Optional[float], Optional[float]] = Field(
        (None, None), description="Current liabilities for the two periods."
    )
    cash_and_equivalents: Tuple[Optional[float], Optional[float]] = Field(
        (None, None), description="Cash and cash equivalents for the two periods."
    )

    # Working capital components (optional but useful)
    inventory: Tuple[Optional[float], Optional[float]] = Field(
        (None, None), description="Inventory for the two periods."
    )
    trade_receivables: Tuple[Optional[float], Optional[float]] = Field(
        (None, None), description="Trade receivables for the two periods."
    )
    trade_payables: Tuple[Optional[float], Optional[float]] = Field(
        (None, None), description="Trade payables for the two periods."
    )

    # Cash Flow
    capex: Tuple[Optional[float], Optional[float]] = Field(
        (None, None), description="Capex (cash paid for PPE/additions) for the two periods (typically negative)."
    )

    notes: List[str] = Field(default_factory=list, description="Extraction notes / caveats.")

    @field_validator("period_labels")
    @classmethod
    def period_labels_must_be_two(cls, v: Tuple[str, str]) -> Tuple[str, str]:
        if len(v) != 2:
            raise ValueError("period_labels must contain exactly 2 entries.")
        if not v[0].strip() or not v[1].strip():
            raise ValueError("period_labels entries must not be empty.")
        return v

    @field_validator(
        "revenue",
        "ebitda_margin_pct",
        "leverage_netdebt_to_ebitda",
        "ebitda",
        "interest_on_loans",
        "cpltd",
        "dscr",
        "operating_cashflow",
        # additions
        "net_profit",
        "interest_expense_total",
        "total_assets",
        "total_equity",
        "total_debt",
        "current_assets",
        "current_liabilities",
        "cash_and_equivalents",
        "inventory",
        "trade_receivables",
        "trade_payables",
        "capex",
    )
    @classmethod
    def _must_be_two_values(cls, v):
        # Defensive validation: ensure every tuple field remains length 2
        if v is None:
            return (None, None)
        if isinstance(v, tuple) and len(v) == 2:
            return v
        raise ValueError("Two-year metric fields must contain exactly 2 entries.")


class DealInputRequest(BaseModel):
    client_name: str
    group_name: Optional[str] = None
    sector: StrategicSector

    rating_anchor: RatingAnchorIn
    eligibility: EligibilityIn

    # Replaces financial_signals
    financials_2y: Financials2YIn

    indicative_raroc_pct: Optional[float] = Field(
        None,
        ge=0.0,
        le=100.0,
        description="Indicative RM-entered RAROC (%) for early screening (non-binding).",
    )

    notes: Optional[str] = Field(None, description="Optional RM notes.")

    @field_validator("client_name")
    @classmethod
    def client_name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("client_name must not be empty.")
        return v


class FinancialsInfer2YRequest(BaseModel):
    text_preview: str
    currency: Optional[str] = None
    period_labels: Optional[List[str]] = None


class Financials2YOut(BaseModel):
    period_labels: List[Optional[str]] = Field(default_factory=lambda: [None, None])
    currency: Optional[str] = None
    confidence: Literal["Low", "Medium", "High"] = "Low"

    revenue: List[Optional[float]] = Field(default_factory=lambda: [None, None])
    ebitda_margin_pct: List[Optional[float]] = Field(default_factory=lambda: [None, None])
    leverage_netdebt_to_ebitda: List[Optional[float]] = Field(default_factory=lambda: [None, None])

    # DSCR drivers
    ebitda: List[Optional[float]] = Field(default_factory=lambda: [None, None])
    interest_on_loans: List[Optional[float]] = Field(default_factory=lambda: [None, None])
    cpltd: List[Optional[float]] = Field(default_factory=lambda: [None, None])

    dscr: List[Optional[float]] = Field(default_factory=lambda: [None, None])
    operating_cashflow: List[Optional[float]] = Field(default_factory=lambda: [None, None])

    # ------------------------------
    # Minimal banker-grade additions
    # ------------------------------

    # P&L
    net_profit: List[Optional[float]] = Field(default_factory=lambda: [None, None])
    interest_expense_total: List[Optional[float]] = Field(default_factory=lambda: [None, None])

    # Balance Sheet
    total_assets: List[Optional[float]] = Field(default_factory=lambda: [None, None])
    total_equity: List[Optional[float]] = Field(default_factory=lambda: [None, None])
    total_debt: List[Optional[float]] = Field(default_factory=lambda: [None, None])
    current_assets: List[Optional[float]] = Field(default_factory=lambda: [None, None])
    current_liabilities: List[Optional[float]] = Field(default_factory=lambda: [None, None])
    cash_and_equivalents: List[Optional[float]] = Field(default_factory=lambda: [None, None])

    # Working capital components
    inventory: List[Optional[float]] = Field(default_factory=lambda: [None, None])
    trade_receivables: List[Optional[float]] = Field(default_factory=lambda: [None, None])
    trade_payables: List[Optional[float]] = Field(default_factory=lambda: [None, None])

    # Cash Flow
    capex: List[Optional[float]] = Field(default_factory=lambda: [None, None])

    notes: List[str] = Field(default_factory=list)


class DealReadinessOut(BaseModel):
    status: DealReadinessStatus
    strengths: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)


# ==========================================
# Banker-grade deterministic signals (NEW)
# ==========================================

class FinancialSignalFlag(BaseModel):
    code: str = Field(..., description='Stable code, e.g. "DSCR_BELOW_1", "MISSING_TOTAL_DEBT".')
    severity: Literal["Low", "Medium", "High"] = Field("Low", description="Severity for UI ordering.")
    message: str = Field(..., description="Human-readable explanation of the issue/flag.")


class FinancialSignals2Y(BaseModel):
    # Growth (YoY %). For a 2-year set, typically only the first element is meaningful.
    revenue_yoy_pct: List[Optional[float]] = Field(default_factory=lambda: [None, None])
    ebitda_yoy_pct: List[Optional[float]] = Field(default_factory=lambda: [None, None])
    net_profit_yoy_pct: List[Optional[float]] = Field(default_factory=lambda: [None, None])

    # Profitability
    net_margin_pct: List[Optional[float]] = Field(default_factory=lambda: [None, None])
    roa_pct: List[Optional[float]] = Field(default_factory=lambda: [None, None])
    roe_pct: List[Optional[float]] = Field(default_factory=lambda: [None, None])

    # Leverage / capital structure
    debt_to_equity: List[Optional[float]] = Field(default_factory=lambda: [None, None])
    equity_ratio_pct: List[Optional[float]] = Field(default_factory=lambda: [None, None])  # equity/assets

    # Liquidity
    current_ratio: List[Optional[float]] = Field(default_factory=lambda: [None, None])
    quick_ratio: List[Optional[float]] = Field(default_factory=lambda: [None, None])

    # Cash conversion / coverage
    cfo_to_ebitda: List[Optional[float]] = Field(default_factory=lambda: [None, None])
    free_cash_flow: List[Optional[float]] = Field(default_factory=lambda: [None, None])  # CFO - capex
    interest_coverage_ebitda: List[Optional[float]] = Field(default_factory=lambda: [None, None])

    # DSCR deterministic (duplicate for clarity vs extracted dscr)
    dscr_deterministic: List[Optional[float]] = Field(default_factory=lambda: [None, None])

    # Explainability / data quality
    flags: List[FinancialSignalFlag] = Field(default_factory=list)


class DealSummaryResponse(BaseModel):
    client_name: str
    group_name: Optional[str] = None
    sector: StrategicSector

    rating_anchor: RatingAnchorIn
    eligibility: EligibilityIn

    # Keep as-is (non-breaking): still uses the input model with tuples.
    financials_2y: Financials2YIn

    indicative_raroc_pct: Optional[float] = Field(
        None,
        ge=0.0,
        le=100.0,
        description="Indicative RM-entered RAROC (%) for early screening (non-binding).",
    )

    deal_readiness: DealReadinessOut
    mandate_fit_summary: str

    # NEW (optional): deterministic financial signals computed in _assess_deal()
    financial_signals: Optional[FinancialSignals2Y] = Field(
        None,
        description="Deterministic, banker-grade computed signals (safe even when AI is off).",
    )

    rm_actions: List[str] = Field(default_factory=list)
    talking_points: List[str] = Field(default_factory=list)

    created_at: Optional[date] = None
    notes: Optional[str] = None


# ===============================
# AI schemas (Explain + Q&A)
# ===============================

class AIQARequest(BaseModel):
    question: str = Field(..., description="User question about the deal summary.")
    deal_summary: Optional[DealSummaryResponse] = None


class AIQAResponse(BaseModel):
    decision: Decision = "N/A"
    rationale: List[str] = Field(default_factory=list)
    conditions_next_steps: List[str] = Field(default_factory=list)
    answer: str
    disclaimer: str


class AIExplainRequest(BaseModel):
    deal_summary: DealSummaryResponse


class AIExplainResponse(BaseModel):
    executive_summary: str
    key_risks_explained: List[str] = Field(default_factory=list)
    rm_talking_points: List[str] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    disclaimer: str

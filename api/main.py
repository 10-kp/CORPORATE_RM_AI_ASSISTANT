# api/main.py
from __future__ import annotations

import io
import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

# =========================
# Env
# =========================
REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env", override=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "").strip()

# Feature flags
AI_ENABLED = os.getenv("AI_ENABLED", "false").strip().lower() in {"1", "true", "yes", "y", "on"}
ALLOW_FALLBACK = os.getenv("ALLOW_FALLBACK", "true").strip().lower() in {"1", "true", "yes", "y", "on"}

# Currency normalization for MVP
MVP_CURRENCY = "AED"

# =========================
# App
# =========================
app = FastAPI(title="Corporate RM AI Assistant", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN] if FRONTEND_ORIGIN else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------
# Favicon (avoid SPA fallback 500)
# -------------------------
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


# =========================
# Schemas
# =========================
from api.schemas import (  # noqa: E402
    AIExplainRequest,
    AIExplainResponse,
    AIQARequest,
    AIQAResponse,
    DealInputRequest,
    DealSummaryResponse,
    Financials2YIn,
    FinancialSignals2Y,
    FinancialSignalFlag,
)

# =========================
# OpenAI client (optional)
# =========================
oa_client = None
if AI_ENABLED and OPENAI_API_KEY:
    try:
        from openai import OpenAI  # type: ignore

        oa_client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception:
        oa_client = None

# =========================
# Health
# =========================
@app.get("/health", include_in_schema=False)
def health():
    return {
        "status": "ok",
        "pid": os.getpid(),
        "ai_enabled_flag": AI_ENABLED,
        "openai_key_present": bool(OPENAI_API_KEY),
        "oa_client_ready": oa_client is not None,
        "model": MODEL_NAME,
    }


# =========================
# Dropdown meta (optional)
# =========================
@app.get("/meta/dropdowns", include_in_schema=False)
def dropdown_meta():
    # MVP: keep only what remains in the UI.
    return {
        "sectors": [
            "Manufacturing",
            "Advanced Technology",
            "Healthcare",
            "Food Security",
            "Renewables",
            "Other",
        ],
        "outlooks": ["Stable", "Positive", "Negative", "Watch"],
        "rating_systems": ["Credit Lens"],
        "confidence_levels": ["Low", "Medium", "High"],
    }


# =========================
# Guardrails
# =========================
_SENSITIVE_PATTERNS = [
    re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),  # IBAN-ish
    re.compile(r"\b\d{12,19}\b"),  # card-ish
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
]


def _contains_sensitive(text: str) -> bool:
    if not text:
        return False
    return any(p.search(text) for p in _SENSITIVE_PATTERNS)


def _guard_no_sensitive(*texts: str):
    for t in texts:
        if t and _contains_sensitive(t):
            raise HTTPException(
                status_code=400,
                detail="Sensitive identifiers detected. Remove PII/account numbers/IBAN/emails and retry.",
            )


# =========================
# Helpers
# =========================
def _get_any(d: Dict[str, Any], *keys: str, default=None):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def _norm_currency(_: Optional[str]) -> str:
    # MVP: force AED across the system to avoid unit/currency drift.
    return MVP_CURRENCY


# =========================
# JSON + numeric helpers
# =========================
def _safe_json_loads(s: str) -> Optional[Dict[str, Any]]:
    """
    Robust JSON loader:
    - Strips common ```json fences
    - Returns None if still not valid JSON object
    """
    if not s:
        return None
    s = s.strip()

    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)

    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
        return None
    except Exception:
        return None


def _coerce_float(x) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        t = x.strip()
        if not t:
            return None
        t = t.replace(",", "")
        # Handle parentheses negatives e.g. (123)
        if t.startswith("(") and t.endswith(")"):
            t = "-" + t[1:-1]
        try:
            return float(t)
        except Exception:
            return None
    return None


def _coerce_2y_array(v) -> List[Optional[float]]:
    # Normalize to [FY-1, FY-2]
    if isinstance(v, list) and len(v) >= 2:
        return [_coerce_float(v[0]), _coerce_float(v[1])]
    return [None, None]


def _compute_dscr_2y(
    ebitda: List[Optional[float]],
    cpltd: List[Optional[float]],
    interest: List[Optional[float]],
) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    for i in range(2):
        e = ebitda[i]
        c = cpltd[i]
        it = interest[i]

        # Missing data -> no DSCR
        if e is None or c is None or it is None:
            out.append(None)
            continue

        # Sanity: CPLTD should not be negative (bad extraction / sign convention)
        if c < 0:
            out.append(None)
            continue

        denom = c + abs(it)
        if denom == 0:
            out.append(None)
            continue

        out.append(round(e / denom, 2))
    return out


def _extract_2y_from_line(text: str, label_patterns: List[str]) -> List[Optional[float]]:
    """
    Extracts two-year values from a line like:
      'EBITDA 22,500 20,000'
      'Interest expense (1,200) (1,100)'
    Returns [FY-1, FY-2] as floats, or [None, None] if not found.
    """
    if not text:
        return [None, None]

    # Normalize whitespace
    t = re.sub(r"[ \t]+", " ", text)

    for pat in label_patterns:
        # Capture two numeric tokens after the label
        m = re.search(
            rf"{pat}\s+([(\-]?\d[\d,]*\.?\d*[)]?)\s+([(\-]?\d[\d,]*\.?\d*[)]?)",
            t,
            flags=re.IGNORECASE,
        )
        if m:
            return [_coerce_float(m.group(1)), _coerce_float(m.group(2))]

    return [None, None]


def _fallback_infer_2y_from_text(text: str, currency_hint: str) -> Dict[str, Any]:
    """
    No-AI fallback for MVP:
    - Extract 2-year financials from text
    - Compute Gross Profit if missing (Revenue – COGS)
    - Compute EBITDA if missing (EBIT + Depreciation & Amortization)
    - Compute DSCR deterministically
    """

    # =========================
    # Income Statement
    # =========================
    revenue = _extract_2y_from_line(text, [r"\bRevenue\b", r"\bSales\b"])
    cogs = _extract_2y_from_line(text, [r"\bCost\s+of\s+Goods\s+Sold\b", r"\bCOGS\b", r"\bCost\s+of\s+Sales\b"])

    gross_profit = _extract_2y_from_line(text, [r"\bGross\s+Profit\b"])
    if gross_profit == [None, None]:
        gp0 = (revenue[0] - cogs[0]) if (revenue[0] is not None and cogs[0] is not None) else None
        gp1 = (revenue[1] - cogs[1]) if (revenue[1] is not None and cogs[1] is not None) else None
        gross_profit = [gp0, gp1]

    net_profit = _extract_2y_from_line(text, [r"\bNet\s+Profit\b", r"\bProfit\s+after\s+tax\b", r"\bPAT\b"])

    # =========================
    # EBITDA (Extract OR Compute)
    # =========================
    ebitda = _extract_2y_from_line(text, [r"\bEBITDA\b"])

    ebit = _extract_2y_from_line(text, [r"\bEBIT\b", r"\bOperating\s+Profit\b", r"\bProfit\s+from\s+Operations\b"])
    depr_amort = _extract_2y_from_line(
        text,
        [
            r"\bDepreciation\b",
            r"\bAmortization\b",
            r"\bDepreciation\s+and\s+Amortization\b",
        ],
    )

    if ebitda == [None, None]:
        e0 = (ebit[0] + depr_amort[0]) if (ebit[0] is not None and depr_amort[0] is not None) else None
        e1 = (ebit[1] + depr_amort[1]) if (ebit[1] is not None and depr_amort[1] is not None) else None
        ebitda = [e0, e1]

    # =========================
    # Balance Sheet
    # =========================
    total_assets = _extract_2y_from_line(text, [r"\bTotal\s+Assets\b"])
    total_equity = _extract_2y_from_line(text, [r"\bTotal\s+Equity\b", r"\bShareholders'\s+Equity\b"])

    # =========================
    # Debt Service
    # =========================
    interest = _extract_2y_from_line(
        text,
        [
            r"\bInterest\b\s+\bExpense\b",
            r"\bInterest\b\s+\bon\b\s+\bLoans\b",
            r"\bFinance\b\s+\bCost\b",
            r"\bBorrowing\b\s+\bCost\b",
        ],
    )
    cpltd = _extract_2y_from_line(
        text,
        [
            r"\bCurrent\s+portion\s+of\s+long[- ]term\s+debt\b",
            r"\bCurrent\s+maturities\s+of\s+long[- ]term\s+debt\b",
            r"\bCurrent\s+maturities\s+of\s+borrowings\b",
            r"\bCPLTD\b",
        ],
    )

    # =========================
    # DSCR (Deterministic)
    # =========================
    dscr = _compute_dscr_2y(ebitda, cpltd, interest)

    # =========================
    # Confidence heuristic
    # =========================
    core_fields = revenue + cogs + gross_profit + net_profit + ebitda + total_assets + total_equity + interest + cpltd
    missing = sum(x is None for x in core_fields)
    confidence = "High" if missing == 0 else ("Medium" if missing <= 4 else "Low")

    return {
        "financials_2y": {
            "period_labels": ["FY-1", "FY-2"],
            "currency": currency_hint,
            "confidence": confidence,
            "revenue": revenue,
            "cogs": cogs,
            "gross_profit": gross_profit,
            "net_profit": net_profit,
            "ebitda": ebitda,
            "interest_on_loans": interest,
            "cpltd": cpltd,
            "dscr": dscr,
            "total_assets": total_assets,
            "total_equity": total_equity,
            "ebitda_margin_pct": [None, None],
            "leverage_netdebt_to_ebitda": [None, None],
            "operating_cashflow": [None, None],
            "notes": [
                "Fallback inference used (no AI).",
                "Gross profit computed as Revenue – COGS where not explicitly stated.",
                "EBITDA computed as EBIT + Depreciation/Amortization where not explicitly stated.",
                "DSCR computed as EBITDA / (CPLTD + abs(Interest on loans)).",
            ],
        },
        "source": "Fallback (regex + deterministic accounting)",
        "debug": {
            "revenue": revenue,
            "cogs": cogs,
            "gross_profit": gross_profit,
            "ebit": ebit,
            "depreciation_amortization": depr_amort,
            "ebitda": ebitda,
            "interest_on_loans": interest,
            "cpltd": cpltd,
        },
    }


# =========================
# Core assessment
# =========================
RAROC_HURDLE = 5.0


def _safe_div(n: Optional[float], d: Optional[float]) -> Optional[float]:
    if n is None or d is None:
        return None
    if d == 0:
        return None
    return n / d


def _yoy_pct(cur: Optional[float], prev: Optional[float]) -> Optional[float]:
    # YoY = (cur - prev) / abs(prev)
    if cur is None or prev is None:
        return None
    if prev == 0:
        return None
    return (cur - prev) / abs(prev)


def _compute_financial_signals_2y(fin: Financials2YIn) -> FinancialSignals2Y:
    """
    Deterministic, banker-grade signals for two periods.
    Convention:
      - index 0 = period_labels[0] (FY-1 / most recent)
      - index 1 = period_labels[1] (FY-2 / prior)
    """
    flags: List[FinancialSignalFlag] = []

    # Unpack tuples (2y)
    rev0, rev1 = fin.revenue
    ebitda0, ebitda1 = fin.ebitda
    pat0, pat1 = fin.net_profit
    cfo0, cfo1 = fin.operating_cashflow

    cpltd0, cpltd1 = fin.cpltd
    int_loans0, int_loans1 = fin.interest_on_loans
    int_total0, int_total1 = fin.interest_expense_total

    assets0, assets1 = fin.total_assets
    equity0, equity1 = fin.total_equity
    debt0, debt1 = fin.total_debt

    ca0, ca1 = fin.current_assets
    cl0, cl1 = fin.current_liabilities
    inv0, inv1 = fin.inventory

    capex0, capex1 = fin.capex

    # Prefer total interest, fallback to interest_on_loans
    ie0 = int_total0 if int_total0 is not None else int_loans0
    ie1 = int_total1 if int_total1 is not None else int_loans1

    # --- DSCR (deterministic) ---
    # IMPORTANT: interest may be negative in statements; always use abs().
    dscr_d0 = _safe_div(
        ebitda0,
        (cpltd0 + abs(int_loans0)) if (cpltd0 is not None and int_loans0 is not None) else None,
    )
    dscr_d1 = _safe_div(
        ebitda1,
        (cpltd1 + abs(int_loans1)) if (cpltd1 is not None and int_loans1 is not None) else None,
    )

    # Flags (minimal, deterministic)
    if ebitda0 is not None and ebitda0 < 0:
        flags.append(
            FinancialSignalFlag(
                code="NEGATIVE_EBITDA",
                severity="High",
                message="EBITDA is negative in the latest period (core operations loss-making).",
            )
        )
    if dscr_d0 is not None and dscr_d0 < 1.0:
        flags.append(
            FinancialSignalFlag(
                code="DSCR_BELOW_1",
                severity="High",
                message="Deterministic DSCR is below 1.0x in the latest period.",
            )
        )

    if debt0 is None:
        flags.append(
            FinancialSignalFlag(
                code="MISSING_TOTAL_DEBT",
                severity="Medium",
                message="Total debt not available; leverage ratios may be incomplete.",
            )
        )
    if equity0 is None:
        flags.append(
            FinancialSignalFlag(
                code="MISSING_EQUITY",
                severity="Medium",
                message="Total equity not available; capital structure ratios may be incomplete.",
            )
        )
    if assets0 is None:
        flags.append(
            FinancialSignalFlag(
                code="MISSING_TOTAL_ASSETS",
                severity="Low",
                message="Total assets not available; ROA/equity ratio may be incomplete.",
            )
        )

    # --- Growth (YoY %) ---
    revenue_yoy0 = _yoy_pct(rev0, rev1)
    ebitda_yoy0 = _yoy_pct(ebitda0, ebitda1)
    pat_yoy0 = _yoy_pct(pat0, pat1)

    # --- Profitability ---
    net_margin0 = _safe_div(pat0, rev0)
    net_margin1 = _safe_div(pat1, rev1)

    roa0 = _safe_div(pat0, assets0)
    roa1 = _safe_div(pat1, assets1)

    roe0 = _safe_div(pat0, equity0)
    roe1 = _safe_div(pat1, equity1)

    # --- Leverage / capital structure ---
    dte0 = _safe_div(debt0, equity0)
    dte1 = _safe_div(debt1, equity1)

    eqr0 = _safe_div(equity0, assets0)  # equity/assets
    eqr1 = _safe_div(equity1, assets1)

    # --- Liquidity ---
    cr0 = _safe_div(ca0, cl0)
    cr1 = _safe_div(ca1, cl1)

    qr0 = _safe_div((ca0 - inv0) if (ca0 is not None and inv0 is not None) else None, cl0)
    qr1 = _safe_div((ca1 - inv1) if (ca1 is not None and inv1 is not None) else None, cl1)

    if cr0 is not None and cr0 < 1.0:
        flags.append(
            FinancialSignalFlag(
                code="CURRENT_RATIO_BELOW_1",
                severity="Medium",
                message="Current ratio is below 1.0x in the latest period.",
            )
        )

    # --- Cash conversion / coverage ---
    cfo_to_ebitda0 = _safe_div(cfo0, ebitda0)
    cfo_to_ebitda1 = _safe_div(cfo1, ebitda1)

    # Deterministic: CFO - capex (whatever sign convention capex has in extraction)
    fcf0 = (cfo0 - capex0) if (cfo0 is not None and capex0 is not None) else None
    fcf1 = (cfo1 - capex1) if (cfo1 is not None and capex1 is not None) else None

    ic0 = _safe_div(ebitda0, ie0)
    ic1 = _safe_div(ebitda1, ie1)

    if ic0 is not None and ic0 < 1.5:
        flags.append(
            FinancialSignalFlag(
                code="LOW_INTEREST_COVERAGE",
                severity="Medium",
                message="EBITDA interest coverage appears weak (<1.5x) in the latest period.",
            )
        )

    return FinancialSignals2Y(
        # YoY: only first slot meaningful in 2-year case; second kept None
        revenue_yoy_pct=[revenue_yoy0, None],
        ebitda_yoy_pct=[ebitda_yoy0, None],
        net_profit_yoy_pct=[pat_yoy0, None],
        # Convert margins/returns to % for UI
        net_margin_pct=[
            (net_margin0 * 100.0) if net_margin0 is not None else None,
            (net_margin1 * 100.0) if net_margin1 is not None else None,
        ],
        roa_pct=[
            (roa0 * 100.0) if roa0 is not None else None,
            (roa1 * 100.0) if roa1 is not None else None,
        ],
        roe_pct=[
            (roe0 * 100.0) if roe0 is not None else None,
            (roe1 * 100.0) if roe1 is not None else None,
        ],
        debt_to_equity=[dte0, dte1],
        equity_ratio_pct=[
            (eqr0 * 100.0) if eqr0 is not None else None,
            (eqr1 * 100.0) if eqr1 is not None else None,
        ],
        current_ratio=[cr0, cr1],
        quick_ratio=[qr0, qr1],
        cfo_to_ebitda=[cfo_to_ebitda0, cfo_to_ebitda1],
        free_cash_flow=[fcf0, fcf1],
        interest_coverage_ebitda=[ic0, ic1],
        dscr_deterministic=[dscr_d0, dscr_d1],
        flags=flags,
    )


def _assess_deal(payload: DealInputRequest) -> DealSummaryResponse:
    _guard_no_sensitive(payload.client_name, payload.group_name or "", payload.notes or "")

    strengths: List[str] = []
    constraints: List[str] = []
    rm_actions: List[str] = []
    talking_points: List[str] = []

    if payload.rating_anchor.grade:
        strengths.append(f"Rating anchor available from {payload.rating_anchor.system}.")
    else:
        constraints.append("No rating grade provided.")
        rm_actions.append("Obtain latest rating grade.")

    s = payload.eligibility.score
    if s >= 4.5:
        strengths.append(f"Strong eligibility score ({s:.1f}/6).")
    elif s >= 3.0:
        constraints.append(f"Moderate eligibility score ({s:.1f}/6).")
    else:
        constraints.append(f"Weak eligibility score ({s:.1f}/6).")

    raroc = payload.indicative_raroc_pct
    if raroc is None:
        constraints.append("RAROC not provided.")
        rm_actions.append("Input RAROC estimate for screening.")
    else:
        if raroc >= RAROC_HURDLE:
            strengths.append(f"RAROC meets hurdle (≥ {RAROC_HURDLE:.1f}%).")
        else:
            constraints.append(f"RAROC below hurdle (< {RAROC_HURDLE:.1f}%).")
            rm_actions.append("Improve pricing/structure to lift RAROC above hurdle.")

    status = "Strong" if not constraints else "Conditional"

    # Ensure currency is normalized in output as well
    fin_out = payload.financials_2y
    try:
        fin_dump = fin_out.model_dump()  # pydantic v2
        fin_dump["currency"] = _norm_currency(fin_dump.get("currency"))
        fin_out = fin_out.__class__.model_validate(fin_dump)  # re-validate same model
    except Exception:
        pass

    # Deterministic banker-grade signals
    signals = _compute_financial_signals_2y(fin_out)

    return DealSummaryResponse(
        client_name=payload.client_name,
        group_name=payload.group_name,
        sector=payload.sector,
        rating_anchor=payload.rating_anchor,
        eligibility=payload.eligibility,
        financials_2y=fin_out,
        indicative_raroc_pct=payload.indicative_raroc_pct,
        deal_readiness={"status": status, "strengths": strengths, "constraints": constraints},
        mandate_fit_summary=f"{payload.client_name} assessed as {status}.",
        financial_signals=signals,
        rm_actions=rm_actions,
        talking_points=talking_points,
        created_at=date.today(),
        notes=payload.notes,
    )


# =========================
# Payload compatibility
# =========================
SECTOR_MAP = {
    "advanced technology": "Advanced Technology",
    "advanced tech": "Advanced Technology",
    "food security": "Food Security",
    "manufacturing": "Manufacturing",
    "healthcare": "Healthcare",
    "renewables": "Renewables",
}


def _norm_sector(v: str) -> str:
    if not v:
        return "Other"
    return SECTOR_MAP.get(v.strip().lower(), v)


def _norm_drivers(v):
    if v is None:
        return None
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        return [x.strip() for x in v.split(",") if x.strip()]
    return None


def _coerce_to_deal_input(raw: Dict[str, Any]) -> DealInputRequest:
    """
    Supports:
    A) NEW nested payload (frontend sends DealInputRequest shape):
       {
         client_name, group_name, sector,
         rating_anchor:{...}, eligibility:{...},
         financials_2y:{...},
         indicative_raroc_pct, notes
       }

    B) Legacy flat payload:
       { client_name, sector/strategic_sector, rating_system, rating_grade, ... }

    NOTE:
    - Legacy "financial_signals" is intentionally NOT supported anymore.
      Frontend must send "financials_2y".
    """

    # ---- Case A: already nested with financials_2y (new schema) ----
    if (
        isinstance(raw.get("rating_anchor"), dict)
        and isinstance(raw.get("eligibility"), dict)
        and isinstance(raw.get("financials_2y"), dict)
    ):
        nested = dict(raw)
        nested["sector"] = _norm_sector(str(nested.get("sector") or "Other"))

        fin = dict(nested.get("financials_2y") or {})
        fin["currency"] = _norm_currency(fin.get("currency"))
        nested["financials_2y"] = fin

        return DealInputRequest.model_validate(nested)

    # ---- Case B: legacy/flat payload ----
    flat = raw

    coerced = {
        "client_name": _get_any(flat, "client_name", default=""),
        "group_name": _get_any(flat, "group_name"),
        "sector": _norm_sector(_get_any(flat, "strategic_sector", "sector", default="")),
        "rating_anchor": {
            "system": _get_any(flat, "rating_system", default=""),
            "grade": str(_get_any(flat, "rating_grade", default="")),
            "outlook": _get_any(flat, "outlook"),
            "as_of": _get_any(flat, "as_of"),
        },
        "eligibility": {
            "score": float(_get_any(flat, "eligibility_score", default=0.0) or 0.0),
            "drivers": _norm_drivers(_get_any(flat, "eligibility_drivers")) or [],
        },
        "financials_2y": {
            "period_labels": ("FY-1", "FY-2"),
            "currency": _norm_currency(None),
            "confidence": "Low",
            "revenue": (None, None),
            "cogs": (None, None),
            "gross_profit": (None, None),
            "net_profit": (None, None),
            "total_assets": (None, None),
            "total_equity": (None, None),
            "ebitda": (None, None),
            "interest_on_loans": (None, None),
            "cpltd": (None, None),
            "dscr": (None, None),
            "operating_cashflow": (None, None),
            "notes": ["Legacy flat payload mapped to financials_2y placeholder."],
        },
        "indicative_raroc_pct": _get_any(flat, "indicative_raroc_pct"),
        "notes": _get_any(flat, "notes"),
    }

    return DealInputRequest.model_validate(coerced)


# =========================
# Credit Application (HYBRID for MVP)
# =========================
class CreditApplicationRequest(BaseModel):
    rm_inputs: Dict[str, Any]
    financials_2y: Dict[str, Any]
    parse_meta: Optional[Dict[str, Any]] = None


class CreditApplicationResponse(BaseModel):
    credit_application_text: str
    source: str


def _fmt_num(x: Optional[float]) -> str:
    if x is None:
        return "N/A"
    try:
        return f"{x:,.0f}"
    except Exception:
        return str(x)


def _pct(n: Optional[float], d: Optional[float]) -> Optional[float]:
    if n is None or d is None or d == 0:
        return None
    try:
        return round((n / d) * 100.0, 1)
    except Exception:
        return None


def _get2(arr: Any) -> List[Optional[float]]:
    if isinstance(arr, list) and len(arr) >= 2:
        return [_coerce_float(arr[0]), _coerce_float(arr[1])]
    return [None, None]


def _compute_gross_profit_if_missing(
    rev: List[Optional[float]],
    gp: List[Optional[float]],
    cogs: List[Optional[float]],
) -> List[Optional[float]]:
    out = [gp[0], gp[1]]
    for i in range(2):
        if out[i] is None and rev[i] is not None and cogs[i] is not None:
            out[i] = rev[i] - cogs[i]
    return out


def _build_hybrid_credit_text(
    rm_inputs: Dict[str, Any],
    fin: Dict[str, Any],
    parse_meta: Optional[Dict[str, Any]],
) -> str:
    # -------------------------
    # Safe unpack (RM inputs)
    # -------------------------
    client = str(rm_inputs.get("client_name") or "").strip() or "Client"
    group = str(rm_inputs.get("group_name") or "").strip() or None
    sector = str(rm_inputs.get("sector") or "").strip() or "N/A"

    rating = rm_inputs.get("rating_anchor") or {}
    rating_sys = str(rating.get("system") or "N/A")
    rating_grade = str(rating.get("grade") or "N/A")
    outlook = str(rating.get("outlook") or "N/A")
    as_of = str(rating.get("as_of") or "N/A")

    elig = rm_inputs.get("eligibility") or {}
    elig_score = elig.get("score")
    elig_drivers = elig.get("drivers") or []
    if isinstance(elig_drivers, str):
        elig_drivers = [x.strip() for x in elig_drivers.split(",") if x.strip()]
    if not isinstance(elig_drivers, list):
        elig_drivers = []

    raroc = rm_inputs.get("indicative_raroc_pct")
    notes = str(rm_inputs.get("notes") or "").strip()

    # -------------------------
    # Safe unpack (Financials)
    # -------------------------
    fin = dict(fin or {})
    period_labels = fin.get("period_labels") or ["FY-1", "FY-2"]
    p1, p2 = (list(period_labels) + ["FY-1", "FY-2"])[:2]  # p1 latest, p2 prior
    currency = _norm_currency(fin.get("currency"))

    rev = _get2(fin.get("revenue"))
    cogs = _get2(fin.get("cogs"))
    gp = _get2(fin.get("gross_profit"))
    np = _get2(fin.get("net_profit"))
    ebitda = _get2(fin.get("ebitda"))

    assets = _get2(fin.get("total_assets"))
    equity = _get2(fin.get("total_equity"))

    interest = _get2(fin.get("interest_on_loans"))
    cpltd = _get2(fin.get("cpltd"))
    dscr = _get2(fin.get("dscr"))

    # Ensure GP is present if Rev/COGS exist
    gp = _compute_gross_profit_if_missing(rev, gp, cogs)

    gm1 = _pct(gp[0], rev[0])
    gm2 = _pct(gp[1], rev[1])
    npm1 = _pct(np[0], rev[0])
    npm2 = _pct(np[1], rev[1])

    conf = str(fin.get("confidence") or "N/A")
    src = str(fin.get("source") or "AI/Regex extraction")

    # -------------------------
    # Parse meta line (optional)
    # -------------------------
    meta_line = ""
    if parse_meta:
        meta_line = (
            f"Source file: {parse_meta.get('filename','N/A')} | "
            f"Pages scanned: {parse_meta.get('pages_scanned','N/A')} | "
            f"Tables found: {parse_meta.get('tables_found','N/A')}"
        )

    # -------------------------
    # Deterministic helpers
    # -------------------------
    def _fmt_pct(x: Optional[float]) -> str:
        return f"{x:.2f}%" if x is not None else "N/A"

    def _trend(cur: Optional[float], prev: Optional[float], label: str) -> str:
        if cur is None or prev is None:
            return f"{label}: N/A (insufficient data)."
        if prev == 0:
            return f"{label}: N/A (prior period is zero)."
        chg = ((cur - prev) / abs(prev)) * 100.0
        if chg > 0:
            return f"{label} increased YoY ({chg:.2f}%)."
        if chg < 0:
            return f"{label} declined YoY ({chg:.2f}%)."
        return f"{label} was flat YoY (0.00%)."

    def _margin_trend(cur: Optional[float], prev: Optional[float], label: str) -> str:
        if cur is None or prev is None:
            return f"{label}: N/A (insufficient data)."
        if cur > prev:
            return f"{label} expanded versus prior period."
        if cur < prev:
            return f"{label} compressed versus prior period."
        return f"{label} was broadly stable versus prior period."

    def _dscr_view(d0: Optional[float]) -> str:
        if d0 is None:
            return "DSCR: N/A (missing inputs)."
        try:
            x = float(d0)
        except Exception:
            return "DSCR: N/A (invalid value)."
        if x >= 1.20:
            return f"DSCR: {x:.2f}x (adequate coverage in latest period)."
        if x >= 1.00:
            return f"DSCR: {x:.2f}x (marginal; structuring/monitoring focus)."
        return f"DSCR: {x:.2f}x (below 1.0x; insufficient internal coverage)."

    def _data_quality_flags() -> List[str]:
        flags: List[str] = []
        if conf in {"Low", "Medium"}:
            flags.append(f"Data confidence: {conf} (validate against audited statements).")
        # Missing core P&L visibility
        if rev[0] is None or ebitda[0] is None or np[0] is None:
            flags.append("Key P&L line items missing for latest period (limited visibility).")
        # DSCR computed but weak
        if dscr[0] is not None:
            try:
                if float(dscr[0]) < 1.0:
                    flags.append("Debt service coverage weak in latest period (DSCR < 1.0x).")
            except Exception:
                flags.append("DSCR value present but not parseable (validate).")
        return flags

    def _credit_conclusion() -> List[str]:
        """
        Deterministic posture based strictly on:
        - DSCR (if available)
        - Data confidence / completeness
        - No new facts introduced
        """
        flags = _data_quality_flags()

        posture = "NEUTRAL"
        rationale: List[str] = []

        d0 = None
        try:
            d0 = float(dscr[0]) if dscr[0] is not None else None
        except Exception:
            d0 = None

        # Base posture primarily on DSCR if available
        if d0 is None:
            posture = "SUPPORT WITH CONDITIONS"
            rationale.append("DSCR unavailable; conclusion contingent on validating cashflow and debt service.")
        elif d0 >= 1.20:
            posture = "SUPPORT"
            rationale.append("Latest-period deterministic DSCR at/above a typical 1.2x comfort threshold.")
        elif d0 >= 1.00:
            posture = "SUPPORT WITH CONDITIONS"
            rationale.append("Latest-period deterministic DSCR is marginal (1.0x–1.2x).")
        else:
            posture = "CAUTION / NOT SUPPORT (AS PRESENTED)"
            rationale.append("Latest-period deterministic DSCR below 1.0x indicates insufficient internal coverage.")

        # Escalate caution if data quality is weak
        if conf in {"Low", "Medium"}:
            if posture == "SUPPORT":
                posture = "SUPPORT WITH CONDITIONS"
                rationale.append("Extraction confidence is not high; validate numbers before reliance.")
            elif posture in {"SUPPORT WITH CONDITIONS"}:
                rationale.append("Elevated extraction uncertainty increases execution / model risk.")
            else:
                rationale.append("Low/Medium extraction confidence reinforces the need to validate source data.")

        if (rev[0] is None or ebitda[0] is None) and posture == "SUPPORT":
            posture = "SUPPORT WITH CONDITIONS"
            rationale.append("Missing core operating metrics in latest period; complete dataset required.")

        lines: List[str] = []
        lines.append(f"Posture: {posture}.")
        for r in rationale:
            lines.append(f"- {r}")
        if flags:
            lines.append("Conditions / focus areas (data-driven):")
            for f in flags:
                lines.append(f"- {f}")
        return lines

    # -------------------------
    # Output (banker-grade, deterministic)
    # -------------------------
    lines: List[str] = []

    # 1) EXECUTIVE SUMMARY (tight)
    lines.append("EXECUTIVE SUMMARY")
    header = f"{client}" + (f" (Group: {group})" if group else "")
    lines.append(f"{header} | Sector: {sector}.")
    lines.append("Key points (deterministic):")

    # Ratings / eligibility
    lines.append(f"- Rating anchor: {rating_sys} | Grade: {rating_grade} | Outlook: {outlook} | As-of: {as_of}.")
    if elig_score is not None:
        try:
            es = f"{float(elig_score):.1f}/6"
        except Exception:
            es = f"{elig_score}/6"
        drv = f" (drivers: {', '.join([str(x) for x in elig_drivers])})" if elig_drivers else ""
        lines.append(f"- Eligibility: {es}{drv}.")
    else:
        lines.append("- Eligibility: N/A (RM input missing).")

    lines.append(f"- Periods / currency: {p1} (latest) and {p2} (prior), {currency}.")
    lines.append(f"- {_trend(rev[0], rev[1], 'Revenue')}")
    lines.append(f"- {_trend(ebitda[0], ebitda[1], 'EBITDA')}")
    lines.append(f"- {_trend(np[0], np[1], 'Net profit')}")
    lines.append(f"- {_margin_trend(gm1, gm2, 'Gross margin')} ({_fmt_pct(gm1)} vs {_fmt_pct(gm2)}).")
    lines.append(f"- {_dscr_view(dscr[0])}")

    if raroc is not None:
        lines.append(f"- Indicative RAROC (RM input): {raroc}%.")
    else:
        lines.append("- Indicative RAROC (RM input): N/A.")

    if notes:
        lines.append(f"RM notes: {notes}")
    lines.append("")

    # 2) BUSINESS OVERVIEW (still deterministic placeholder, but cleaner)
    lines.append("BUSINESS OVERVIEW")
    lines.append("To be completed from RM inputs and due diligence (MVP placeholder; no inferred narrative).")
    lines.append("")

    # 3) FINANCIAL PERFORMANCE (2-YEAR)
    lines.append("FINANCIAL PERFORMANCE (2-YEAR)")
    lines.append(f"Currency: {currency}. Periods: {p1} (latest) and {p2} (prior).")
    if meta_line:
        lines.append(meta_line)
    lines.append("")

    lines.append("Commentary (deterministic)")
    lines.append(f"- {_trend(rev[0], rev[1], 'Revenue')}")
    lines.append(f"- {_trend(gp[0], gp[1], 'Gross profit')}")
    lines.append(f"- {_trend(ebitda[0], ebitda[1], 'EBITDA')}")
    lines.append(f"- {_trend(np[0], np[1], 'Net profit')}")
    lines.append(f"- {_margin_trend(gm1, gm2, 'Gross margin')}")
    lines.append(f"- {_margin_trend(npm1, npm2, 'Net margin')}")
    lines.append(f"- {_dscr_view(dscr[0])}")
    lines.append("")

    lines.append("Appendix — extracted figures (2Y)")
    lines.append(f"- Revenue: {p1} {_fmt_num(rev[0])} | {p2} {_fmt_num(rev[1])}")
    lines.append(f"- COGS: {p1} {_fmt_num(cogs[0])} | {p2} {_fmt_num(cogs[1])}")
    lines.append(f"- Gross profit: {p1} {_fmt_num(gp[0])} | {p2} {_fmt_num(gp[1])}")
    lines.append(f"- Gross margin: {p1} {_fmt_pct(gm1)} | {p2} {_fmt_pct(gm2)}")
    lines.append(f"- EBITDA: {p1} {_fmt_num(ebitda[0])} | {p2} {_fmt_num(ebitda[1])}")
    lines.append(f"- Net profit: {p1} {_fmt_num(np[0])} | {p2} {_fmt_num(np[1])}")
    lines.append(f"- Net margin: {p1} {_fmt_pct(npm1)} | {p2} {_fmt_pct(npm2)}")
    lines.append(
        f"- Interest (loans): {p1} {_fmt_num(abs(interest[0]) if interest[0] is not None else None)} | "
        f"{p2} {_fmt_num(abs(interest[1]) if interest[1] is not None else None)}"
    )
    lines.append(f"- CPLTD: {p1} {_fmt_num(cpltd[0])} | {p2} {_fmt_num(cpltd[1])}")
    lines.append(
        f"- DSCR (deterministic): {p1} {(f'{float(dscr[0]):.2f}x' if dscr[0] is not None else 'N/A')} | "
        f"{p2} {(f'{float(dscr[1]):.2f}x' if dscr[1] is not None else 'N/A')}"
    )
    lines.append("")

    # 4) KEY RISKS (data-driven only)
    lines.append("KEY RISKS (DATA-DRIVEN)")
    dq = _data_quality_flags()
    if dq:
        for f in dq:
            lines.append(f"- {f}")
    else:
        lines.append("- N/A (no data-driven risk flags triggered under MVP rules).")
    lines.append("")

    # 5) CREDIT CONCLUSION (deterministic posture)
    lines.append("CREDIT CONCLUSION (DETERMINISTIC)")
    lines.extend(_credit_conclusion())
    lines.append("")

    # 6) DISCLAIMER
    lines.append("DISCLAIMER")
    lines.append(
        "Decision-support output for internal use only. Figures are best-effort extracted and may be incomplete or inaccurate; "
        "validate against audited financial statements and source documents prior to Credit Committee submission."
    )

    return "\n".join(lines).strip()

# =========================
# Endpoints
# =========================
@app.post("/financials/parse-pdf")
async def parse_pdf(file: UploadFile = File(...)):
    filename = file.filename or "uploaded.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file received.")

    MAX_BYTES = 10 * 1024 * 1024  # 10 MB
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="PDF too large. Please upload a PDF under 10MB.")

    try:
        import pdfplumber  # type: ignore
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="pdfplumber not installed. Add it to api/requirements.txt and redeploy.",
        )

    text_parts: List[str] = []
    tables_found = 0
    pages_scanned = 0

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        pages_scanned = min(len(pdf.pages), 3)  # limit to first 3 pages
        for i in range(pages_scanned):
            page = pdf.pages[i]
            txt = (page.extract_text() or "").strip()
            if txt:
                text_parts.append(f"[Page {i+1}]\n{txt}")

            try:
                tables = page.extract_tables() or []
                for t in tables:
                    if t and any(any(cell for cell in row) for row in t):
                        tables_found += 1
            except Exception:
                pass

    text_full = "\n\n".join(text_parts).strip()

    # Cap for MVP to avoid huge payloads
    MAX_TEXT_CHARS = 25000
    text = text_full[:MAX_TEXT_CHARS]
    if len(text_full) > MAX_TEXT_CHARS:
        text += "\n... (truncated to 25k chars)"

    # Preview for UI
    text_preview = text
    if len(text_preview) > 6000:
        text_preview = text_preview[:6000] + "\n... (preview truncated)"

    return {
        "filename": filename,
        "pages_scanned": pages_scanned,
        "tables_found": tables_found,
        "text": text,
        "text_preview": text_preview,
        "note": (
            "PDF extraction is best-effort. If this PDF is scanned, text may be empty. "
            "For reliable parsing, use Excel/CSV."
        ),
    }


@app.post("/financials/infer-2y")
def infer_financials_2y(payload: Dict[str, Any]):
    """
    MVP objective:
    - Extract two-year values from statements
    - Compute DSCR deterministically:
        DSCR = EBITDA / (CPLTD + abs(Interest on loans))
    """
    text = (payload.get("text") or "").strip()
    currency_hint = _norm_currency(payload.get("currency_hint"))

    if not text:
        raise HTTPException(status_code=400, detail="No extracted text provided.")

    _guard_no_sensitive(text)

    # If AI disabled: fallback extraction
    if oa_client is None:
        out = _fallback_infer_2y_from_text(text, currency_hint)
        out["debug"] = dict(out.get("debug") or {})
        out["debug"]["pid"] = os.getpid()
        out["debug"]["oa_client_ready"] = False
        out["debug"]["ai_enabled_flag"] = AI_ENABLED
        out["debug"]["openai_key_present"] = bool(OPENAI_API_KEY)
        out["debug"]["model"] = MODEL_NAME
        return out

    prompt = f"""
You are a senior wholesale credit analyst extracting inputs from financial statements.

Task:
From the text, extract TWO YEAR values (FY-1, FY-2) for:

INCOME STATEMENT:
1) Revenue / Sales (amount)
2) COGS / Cost of Goods Sold / Cost of Sales (amount) if explicitly stated; otherwise null
3) Gross Profit: if not explicitly stated, return null (we will compute it in backend if Rev and COGS exist)
4) Net Profit / Profit after tax / PAT (amount)

BALANCE SHEET ANCHORS:
5) Total Assets (amount)
6) Total Equity (amount)

DEBT SERVICE:
7) EBITDA (amount)
8) Interest on loans / borrowing-related finance cost (amount)
9) Current Portion of Long-term Debt (CPLTD) / current maturities of long-term borrowings (amount)

Return STRICT JSON ONLY in the following shape (no extra keys, no commentary outside JSON):

{{
  "period_labels": ["FY-1", "FY-2"],
  "currency": "{currency_hint}",

  "revenue": [number|null, number|null],
  "cogs": [number|null, number|null],
  "gross_profit": [number|null, number|null],
  "net_profit": [number|null, number|null],

  "total_assets": [number|null, number|null],
  "total_equity": [number|null, number|null],

  "ebitda": [number|null, number|null],
  "interest_on_loans": [number|null, number|null],
  "cpltd": [number|null, number|null],

  "confidence": "Low" | "Medium" | "High",
  "notes": ["short bullets on where each number came from or what's missing"]
}}

Rules:
- Use ONLY what is present in the text. If unclear, return null.
- Do NOT fabricate or derive numbers unless explicitly stated.
- EBITDA: prefer explicitly stated "EBITDA". If not stated, do NOT derive unless BOTH EBIT and Depreciation/Amortization are clearly stated for the same year.
- Interest: include interest on borrowings/loans; if only total finance cost is shown, use it and note it may include leases.
- CPLTD: must come from balance sheet/notes (current portion/current maturities of long-term debt/borrowings).
- Do not do DSCR calculation.
- Numbers: return plain numbers (no commas). Preserve sign if shown.

Extracted text:
{text}
""".strip()

    try:
        resp = oa_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a conservative credit analyst. "
                        "Never fabricate numbers. "
                        "Return STRICT JSON only, no markdown."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )

        content = (resp.choices[0].message.content or "").strip()
        obj = _safe_json_loads(content)

        if obj is None:
            fix_prompt = f"""
The following was not valid JSON. Output valid STRICT JSON ONLY matching the required schema and using the same values.

Bad output:
{content}
""".strip()
            resp2 = oa_client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": "Fix JSON formatting only. Return STRICT JSON only."},
                    {"role": "user", "content": fix_prompt},
                ],
            )
            content2 = (resp2.choices[0].message.content or "").strip()
            obj = _safe_json_loads(content2)

        if obj is None:
            raise HTTPException(status_code=500, detail="AI response could not be parsed as JSON.")

        revenue = _coerce_2y_array(obj.get("revenue"))
        cogs = _coerce_2y_array(obj.get("cogs"))
        gross_profit = _coerce_2y_array(obj.get("gross_profit"))
        net_profit = _coerce_2y_array(obj.get("net_profit"))
        total_assets = _coerce_2y_array(obj.get("total_assets"))
        total_equity = _coerce_2y_array(obj.get("total_equity"))

        ebitda = _coerce_2y_array(obj.get("ebitda"))
        interest = _coerce_2y_array(obj.get("interest_on_loans"))
        cpltd = _coerce_2y_array(obj.get("cpltd"))
        dscr = _compute_dscr_2y(ebitda, cpltd, interest)

        # If GP not provided, compute when Rev and COGS exist
        if gross_profit == [None, None]:
            gp0 = (revenue[0] - cogs[0]) if (revenue[0] is not None and cogs[0] is not None) else None
            gp1 = (revenue[1] - cogs[1]) if (revenue[1] is not None and cogs[1] is not None) else None
            gross_profit = [gp0, gp1]

        conf = str(obj.get("confidence") or "Low").strip()
        if conf not in {"Low", "Medium", "High"}:
            conf = "Low"

        core = revenue + cogs + gross_profit + net_profit + total_assets + total_equity + ebitda + interest + cpltd
        missing = sum(x is None for x in core)
        if missing >= 7:
            conf = "Low"
        elif missing >= 3 and conf == "High":
            conf = "Medium"

        notes = obj.get("notes") or []
        if not isinstance(notes, list):
            notes = [str(notes)]
        notes.append("DSCR computed deterministically as EBITDA / (CPLTD + abs(Interest on loans)).")

        financials_2y = {
            "period_labels": ["FY-1", "FY-2"],
            "currency": str(obj.get("currency") or currency_hint),
            "confidence": conf,
            "revenue": revenue,
            "cogs": cogs,
            "gross_profit": gross_profit,
            "net_profit": net_profit,
            "total_assets": total_assets,
            "total_equity": total_equity,
            "ebitda": ebitda,
            "interest_on_loans": interest,
            "cpltd": cpltd,
            "dscr": dscr,
            "ebitda_margin_pct": [None, None],
            "leverage_netdebt_to_ebitda": [None, None],
            "operating_cashflow": [None, None],
            "notes": notes[:12],
            "source": "AI/Regex extraction",
        }

        return {
            "financials_2y": financials_2y,
            "source": "AI-extracted inputs + deterministic DSCR",
            "debug": {
                "revenue": revenue,
                "cogs": cogs,
                "gross_profit": gross_profit,
                "net_profit": net_profit,
                "total_assets": total_assets,
                "total_equity": total_equity,
                "ebitda": ebitda,
                "interest_on_loans": interest,
                "cpltd": cpltd,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        msg = str(e)

        if ("insufficient_quota" in msg) or ("You exceeded your current quota" in msg) or ("429" in msg):
            if not ALLOW_FALLBACK:
                raise HTTPException(
                    status_code=503,
                    detail="OpenAI quota exceeded or unavailable. Enable ALLOW_FALLBACK or fix billing.",
                )

            out = _fallback_infer_2y_from_text(text, currency_hint)
            out["debug"] = dict(out.get("debug") or {})
            out["debug"]["pid"] = os.getpid()
            out["debug"]["fallback_reason"] = "openai_429_or_quota"
            out["debug"]["openai_error"] = msg[:200]
            out["debug"]["model"] = MODEL_NAME
            return out

        raise HTTPException(status_code=500, detail=f"Inference failed: {msg}")


@app.post("/assess", response_model=DealSummaryResponse)
def assess_deal(payload: Dict[str, Any]):
    if isinstance(payload, dict) and "financial_signals" in payload:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", "financial_signals"],
                    "msg": "Legacy field 'financial_signals' is not supported. Send 'financials_2y' (DealInputRequest schema).",
                    "type": "value_error.legacy_field",
                }
            ],
        )

    try:
        deal_input = _coerce_to_deal_input(payload)
    except ValidationError as e:
        cleaned = []
        for err in e.errors():
            err = dict(err)
            err.pop("ctx", None)
            cleaned.append(err)
        raise HTTPException(status_code=422, detail=cleaned)

    return _assess_deal(deal_input)


# =========================
# Step 3 (HYBRID) endpoint used by your UI
# =========================
@app.post("/ai/credit-application", response_model=CreditApplicationResponse)
def ai_credit_application_hybrid(req: CreditApplicationRequest):
    rm_inputs = req.rm_inputs or {}
    fin = req.financials_2y or {}
    parse_meta = req.parse_meta

    _guard_no_sensitive(
        str(rm_inputs.get("client_name") or ""),
        str(rm_inputs.get("group_name") or ""),
        str(rm_inputs.get("notes") or ""),
    )

    # Normalize currency (MVP rule)
    fin = dict(fin)
    fin["currency"] = _norm_currency(fin.get("currency"))

    fin.setdefault("period_labels", ["FY-1", "FY-2"])

    # Always build deterministic hybrid draft
    draft = _build_hybrid_credit_text(rm_inputs, fin, parse_meta)

    # ---------- AI OFF ----------
    if oa_client is None:
        return CreditApplicationResponse(
            credit_application_text=draft,
            source="Deterministic template (AI disabled)",
        )

    # ---------- AI ON (POLISH ONLY) ----------
    prompt = f"""
You are a senior corporate credit analyst writing for Credit Committee.

Rewrite the draft below into a concise, judge-friendly credit note.

Rules:
- Do NOT add, infer, or change any numbers.
- Do NOT introduce new facts beyond what is in the draft.
- If something is N/A, keep it as N/A.
- Do NOT repeat the input fields verbatim.
- Convert numbers into insight and implications.

Output format (exact headings):
1) Executive Summary (5–8 bullets)
2) Financial Snapshot (2–3 short paragraphs)
3) Key Risks and Mitigants (3–5 bullets)
4) Recommendation (1 paragraph)

Draft:
{draft}
""".strip()

    try:
        resp = oa_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "Return plain text only. Do not fabricate facts or numbers."},
                {"role": "user", "content": prompt},
            ],
        )
        polished = (resp.choices[0].message.content or "").strip()

        return CreditApplicationResponse(
            credit_application_text=polished or draft,
            source="AI-polished (facts constrained to extracted data)",
        )

    except Exception:
        return CreditApplicationResponse(
            credit_application_text=draft,
            source="Deterministic template (AI fallback)",
        )

# =========================
# Step 3 (optional) credit-application from deal summary
# Renamed to avoid route collision with /ai/credit-application
# =========================
class AICreditApplicationRequest(BaseModel):
    deal_summary: DealSummaryResponse


class AICreditApplicationResponse(BaseModel):
    credit_application_text: str
    disclaimer: str


@app.post("/ai/credit-application-from-summary", response_model=AICreditApplicationResponse)
def ai_credit_application_from_summary(req: AICreditApplicationRequest):
    """
    Optional: generate a fuller narrative using ONLY DealSummaryResponse.
    Kept separate from the MVP Hybrid endpoint to avoid route collisions.
    """
    deal = req.deal_summary
    _guard_no_sensitive(deal.client_name, deal.group_name or "", deal.notes or "")

    # If AI is OFF: deterministic professional template
    if oa_client is None:
        fin = getattr(deal, "financials_2y", None)
        p0 = fin.period_labels[0] if fin and fin.period_labels else "FY-1"
        p1 = fin.period_labels[1] if fin and fin.period_labels else "FY-2"

        def _v(arr, i):
            try:
                return arr[i]
            except Exception:
                return None

        text = f"""CREDIT APPLICATION – CREDIT COMMITTEE (DRAFT)

1. Applicant / Group
- Client: {deal.client_name}
- Group: {deal.group_name or "N/A"}
- Sector: {deal.sector}

2. Rating & Policy Anchors
- Rating system: {deal.rating_anchor.system}
- Rating grade: {deal.rating_anchor.grade}
- Outlook: {deal.rating_anchor.outlook or "N/A"} | As of: {deal.rating_anchor.as_of or "N/A"}
- Eligibility score: {deal.eligibility.score:.1f}/6
- Eligibility drivers: {", ".join(deal.eligibility.drivers) if deal.eligibility.drivers else "N/A"}
- Indicative RAROC: {deal.indicative_raroc_pct if deal.indicative_raroc_pct is not None else "N/A"}%

3. Financial Performance (2Y)
- Periods: {p0}, {p1}
- Revenue: {_v(getattr(fin, "revenue", [None, None]), 0)} / {_v(getattr(fin, "revenue", [None, None]), 1)}
- Gross Profit: {_v(getattr(fin, "gross_profit", [None, None]), 0)} / {_v(getattr(fin, "gross_profit", [None, None]), 1)}
- EBITDA: {_v(getattr(fin, "ebitda", [None, None]), 0)} / {_v(getattr(fin, "ebitda", [None, None]), 1)}
- Net Profit: {_v(getattr(fin, "net_profit", [None, None]), 0)} / {_v(getattr(fin, "net_profit", [None, None]), 1)}
- Total Assets: {_v(getattr(fin, "total_assets", [None, None]), 0)} / {_v(getattr(fin, "total_assets", [None, None]), 1)}
- Total Equity: {_v(getattr(fin, "total_equity", [None, None]), 0)} / {_v(getattr(fin, "total_equity", [None, None]), 1)}
- DSCR: {_v(getattr(fin, "dscr", [None, None]), 0)}x / {_v(getattr(fin, "dscr", [None, None]), 1)}x

4. Key Credit Observations
- Deal readiness status: {deal.deal_readiness.status}
- Strengths: {("; ".join(deal.deal_readiness.strengths[:5]) if deal.deal_readiness and deal.deal_readiness.strengths else "N/A")}
- Constraints: {("; ".join(deal.deal_readiness.constraints[:5]) if deal.deal_readiness and deal.deal_readiness.constraints else "N/A")}

5. RM Actions / Next Steps
{chr(10).join([f"- {x}" for x in (deal.rm_actions or [])][:8]) if deal.rm_actions else "- N/A"}

Disclaimer: Decision-support only. Validate independently before submission.
"""
        return AICreditApplicationResponse(
            credit_application_text=text.strip(),
            disclaimer="Decision-support only. Validate independently before submission.",
        )

    # AI path
    try:
        prompt = f"""
You are a senior corporate credit analyst writing a Credit Committee credit application.

Write a professional credit application using ONLY the deal summary provided. Do not invent facts.

Required structure:
1) Executive summary (credit committee tone)
2) Financial performance (2-year): revenue, profitability, margins, DSCR commentary (only if numbers exist)
3) Balance sheet anchors: total assets and total equity commentary (high level; no invented ratios)
4) Rating & eligibility: interpret the rating anchor + eligibility inputs
5) Key risks and mitigants: concise bullets
6) Committee-ready recommendation language: neutral phrasing (no approval guarantee)

Return STRICT JSON ONLY:
{{
  "credit_application_text": "string"
}}

Deal summary:
{deal.model_dump_json(indent=2)}
""".strip()

        resp = oa_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a conservative credit analyst. "
                        "Do not invent facts. Use only the deal summary. "
                        "Write in Credit Committee style. Return STRICT JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )

        content = (resp.choices[0].message.content or "").strip()
        obj = _safe_json_loads(content)
        if obj is None or not isinstance(obj.get("credit_application_text"), str):
            raise ValueError("AI returned invalid JSON for credit application.")

        return AICreditApplicationResponse(
            credit_application_text=obj["credit_application_text"].strip(),
            disclaimer="Decision-support only. Validate independently before submission.",
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Credit application generation failed.")


@app.post("/ai/explain", response_model=AIExplainResponse)
def ai_explain(req: AIExplainRequest):
    deal = req.deal_summary
    _guard_no_sensitive(deal.client_name, deal.group_name or "", deal.notes or "")

    dr = deal.deal_readiness
    constraints = list(dr.constraints) if dr and getattr(dr, "constraints", None) else []
    strengths = list(dr.strengths) if dr and getattr(dr, "strengths", None) else []
    rm_actions = list(deal.rm_actions or [])
    talking = list(deal.talking_points or [])

    if oa_client is None:
        exec_sum = deal.mandate_fit_summary or ""
        if strengths:
            exec_sum += ("\nStrengths: " + "; ".join(strengths[:3]))
        if constraints:
            exec_sum += ("\nConstraints: " + "; ".join(constraints[:3]))
        return AIExplainResponse(
            executive_summary=exec_sum.strip(),
            key_risks_explained=constraints[:10],
            rm_talking_points=(rm_actions[:6] or talking[:6]),
            disclaimer="Decision-support only. Validate independently before submission.",
        )

    try:
        prompt = f"""
Using ONLY the deal summary below, produce a structured analyst explanation.

Rules:
- Do NOT repeat the assessment bullets verbatim.
- Explain causality: why each constraint matters and what it implies for risk/structure.
- Do NOT give a final Proceed/Decline recommendation.
- If information is missing, explicitly state it in the narrative (do not invent facts).

Return STRICT JSON with keys:
executive_summary (string),
key_risks_explained (list of strings),
rm_talking_points (list of strings)

Deal summary:
{deal.model_dump_json(indent=2)}
""".strip()

        resp = oa_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior credit analyst writing an internal note. "
                        "Be critical and specific. Link screening outputs "
                        "to credit risk, headroom, and concrete structuring levers. "
                        "Do NOT invent facts beyond the deal summary. "
                        "Return STRICT JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )

        content = (resp.choices[0].message.content or "").strip()
        obj = _safe_json_loads(content) if content else None
        if obj is None:
            raise ValueError("AI returned non-JSON or invalid JSON.")

        risks = [str(x).strip() for x in (obj.get("key_risks_explained") or []) if str(x).strip()]
        tps = [str(x).strip() for x in (obj.get("rm_talking_points") or []) if str(x).strip()]

        return AIExplainResponse(
            executive_summary=str(obj.get("executive_summary", "")).strip(),
            key_risks_explained=risks[:10],
            rm_talking_points=tps[:10],
            disclaimer="Decision-support only. Validate independently before submission.",
        )

    except Exception:
        exec_sum = deal.mandate_fit_summary or ""
        return AIExplainResponse(
            executive_summary=exec_sum.strip(),
            key_risks_explained=constraints[:10],
            rm_talking_points=(rm_actions[:6] or talking[:6]),
            disclaimer="Decision-support only. Validate independently before submission.",
        )


def _is_go_nogo_question(q: str) -> bool:
    q = (q or "").lower()
    return any(
        x in q
        for x in [
            "proceed",
            "decline",
            "go/no-go",
            "go no go",
            "walk away",
            "approve",
            "reject",
            "proceed or decline",
            "go or no go",
            "go/no go",
            "go/no-go decision",
            "go no-go",
            "go no-go?",
        ]
    )


def _dscr_both_years_below(deal, threshold: float) -> bool:
    try:
        fin = getattr(deal, "financials_2y", None)
        dscr = getattr(fin, "dscr", None)

        if not dscr:
            return False
        if len(dscr) < 2:
            return False

        d1 = dscr[0]
        d2 = dscr[1]

        if d1 is None or d2 is None:
            return False

        return float(d1) < threshold and float(d2) < threshold
    except Exception:
        return False


@app.post("/ai/qa", response_model=AIQAResponse)
def ai_qa(req: AIQARequest):
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required.")

    deal = req.deal_summary
    if deal is None:
        return AIQAResponse(
            decision="N/A",
            rationale=[],
            conditions_next_steps=[],
            answer="Please run an assessment first, then ask your question again.",
            disclaimer="Decision-support only.",
        )

    _guard_no_sensitive(question, deal.client_name, deal.group_name or "", deal.notes or "")

    # ---------- Deterministic credit-policy gate ----------
    if _is_go_nogo_question(question):
        dr = deal.deal_readiness
        status = getattr(dr, "status", None)

        if status == "Weak":
            return AIQAResponse(
                decision="Decline",
                rationale=["Screening status is Weak in the deal summary."],
                conditions_next_steps=["Rework structure and re-run assessment after key gaps are addressed."],
                answer="Decision: Decline\n- Screening status is Weak.",
                disclaimer="Decision-support only.",
            )

        DSCR_FLOOR = 1.20
        if _dscr_both_years_below(deal, DSCR_FLOOR):
            return AIQAResponse(
                decision="Restructure",
                rationale=[f"DSCR is below {DSCR_FLOOR:.2f}x in both years."],
                conditions_next_steps=["Extend tenor, add grace, or strengthen support to restore DSCR."],
                answer=f"Decision: Restructure\n- DSCR below {DSCR_FLOOR:.2f}x in both years.",
                disclaimer="Decision-support only.",
            )
    # ---------- End deterministic gate ----------

    if oa_client is None:
        return AIQAResponse(
            decision="N/A",
            rationale=[],
            conditions_next_steps=[],
            answer="AI is not enabled in this environment.",
            disclaimer="Decision-support only.",
        )

    try:
        prompt = f"""
Question: {question}

If this is a go/no-go question, choose exactly one:
Proceed / Restructure / Decline.

Return STRICT JSON with:
decision, rationale, conditions_next_steps, answer

Deal summary:
{deal.model_dump_json(indent=2)}
""".strip()

        resp = oa_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "Return STRICT JSON only."},
                {"role": "user", "content": prompt},
            ],
        )

        content = (resp.choices[0].message.content or "").strip()
        obj = _safe_json_loads(content)

        if obj is None:
            raise ValueError("Invalid JSON from AI")

        decision = str(obj.get("decision") or "N/A").strip()
        if decision not in {"Proceed", "Restructure", "Decline"}:
            decision = "Restructure" if _is_go_nogo_question(question) else "N/A"

        rationale_raw = obj.get("rationale") or []
        conditions_raw = obj.get("conditions_next_steps") or []

        rationale = [str(x).strip() for x in rationale_raw if str(x).strip()] if isinstance(rationale_raw, list) else []
        conditions = [str(x).strip() for x in conditions_raw if str(x).strip()] if isinstance(conditions_raw, list) else []

        answer = obj.get("answer")
        answer_str = str(answer).strip() if isinstance(answer, (str, int, float)) else ""

        if not answer_str:
            lines = [f"Decision: {decision}"]
            if rationale:
                lines.append("Rationale:")
                lines.extend([f"- {x}" for x in rationale[:5]])
            if conditions:
                lines.append("Conditions / next steps:")
                lines.extend([f"- {x}" for x in conditions[:5]])
            answer_str = "\n".join(lines).strip()

        return AIQAResponse(
            decision=decision,
            rationale=rationale[:5],
            conditions_next_steps=conditions[:5],
            answer=answer_str,
            disclaimer="Decision-support only.",
        )

    except Exception:
        decision = "Restructure" if _is_go_nogo_question(question) else "N/A"
        return AIQAResponse(
            decision=decision,
            rationale=[],
            conditions_next_steps=[],
            answer=f"Decision: {decision}",
            disclaimer="Decision-support only.",
        )


# =========================
# SPA serving
# =========================
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
INDEX_HTML = FRONTEND_DIST / "index.html"
ASSETS_DIR = FRONTEND_DIST / "assets"

if ASSETS_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


@app.get("/.well-known/appspecific/com.chrome.devtools.json", include_in_schema=False)
def chrome_devtools_probe():
    return Response(status_code=204)


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    if INDEX_HTML.is_file():
        return FileResponse(str(INDEX_HTML))
    return JSONResponse({"detail": "Frontend not built"}, status_code=500)

# api/main.py
from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# =========================
# Env
# =========================
REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "").strip()

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

# =========================
# Health
# =========================
@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}


# =========================
# Dropdown meta (optional)
# =========================
@app.get("/meta/dropdowns", include_in_schema=False)
def dropdown_meta():
    return {
        "sectors": ["Manufacturing", "Advanced Technology", "Healthcare", "Food Security", "Renewables", "Other"],
        "outlooks": ["Stable", "Positive", "Negative", "Watch"],
        "trend_3y": ["Improving", "Stable", "Declining"],
        "margin_trend_3y": ["Improving", "Stable", "Under Pressure"],
        "leverage_position": ["Low", "Moderate", "Elevated"],
        "cashflow_quality": ["Strong", "Adequate", "Weak"],
        "earnings_volatility": ["Low", "Moderate", "High"],
        "capex_growth_investment": ["Low", "Moderate", "High"],
        "financial_transparency": ["Strong", "Adequate", "Weak"],
        "rating_systems": ["Credit Lens"],
    }


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
)

# =========================
# OpenAI client (optional)
# =========================
oa_client = None
if OPENAI_API_KEY:
    try:
        from openai import OpenAI  # type: ignore

        oa_client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception:
        oa_client = None

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


# =========================
# Normalisers
# =========================
SECTOR_MAP = {
    "advanced technology": "Advanced Technology",
    "advanced tech": "Advanced Technology",
    "food security": "Food Security",
    "manufacturing": "Manufacturing",
    "healthcare": "Healthcare",
    "renewables": "Renewables",
}

# margin_trend_3y allowed: Improving | Stable | Under Pressure
MARGIN_MAP = {
    "improving": "Improving",
    "stable": "Stable",
    "under pressure": "Under Pressure",
    "deteriorating": "Under Pressure",
    "declining": "Under Pressure",
}

# revenue_trend_3y allowed (commonly): Improving | Stable | Declining
TREND_MAP = {
    "improving": "Improving",
    "stable": "Stable",
    "declining": "Declining",
    "deteriorating": "Declining",
    "under pressure": "Declining",
}

LEVERAGE_MAP = {
    "low": "Low",
    "moderate": "Moderate",
    "elevated": "Elevated",
    "high": "Elevated",
}


def _norm_sector(v: str) -> str:
    if not v:
        return "Other"
    return SECTOR_MAP.get(v.strip().lower(), v)


def _norm_margin(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    return MARGIN_MAP.get(v.strip().lower(), v)


def _norm_trend(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    return TREND_MAP.get(v.strip().lower(), v)


def _norm_leverage(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    return LEVERAGE_MAP.get(v.strip().lower(), v)


def _norm_drivers(v):
    if v is None:
        return None
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        return [x.strip() for x in v.split(",") if x.strip()]
    return None


# =========================
# Payload compatibility
# =========================
def _coerce_to_deal_input(raw: Dict[str, Any]) -> DealInputRequest:
    # --- Case B: nested payload ---
    if isinstance(raw.get("sector"), dict) or isinstance(raw.get("eligibility"), dict) or isinstance(raw.get("financials"), dict):
        sector_obj = raw.get("sector") or {}
        elig_obj = raw.get("eligibility") or {}
        fin_obj = raw.get("financials") or {}

        coerced = {
            "client_name": _get_any(sector_obj, "client_name", default=_get_any(raw, "client_name", default="")),
            "group_name": _get_any(sector_obj, "group_name", default=_get_any(raw, "group_name")),
            "sector": _norm_sector(
                _get_any(
                    sector_obj,
                    "strategic_sector",
                    "sector",
                    default=_get_any(raw, "strategic_sector", "sector", default=""),
                )
            ),
            "rating_anchor": {
                "system": _get_any(sector_obj, "rating_system", default=_get_any(raw, "rating_system", default="")),
                "grade": str(_get_any(sector_obj, "rating_grade", default=_get_any(raw, "rating_grade", default=""))),
                "outlook": _get_any(sector_obj, "outlook", default=_get_any(raw, "outlook")),
            },
            "eligibility": {
                "score": float(
                    _get_any(elig_obj, "eligibility_score", "score", default=_get_any(raw, "eligibility_score", default=0.0)) or 0.0
                ),
                "drivers": _norm_drivers(
                    _get_any(elig_obj, "eligibility_drivers", "drivers", default=_get_any(raw, "eligibility_drivers"))
                ) or [],
            },
            "financial_signals": {
                "revenue_trend_3y": _norm_trend(_get_any(fin_obj, "revenue_trend_3y", default=_get_any(raw, "revenue_trend_3y"))),
                "margin_trend_3y": _norm_margin(_get_any(fin_obj, "margin_trend_3y", default=_get_any(raw, "margin_trend_3y"))),
                "leverage_position": _norm_leverage(_get_any(fin_obj, "leverage_position", default=_get_any(raw, "leverage_position"))),
                "cashflow_quality": _get_any(
                    fin_obj, "cashflow_quality", "cash_flow_quality", default=_get_any(raw, "cashflow_quality", "cash_flow_quality")
                ),
                "earnings_volatility": _get_any(fin_obj, "earnings_volatility", default=_get_any(raw, "earnings_volatility")),
                "capex_growth_investment": _get_any(fin_obj, "capex_growth_investment", default=_get_any(raw, "capex_growth_investment")),
                "financial_transparency": _get_any(fin_obj, "financial_transparency", default=_get_any(raw, "financial_transparency")),
            },
            "indicative_raroc_pct": _get_any(raw, "indicative_raroc_pct"),
            "notes": _get_any(raw, "notes"),
        }
        return DealInputRequest.model_validate(coerced)

    # --- Case A: flat payload ---
    flat = raw
    coerced = {
        "client_name": _get_any(flat, "client_name", default=""),
        "group_name": _get_any(flat, "group_name"),
        "sector": _norm_sector(_get_any(flat, "strategic_sector", "sector", default="")),
        "rating_anchor": {
            "system": _get_any(flat, "rating_system", default=""),
            "grade": str(_get_any(flat, "rating_grade", default="")),
            "outlook": _get_any(flat, "outlook"),
        },
        "eligibility": {
            "score": float(_get_any(flat, "eligibility_score", default=0.0) or 0.0),
            "drivers": _norm_drivers(_get_any(flat, "eligibility_drivers")) or [],
        },
        "financial_signals": {
            "revenue_trend_3y": _norm_trend(_get_any(flat, "revenue_trend_3y")),
            "margin_trend_3y": _norm_margin(_get_any(flat, "margin_trend_3y")),  # FIX: no fin_obj here
            "leverage_position": _norm_leverage(_get_any(flat, "leverage_position")),
            "cashflow_quality": _get_any(flat, "cashflow_quality", "cash_flow_quality"),
            "earnings_volatility": _get_any(flat, "earnings_volatility"),
            "capex_growth_investment": _get_any(flat, "capex_growth_investment"),
            "financial_transparency": _get_any(flat, "financial_transparency"),
        },
        "indicative_raroc_pct": _get_any(flat, "indicative_raroc_pct"),
        "notes": _get_any(flat, "notes"),
    }
    return DealInputRequest.model_validate(coerced)


# =========================
# Core assessment
# =========================
RAROC_HURDLE = 5.0

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

# RAROC is mandatory now; still guard just in case
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

    return DealSummaryResponse(
        client_name=payload.client_name,
        group_name=payload.group_name,
        sector=payload.sector,
        rating_anchor=payload.rating_anchor,
        eligibility=payload.eligibility,
        financial_signals=payload.financial_signals,
        indicative_raroc_pct=payload.indicative_raroc_pct,
        deal_readiness={"status": status, "strengths": strengths, "constraints": constraints},
        mandate_fit_summary=f"{payload.client_name} assessed as {status}.",
        rm_actions=rm_actions,
        talking_points=talking_points,
        created_at=date.today(),
        notes=payload.notes,
    )


# =========================
# Endpoints
# =========================
@app.post("/assess", response_model=DealSummaryResponse)
def assess_deal(payload: Dict[str, Any]):
    deal_input = _coerce_to_deal_input(payload)
    return _assess_deal(deal_input)


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

    prompt = (
        "You are a corporate banking RM copilot. Be concise and conservative. "
        "Use ONLY the provided summary; do not invent facts. "
        "Return STRICT JSON with keys: executive_summary, key_risks_explained, rm_talking_points.\n\n"
        f"SUMMARY:\n{deal.model_dump_json(indent=2)}"
    )

    try:
        resp = oa_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": (
        "You are a corporate banking Relationship Manager preparing a credit discussion note. "
        "Be critical, commercially realistic, and conservative. "
        "Explicitly link financial signals (margins, leverage, cash flow, transparency) "
        "to credit risk, headroom, and structuring options. "
        "Do NOT decline unless risks are clearly terminal. "
        "Avoid generic advice. Use banking language. "
        "Return STRICT JSON only."
    ),
},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        content = (resp.choices[0].message.content or "").strip()
        obj = json.loads(content) if content else {}
        return AIExplainResponse(
            executive_summary=str(obj.get("executive_summary", "")).strip(),
            key_risks_explained=list(obj.get("key_risks_explained", []))[:10],
            rm_talking_points=list(obj.get("rm_talking_points", []))[:10],
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


@app.post("/ai/qa", response_model=AIQAResponse)
def ai_qa(req: AIQARequest):
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required.")

    deal = req.deal_summary

    # If somehow deal_summary is missing, do NOT crash
    if deal is None:
        return AIQAResponse(
            answer="Please run an assessment first, then ask your question again.",
            disclaimer="Decision-support only.",
        )

    _guard_no_sensitive(question, deal.client_name, deal.group_name or "", deal.notes or "")

    # If AI not configured, do NOT 500
    if oa_client is None:
        return AIQAResponse(
            answer="AI is not enabled in this environment.",
            disclaimer="Decision-support only.",
        )

    prompt = (
        "You are a corporate banking RM copilot. Answer the question using ONLY the provided deal summary. "
        "If the answer is not supported by the summary, say what is missing.\n\n"
        f"QUESTION:\n{question}\n\n"
        f"DEAL SUMMARY:\n{deal.model_dump_json(indent=2)}"
    )

    try:
        resp = oa_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": (
        "You are a corporate banking Relationship Manager answering questions for a credit discussion. "
        "Be critical and constructive. "
        "Ground answers in the deal summary only. "
        "If risks outweigh mitigants, say so clearly. "
        "If information is missing, state what is required before proceeding. "
        "Use professional banking language. Do not invent facts."
    ),
},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        answer = (resp.choices[0].message.content or "").strip()

        # If model returns empty text, still avoid 500
        if not answer:
            answer = "Insufficient information in the current summary to answer this. Please add more deal details."

        return AIQAResponse(
            answer=answer,
            disclaimer="Decision-support only. Validate independently before submission.",
        )

    except Exception:
        # Never fail hard in demo: return deterministic fallback
        dr = deal.deal_readiness
        constraints = list(dr.constraints) if dr and getattr(dr, "constraints", None) else []
        actions = list(deal.rm_actions or [])

        fallback = []
        if actions:
            fallback.append("Recommended actions:")
            fallback.extend([f"- {x}" for x in actions[:6]])
        if constraints:
            fallback.append("\nKey constraints:")
            fallback.extend([f"- {x}" for x in constraints[:6]])
        if not fallback:
            fallback.append("Assessment summary is insufficient to answer this. Please add more deal details.")

        return AIQAResponse(
            answer="\n".join(fallback).strip(),
            disclaimer="Decision-support only. Validate independently before submission.",
        )

# =========================
# SPA serving
# =========================
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
INDEX_HTML = FRONTEND_DIST / "index.html"
ASSETS_DIR = FRONTEND_DIST / "assets"

if ASSETS_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    if INDEX_HTML.is_file():
        return FileResponse(str(INDEX_HTML))
    return JSONResponse({"detail": "Frontend not built"}, status_code=500)

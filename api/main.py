# api/main.py
from __future__ import annotations

import os
import re
from datetime import date
from typing import Any, Dict, List, Optional
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# =========================
# Load environment variables
# =========================
ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

# =========================
# App & schemas
# =========================
from api.schemas import (
    AIExplainRequest,
    AIExplainResponse,
    AIQARequest,
    AIQAResponse,
    DealInputRequest,
    DealSummaryResponse,
)

oa_client = None
if OPENAI_API_KEY:
    try:
        from openai import OpenAI

        oa_client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception:
        oa_client = None


# =========================
# App
# =========================
app = FastAPI(title="Corporate RM AI Assistant", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# Step 2 (Hardening): input guardrails
# =========================
_SENSITIVE_PATTERNS = [
    re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),  # IBAN-ish
    re.compile(r"\b\d{12,19}\b"),  # long digit strings (acct/card-ish)
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),  # email
]

def _contains_sensitive(text: str) -> bool:
    if not text:
        return False
    t = text.strip()
    if not t:
        return False
    return any(p.search(t) for p in _SENSITIVE_PATTERNS)

def _guard_no_sensitive(*texts: str):
    for t in texts:
        if _contains_sensitive(t):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Sensitive identifiers detected. Remove PII/account numbers/IBAN/emails and retry "
                    "with anonymised inputs."
                ),
            )


# =========================
# Step 3 (Credit logic tightening): deterministic assessment
# =========================
def _assess_deal(payload: DealInputRequest) -> DealSummaryResponse:
    # --- Guardrails (apply to any free-text fields)
    _guard_no_sensitive(payload.client_name, payload.group_name or "", payload.notes or "")

    strengths: List[str] = []
    constraints: List[str] = []
    rm_actions: List[str] = []
    talking_points: List[str] = []

    # Rating anchor signals (simple)
    if payload.rating_anchor.grade.strip():
        strengths.append(f"Rating anchor available from {payload.rating_anchor.system}.")
    else:
        constraints.append("No rating grade provided; cannot anchor risk positioning.")
        rm_actions.append("Obtain/confirm latest internal/external rating grade and date.")

    # Eligibility score (0–6)
    s = payload.eligibility.score
    if s >= 4.5:
        strengths.append(f"Strong strategic eligibility score ({s:.1f}/6).")
    elif s >= 3.0:
        strengths.append(f"Moderate strategic eligibility score ({s:.1f}/6).")
        constraints.append("Eligibility is not strongly differentiated vs. strategic mandate.")
        rm_actions.append("Strengthen eligibility case (job creation, exports, ICV, localisation, etc.).")
    else:
        constraints.append(f"Weak strategic eligibility score ({s:.1f}/6).")
        rm_actions.append("Rework mandate alignment narrative and quantify eligibility drivers.")

    if payload.eligibility.drivers:
        strengths.append("Eligibility drivers provided.")

    # Financial signals
    fs = payload.financial_signals

    # Revenue
    if fs.revenue_trend_3y == "Improving":
        strengths.append("Revenue trend improving over 3 years.")
    elif fs.revenue_trend_3y == "Declining":
        constraints.append("Revenue trend declining over 3 years.")
        rm_actions.append("Validate orderbook, customer concentration, and recovery plan.")

    # Margin
    if fs.margin_trend_3y == "Improving":
        strengths.append("Margins improving over 3 years.")
    elif fs.margin_trend_3y == "Under Pressure":
        constraints.append("Margins under pressure; risk to debt service capacity.")
        rm_actions.append("Assess pricing power, input cost pass-through, and covenant buffers.")

    # Leverage
    if fs.leverage_position == "Low":
        strengths.append("Low leverage position.")
    elif fs.leverage_position == "Elevated":
        constraints.append("Elevated leverage position; reduced headroom.")
        rm_actions.append("Consider structure support: amortisation, covenants, collateral, DSRA/DSCR.")

    # Cash flow quality
    if fs.cashflow_quality == "Strong":
        strengths.append("Strong cash flow quality.")
    elif fs.cashflow_quality == "Weak":
        constraints.append("Weak cash flow quality; potential working-capital stress.")
        rm_actions.append("Request WC cycle analysis, ageing, and evidence of collections discipline.")

    # Earnings volatility
    if fs.earnings_volatility == "High":
        constraints.append("High earnings volatility; needs stronger controls/monitoring.")
        rm_actions.append("Add monitoring triggers and tighten covenants; test downside scenarios.")

    # Capex/investment
    if fs.capex_growth_investment == "High":
        constraints.append("High capex/growth investment increases execution risk.")
        rm_actions.append("Validate capex plan, milestones, contingencies, and sponsor support.")

    # Transparency
    if fs.financial_transparency == "Weak":
        constraints.append("Weak financial transparency limits credit comfort.")
        rm_actions.append("Obtain audited financials, detailed management accounts, and bank statements.")

    # Determine readiness
    # Simple rule: any "major" constraints -> Conditional, multiple -> Weak
    major_count = 0
    for c in constraints:
        if any(k in c.lower() for k in ["declining", "under pressure", "elevated", "weak", "high"]):
            major_count += 1

    if major_count >= 3:
        status = "Weak"
    elif major_count >= 1:
        status = "Conditional"
    else:
        status = "Strong"

    # Talking points (RM-friendly)
    if status == "Strong":
        talking_points.append("Mandate fit is clear; focus discussion on facility sizing and structure.")
    elif status == "Conditional":
        talking_points.append("Proceed subject to resolving key constraints and tightening structure.")
    else:
        talking_points.append("Defer credit appetite until constraints are addressed and visibility improves.")

    # Mandate fit summary (1 paragraph)
    mandate_fit_summary = (
        f"{payload.client_name} sits in the '{payload.sector}' sector with eligibility score "
        f"{payload.eligibility.score:.1f}/6. Deal readiness is assessed as {status} based on "
        f"rating anchor, eligibility strength, and RM-level financial signals (revenue/margin/leverage/"
        f"cash flow/volatility/transparency)."
    )

    return DealSummaryResponse(
        client_name=payload.client_name,
        group_name=payload.group_name,
        sector=payload.sector,
        rating_anchor=payload.rating_anchor,
        eligibility=payload.eligibility,
        financial_signals=payload.financial_signals,
        deal_readiness={"status": status, "strengths": strengths, "constraints": constraints},
        mandate_fit_summary=mandate_fit_summary,
        rm_actions=rm_actions,
        talking_points=talking_points,
        created_at=date.today(),
        notes=payload.notes,
    )


# =========================
# API endpoints
# =========================
@app.post("/assess", response_model=DealSummaryResponse)
def assess_deal(payload: DealInputRequest):
    return _assess_deal(payload)


# Keep your old scoring endpoint if you still use it elsewhere
# (Safe stub: you can remove if not needed)
@app.post("/api/score")
def api_score(payload: Dict[str, Any]):
    # This is intentionally a placeholder.
    # If you still have the LightGBM PD model path, keep your original /api/score code.
    return {"ok": True, "message": "Use POST /assess for deal readiness MVP."}


# =========================
# AI helpers
# =========================
def _deal_to_brief(deal: DealSummaryResponse) -> str:
    # deal is a Pydantic object, so use model_dump()
    d = deal.model_dump()
    dr = d.get("deal_readiness", {}) or {}
    return (
        f"Client: {d.get('client_name')}\n"
        f"Sector: {d.get('sector')}\n"
        f"Rating: {d.get('rating_anchor', {}).get('system')} / {d.get('rating_anchor', {}).get('grade')}\n"
        f"Eligibility: {d.get('eligibility', {}).get('score')} / 6\n"
        f"Readiness: {dr.get('status')}\n"
        f"Strengths: {', '.join(dr.get('strengths', [])[:6])}\n"
        f"Constraints: {', '.join(dr.get('constraints', [])[:6])}\n"
        f"RM actions: {', '.join(d.get('rm_actions', [])[:8])}\n"
        f"Notes: {d.get('notes') or ''}\n"
    )

def _fallback_ai_qa(question: str, deal: Optional[DealSummaryResponse]) -> str:
    if not deal:
        return "Provide a deal assessment first (POST /assess), then ask a question grounded in the summary."
    d = deal.model_dump()
    dr = d.get("deal_readiness", {}) or {}
    status = dr.get("status", "Conditional")
    constraints = dr.get("constraints", [])
    actions = d.get("rm_actions", [])
    if status == "Strong":
        return "Proceed to structure discussion: facility sizing, tenor, security, covenants, and pricing calibration."
    if constraints:
        return (
            "Prioritise the top constraints first:\n- "
            + "\n- ".join(constraints[:5])
            + "\n\nNext RM actions:\n- "
            + "\n- ".join(actions[:6] or ["Request missing information and tighten structure accordingly."])
        )
    return "Focus on clarifying rating anchor, eligibility drivers, and the weakest financial signals."

def _ai_disclaimer() -> str:
    return (
        "Do not enter confidential/internal customer data into external AI. "
        "Use anonymised inputs only. Outputs are decision-support and must be reviewed by a qualified banker."
    )


# =========================
# AI endpoints
# =========================
@app.post("/ai/explain", response_model=AIExplainResponse)
def ai_explain(payload: AIExplainRequest):
    # Guard notes
    if payload.deal_summary.notes:
        _guard_no_sensitive(payload.deal_summary.notes)

    # If no OpenAI, return deterministic explain
    if not oa_client:
        d = payload.deal_summary.model_dump()
        dr = d.get("deal_readiness", {}) or {}
        return AIExplainResponse(
            executive_summary=d.get("mandate_fit_summary", ""),
            key_risks_explained=(dr.get("constraints", []) or [])[:6],
            rm_talking_points=(d.get("talking_points", []) or [])[:6],
            disclaimer=_ai_disclaimer(),
        )

    prompt = (
        "You are a corporate banking RM copilot. You must be concise, practical, and risk-aware.\n"
        "You must NOT invent data. Use only the deal summary.\n\n"
        f"DEAL SUMMARY:\n{_deal_to_brief(payload.deal_summary)}\n"
        "Task: produce (1) an executive summary (2) key risks explained (bullets) "
        "(3) RM talking points (bullets)."
    )

    try:
        resp = oa_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "Return JSON only, matching the requested fields."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        content = resp.choices[0].message.content or ""
    except Exception:
        d = payload.deal_summary.model_dump()
        dr = d.get("deal_readiness", {}) or {}
        return AIExplainResponse(
            executive_summary=d.get("mandate_fit_summary", ""),
            key_risks_explained=(dr.get("constraints", []) or [])[:6],
            rm_talking_points=(d.get("talking_points", []) or [])[:6],
            disclaimer=_ai_disclaimer(),
        )

    # Minimal robust JSON parsing without extra deps
    import json

    try:
        obj = json.loads(content)
        return AIExplainResponse(
            executive_summary=str(obj.get("executive_summary", "")),
            key_risks_explained=list(obj.get("key_risks_explained", []))[:10],
            rm_talking_points=list(obj.get("rm_talking_points", []))[:10],
            disclaimer=_ai_disclaimer(),
        )
    except Exception:
        # If model returned non-JSON, fallback
        d = payload.deal_summary.model_dump()
        dr = d.get("deal_readiness", {}) or {}
        return AIExplainResponse(
            executive_summary=d.get("mandate_fit_summary", ""),
            key_risks_explained=(dr.get("constraints", []) or [])[:6],
            rm_talking_points=(d.get("talking_points", []) or [])[:6],
            disclaimer=_ai_disclaimer(),
        )


@app.post("/ai/qa", response_model=AIQAResponse)
def ai_qa(payload: AIQARequest):
    _guard_no_sensitive(payload.question)

    # Deterministic if no AI
    if not oa_client:
        return AIQAResponse(
            answer=_fallback_ai_qa(payload.question, payload.deal_summary),
            disclaimer=_ai_disclaimer(),
        )

    deal = payload.deal_summary
    if deal and deal.notes:
        _guard_no_sensitive(deal.notes)

    prompt = (
        "You are a corporate banking RM copilot. Answer the user's question using ONLY the deal summary.\n"
        "If the deal summary is missing something, say what is missing and propose RM next steps.\n"
        "Be concise and structured.\n\n"
        + (f"DEAL SUMMARY:\n{_deal_to_brief(deal)}\n" if deal else "DEAL SUMMARY: (none)\n")
        + f"QUESTION:\n{payload.question}\n"
    )

    try:
        resp = oa_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "Be concise. Avoid hallucinations. No confidential data."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        answer = (resp.choices[0].message.content or "").strip()
        if not answer:
            answer = _fallback_ai_qa(payload.question, deal)
        return AIQAResponse(answer=answer, disclaimer=_ai_disclaimer())
    except Exception:
        return AIQAResponse(
            answer=_fallback_ai_qa(payload.question, deal),
            disclaimer=_ai_disclaimer(),
        )


# =========================
# SPA (serve built frontend if present)
# =========================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")
INDEX_HTML = os.path.join(STATIC_DIR, "index.html")

if os.path.exists(INDEX_HTML):
    assets_dir = os.path.join(STATIC_DIR, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/", include_in_schema=False)
    def spa_root():
        return FileResponse(INDEX_HTML)

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        return FileResponse(INDEX_HTML)
else:
    @app.get("/", include_in_schema=False)
    def root():
        return {
            "status": "ok",
            "docs": "/docs",
            "assess_endpoint": "POST /assess",
            "ai_qa": "POST /ai/qa",
            "ai_explain": "POST /ai/explain",
        }

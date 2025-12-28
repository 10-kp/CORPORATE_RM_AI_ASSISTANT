# api/main.py
from __future__ import annotations

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
# App (create ONCE)
# =========================
app = FastAPI(title="Corporate RM AI Assistant", version="0.1.0")


# =========================
# CORS
# =========================
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
# Input guardrails
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
# Deterministic assessment
# =========================
def _assess_deal(payload: DealInputRequest) -> DealSummaryResponse:
    _guard_no_sensitive(payload.client_name, payload.group_name or "", payload.notes or "")

    strengths: List[str] = []
    constraints: List[str] = []
    rm_actions: List[str] = []
    talking_points: List[str] = []

    # Rating anchor
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

    # RAROC (NEW)
    if payload.indicative_raroc_pct is not None:
        r = float(payload.indicative_raroc_pct)
        if r >= 5.0:
            strengths.append(f"Indicative RAROC meets hurdle ({r:.1f}%).")
        else:
            constraints.append(f"Indicative RAROC below hurdle ({r:.1f}% vs 5.0%).")
            rm_actions.append("Improve risk–return: increase pricing margin (spread) where feasible.")
            rm_actions.append("Improve risk–return: add upfront/arrangement fees or commitment fees.")
            rm_actions.append("Improve risk–return: consider shorter tenor or amortisation to reduce risk.")
            rm_actions.append("Improve risk–return: strengthen security/guarantees or reduce facility size.")

    # Financial signals
    fs = payload.financial_signals

    if fs.revenue_trend_3y == "Improving":
        strengths.append("Revenue trend improving over 3 years.")
    elif fs.revenue_trend_3y == "Declining":
        constraints.append("Revenue trend declining over 3 years.")
        rm_actions.append("Validate orderbook, customer concentration, and recovery plan.")

    if fs.margin_trend_3y == "Improving":
        strengths.append("Margins improving over 3 years.")
    elif fs.margin_trend_3y == "Under Pressure":
        constraints.append("Margins under pressure; risk to debt service capacity.")
        rm_actions.append("Assess pricing power, input cost pass-through, and covenant buffers.")

    if fs.leverage_position == "Low":
        strengths.append("Low leverage position.")
    elif fs.leverage_position == "Elevated":
        constraints.append("Elevated leverage position; reduced headroom.")
        rm_actions.append("Consider structure support: amortisation, covenants, collateral, DSRA/DSCR.")

    if fs.cashflow_quality == "Strong":
        strengths.append("Strong cash flow quality.")
    elif fs.cashflow_quality == "Weak":
        constraints.append("Weak cash flow quality; potential working-capital stress.")
        rm_actions.append("Request WC cycle analysis, ageing, and evidence of collections discipline.")

    if fs.earnings_volatility == "High":
        constraints.append("High earnings volatility; needs stronger controls/monitoring.")
        rm_actions.append("Add monitoring triggers and tighten covenants; test downside scenarios.")

    if fs.capex_growth_investment == "High":
        constraints.append("High capex/growth investment increases execution risk.")
        rm_actions.append("Validate capex plan, milestones, contingencies, and sponsor support.")

    if fs.financial_transparency == "Weak":
        constraints.append("Weak financial transparency limits credit comfort.")
        rm_actions.append("Obtain audited financials, detailed management accounts, and bank statements.")

    # Readiness label
    major_count = 0
    for c in constraints:
        if any(k in c.lower() for k in ["declining", "under pressure", "elevated", "weak", "high", "below hurdle"]):
            major_count += 1

    if major_count >= 3:
        status = "Weak"
    elif major_count >= 1:
        status = "Conditional"
    else:
        status = "Strong"

    if status == "Strong":
        talking_points.append("Mandate fit is clear; focus discussion on facility sizing and structure.")
    elif status == "Conditional":
        talking_points.append("Proceed subject to resolving key constraints and tightening structure.")
    else:
        talking_points.append("Defer credit appetite until constraints are addressed and visibility improves.")

    mandate_fit_summary = (
        f"{payload.client_name} sits in the '{payload.sector}' sector with eligibility score "
        f"{payload.eligibility.score:.1f}/6. Deal readiness is assessed as {status} based on "
        f"rating anchor, eligibility strength, RM-level financial signals, and indicative risk–return."
    )

    return DealSummaryResponse(
        client_name=payload.client_name,
        group_name=payload.group_name,
        sector=payload.sector,
        rating_anchor=payload.rating_anchor,
        eligibility=payload.eligibility,
        financial_signals=payload.financial_signals,
        indicative_raroc_pct=payload.indicative_raroc_pct,
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


@app.post("/api/score")
def api_score(payload: Dict[str, Any]):
    return {"ok": True, "message": "Use POST /assess for deal readiness MVP."}


# =========================
# AI helpers/endpoints
# =========================
def _deal_to_brief(deal: DealSummaryResponse) -> str:
    d = deal.model_dump()
    dr = d.get("deal_readiness", {}) or {}
    return (
        f"Client: {d.get('client_name')}\n"
        f"Sector: {d.get('sector')}\n"
        f"Rating: {d.get('rating_anchor', {}).get('system')} / {d.get('rating_anchor', {}).get('grade')}\n"
        f"Eligibility: {d.get('eligibility', {}).get('score')} / 6\n"
        f"Indicative RAROC: {d.get('indicative_raroc_pct') if d.get('indicative_raroc_pct') is not None else 'N/A'}%\n"
        f"Readiness: {dr.get('status')}\n"
        f"Strengths: {', '.join(dr.get('strengths', [])[:6])}\n"
        f"Constraints: {', '.join(dr.get('constraints', [])[:6])}\n"
        f"RM actions: {', '.join(d.get('rm_actions', [])[:8])}\n"
        f"Notes: {d.get('notes') or ''}\n"
    )


def _ai_disclaimer() -> str:
    return (
        "Do not enter confidential/internal customer data into external AI. "
        "Use anonymised inputs only. Outputs are decision-support and must be reviewed by a qualified banker."
    )


def _fallback_ai_qa(question: str, deal: Optional[DealSummaryResponse]) -> str:
    if not deal:
        return "Run an assessment first (POST /assess), then ask a question grounded in the summary."
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
    return "Clarify rating anchor, eligibility drivers, and the weakest financial signals."


@app.post("/ai/explain", response_model=AIExplainResponse)
def ai_explain(payload: AIExplainRequest):
    if payload.deal_summary.notes:
        _guard_no_sensitive(payload.deal_summary.notes)

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
        "You are a corporate banking RM copilot. Be concise, practical, risk-aware. Do NOT invent data.\n\n"
        f"DEAL SUMMARY:\n{_deal_to_brief(payload.deal_summary)}\n"
        "Return JSON with: executive_summary (string), key_risks_explained (list), rm_talking_points (list)."
    )

    import json

    try:
        resp = oa_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "Return JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        content = resp.choices[0].message.content or ""
        obj = json.loads(content)
        return AIExplainResponse(
            executive_summary=str(obj.get("executive_summary", "")),
            key_risks_explained=list(obj.get("key_risks_explained", []))[:10],
            rm_talking_points=list(obj.get("rm_talking_points", []))[:10],
            disclaimer=_ai_disclaimer(),
        )
    except Exception:
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

    if not oa_client:
        return AIQAResponse(answer=_fallback_ai_qa(payload.question, payload.deal_summary), disclaimer=_ai_disclaimer())

    deal = payload.deal_summary
    if deal and deal.notes:
        _guard_no_sensitive(deal.notes)

    prompt = (
        "Answer using ONLY the deal summary. If missing info, say what is missing and RM next steps.\n\n"
        + (f"DEAL SUMMARY:\n{_deal_to_brief(deal)}\n" if deal else "DEAL SUMMARY: (none)\n")
        + f"QUESTION:\n{payload.question}\n"
    )

    try:
        resp = oa_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "Be concise. No hallucinations. No confidential data."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        answer = (resp.choices[0].message.content or "").strip()
        if not answer:
            answer = _fallback_ai_qa(payload.question, deal)
        return AIQAResponse(answer=answer, disclaimer=_ai_disclaimer())
    except Exception:
        return AIQAResponse(answer=_fallback_ai_qa(payload.question, deal), disclaimer=_ai_disclaimer())


# =========================
# SPA: serve built frontend from frontend/dist
# =========================
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
INDEX_HTML = FRONTEND_DIST / "index.html"
ASSETS_DIR = FRONTEND_DIST / "assets"

# Serve /assets from Vite build
if ASSETS_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

_API_PREFIXES = ("assess", "ai", "api", "docs", "openapi.json", "health", "assets")


@app.get("/", include_in_schema=False)
def spa_root():
    if INDEX_HTML.is_file():
        return FileResponse(str(INDEX_HTML))
    return JSONResponse(
        {"detail": "Frontend not built. Run: cd frontend && npm ci && npm run build"},
        status_code=500,
    )


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    if full_path.startswith(_API_PREFIXES):
        raise HTTPException(status_code=404, detail="Not found")
    if INDEX_HTML.is_file():
        return FileResponse(str(INDEX_HTML))
    return JSONResponse(
        {"detail": "Frontend not built. Run: cd frontend && npm ci && npm run build"},
        status_code=500,
    )

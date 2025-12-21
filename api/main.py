# api/main.py
import os
from typing import Dict, Any, Optional, List, Union

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from openai import OpenAI
from openai import RateLimitError

from api.schemas import (
    DealInputRequest,
    DealSummaryResponse,
    AIQARequest,
    AIQAResponse,
    AIExplainRequest,
    AIExplainResponse,
)

# -----------------------------
# App config
# -----------------------------
app = FastAPI(title="Corporate RM Deal Readiness API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # OK for local dev; tighten for prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DISCLAIMER = "Decision-support only. Verify independently. Not a credit decision or approval."
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Safe OpenAI init (never crash if key missing)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
oa_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


# -----------------------------
# Utilities
# -----------------------------
def _to_dict(obj: Any) -> Dict[str, Any]:
    """
    Normalize Pydantic model or dict to plain dict.
    Handles Pydantic v2 (model_dump) and v1 (dict).
    """
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):  # Pydantic v2
        return obj.model_dump()
    if hasattr(obj, "dict"):  # Pydantic v1
        return obj.dict()
    # last resort
    return {}


# -----------------------------
# Step 3: Credit logic tightening
# -----------------------------
def _count_weak_signals(financial_signals: Dict[str, Any]) -> int:
    weak = 0
    for _, v in (financial_signals or {}).items():
        if isinstance(v, str) and v.strip().lower() == "weak":
            weak += 1
    return weak


def compute_readiness(eligibility_score: float, financial_signals: Dict[str, Any]) -> str:
    """
    Rules:
      - Strong if eligibility >= 4.0 AND no weak signals
      - Weak if 2+ weak signals
      - else Conditional
    """
    weak_count = _count_weak_signals(financial_signals)
    if weak_count >= 2:
        return "Weak"
    if eligibility_score >= 4.0 and weak_count == 0:
        return "Strong"
    return "Conditional"


def build_deal_summary(payload: DealInputRequest) -> Dict[str, Any]:
    """
    Produces the response expected by the frontend and AI endpoints.
    """
    elig_score = float(payload.eligibility.score)
    drivers = payload.eligibility.drivers or []
    sector = payload.sector

    fs = _to_dict(payload.financial_signals)
    status = compute_readiness(elig_score, fs)
    weak_count = _count_weak_signals(fs)

    strengths: List[str] = []
    constraints: List[str] = []

    # Strengths / constraints from eligibility
    if elig_score >= 4.0:
        strengths.append("Eligibility score indicates strong alignment with mandate.")
    elif elig_score >= 3.0:
        strengths.append("Eligibility score indicates partial alignment with mandate.")
    else:
        constraints.append("Low eligibility score may limit mandate alignment.")

    if drivers:
        strengths.append(
            f"Eligibility drivers provided: {', '.join(drivers[:5])}" + ("..." if len(drivers) > 5 else "")
        )

    # Constraints from signals
    if weak_count >= 2:
        constraints.append("Multiple weak financial signals indicate elevated credit risk.")
    elif weak_count == 1:
        constraints.append("One weak financial signal flagged; requires validation and mitigants.")

    if elig_score < 4.0:
        constraints.append("Eligibility score below strong alignment threshold")

    # RM actions
    rm_actions: List[str] = []
    if elig_score < 4.0:
        rm_actions.append("Identify actions to improve eligibility drivers (exports, ICV, strategic impact).")
    if weak_count >= 1:
        rm_actions.append("Request supporting evidence for financial signals (audited FS, bank statements, aging, covenants).")
        rm_actions.append("Consider mitigants: collateral, tighter covenants, DSRA/escrow, shorter tenor, pricing adjustment.")
    if not rm_actions:
        rm_actions.append("Proceed to detailed credit assessment (KYC, financial spreading, cashflow, security package).")

    # Talking points (RM-facing)
    if status == "Strong":
        talking_points = [
            "Confirm facility purpose, tenor, security, and repayment source.",
            "Validate rating anchor and latest performance trend.",
            "Agree documentation timeline and conditions precedent.",
        ]
    elif status == "Conditional":
        talking_points = [
            "Clarify which drivers can lift eligibility and by when.",
            "Validate weak/uncertain financial areas with evidence.",
            "Discuss structure enhancements (security/covenants/DSRA).",
        ]
    else:
        talking_points = [
            "Explain key credit concerns and what data is needed to reconsider.",
            "Explore alternative structures or smaller exposure/shorter tenor.",
            "Assess sponsor support and credible mitigants before proceeding.",
        ]

    mandate_fit_summary = (
        f"The deal operates in the {sector} sector with an eligibility score of {elig_score:.1f}. "
        f"Overall readiness is assessed as {status}."
    )

    return {
        "client_name": payload.client_name,
        "group_name": payload.group_name,
        "sector": sector,
        "deal_readiness": {"status": status, "strengths": strengths, "constraints": constraints},
        "rm_actions": rm_actions,
        "talking_points": talking_points,
        "mandate_fit_summary": mandate_fit_summary,
        "created_at": getattr(payload.rating_anchor, "as_of", None),
        "notes": payload.notes,
        "rating_anchor": _to_dict(payload.rating_anchor),
        "eligibility": _to_dict(payload.eligibility),
        "financial_signals": fs,
    }


# -----------------------------
# Core endpoints
# -----------------------------
@app.post("/assess", response_model=DealSummaryResponse)
def assess_deal(payload: DealInputRequest):
    return build_deal_summary(payload)


@app.post("/api/score")
def score(payload: Dict[str, Any]):
    return {
        "pd": 0.08,
        "feats": [],
        "model_version": "stub-0.1",
        "note": "Placeholder. Use /assess for deal readiness.",
    }


# -----------------------------
# Step 2: AI hardening (never 500)
# -----------------------------
def _deal_to_brief(deal_any: Any) -> str:
    deal = _to_dict(deal_any)

    client = deal.get("client_name", "")
    sector = deal.get("sector", "")
    rating = deal.get("rating_anchor", {}) or {}
    elig = deal.get("eligibility", {}) or {}
    fs = deal.get("financial_signals", {}) or {}
    dr = deal.get("deal_readiness", {}) or {}

    lines: List[str] = []
    lines.append(f"Client: {client}")
    lines.append(f"Sector: {sector}")
    lines.append(
        f"Rating: {rating.get('system','')} {rating.get('grade','')} "
        f"(Outlook: {rating.get('outlook','')})"
    )
    lines.append(
        f"Eligibility score: {elig.get('score','')}; Drivers: {', '.join(elig.get('drivers', []) or [])}"
    )
    lines.append(
        "Financial signals: "
        f"Revenue={fs.get('revenue_trend_3y','')}, "
        f"Margin={fs.get('margin_trend_3y','')}, "
        f"Leverage={fs.get('leverage_position','')}, "
        f"Cashflow={fs.get('cashflow_quality','')}, "
        f"Volatility={fs.get('earnings_volatility','')}, "
        f"Capex={fs.get('capex_growth_investment','')}, "
        f"Transparency={fs.get('financial_transparency','')}"
    )
    lines.append(
        f"Deal readiness: {dr.get('status','')}; "
        f"Constraints: {', '.join(dr.get('constraints', []) or [])}; "
        f"Strengths: {', '.join(dr.get('strengths', []) or [])}"
    )
    lines.append(f"Mandate fit summary: {deal.get('mandate_fit_summary','')}")
    lines.append(f"RM actions: {', '.join(deal.get('rm_actions', []) or [])}")

    return "\n".join(lines)


def _fallback_ai_qa(question: str, deal_any: Any) -> str:
    deal = _to_dict(deal_any)

    q = (question or "").strip().lower()
    dr = deal.get("deal_readiness", {}) or {}
    status = dr.get("status", "Conditional")
    constraints = dr.get("constraints", []) or []
    actions = deal.get("rm_actions", []) or []
    summary = deal.get("mandate_fit_summary", "")

    if "next" in q or "do i do" in q or "do next" in q:
        bullets: List[str] = []
        if constraints:
            bullets.append("Address constraints:")
            bullets += [f"- {c}" for c in constraints]
        if actions:
            bullets.append("RM next steps:")
            bullets += [f"- {a}" for a in actions]
        if not bullets:
            bullets = [
                "- Validate inputs (rating, eligibility, financial signals).",
                "- Proceed to detailed credit memo and structuring.",
            ]
        return f"Status: {status}\n{summary}\n\n" + "\n".join(bullets)

    return (
        f"Status: {status}\n"
        f"{summary}\n\n"
        f"Constraints: {', '.join(constraints) if constraints else 'None flagged'}\n"
        f"RM actions: {', '.join(actions) if actions else 'None suggested'}"
    )


def _fallback_ai_explain(deal_any: Any) -> Dict[str, Any]:
    deal = _to_dict(deal_any)

    dr = deal.get("deal_readiness", {}) or {}
    status = dr.get("status", "Conditional")
    constraints = dr.get("constraints", []) or []
    actions = deal.get("rm_actions", []) or []
    summary = deal.get("mandate_fit_summary", "")

    exec_summary = f"{summary} Readiness is assessed as {status}."
    key_risks = constraints if constraints else ["No major constraints flagged based on provided inputs."]
    talking = actions if actions else ["Confirm rating anchor details and obtain supporting documentation."]

    return {
        "executive_summary": exec_summary,
        "key_risks_explained": key_risks,
        "rm_talking_points": talking,
    }


@app.post("/ai/qa", response_model=AIQAResponse)
def ai_qa(payload: AIQARequest):
    # IMPORTANT: payload.deal_summary can be DealSummaryResponse (Pydantic) or None
    deal_any = payload.deal_summary
    safe_answer = _fallback_ai_qa(payload.question, deal_any)

    # Optional AI enhancement
    answer = safe_answer
    if oa_client is not None:
        try:
            prompt_text = (
                "You are a Corporate RM assistant at a bank. "
                "Answer concisely in actionable RM terms.\n\n"
                f"DEAL SUMMARY:\n{_deal_to_brief(deal_any)}\n"
                f"QUESTION: {payload.question}\n"
            )
            r = oa_client.responses.create(model=MODEL_NAME, input=prompt_text)
            if getattr(r, "output_text", None):
                answer = r.output_text.strip()
        except RateLimitError:
            answer = safe_answer + "\n\n(Note: AI enhancement temporarily unavailable due to rate limit.)"
        except Exception as e:
            answer = safe_answer + f"\n\n(Note: AI enhancement unavailable: {type(e).__name__}.)"

    return AIQAResponse(answer=answer, disclaimer=DISCLAIMER)


@app.post("/ai/explain", response_model=AIExplainResponse)
def ai_explain(payload: AIExplainRequest):
    deal_any = payload.deal_summary
    fb = _fallback_ai_explain(deal_any)

    executive_summary = fb["executive_summary"]
    key_risks_explained = fb["key_risks_explained"]
    rm_talking_points = fb["rm_talking_points"]

    # Optional AI enhancement (safe)
    if oa_client is not None:
        try:
            prompt_text = (
                "You are a bank credit/RM assistant. "
                "Write a short executive summary (3-5 lines) and 5 RM talking points.\n\n"
                f"DEAL SUMMARY:\n{_deal_to_brief(deal_any)}\n"
            )
            r = oa_client.responses.create(model=MODEL_NAME, input=prompt_text)
            if getattr(r, "output_text", None):
                executive_summary = r.output_text.strip()
        except Exception:
            pass

    return AIExplainResponse(
        executive_summary=executive_summary,
        key_risks_explained=key_risks_explained,
        rm_talking_points=rm_talking_points,
        disclaimer=DISCLAIMER,
    )


# -----------------------------
# SPA serving (optional)
# Looks for: api/static/index.html
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
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
        return {"status": "ok", "docs": "/docs", "assess_endpoint": "POST /assess"}

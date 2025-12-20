# api/main.py
# ---------- imports ----------
import os
import math
import re
from typing import Optional, Union

import numpy as np
import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from openai import OpenAI, RateLimitError

from api.schemas import (
    DealInputRequest,
    DealSummaryResponse,
    AIExplainRequest,
    AIExplainResponse,
    AIQARequest,
    AIQAResponse,
)

from src.domain.deal_summary import (
    DealSummary,
    DealReadiness,
    Eligibility,
    FinancialSignals,
    RatingAnchor,
)

# ---------- constants ----------
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
DISCLAIMER = "Decision-support only. Verify independently. Not a credit decision or approval."

# ---------- OpenAI client (safe init) ----------
oa_client: Optional[OpenAI] = None
if os.getenv("OPENAI_API_KEY"):
    oa_client = OpenAI()

# ---------- FastAPI app + CORS ----------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- model loading ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
JOBLIB_PATH = os.path.join(MODELS_DIR, "model.joblib")
TXT_PATH = os.path.join(MODELS_DIR, "model.txt")

USE_REAL = False
BOOSTER = None
EXPECTED = []
EXPLAINER = None

try:
    if os.path.exists(JOBLIB_PATH):
        import joblib

        MODEL = joblib.load(JOBLIB_PATH)
        BOOSTER = MODEL.booster_ if hasattr(MODEL, "booster_") else MODEL
        EXPECTED = list(BOOSTER.feature_name() or [])
        USE_REAL = True
        print(f"[startup] Loaded joblib model with {len(EXPECTED)} features.")
    elif os.path.exists(TXT_PATH):
        import lightgbm as lgb

        BOOSTER = lgb.Booster(model_file=TXT_PATH)
        EXPECTED = list(BOOSTER.feature_name() or [])
        USE_REAL = True
        print(f"[startup] Loaded LightGBM text model with {len(EXPECTED)} features.")
    else:
        print("[startup] No model file found — running in MOCK mode.")
except Exception as e:
    print(f"[startup] Failed to load model file: {e}. Falling back to MOCK mode.")
    BOOSTER = None
    USE_REAL = False

# optional SHAP
if USE_REAL and BOOSTER is not None:
    try:
        import shap

        EXPLAINER = shap.TreeExplainer(BOOSTER)
        print("[startup] SHAP explainer ready.")
    except Exception as e:
        print(f"[startup] SHAP unavailable ({e}). Will use global importances.")


# ---------- /api/score schema ----------
class ScoreIn(BaseModel):
    loan_amnt: Union[float, str] | None = None
    int_rate: Union[float, str] | None = None
    dti: Union[float, str] | None = None
    annual_inc: Union[float, str] | None = None
    term: Union[int, str] | None = 36
    grade: str | None = "B"
    revol_util: Union[float, str] | None = None
    delinq_2yrs: Union[int, str] | None = 0
    open_acc: Union[int, str] | None = 0
    model_config = ConfigDict(extra="ignore")


def _fnum(x, default=0.0) -> float:
    if x is None:
        return float(default)
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        s = x.strip().replace(",", "")
        m = re.search(r"-?\d+(\.\d+)?", s)
        if m:
            return float(m.group(0))
    return float(default)


def _fint(x, default=0) -> int:
    return int(round(_fnum(x, default)))


def build_row(obj) -> pd.DataFrame:
    gmap = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 5, "G": 6}
    base = {
        "loan_amnt": float(obj.loan_amnt),
        "int_rate": float(obj.int_rate),
        "dti": float(obj.dti),
        "annual_inc": float(obj.annual_inc),
        "revol_util": float(obj.revol_util),
        "delinq_2yrs": float(obj.delinq_2yrs),
        "open_acc": float(obj.open_acc),
        "term": float(obj.term),
        "grade": float(gmap.get(obj.grade, 1)),
        "grade_idx": float(gmap.get(obj.grade, 1)),
    }

    if not EXPECTED:
        cols = [
            "loan_amnt",
            "int_rate",
            "dti",
            "annual_inc",
            "term",
            "grade_idx",
            "revol_util",
            "delinq_2yrs",
            "open_acc",
        ]
        return pd.DataFrame([[base.get(k, 0.0) for k in cols]], columns=cols)

    row = {c: 0.0 for c in EXPECTED}
    for k in ["loan_amnt", "int_rate", "dti", "annual_inc", "revol_util", "delinq_2yrs", "open_acc"]:
        if k in row:
            row[k] = base[k]

    if "term" in row:
        row["term"] = base["term"]
    else:
        tcol = f"term_{int(base['term'])}"
        if tcol in row:
            row[tcol] = 1.0

    if "grade" in row:
        row["grade"] = base["grade"]
    if "grade_idx" in row:
        row["grade_idx"] = base["grade_idx"]
    else:
        gcol = f"grade_{str(obj.grade).upper()}"
        if gcol in row:
            row[gcol] = 1.0

    return pd.DataFrame([row], columns=EXPECTED)


# ---------- domain logic ----------
def build_deal_summary(payload: DealInputRequest) -> DealSummary:
    strengths = []
    constraints = []
    rm_actions = []
    talking_points = []

    # Eligibility interpretation
    if payload.eligibility.score >= 4.0:
        strengths.append("Eligibility score supports mandate alignment")
    else:
        constraints.append("Eligibility score below strong alignment threshold")
        rm_actions.append("Identify actions to improve eligibility drivers")

    # Sector alignment
    if payload.sector in {"Manufacturing", "Advanced Technology", "Healthcare", "Food Security", "Renewables"}:
        strengths.append(f"Operates in strategic sector: {payload.sector}")
    else:
        constraints.append("Sector is not a core strategic priority")

    # Financial signals
    if payload.financial_signals.margin_trend_3y == "Under Pressure":
        constraints.append("Margins under pressure")
        rm_actions.append("Discuss margin recovery or cost optimisation plans")

    if payload.financial_signals.leverage_position == "Elevated":
        constraints.append("Leverage is elevated")
        rm_actions.append("Assess deleveraging or capital support options")

    if payload.financial_signals.cashflow_quality == "Weak":
        constraints.append("Cash flow generation is weak")
        rm_actions.append("Clarify cash flow sustainability and liquidity buffers")

    # Deal readiness
    if not constraints:
        status = "Strong"
    elif len(constraints) <= 2:
        status = "Conditional"
    else:
        status = "Weak"

    mandate_fit_summary = (
        f"The deal operates in the {payload.sector} sector with an "
        f"eligibility score of {payload.eligibility.score:.1f}. "
        f"Overall readiness is assessed as {status}."
    )

    return DealSummary(
        client_name=payload.client_name,
        group_name=payload.group_name,
        sector=payload.sector,
        rating_anchor=RatingAnchor(**payload.rating_anchor.model_dump()),
        eligibility=Eligibility(**payload.eligibility.model_dump()),
        financial_signals=FinancialSignals(**payload.financial_signals.model_dump()),
        deal_readiness=DealReadiness(status=status, strengths=strengths, constraints=constraints),
        mandate_fit_summary=mandate_fit_summary,
        rm_actions=rm_actions,
        talking_points=talking_points,
        notes=payload.notes,
    )


# ---------- endpoints ----------
@app.post("/assess", response_model=DealSummaryResponse)
def assess_deal(payload: DealInputRequest):
    deal = build_deal_summary(payload)
    return deal.to_dict()


@app.post("/api/score")
def score(p: ScoreIn):
    loan_amnt = _fnum(p.loan_amnt)
    int_rate = _fnum(p.int_rate)
    dti = _fnum(p.dti)
    annual_inc = _fnum(p.annual_inc)
    term_val = 60 if _fint(p.term) >= 60 else 36
    grade_chr = (p.grade or "B").strip().upper()[0]
    revol_util = _fnum(p.revol_util)
    delinq_2yrs = _fint(p.delinq_2yrs)
    open_acc = _fint(p.open_acc)

    if USE_REAL and BOOSTER is not None:
        class _Q:
            pass

        q = _Q()
        q.loan_amnt = loan_amnt
        q.int_rate = int_rate
        q.dti = dti
        q.annual_inc = annual_inc
        q.term = term_val
        q.grade = grade_chr
        q.revol_util = revol_util
        q.delinq_2yrs = delinq_2yrs
        q.open_acc = open_acc

        X = build_row(q)
        y = BOOSTER.predict(X)
        pd_hat = float(np.clip(y[0], 0.0, 1.0))

        feats = []
        if EXPLAINER is not None:
            shap_vals = EXPLAINER.shap_values(X)
            if isinstance(shap_vals, list):
                shap_vals = shap_vals[-1]
            sv = shap_vals[0]
            feats = [{"name": n, "value": float(abs(v))} for n, v in zip(list(X.columns), sv)]
        else:
            gains = BOOSTER.feature_importance(importance_type="gain")
            names = BOOSTER.feature_name() or list(X.columns)
            feats = [{"name": n, "value": float(g)} for n, g in zip(names, gains)]

        feats.sort(key=lambda d: d["value"], reverse=True)
        return {"pd": pd_hat, "feats": feats[:7], "model_version": "real-lightgbm"}

    # MOCK fallback
    gmap = dict(A=0, B=1, C=2, D=3, E=4, F=5, G=6)
    w = dict(
        intercept=-2.0,
        int_rate=0.15,
        dti=0.04,
        annual_inc=-0.000002,
        term=0.2,
        grade=0.18,
        revol_util=0.01,
        delinq_2yrs=0.25,
        open_acc=-0.02,
        loan_amnt=0.000002,
    )
    x = (
        w["intercept"]
        + w["int_rate"] * int_rate
        + w["dti"] * dti
        + w["annual_inc"] * annual_inc
        + w["term"] * (1 if term_val == 60 else 0)
        + w["grade"] * gmap[grade_chr]
        + w["revol_util"] * revol_util
        + w["delinq_2yrs"] * delinq_2yrs
        + w["open_acc"] * open_acc
        + w["loan_amnt"] * loan_amnt
    )
    pd_hat = 1 / (1 + math.exp(-x))
    feats = [
        {"name": "Interest rate (%)", "value": abs(w["int_rate"] * int_rate)},
        {"name": "Debt-to-income (%)", "value": abs(w["dti"] * dti)},
        {"name": "Term (60m flag)", "value": abs(w["term"] * (1 if term_val == 60 else 0))},
        {"name": "Grade (A→G)", "value": abs(w["grade"] * gmap[grade_chr])},
        {"name": "Revolving util (%)", "value": abs(w["revol_util"] * revol_util)},
        {"name": "Annual income (AED)", "value": abs(w["annual_inc"] * annual_inc)},
        {"name": "Delinq in 2 yrs", "value": abs(w["delinq_2yrs"] * delinq_2yrs)},
        {"name": "Open accounts", "value": abs(w["open_acc"] * open_acc)},
        {"name": "Loan amount (AED)", "value": abs(w["loan_amnt"] * loan_amnt)},
    ]
    feats.sort(key=lambda d: d["value"], reverse=True)
    return {"pd": float(pd_hat), "feats": feats[:7], "model_version": "demo-mock"}


# ===============================
# AI: Q&A
# ===============================
@app.post("/ai/qa", response_model=AIQAResponse)
def ai_qa(payload: AIQARequest):
    if oa_client is None:
        return AIQAResponse(
            answer="AI not configured. Set OPENAI_API_KEY to enable AI responses.",
            disclaimer=DISCLAIMER,
        )

    try:
        # If your schema uses `question`, this works; if it's `query`, adjust here.
        user_q = getattr(payload, "question", None) or getattr(payload, "query", None) or ""

        r = oa_client.responses.create(
            model=MODEL_NAME,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are a corporate banking RM copilot. "
                        "Give practical next steps and clarify missing info. "
                        "Be concise and actionable."
                    ),
                },
                {"role": "user", "content": user_q},
            ],
        )

        return AIQAResponse(answer=r.output_text, disclaimer=DISCLAIMER)

    except RateLimitError:
        return AIQAResponse(answer="AI temporarily unavailable (rate limit).", disclaimer=DISCLAIMER)
    except Exception as e:
        return AIQAResponse(answer=f"AI error: {type(e).__name__}", disclaimer=DISCLAIMER)


# ===============================
# AI: Explain deal
# ===============================
@app.post("/ai/explain", response_model=AIExplainResponse)
def ai_explain(payload: AIExplainRequest):
    if oa_client is None:
        return AIExplainResponse(
            executive_summary="AI not configured. Set OPENAI_API_KEY to enable explanations.",
            key_risks_explained=[],
            rm_talking_points=[],
            disclaimer=DISCLAIMER,
        )

    # Accept either a nested object or a dict, depending on your schema
    deal_obj = getattr(payload, "deal_summary", None) or getattr(payload, "deal", None) or payload
    try:
        deal_dict = deal_obj.model_dump() if hasattr(deal_obj, "model_dump") else dict(deal_obj)
    except Exception:
        deal_dict = {"deal": str(deal_obj)}

    prompt = (
        "Explain the deal in RM-friendly terms.\n\n"
        "1) Executive summary (2-3 lines)\n"
        "2) Key risks explained (bullets)\n"
        "3) RM talking points (bullets)\n\n"
        f"Deal data:\n{deal_dict}"
    )

    try:
        r = oa_client.responses.create(
            model=MODEL_NAME,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are a corporate credit/risk assistant. "
                        "Do not invent facts not present in the deal data. "
                        "If information is missing, say what is missing."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )

        # Minimal safe parse: keep everything in exec summary, leave lists empty (you can improve later)
        return AIExplainResponse(
            executive_summary=r.output_text,
            key_risks_explained=[],
            rm_talking_points=[],
            disclaimer=DISCLAIMER,
        )

    except RateLimitError:
        return AIExplainResponse(
            executive_summary="AI temporarily unavailable (rate limit).",
            key_risks_explained=[],
            rm_talking_points=[],
            disclaimer=DISCLAIMER,
        )
    except Exception as e:
        return AIExplainResponse(
            executive_summary=f"AI error: {type(e).__name__}",
            key_risks_explained=[],
            rm_talking_points=[],
            disclaimer=DISCLAIMER,
        )


# ---------- SPA (serve built frontend if present) ----------
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

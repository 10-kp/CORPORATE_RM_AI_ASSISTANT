# api/main.py
from __future__ import annotations

import io
import json
import os
import re
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


# =========================
# Env
# =========================
REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env", override=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-5-mini").strip()
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "").strip()

AI_ENABLED = os.getenv("AI_ENABLED", "false").strip().lower() in {"1", "true", "yes", "y", "on"}
MVP_CURRENCY = "AED"

# =========================
# App
# =========================
app = FastAPI(title="Corporate RM AI Assistant", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN] if FRONTEND_ORIGIN else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# Serve SPA (Vite dist)
# =========================
DIST_DIR = REPO_ROOT / "frontend" / "dist"
ASSETS_DIR = DIST_DIR / "assets"

if DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/", include_in_schema=False)
def root():
    index = DIST_DIR / "index.html"
    if index.exists():
        return Response(content=index.read_text(encoding="utf-8"), media_type="text/html")
    return {"status": "ok", "note": "frontend/dist not found; build frontend for SPA."}


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
# Guardrails (PII)
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
# Schemas (MVP-only)
# =========================
class RatingAnchorIn(BaseModel):
    system: str = "Credit Lens"
    grade: str = "N/A"
    outlook: Optional[str] = "N/A"
    as_of: Optional[str] = "N/A"


class EligibilityIn(BaseModel):
    score: Optional[float] = None
    drivers: List[str] = []


class RMInputsIn(BaseModel):
    client_name: Optional[str] = None
    group_name: Optional[str] = None
    sector: Optional[str] = None
    rating_anchor: Optional[RatingAnchorIn] = None
    eligibility: Optional[EligibilityIn] = None
    indicative_raroc_pct: Optional[float] = None
    notes: Optional[str] = None


class Financials2YIn(BaseModel):
    period_labels: List[str] = ["FY-1", "FY-2"]
    currency: str = MVP_CURRENCY
    confidence: Optional[str] = None
    source: Optional[str] = None

    revenue: List[Optional[float]] = [None, None]
    cogs: List[Optional[float]] = [None, None]
    gross_profit: List[Optional[float]] = [None, None]
    ebitda: List[Optional[float]] = [None, None]
    net_profit: List[Optional[float]] = [None, None]

    total_assets: List[Optional[float]] = [None, None]
    total_equity: List[Optional[float]] = [None, None]

    interest_on_loans: List[Optional[float]] = [None, None]
    cpltd: List[Optional[float]] = [None, None]
    dscr: List[Optional[float]] = [None, None]


class ParseMetaIn(BaseModel):
    filename: Optional[str] = None
    pages_scanned: Optional[int] = None
    tables_found: Optional[int] = None


class CreditApplicationRequest(BaseModel):
    rm_inputs: Optional[Dict[str, Any]] = None
    financials_2y: Optional[Dict[str, Any]] = None
    parse_meta: Optional[Dict[str, Any]] = None


class CreditApplicationResponse(BaseModel):
    credit_application_text: str
    source: Optional[str] = None


class Infer2YRequest(BaseModel):
    text: str
    currency_hint: Optional[str] = None


# =========================
# Numeric helpers
# =========================
_NUM_RE = re.compile(r"\(?-?\d[\d,]*\.?\d*\)?")


def _norm_currency(_: Optional[str]) -> str:
    return MVP_CURRENCY


def _coerce_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        t = x.strip()
        if not t:
            return None
        t = t.replace(",", "")
        if t.startswith("(") and t.endswith(")"):
            t = "-" + t[1:-1]
        try:
            return float(t)
        except Exception:
            return None
    return None


def _pct(numer: Optional[float], denom: Optional[float]) -> Optional[float]:
    if numer is None or denom is None or denom == 0:
        return None
    return (numer / denom) * 100.0


def _fmt_num(x: Optional[float], decimals: int = 0) -> str:
    if x is None:
        return "N/A"
    try:
        if decimals == 0:
            return f"{x:,.0f}"
        return f"{x:,.{decimals}f}"
    except Exception:
        return "N/A"


def _fmt_pct(x: Optional[float]) -> str:
    if x is None:
        return "N/A"
    return f"{x:.2f}%"


def _to_number(raw: Optional[str]) -> Optional[float]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    s = s.replace("**", "").strip()
    m = _NUM_RE.search(s)
    if not m:
        return None
    token = m.group(0).replace(",", "").strip()
    neg = token.startswith("(") and token.endswith(")")
    token = token.strip("()")
    try:
        val = float(token)
        return -val if neg else val
    except Exception:
        return None


def _extract_row_2y(text: str, label: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Extract 2 values from common 'pipe' table rows OR loose rows.
    Works well when parse output contains lines like:
      | Revenue | 485,250 | 432,100 |
    """
    if not text:
        return (None, None)

    lines = text.replace("\u00a0", " ").splitlines()
    label_l = label.lower()

    for ln in lines:
        if label_l not in ln.lower():
            continue

        # pipe-table style
        parts = [p.strip() for p in ln.split("|") if p.strip()]
        if len(parts) >= 3 and label_l in parts[0].lower():
            v1 = _to_number(parts[1])
            v2 = _to_number(parts[2])
            if v1 is not None or v2 is not None:
                return (v1, v2)

        # fallback: first 2 numbers after label
        after = ln.lower().split(label_l, 1)[-1]
        nums = _NUM_RE.findall(after)
        if len(nums) >= 2:
            return (_to_number(nums[0]), _to_number(nums[1]))

    return (None, None)


def _extract_2y_from_line(text: str, label_patterns: List[str]) -> List[Optional[float]]:
    if not text:
        return [None, None]

    t = re.sub(r"[ \t]+", " ", text)

    for pat in label_patterns:
        m = re.search(
            rf"{pat}\s+([(\-]?\d[\d,]*\.?\d*[)]?)\s+([(\-]?\d[\d,]*\.?\d*[)]?)",
            t,
            flags=re.IGNORECASE,
        )
        if m:
            return [_coerce_float(m.group(1)), _coerce_float(m.group(2))]

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
        if e is None or c is None or it is None:
            out.append(None)
            continue
        if c < 0:
            out.append(None)
            continue
        denom = c + abs(it)
        if denom == 0:
            out.append(None)
            continue
        out.append(round(e / denom, 2))
    return out


def _merge_2y(primary: List[Optional[float]], secondary: List[Optional[float]]) -> List[Optional[float]]:
    return primary if (primary[0] is not None or primary[1] is not None) else secondary


# =========================
# Step 1: PDF parse endpoint
# =========================
@app.post("/financials/parse-pdf")
async def parse_pdf(file: UploadFile = File(...)):
    filename = file.filename or "uploaded.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file received.")

    MAX_BYTES = 10 * 1024 * 1024
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="PDF too large. Please upload a PDF under 10MB.")

    try:
        import pdfplumber  # type: ignore
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Dependency error: {type(e).__name__}: {e}")

    try:
        text_parts: List[str] = []
        tables_found = 0

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages_scanned = min(len(pdf.pages), 3)
            for i in range(pages_scanned):
                page = pdf.pages[i]
                txt = (page.extract_text() or "").strip()
                if txt:
                    text_parts.append(f"[Page {i+1}]\n{txt}")

                # count tables best-effort (do NOT serialize table content)
                try:
                    t = page.extract_tables() or []
                    for tbl in t:
                        if tbl and any(any(cell for cell in row) for row in tbl):
                            tables_found += 1
                except Exception:
                    pass

        text_full = "\n\n".join(text_parts).strip()

        # Cap for MVP
        MAX_TEXT_CHARS = 25000
        text = text_full[:MAX_TEXT_CHARS]
        if len(text_full) > MAX_TEXT_CHARS:
            text += "\n... (truncated to 25k chars)"

        text_preview = text if len(text) <= 6000 else (text[:6000] + "\n... (preview truncated)")

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

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"parse-pdf runtime failure: {type(e).__name__}: {e}")


# =========================
# Step 1b: Infer 2Y from text (no-AI deterministic)
# =========================
def _fallback_infer_2y_from_text(text: str, currency_hint: str) -> Dict[str, Any]:
    # Row-based extraction (preferred for pipe/statement tables)
    rev_r = _extract_row_2y(text, "Revenue")
    cogs_r = _extract_row_2y(text, "Cost of Goods Sold")
    gp_r = _extract_row_2y(text, "Gross Profit")
    ebit_r = _extract_row_2y(text, "Operating Profit (EBIT)")
    da_r = _extract_row_2y(text, "Depreciation & Amortization")
    interest_r = _extract_row_2y(text, "Interest on Loans")
    np_r = _extract_row_2y(text, "Net Profit")
    if np_r == (None, None):
        np_r = _extract_row_2y(text, "Net Profit / PAT")

    assets_r = _extract_row_2y(text, "TOTAL ASSETS")
    equity_r = _extract_row_2y(text, "Total Equity")
    cpltd_r = _extract_row_2y(text, "Current Portion of Borrowings")

    revenue_row = [rev_r[0], rev_r[1]]
    cogs_row = [cogs_r[0], cogs_r[1]]
    gross_profit_row = [gp_r[0], gp_r[1]]
    net_profit_row = [np_r[0], np_r[1]]
    total_assets_row = [assets_r[0], assets_r[1]]
    total_equity_row = [equity_r[0], equity_r[1]]
    interest_row = [interest_r[0], interest_r[1]]
    cpltd_row = [cpltd_r[0], cpltd_r[1]]

    ebitda_row = [
        (ebit_r[0] + abs(da_r[0])) if (ebit_r[0] is not None and da_r[0] is not None) else None,
        (ebit_r[1] + abs(da_r[1])) if (ebit_r[1] is not None and da_r[1] is not None) else None,
    ]

    # Regex fallback extraction (loose text PDFs)
    revenue = _extract_2y_from_line(text, [r"\bRevenue\b", r"\bSales\b"])
    cogs = _extract_2y_from_line(text, [r"\bCost\s+of\s+Goods\s+Sold\b", r"\bCOGS\b", r"\bCost\s+of\s+Sales\b"])
    gross_profit = _extract_2y_from_line(text, [r"\bGross\s+Profit\b"])
    net_profit = _extract_2y_from_line(text, [r"\bNet\s+Profit\b", r"\bProfit\s+after\s+tax\b", r"\bPAT\b"])
    ebitda = _extract_2y_from_line(text, [r"\bEBITDA\b"])

    ebit = _extract_2y_from_line(text, [r"\bEBIT\b", r"\bOperating\s+Profit\b", r"\bProfit\s+from\s+Operations\b"])
    depr_amort = _extract_2y_from_line(
        text, [r"\bDepreciation\b", r"\bAmortization\b", r"\bDepreciation\s+and\s+Amortization\b"]
    )
    if ebitda == [None, None]:
        ebitda = [
            (ebit[0] + abs(depr_amort[0])) if (ebit[0] is not None and depr_amort[0] is not None) else None,
            (ebit[1] + abs(depr_amort[1])) if (ebit[1] is not None and depr_amort[1] is not None) else None,
        ]

    total_assets = _extract_2y_from_line(text, [r"\bTotal\s+Assets\b"])
    total_equity = _extract_2y_from_line(text, [r"\bTotal\s+Equity\b", r"\bShareholders'\s+Equity\b"])
    interest = _extract_2y_from_line(
        text, [r"\bInterest\b\s+\bExpense\b", r"\bInterest\b\s+\bon\b\s+\bLoans\b", r"\bFinance\b\s+\bCost\b"]
    )
    cpltd = _extract_2y_from_line(
        text,
        [
            r"\bCurrent\s+portion\s+of\s+long[- ]term\s+debt\b",
            r"\bCurrent\s+maturities\s+of\s+borrowings\b",
            r"\bCPLTD\b",
        ],
    )

    # Prefer row-based when present
    revenue = _merge_2y(revenue_row, revenue)
    cogs = _merge_2y(cogs_row, cogs)
    gross_profit = _merge_2y(gross_profit_row, gross_profit)
    net_profit = _merge_2y(net_profit_row, net_profit)
    total_assets = _merge_2y(total_assets_row, total_assets)
    total_equity = _merge_2y(total_equity_row, total_equity)
    interest = _merge_2y(interest_row, interest)
    cpltd = _merge_2y(cpltd_row, cpltd)
    ebitda = _merge_2y(ebitda_row, ebitda)

    # Compute GP if still missing
    if gross_profit == [None, None]:
        gross_profit = [
            (revenue[0] - cogs[0]) if (revenue[0] is not None and cogs[0] is not None) else None,
            (revenue[1] - cogs[1]) if (revenue[1] is not None and cogs[1] is not None) else None,
        ]

    dscr = _compute_dscr_2y(ebitda, cpltd, interest)

    core_fields = revenue + cogs + gross_profit + net_profit + ebitda + total_assets + total_equity + interest + cpltd
    missing = sum(x is None for x in core_fields)
    confidence = "High" if missing == 0 else ("Medium" if missing <= 4 else "Low")

    return {
        "financials_2y": {
            "period_labels": ["FY-1", "FY-2"],
            "currency": currency_hint,
            "confidence": confidence,
            "source": "Fallback (row + regex + deterministic)",
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
        }
    }


@app.post("/financials/infer-2y")
def infer_2y(req: Infer2YRequest):
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Missing text.")
    currency_hint = _norm_currency(req.currency_hint)
    out = _fallback_infer_2y_from_text(text, currency_hint)
    return out


# =========================
# Hybrid credit memo builder (MVP judge-friendly)
# =========================
def _yoy_pct(latest: Optional[float], prior: Optional[float]) -> Optional[float]:
    if latest is None or prior is None or prior == 0:
        return None
    return ((latest - prior) / abs(prior)) * 100.0


def _margin_comment(metric_name: str, latest: Optional[float], prior: Optional[float]) -> str:
    if latest is None or prior is None:
        return f"{metric_name}: N/A."
    if latest > prior:
        return f"{metric_name} expanded modestly ({latest:.2f}% vs {prior:.2f}%)."
    if latest < prior:
        return f"{metric_name} compressed modestly ({latest:.2f}% vs {prior:.2f}%)."
    return f"{metric_name} was broadly stable ({latest:.2f}% vs {prior:.2f}%)."


def _dscr_sentence(dscr_latest: Optional[float], dscr_prior: Optional[float]) -> str:
    if dscr_latest is None:
        return "Debt service capacity: N/A (DSCR not available from extracted data)."
    prior_txt = f" (prior {dscr_prior:.2f}x)" if dscr_prior is not None else ""
    if dscr_latest >= 1.2:
        return f"Debt service capacity is strong: deterministic DSCR {dscr_latest:.2f}x{prior_txt}."
    if dscr_latest >= 1.0:
        return f"Debt service capacity is marginal: deterministic DSCR {dscr_latest:.2f}x{prior_txt} (structuring / monitoring focus)."
    return f"Debt service capacity is weak: deterministic DSCR {dscr_latest:.2f}x{prior_txt}."


def _build_hybrid_credit_text(rm_inputs: Dict[str, Any], fin: Dict[str, Any], parse_meta: Optional[Dict[str, Any]]) -> str:
    # RM
    client = str(rm_inputs.get("client_name") or "Client").strip() or "Client"
    group = str(rm_inputs.get("group_name") or "").strip() or None
    sector = str(rm_inputs.get("sector") or "N/A")

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
    elig_drivers = [str(x) for x in elig_drivers]

    raroc = rm_inputs.get("indicative_raroc_pct")

    # FIN (2Y)
    period_labels = fin.get("period_labels") or ["FY-1", "FY-2"]
    p1, p2 = (period_labels + ["FY-1", "FY-2"])[:2]
    currency = _norm_currency(fin.get("currency"))

    def _get2(key: str) -> List[Optional[float]]:
        v = fin.get(key)
        if isinstance(v, list) and len(v) >= 2:
            return [_coerce_float(v[0]), _coerce_float(v[1])]
        return [None, None]

    rev = _get2("revenue")
    cogs = _get2("cogs")
    gp = _get2("gross_profit")
    ebitda = _get2("ebitda")
    np = _get2("net_profit")
    interest = _get2("interest_on_loans")
    cpltd = _get2("cpltd")
    dscr = _get2("dscr")

    # compute margins
    gm1 = _pct(gp[0], rev[0])
    gm2 = _pct(gp[1], rev[1])
    nm1 = _pct(np[0], rev[0])
    nm2 = _pct(np[1], rev[1])

    # YoY
    rev_yoy = _yoy_pct(rev[0], rev[1])
    ebitda_yoy = _yoy_pct(ebitda[0], ebitda[1])
    np_yoy = _yoy_pct(np[0], np[1])

    # meta
    meta_line = ""
    if parse_meta:
        meta_line = (
            f"Source file: {parse_meta.get('filename','N/A')} | "
            f"Pages scanned: {parse_meta.get('pages_scanned','N/A')} | "
            f"Tables found: {parse_meta.get('tables_found','N/A')}"
        )

    # Build output
    lines: List[str] = []
    lines.append("1) Executive Summary (5–8 bullets)")
    lines.append(f"- Issuer: {client}" + (f" (Group: {group})" if group else "") + f"; sector: {sector}.")
    lines.append(f"- Internal anchor: {rating_sys}; grade {rating_grade} with {outlook} outlook (as-of {as_of}).")
    if elig_score is not None:
        try:
            es = float(elig_score)
            drivers_txt = f", driven by {', '.join(elig_drivers)}" if elig_drivers else ""
            lines.append(f"- Eligibility score {es:.1f}/6{drivers_txt}.")
        except Exception:
            lines.append(f"- Eligibility score {elig_score}/6.")
    else:
        lines.append("- Eligibility score: N/A (RM input missing).")

    # Growth bullet
    growth_parts = []
    if rev_yoy is not None:
        growth_parts.append(f"revenue {_fmt_pct(rev_yoy)}")
    if ebitda_yoy is not None:
        growth_parts.append(f"EBITDA {_fmt_pct(ebitda_yoy)}")
    if np_yoy is not None:
        growth_parts.append(f"net profit {_fmt_pct(np_yoy)}")
    if growth_parts:
        lines.append(f"- Top-line and profitability moved year-on-year: {', '.join(growth_parts)}.")
    else:
        lines.append("- Top-line and profitability: N/A (insufficient extracted data).")

    # Margins bullet
    if gm1 is not None and gm2 is not None:
        lines.append(f"- Margins: gross margin {gm1:.2f}% (prior {gm2:.2f}%).")
    else:
        lines.append("- Gross margin: N/A.")
    if nm1 is not None and nm2 is not None:
        lines.append(f"- Net margin {nm1:.2f}% (prior {nm2:.2f}%).")
    else:
        lines.append("- Net margin: N/A.")

    lines.append(f"- {_dscr_sentence(dscr[0], dscr[1])}")
    if raroc is not None:
        try:
            lines.append(f"- Indicative RAROC {float(raroc):.1f}%.")
        except Exception:
            lines.append(f"- Indicative RAROC {raroc}%.")
    else:
        lines.append("- Indicative RAROC: N/A.")

    if interest[0] is not None or cpltd[0] is not None:
        i0 = abs(interest[0]) if interest[0] is not None else None
        i1 = abs(interest[1]) if interest[1] is not None else None
        lines.append(
            f"- Debt service inputs: interest expense {p1} {_fmt_num(i0)}"
            + (f" (prior {_fmt_num(i1)})" if i1 is not None else "")
            + f"; CPLTD {p1} {_fmt_num(cpltd[0])} (prior {_fmt_num(cpltd[1])})."
        )

    lines.append("")
    lines.append("2) Financial Snapshot (2–3 short paragraphs)")
    if rev[0] is not None and rev[1] is not None:
        lines.append(
            f"Latest-period financials show {('growth' if (rev_yoy or 0) >= 0 else 'contraction')} "
            f"with revenue at {_fmt_num(rev[0])} vs {_fmt_num(rev[1])} ({currency}). "
            f"Gross profit is {_fmt_num(gp[0])} vs {_fmt_num(gp[1])}, supporting EBITDA of {_fmt_num(ebitda[0])} "
            f"and net profit of {_fmt_num(np[0])} in the latest period."
        )
    else:
        lines.append("Latest-period financials: N/A (insufficient extracted income statement data).")

    lines.append(
        f"{_margin_comment('Gross margin', gm1, gm2)} "
        f"{_margin_comment('Net margin', nm1, nm2)}"
    )

    lines.append(
        f"{_dscr_sentence(dscr[0], dscr[1])} "
        "Metrics are based on extracted source text and must be validated against audited statements prior to committee submission."
    )

    lines.append("")
    lines.append("3) Key Risks and Mitigants (3–5 bullets)")
    lines.append("- No automated/data-driven risk flags are triggered under the MVP rules where quantitative data is available.")
    lines.append("- Extraction is best-effort; validate figures against audited statements (disclaimer applies).")
    lines.append("- Business-profile and operational risks remain RM-owned; final credit view must incorporate qualitative due diligence.")

    lines.append("")
    lines.append("4) Recommendation (1 paragraph)")
    posture = "SUPPORT" if (dscr[0] is None or dscr[0] >= 1.2) else "CAUTION"
    lines.append(
        f"Posture: {posture} — based on extracted performance indicators, including year-on-year trends, "
        f"margin movement and deterministic DSCR where available. Prior to final Credit Committee approval, "
        f"require validation of extracted numbers against audited source documents and completion of RM qualitative sections."
    )

    if meta_line:
        lines.append("")
        lines.append(f"[MVP metadata] {meta_line}")

    return "\n".join(lines).strip()


# =========================
# Step 3 (HYBRID) endpoint used by UI
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

    fin = dict(fin)
    fin["currency"] = _norm_currency(fin.get("currency"))
    fin.setdefault("period_labels", ["FY-1", "FY-2"])

    draft = _build_hybrid_credit_text(rm_inputs, fin, parse_meta)

    # AI OFF
    if oa_client is None:
        return CreditApplicationResponse(
            credit_application_text=draft,
            source="Deterministic template (AI disabled)",
        )

    # AI ON (polish-only)
    prompt = f"""
You are a senior corporate credit analyst.

Rewrite the following credit note for Credit Committee review:
- Keep the structure exactly (Executive Summary / Financial Snapshot / Key Risks / Recommendation)
- Do NOT add, infer, or change any numbers
- Do NOT introduce new facts
- Preserve N/A items as N/A
Return plain text only.

Text:
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

// frontend/src/App.tsx
import { useMemo, useState } from "react";
import "./App.css";

type DealInputRequest = {
  client_name: string;
  group_name?: string | null;
  strategic_sector: string;

  rating_system: string;
  rating_grade: string;
  outlook?: string | null;
  as_of?: string | null;

  eligibility_score: number;
  eligibility_drivers?: string | null;

  revenue_trend_3y: string;
  margin_trend_3y: string;
  leverage_position: string;
  cash_flow_quality: string;
  earnings_volatility: string;
  capex_growth_investment: string;
  financial_transparency: string;

  indicative_raroc_pct?: number | null;

  notes?: string | null;
};

type DealSummaryResponse = {
  // Keep this flexible; backend may add fields over time
  [key: string]: any;
};

type AIExplainResponse = {
  explanation: string;
};

type AIQAResponse = {
  answer: string;
};

const SECTORS = [
  "Manufacturing",
  "Healthcare",
  "Advanced technology",
  "Food security",
  "Renewables",
];

const OUTLOOKS = ["Stable", "Positive", "Negative", "Watch"];
const TRENDS = ["Improving", "Stable", "Deteriorating"];
const POSITIONS = ["Low", "Moderate", "High"];
const QUALITIES = ["Strong", "Adequate", "Weak"];
const VOLATILITY = ["Low", "Moderate", "High"];
const INVESTMENT = ["Low", "Moderate", "High"];
const TRANSPARENCY = ["Strong", "Adequate", "Weak"];
const RATING_SYSTEMS = ["Credit Lens"];

function asText(v: any): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "string") return v;
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}

function isNumberOrEmpty(v: string): boolean {
  if (v === "") return true;
  return !Number.isNaN(Number(v));
}

export default function App() {
  const API_BASE =
    (import.meta as any).env?.VITE_API_BASE?.trim() || "http://127.0.0.1:8000";

  // -------------------------
  // Form state (left panel)
  // -------------------------
  const [clientName, setClientName] = useState<string>("");
  const [groupName, setGroupName] = useState<string>("");
  const [sector, setSector] = useState<string>(SECTORS[0]);

  const [ratingSystem, setRatingSystem] = useState<string>(RATING_SYSTEMS[0]);
  const [ratingGrade, setRatingGrade] = useState<string>("");
  const [outlook, setOutlook] = useState<string>(OUTLOOKS[0]);
  const [asOf, setAsOf] = useState<string>("");

  const [eligibilityScore, setEligibilityScore] = useState<string>("3.5");
  const [eligibilityDrivers, setEligibilityDrivers] = useState<string>("");

  const [revTrend, setRevTrend] = useState<string>(TRENDS[1]);
  const [marginTrend, setMarginTrend] = useState<string>(TRENDS[1]);
  const [leveragePos, setLeveragePos] = useState<string>(POSITIONS[1]);
  const [cfQuality, setCfQuality] = useState<string>(QUALITIES[1]);
  const [earnVol, setEarnVol] = useState<string>(VOLATILITY[1]);
  const [capex, setCapex] = useState<string>(INVESTMENT[1]);
  const [transparency, setTransparency] = useState<string>(TRANSPARENCY[1]);

  // NEW: RAROC (RM-entered)
  const [indicativeRarocPct, setIndicativeRarocPct] = useState<string>("");

  const [notes, setNotes] = useState<string>("");

  // -------------------------
  // Outputs (right panel)
  // -------------------------
  const [assessResult, setAssessResult] = useState<DealSummaryResponse | null>(
    null
  );
  const [aiExplain, setAiExplain] = useState<string>("");
  const [aiQA, setAiQA] = useState<string>("");
  const [qaQuestion, setQaQuestion] = useState<string>("");

  const [busyAssess, setBusyAssess] = useState<boolean>(false);
  const [busyExplain, setBusyExplain] = useState<boolean>(false);
  const [busyQA, setBusyQA] = useState<boolean>(false);

  const [errorMsg, setErrorMsg] = useState<string>("");

  const canAssess = useMemo(() => {
    if (!clientName.trim()) return false;
    if (!ratingGrade.trim()) return false;
    if (!isNumberOrEmpty(eligibilityScore) || eligibilityScore === "")
      return false;
    // RAROC is optional; if provided, must be numeric
    if (!isNumberOrEmpty(indicativeRarocPct)) return false;
    return true;
  }, [clientName, ratingGrade, eligibilityScore, indicativeRarocPct]);

  function buildPayload(): DealInputRequest {
    const elig = Number(eligibilityScore);

    const raroc =
      indicativeRarocPct.trim() === "" ? null : Number(indicativeRarocPct);

    return {
      client_name: clientName.trim(),
      group_name: groupName.trim() ? groupName.trim() : null,
      strategic_sector: sector,

      rating_system: ratingSystem,
      rating_grade: ratingGrade.trim(),
      outlook: outlook || null,
      as_of: asOf.trim() ? asOf.trim() : null,

      eligibility_score: elig,
      eligibility_drivers: eligibilityDrivers.trim()
        ? eligibilityDrivers.trim()
        : null,

      revenue_trend_3y: revTrend,
      margin_trend_3y: marginTrend,
      leverage_position: leveragePos,
      cash_flow_quality: cfQuality,
      earnings_volatility: earnVol,
      capex_growth_investment: capex,
      financial_transparency: transparency,

      indicative_raroc_pct: raroc,

      notes: notes.trim() ? notes.trim() : null,
    };
  }

  async function postJSON<T>(path: string, body: any): Promise<T> {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const t = await res.text();
      throw new Error(
        `HTTP ${res.status} ${res.statusText}${t ? ` — ${t}` : ""}`
      );
    }
    return (await res.json()) as T;
  }

  async function onAssess() {
    setErrorMsg("");
    setAiExplain("");
    setAiQA("");
    setAssessResult(null);

    setBusyAssess(true);
    try {
      const payload = buildPayload();
      const result = await postJSON<DealSummaryResponse>("/assess", payload);
      setAssessResult(result);
    } catch (e: any) {
      setErrorMsg(e?.message || "Assessment failed.");
    } finally {
      setBusyAssess(false);
    }
  }

  async function onExplain() {
    setErrorMsg("");
    setAiExplain("");

    if (!assessResult) {
      setErrorMsg("Run /assess first. Explanation requires an assessment.");
      return;
    }

    setBusyExplain(true);
    try {
      // Backend contract usually expects { deal_summary: ... } or { assessment: ... }.
      // We send a safe structure: { deal_summary: assessResult }
      const resp = await postJSON<AIExplainResponse>("/ai/explain", {
        deal_summary: assessResult,
      });
      setAiExplain(resp.explanation || "");
    } catch (e: any) {
      setErrorMsg(e?.message || "AI explain failed.");
    } finally {
      setBusyExplain(false);
    }
  }

  async function onAsk() {
    setErrorMsg("");
    setAiQA("");

    const q = qaQuestion.trim();
    if (!q) {
      setErrorMsg("Enter a question first.");
      return;
    }

    setBusyQA(true);
    try {
      const resp = await postJSON<AIQAResponse>("/ai/qa", {
        question: q,
        deal_summary: assessResult, // may be null if user didn’t run assess; backend can handle
      });
      setAiQA(resp.answer || "");
    } catch (e: any) {
      setErrorMsg(e?.message || "AI Q&A failed.");
    } finally {
      setBusyQA(false);
    }
  }

  function clearAll() {
    setErrorMsg("");
    setAssessResult(null);
    setAiExplain("");
    setAiQA("");
    setQaQuestion("");
  }

  function clearAI() {
    setErrorMsg("");
    setAiExplain("");
    setAiQA("");
  }

  // -------------------------
  // Render
  // -------------------------
  return (
    <div className="app">
      <header className="app-header">
        <h1>Corporate RM Deal Readiness &amp; Mandate Fit Assistant</h1>
        <div className="subtle">/assess + AI explain + deal Q&amp;A</div>
      </header>

      <main className="grid">
        {/* LEFT: Inputs */}
        <section className="panel">
          <h2>Client</h2>

          <label>Client name *</label>
          <input
            value={clientName}
            onChange={(e) => setClientName(e.target.value)}
            placeholder="e.g., ABC Manufacturing LLC"
          />

          <label>Group name</label>
          <input
            value={groupName}
            onChange={(e) => setGroupName(e.target.value)}
            placeholder="Optional"
          />

          <label>Strategic sector</label>
          <select value={sector} onChange={(e) => setSector(e.target.value)}>
            {SECTORS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>

          <h2>Rating anchor</h2>

          <label>System</label>
          <select
            value={ratingSystem}
            onChange={(e) => setRatingSystem(e.target.value)}
          >
            {RATING_SYSTEMS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>

          <label>Rating grade *</label>
          <input
            value={ratingGrade}
            onChange={(e) => setRatingGrade(e.target.value)}
            placeholder="e.g., Baa3 / B / BB (as per system)"
          />

          <label>Outlook</label>
          <select value={outlook} onChange={(e) => setOutlook(e.target.value)}>
            {OUTLOOKS.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>

          <label>As of (YYYY-MM-DD)</label>
          <input
            value={asOf}
            onChange={(e) => setAsOf(e.target.value)}
            placeholder="Optional"
          />

          <h2>Eligibility</h2>

          <label>Eligibility score (0–6) *</label>
          <input
            type="number"
            step="0.1"
            min="0"
            max="6"
            value={eligibilityScore}
            onChange={(e) => setEligibilityScore(e.target.value)}
          />

          <label>Eligibility drivers (comma-separated)</label>
          <input
            value={eligibilityDrivers}
            onChange={(e) => setEligibilityDrivers(e.target.value)}
            placeholder="e.g., Job creation, Exports, Import substitution"
          />

          <h2>Financial signals</h2>

          <label>Revenue trend (3Y)</label>
          <select value={revTrend} onChange={(e) => setRevTrend(e.target.value)}>
            {TRENDS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>

          <label>Margin trend (3Y)</label>
          <select
            value={marginTrend}
            onChange={(e) => setMarginTrend(e.target.value)}
          >
            {TRENDS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>

          <label>Leverage position</label>
          <select
            value={leveragePos}
            onChange={(e) => setLeveragePos(e.target.value)}
          >
            {POSITIONS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>

          <label>Cash flow quality</label>
          <select
            value={cfQuality}
            onChange={(e) => setCfQuality(e.target.value)}
          >
            {QUALITIES.map((q) => (
              <option key={q} value={q}>
                {q}
              </option>
            ))}
          </select>

          <label>Earnings volatility</label>
          <select
            value={earnVol}
            onChange={(e) => setEarnVol(e.target.value)}
          >
            {VOLATILITY.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>

          <label>Capex / growth investment</label>
          <select value={capex} onChange={(e) => setCapex(e.target.value)}>
            {INVESTMENT.map((i) => (
              <option key={i} value={i}>
                {i}
              </option>
            ))}
          </select>

          <label>Financial transparency</label>
          <select
            value={transparency}
            onChange={(e) => setTransparency(e.target.value)}
          >
            {TRANSPARENCY.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>

          {/* NEW: RAROC input box */}
          <h2>Risk–Return check</h2>
          <label>Indicative RAROC (%)</label>
          <input
            type="number"
            step="0.1"
            min="0"
            max="100"
            value={indicativeRarocPct}
            onChange={(e) => setIndicativeRarocPct(e.target.value)}
            placeholder="e.g., 4.8"
          />
          <div className="subtle">
            RM-entered screening input. Non-binding; final pricing/return remains
            subject to Credit validation.
          </div>

          <h2>Notes</h2>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Optional RM notes"
            rows={5}
          />

          <div className="btn-row">
            <button onClick={onAssess} disabled={!canAssess || busyAssess}>
              {busyAssess ? "Assessing..." : "Assess deal"}
            </button>
            <button onClick={clearAll} className="secondary">
              Clear result
            </button>
          </div>

          <div className="subtle">
            Backend endpoints (frontend calls): <code>/assess</code>,{" "}
            <code>/ai/explain</code>, <code>/ai/qa</code>
          </div>

          {errorMsg && <div className="error">{errorMsg}</div>}
        </section>

        {/* RIGHT: Outputs */}
        <section className="panel">
          <h2>Assessment output</h2>
          <div className="subtle">
            Run an assessment to see deal readiness, constraints, and RM actions.
          </div>

          <pre className="output">{assessResult ? asText(assessResult) : ""}</pre>

          <div className="box">
            <h3>AI: Explain assessment</h3>
            <div className="subtle">
              Uses <code>/ai/explain</code>. Requires an assessment result.
            </div>
            <div className="btn-row">
              <button
                onClick={onExplain}
                disabled={!assessResult || busyExplain}
              >
                {busyExplain ? "Generating..." : "Generate explanation"}
              </button>
              <button onClick={clearAI} className="secondary">
                Clear AI output
              </button>
            </div>
            <pre className="output">{aiExplain}</pre>
          </div>

          <div className="box">
            <h3>AI: Deal Q&amp;A</h3>
            <div className="subtle">
              Uses <code>/ai/qa</code>. If you ran <code>/assess</code>, it will
              pass the deal summary to AI.
            </div>
            <div className="qa-row">
              <input
                value={qaQuestion}
                onChange={(e) => setQaQuestion(e.target.value)}
                placeholder="e.g., What are the top 3 approval risks?"
              />
              <button onClick={onAsk} disabled={busyQA}>
                {busyQA ? "..." : "Ask"}
              </button>
            </div>
            <pre className="output">{aiQA}</pre>
          </div>

          <div className="subtle">
            API base: <code>{API_BASE}</code>
          </div>
        </section>
      </main>
    </div>
  );
}

import { useEffect, useMemo, useRef, useState } from "react";
import "./App.css";

/**
 * API base:
 * - Local dev: http://127.0.0.1:8000
 * - Render: same-origin (empty string) so fetch("/assess") works
 */
function getApiBase() {
  const envBase = (import.meta as any).env?.VITE_API_BASE?.trim?.() || "";
  if (envBase) return envBase;
  const host = window.location.hostname;
  if (host === "localhost" || host === "127.0.0.1") return "http://127.0.0.1:8000";
  return "";
}

const API_BASE = getApiBase();

type StrategicSector =
  | "Manufacturing"
  | "Advanced Technology"
  | "Healthcare"
  | "Food Security"
  | "Renewables"
  | "Other";

type Trend3Y = "Improving" | "Stable" | "Declining";
type MarginTrend3Y = "Improving" | "Stable" | "Under Pressure";
type Signal3 = "Strong" | "Adequate" | "Weak";
type Leverage = "Low" | "Moderate" | "Elevated";
type Volatility = "Low" | "Moderate" | "High";
type Investment = "High" | "Moderate" | "Low";

type DealReadinessStatus = "Strong" | "Conditional" | "Weak";
type Decision = "Proceed" | "Restructure" | "Decline" | "N/A";

type RatingAnchor = {
  system: string;
  grade: string;
  outlook?: string | null;
  as_of?: string | null;
};

type Eligibility = {
  score: number;
  drivers: string[];
  breakdown?: Record<string, number>;
};

type FinancialSignals = {
  revenue_trend_3y: Trend3Y;
  margin_trend_3y: MarginTrend3Y;
  leverage_position: Leverage;
  cashflow_quality: Signal3;
  earnings_volatility: Volatility;
  capex_growth_investment: Investment;
  financial_transparency: Signal3;
};

type DealReadinessOut = {
  status: DealReadinessStatus;
  strengths: string[];
  constraints: string[];
};

type DealSummaryResponse = {
  client_name: string;
  group_name?: string | null;
  sector: StrategicSector;

  rating_anchor: RatingAnchor;
  eligibility: Eligibility;
  financial_signals: FinancialSignals;

  indicative_raroc_pct?: number | null;

  deal_readiness: DealReadinessOut;
  mandate_fit_summary: string;

  rm_actions: string[];
  talking_points: string[];

  created_at?: string | null;
  notes?: string | null;
};

type AIExplainResponse = {
  executive_summary: string;
  key_risks_explained: string[];
  rm_talking_points: string[];
  missing_information?: string[];
  disclaimer: string;
};

type AIQAResponse = {
  decision: Decision;
  rationale: string[];
  conditions_next_steps: string[];
  answer: string;
  disclaimer: string;
};

async function postJSON<T>(path: string, body: any): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(txt || `Request failed (${res.status})`);
  }
  return (await res.json()) as T;
}

function safeNum(v: any, fallback: number) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function splitDrivers(s: string): string[] {
  return (s || "")
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
}

export default function App() {
  // Scroll target: right panel
  const resultRef = useRef<HTMLDivElement | null>(null);

  // Inputs
  const [clientName, setClientName] = useState("");
  const [groupName, setGroupName] = useState("");
  const [sector, setSector] = useState<StrategicSector>("Manufacturing");

  const [ratingSystem, setRatingSystem] = useState("Credit Lens");
  const [ratingGrade, setRatingGrade] = useState("6");
  const [outlook, setOutlook] = useState<string>("Stable");
  const [asOf, setAsOf] = useState<string>("");

  const [eligScore, setEligScore] = useState<number>(3.0);
  const [eligDrivers, setEligDrivers] = useState<string>("");

  const [revTrend, setRevTrend] = useState<Trend3Y>("Stable");
  const [marginTrend, setMarginTrend] = useState<MarginTrend3Y>("Stable");
  const [leverage, setLeverage] = useState<Leverage>("Moderate");
  const [cashflow, setCashflow] = useState<Signal3>("Adequate");
  const [volatility, setVolatility] = useState<Volatility>("Moderate");
  const [capex, setCapex] = useState<Investment>("Moderate");
  const [transparency, setTransparency] = useState<Signal3>("Adequate");

  const [raroc, setRaroc] = useState<number>(4.3);
  const [notes, setNotes] = useState<string>("");

  // Outputs
  const [assessResult, setAssessResult] = useState<DealSummaryResponse | null>(null);
  const [showRaw, setShowRaw] = useState(false);

  const [aiExplain, setAiExplain] = useState<AIExplainResponse | null>(null);
  const [aiQa, setAiQa] = useState<AIQAResponse | null>(null);
  const [qaQuestion, setQaQuestion] = useState("");

  // Busy / error
  const [busyAssess, setBusyAssess] = useState(false);
  const [busyExplain, setBusyExplain] = useState(false);
  const [busyQa, setBusyQa] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const payload = useMemo(() => {
    return {
      client_name: clientName,
      group_name: groupName || null,
      sector,
      rating_anchor: {
        system: ratingSystem,
        grade: ratingGrade,
        outlook: outlook || null,
        as_of: asOf || null,
      },
      eligibility: {
        score: safeNum(eligScore, 0),
        drivers: splitDrivers(eligDrivers),
      },
      financial_signals: {
        revenue_trend_3y: revTrend,
        margin_trend_3y: marginTrend,
        leverage_position: leverage,
        cashflow_quality: cashflow,
        earnings_volatility: volatility,
        capex_growth_investment: capex,
        financial_transparency: transparency,
      },
      indicative_raroc_pct: safeNum(raroc, 0),
      notes: notes || null,
    };
  }, [
    clientName,
    groupName,
    sector,
    ratingSystem,
    ratingGrade,
    outlook,
    asOf,
    eligScore,
    eligDrivers,
    revTrend,
    marginTrend,
    leverage,
    cashflow,
    volatility,
    capex,
    transparency,
    raroc,
    notes,
  ]);

  // Auto-scroll after assessResult appears
  useEffect(() => {
    if (assessResult) {
      // allow DOM paint
      setTimeout(() => {
        resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 50);
    }
  }, [assessResult]);

  async function onAssess() {
    setErrorMsg("");
    setShowRaw(false);
    setAiExplain(null);
    setAiQa(null);

    setBusyAssess(true);
    try {
      const res = await postJSON<DealSummaryResponse>("/assess", payload);
      setAssessResult(res);
    } catch (e: any) {
      setErrorMsg(e?.message || "Assessment failed.");
      setAssessResult(null);
    } finally {
      setBusyAssess(false);
    }
  }

  async function onExplain() {
    if (!assessResult) return;
    setErrorMsg("");
    setBusyExplain(true);
    try {
      const res = await postJSON<AIExplainResponse>("/ai/explain", { deal_summary: assessResult });
      setAiExplain(res);
    } catch (e: any) {
      setErrorMsg(e?.message || "Explain failed.");
      setAiExplain(null);
    } finally {
      setBusyExplain(false);
    }
  }

  async function onAskQa() {
    setErrorMsg("");
    setBusyQa(true);
    try {
      const res = await postJSON<AIQAResponse>("/ai/qa", {
        question: qaQuestion,
        deal_summary: assessResult,
      });
      setAiQa(res);
    } catch (e: any) {
      setErrorMsg(e?.message || "Q&A failed.");
      setAiQa(null);
    } finally {
      setBusyQa(false);
    }
  }

  function onClear() {
    setErrorMsg("");
    setAssessResult(null);
    setAiExplain(null);
    setAiQa(null);
    setQaQuestion("");
    setShowRaw(false);
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>Corporate RM Deal Readiness &amp; Mandate Fit Assistant</h1>
        <div className="subtle">Assessment + explanation + deal Q&amp;A</div>
      </header>

      {errorMsg ? (
        <div className="error" style={{ margin: "10px 0" }}>
          {errorMsg}
        </div>
      ) : null}

      <main className="grid">
        {/* LEFT: Inputs */}
        <section className="panel">
          <h2>Inputs</h2>

          <label>Client name *</label>
          <input value={clientName} onChange={(e) => setClientName(e.target.value)} placeholder="Client name" />

          <label>Group name</label>
          <input value={groupName} onChange={(e) => setGroupName(e.target.value)} placeholder="Group name" />

          <label>Strategic sector</label>
          <select value={sector} onChange={(e) => setSector(e.target.value as StrategicSector)}>
            <option>Manufacturing</option>
            <option>Advanced Technology</option>
            <option>Healthcare</option>
            <option>Food Security</option>
            <option>Renewables</option>
            <option>Other</option>
          </select>

          <hr />

          <h3>Rating anchor</h3>
          <label>System</label>
          <select value={ratingSystem} onChange={(e) => setRatingSystem(e.target.value)}>
            <option>Credit Lens</option>
          </select>

          <label>Rating grade *</label>
          <input value={ratingGrade} onChange={(e) => setRatingGrade(e.target.value)} placeholder="e.g. 6" />

          <label>Outlook</label>
          <select value={outlook} onChange={(e) => setOutlook(e.target.value)}>
            <option>Stable</option>
            <option>Positive</option>
            <option>Negative</option>
            <option>Watch</option>
          </select>

          <label>As of (YYYY-MM-DD)</label>
          <input value={asOf} onChange={(e) => setAsOf(e.target.value)} placeholder="Optional" />

          <hr />

          <h3>Eligibility</h3>
          <label>Eligibility score (0–6) *</label>
          <input
            type="number"
            step="0.1"
            value={eligScore}
            onChange={(e) => setEligScore(safeNum(e.target.value, 0))}
          />

          <label>Eligibility drivers (comma-separated)</label>
          <input value={eligDrivers} onChange={(e) => setEligDrivers(e.target.value)} placeholder="e.g., ICV, jobs" />

          <hr />

          <h3>Financial signals</h3>
          <label>Revenue trend (3Y)</label>
          <select value={revTrend} onChange={(e) => setRevTrend(e.target.value as Trend3Y)}>
            <option>Improving</option>
            <option>Stable</option>
            <option>Declining</option>
          </select>

          <label>Margin trend (3Y)</label>
          <select value={marginTrend} onChange={(e) => setMarginTrend(e.target.value as MarginTrend3Y)}>
            <option>Improving</option>
            <option>Stable</option>
            <option>Under Pressure</option>
          </select>

          <label>Leverage position</label>
          <select value={leverage} onChange={(e) => setLeverage(e.target.value as Leverage)}>
            <option>Low</option>
            <option>Moderate</option>
            <option>Elevated</option>
          </select>

          <label>Cash flow quality</label>
          <select value={cashflow} onChange={(e) => setCashflow(e.target.value as Signal3)}>
            <option>Strong</option>
            <option>Adequate</option>
            <option>Weak</option>
          </select>

          <label>Earnings volatility</label>
          <select value={volatility} onChange={(e) => setVolatility(e.target.value as Volatility)}>
            <option>Low</option>
            <option>Moderate</option>
            <option>High</option>
          </select>

          <label>Capex / growth investment</label>
          <select value={capex} onChange={(e) => setCapex(e.target.value as Investment)}>
            <option>High</option>
            <option>Moderate</option>
            <option>Low</option>
          </select>

          <label>Financial transparency</label>
          <select value={transparency} onChange={(e) => setTransparency(e.target.value as Signal3)}>
            <option>Strong</option>
            <option>Adequate</option>
            <option>Weak</option>
          </select>

          <hr />

          <h3>RAROC</h3>
          <label>RAROC (%)</label>
          <input type="number" step="0.1" value={raroc} onChange={(e) => setRaroc(safeNum(e.target.value, 0))} />
          <div className="subtle">
            RM-entered screening estimate. Indicative only; final approval subject to Credit assessment.
          </div>

          <hr />

          <label>Notes</label>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Optional RM notes" />

          <div className="btn-row">
            <button onClick={onAssess} disabled={busyAssess || !clientName.trim()}>
              {busyAssess ? "Assessing..." : "Assess deal"}
            </button>
            <button className="secondary" onClick={onClear} disabled={busyAssess || busyExplain || busyQa}>
              Clear result
            </button>
          </div>

          <div className="subtle">System endpoints: /assess, /ai/explain, /ai/qa</div>
        </section>

        {/* RIGHT: Outputs */}
        <section className="panel" ref={resultRef}>
          <h2>Assessment output</h2>
          <div className="subtle">Run an assessment to see deal readiness, constraints, and RM actions.</div>

          {assessResult ? (
            <>
              <div className="card">
                <div className="row">
                  <div>
                    <div className="k">Deal readiness</div>
                    <div className="v">{assessResult.deal_readiness?.status}</div>
                    <div className="k" style={{ marginTop: 10 }}>
                      Mandate fit summary
                    </div>
                    <div className="v">{assessResult.mandate_fit_summary}</div>
                  </div>
                  <div className="badge">{assessResult.deal_readiness?.status}</div>
                </div>

                <div className="k" style={{ marginTop: 10 }}>
                  Constraints
                </div>
                <ul>
                  {(assessResult.deal_readiness?.constraints || []).map((x, i) => (
                    <li key={i}>{x}</li>
                  ))}
                </ul>

                <div className="k">RM actions</div>
                <ul>
                  {(assessResult.rm_actions || []).map((x, i) => (
                    <li key={i}>{x}</li>
                  ))}
                </ul>

                <div className="k">Strengths</div>
                <ul>
                  {(assessResult.deal_readiness?.strengths || []).map((x, i) => (
                    <li key={i}>{x}</li>
                  ))}
                </ul>
              </div>

              <div className="btn-row">
                <button className="secondary" onClick={() => setShowRaw((v) => !v)}>
                  {showRaw ? "Hide raw JSON" : "Show raw JSON"}
                </button>
              </div>

              {showRaw ? (
                <pre className="output">{JSON.stringify(assessResult, null, 2)}</pre>
              ) : null}

              <hr />

              <h2>AI: Explain assessment</h2>
              <div className="subtle">Generate a structured explanation based on the assessment.</div>

              <div className="btn-row">
                <button onClick={onExplain} disabled={busyExplain}>
                  {busyExplain ? "Generating..." : "Generate explanation"}
                </button>
                <button className="secondary" onClick={() => setAiExplain(null)} disabled={busyExplain}>
                  Clear AI output
                </button>
              </div>

              {aiExplain ? (
                <div className="card">
                  <div className="k">Executive summary</div>
                  <div className="v">{aiExplain.executive_summary}</div>

                  <div className="k" style={{ marginTop: 10 }}>
                    Key risks (explained)
                  </div>
                  <ul>
                    {(aiExplain.key_risks_explained || []).map((x, i) => (
                      <li key={i}>{x}</li>
                    ))}
                  </ul>

                  <div className="k">RM talking points</div>
                  <ul>
                    {(aiExplain.rm_talking_points || []).map((x, i) => (
                      <li key={i}>{x}</li>
                    ))}
                  </ul>

                  <div className="k">Disclaimer</div>
                  <div className="v">{aiExplain.disclaimer}</div>
                </div>
              ) : null}

              <hr />

              <h2>AI: Deal Q&amp;A</h2>
              <div className="subtle">Ask a question; if an assessment exists, it is used as context.</div>

              <div className="row" style={{ gap: 10 }}>
                <input
                  value={qaQuestion}
                  onChange={(e) => setQaQuestion(e.target.value)}
                  placeholder="What to do next?"
                />
                <button onClick={onAskQa} disabled={busyQa || !qaQuestion.trim()}>
                  {busyQa ? "Asking..." : "Ask"}
                </button>
              </div>

              {aiQa ? (
                <div className="card">
                  <div className="k">Decision</div>
                  <div className="v">{aiQa.decision}</div>

                  <div className="k" style={{ marginTop: 10 }}>
                    Answer
                  </div>
                  <pre className="output">{aiQa.answer}</pre>

                  <div className="k">Disclaimer</div>
                  <div className="v">{aiQa.disclaimer}</div>
                </div>
              ) : null}
            </>
          ) : (
            <div className="subtle" style={{ marginTop: 10 }}>
              Run an assessment to see outputs.
            </div>
          )}

          <div className="subtle" style={{ marginTop: 10 }}>
            Connection: {API_BASE ? API_BASE : ""}
          </div>
        </section>
      </main>
    </div>
  );
}

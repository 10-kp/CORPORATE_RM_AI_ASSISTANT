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

type DealSummaryResponse = { [key: string]: any };

type AIExplainResponse = {
  executive_summary?: string;
  key_risks_explained?: string[];
  rm_talking_points?: string[];
  disclaimer?: string;
};

type AIQAResponse = {
  answer: string;
  disclaimer?: string;
};

// Use labels that look professional + align with backend normalisers
const SECTORS = ["Manufacturing", "Healthcare", "Advanced Technology", "Food Security", "Renewables"];
const OUTLOOKS = ["Stable", "Positive", "Negative", "Watch"];

// revenue trend allowed: Improving | Stable | Declining
const TRENDS = ["Improving", "Stable", "Declining"];

// margin trend allowed: Improving | Stable | Under Pressure
const MARGIN_TRENDS = ["Improving", "Stable", "Under Pressure"];

// leverage allowed: Low | Moderate | Elevated
const POSITIONS = ["Low", "Moderate", "Elevated"];

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

function formatExplain(resp: AIExplainResponse): string {
  const parts: string[] = [];
  if (resp.executive_summary) parts.push(`Executive summary\n${resp.executive_summary}`);
  if (resp.key_risks_explained?.length) parts.push(`Key risks\n- ${resp.key_risks_explained.join("\n- ")}`);
  if (resp.rm_talking_points?.length) parts.push(`RM talking points\n- ${resp.rm_talking_points.join("\n- ")}`);
  if (resp.disclaimer) parts.push(`Disclaimer\n${resp.disclaimer}`);
  return parts.join("\n\n");
}

/* =====================
   Professional cards
===================== */

function ReadableCard({ text }: { text: string }) {
  const sections = text
    .split(/\n\s*\n/)
    .map((b) => b.trim())
    .filter(Boolean)
    .map((block) => {
      const lines = block.split("\n").map((l) => l.trim()).filter(Boolean);
      const title = (lines[0] || "").replace(/:$/, "");
      const rest = lines.slice(1);

      const bullets = rest.filter((l) => l.startsWith("-")).map((l) => l.replace(/^-+\s*/, ""));
      const body = rest.filter((l) => !l.startsWith("-")).join(" ");

      return { title, bullets, body };
    });

  return (
    <div className="cardout">
      {sections.map((s, i) => (
        <div key={i} className="cardout-section">
          <div className="cardout-title">{s.title}</div>
          {s.bullets.length > 0 ? (
            <ul className="cardout-list">
              {s.bullets.map((b, j) => <li key={j}>{b}</li>)}
            </ul>
          ) : (
            <div className="cardout-text">{s.body}</div>
          )}
        </div>
      ))}
    </div>
  );
}

function Badge({ status }: { status: string }) {
  const s = (status || "").toLowerCase();
  const cls =
    s === "strong" ? "badge badge-strong" : s === "conditional" ? "badge badge-conditional" : "badge badge-weak";
  return <span className={cls}>{status || "—"}</span>;
}

function AssessmentReadable({ assessment }: { assessment: DealSummaryResponse }) {
  const dr = assessment?.deal_readiness || {};
  const status = dr?.status || "—";

  return (
    <div className="readable">
      <div className="readable-row">
        <div className="readable-title">Deal readiness</div>
        <Badge status={status} />
      </div>

      {assessment?.mandate_fit_summary && (
        <>
          <div className="readable-title">Mandate fit summary</div>
          <div className="readable-text">{assessment.mandate_fit_summary}</div>
        </>
      )}

      {Array.isArray(dr?.constraints) && dr.constraints.length > 0 && (
        <>
          <div className="readable-title">Constraints</div>
          <ul className="readable-list">
            {dr.constraints.map((c: string, i: number) => <li key={i}>{c}</li>)}
          </ul>
        </>
      )}

      {Array.isArray(assessment?.rm_actions) && assessment.rm_actions.length > 0 && (
        <>
          <div className="readable-title">RM actions</div>
          <ul className="readable-list">
            {assessment.rm_actions.map((a: string, i: number) => <li key={i}>{a}</li>)}
          </ul>
        </>
      )}

      {Array.isArray(dr?.strengths) && dr.strengths.length > 0 && (
        <>
          <div className="readable-title">Strengths</div>
          <ul className="readable-list">
            {dr.strengths.map((s: string, i: number) => <li key={i}>{s}</li>)}
          </ul>
        </>
      )}
    </div>
  );
}

export default function App() {
  const API_BASE =  (import.meta as any).env?.VITE_API_BASE?.trim() ||
  ((window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")
    ? "http://127.0.0.1:8000"
    : "");

  // Form state (left panel)
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
  const [marginTrend, setMarginTrend] = useState<string>(MARGIN_TRENDS[1]);
  const [leveragePos, setLeveragePos] = useState<string>(POSITIONS[1]);
  const [cfQuality, setCfQuality] = useState<string>(QUALITIES[1]);
  const [earnVol, setEarnVol] = useState<string>(VOLATILITY[1]);
  const [capex, setCapex] = useState<string>(INVESTMENT[1]);
  const [transparency, setTransparency] = useState<string>(TRANSPARENCY[1]);

  const [indicativeRarocPct, setIndicativeRarocPct] = useState<string>("5.0%");
  const [notes, setNotes] = useState<string>("");

  // Outputs (right panel)
  const [assessResult, setAssessResult] = useState<DealSummaryResponse | null>(null);
  const [showRaw, setShowRaw] = useState<boolean>(false);

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
    if (!isNumberOrEmpty(eligibilityScore) || eligibilityScore === "") return false;
    if (indicativeRarocPct.trim() === "") return false;
    if (Number.isNaN(Number(indicativeRarocPct))) return false;
    return true;
  }, [clientName, ratingGrade, eligibilityScore, indicativeRarocPct]);

  function buildPayload(): DealInputRequest {
    const elig = Number(eligibilityScore);
    const raroc = Number(indicativeRarocPct);

    return {
      client_name: clientName.trim(),
      group_name: groupName.trim() ? groupName.trim() : null,
      strategic_sector: sector,

      rating_system: ratingSystem,
      rating_grade: ratingGrade.trim(),
      outlook: outlook || null,
      as_of: asOf.trim() ? asOf.trim() : null,

      eligibility_score: elig,
      eligibility_drivers: eligibilityDrivers.trim() ? eligibilityDrivers.trim() : null,

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
      throw new Error(`HTTP ${res.status} ${res.statusText}${t ? ` — ${t}` : ""}`);
    }
    return (await res.json()) as T;
  }

  async function onAssess() {
    setErrorMsg("");
    setAiExplain("");
    setAiQA("");
    setAssessResult(null);
    setShowRaw(false);

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
      setErrorMsg("Run an assessment first.");
      return;
    }

    setBusyExplain(true);
    try {
      const resp = await postJSON<AIExplainResponse>("/ai/explain", { deal_summary: assessResult });
      setAiExplain(formatExplain(resp));
    } catch (e: any) {
      setErrorMsg(e?.message || "Explanation failed.");
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
        deal_summary: assessResult,
      });

      // Render as sections
      const text = resp.disclaimer
        ? `Answer\n${resp.answer}\n\nDisclaimer\n${resp.disclaimer}`
        : `Answer\n${resp.answer}`;
      setAiQA(text);
    } catch (e: any) {
      setErrorMsg(e?.message || "Q&A failed.");
    } finally {
      setBusyQA(false);
    }
  }

  function clearAll() {
    setErrorMsg("");
    setAssessResult(null);
    setShowRaw(false);
    setAiExplain("");
    setAiQA("");
    setQaQuestion("");
  }

  function clearAI() {
    setErrorMsg("");
    setAiExplain("");
    setAiQA("");
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>Corporate RM Deal Readiness &amp; Mandate Fit Assistant</h1>
        <div className="subtle">Assessment + explanation + deal Q&amp;A</div>
      </header>

      <main className="grid">
        {/* LEFT: Inputs */}
        <section className="panel">
          <h2>Client</h2>

          <label>Client name *</label>
          <input value={clientName} onChange={(e) => setClientName(e.target.value)} placeholder="e.g., ABC Manufacturing LLC" />

          <label>Group name</label>
          <input value={groupName} onChange={(e) => setGroupName(e.target.value)} placeholder="Optional" />

          <label>Strategic sector</label>
          <select value={sector} onChange={(e) => setSector(e.target.value)}>
            {SECTORS.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>

          <h2>Rating anchor</h2>

          <label>System</label>
          <select value={ratingSystem} onChange={(e) => setRatingSystem(e.target.value)}>
            {RATING_SYSTEMS.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>

          <label>Rating grade *</label>
          <input value={ratingGrade} onChange={(e) => setRatingGrade(e.target.value)} placeholder="e.g., 6" />

          <label>Outlook</label>
          <select value={outlook} onChange={(e) => setOutlook(e.target.value)}>
            {OUTLOOKS.map((o) => (
              <option key={o} value={o}>{o}</option>
            ))}
          </select>

          <label>As of (YYYY-MM-DD)</label>
          <input value={asOf} onChange={(e) => setAsOf(e.target.value)} placeholder="Optional" />

          <h2>Eligibility</h2>

          <label>Eligibility score (0–6) *</label>
          <input type="number" step="0.1" min="0" max="6" value={eligibilityScore} onChange={(e) => setEligibilityScore(e.target.value)} />

          <label>Eligibility drivers (comma-separated)</label>
          <input value={eligibilityDrivers} onChange={(e) => setEligibilityDrivers(e.target.value)} placeholder="e.g., Job creation, Exports, ICV" />

          <h2>Financial signals</h2>

          <label>Revenue trend (3Y)</label>
          <select value={revTrend} onChange={(e) => setRevTrend(e.target.value)}>
            {TRENDS.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>

          <label>Margin trend (3Y)</label>
          <select value={marginTrend} onChange={(e) => setMarginTrend(e.target.value)}>
            {MARGIN_TRENDS.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>

          <label>Leverage position</label>
          <select value={leveragePos} onChange={(e) => setLeveragePos(e.target.value)}>
            {POSITIONS.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>

          <label>Cash flow quality</label>
          <select value={cfQuality} onChange={(e) => setCfQuality(e.target.value)}>
            {QUALITIES.map((q) => (
              <option key={q} value={q}>{q}</option>
            ))}
          </select>

          <label>Earnings volatility</label>
          <select value={earnVol} onChange={(e) => setEarnVol(e.target.value)}>
            {VOLATILITY.map((v) => (
              <option key={v} value={v}>{v}</option>
            ))}
          </select>

          <label>Capex / growth investment</label>
          <select value={capex} onChange={(e) => setCapex(e.target.value)}>
            {INVESTMENT.map((i) => (
              <option key={i} value={i}>{i}</option>
            ))}
          </select>

          <label>Financial transparency</label>
          <select value={transparency} onChange={(e) => setTransparency(e.target.value)}>
            {TRANSPARENCY.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>

          <h2>RAROC</h2>
          <label>RAROC (%)</label>
          <input
            type="number"
            step="0.1"
            min="0"
            max="100"
            value={indicativeRarocPct}
            onChange={(e) => setIndicativeRarocPct(e.target.value)}
          />
          <div className="subtle">RM-entered screening estimate. Indicative only; final approval subject to Credit assessment.</div>

          <h2>Notes</h2>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Optional RM notes" rows={5} />

          <div className="btn-row">
            <button onClick={onAssess} disabled={!canAssess || busyAssess}>
              {busyAssess ? "Assessing..." : "Assess deal"}
            </button>
            <button onClick={clearAll} className="secondary">
              Clear result
            </button>
          </div>

          <div className="subtle">
            System endpoints: <code>/assess</code>, <code>/ai/explain</code>, <code>/ai/qa</code>
          </div>

          {errorMsg && <div className="error">{errorMsg}</div>}
        </section>

        {/* RIGHT: Outputs */}
        <section className="panel">
          <h2>Assessment output</h2>
          <div className="subtle">Run an assessment to see deal readiness, constraints, and RM actions.</div>

          {assessResult ? (
            <>
              <AssessmentReadable assessment={assessResult} />
              <div className="btn-row" style={{ marginTop: 10 }}>
                <button className="secondary" onClick={() => setShowRaw((v) => !v)}>
                  {showRaw ? "Hide raw JSON" : "Show raw JSON"}
                </button>
              </div>
              {showRaw && <pre className="output">{asText(assessResult)}</pre>}
            </>
          ) : (
            <div className="subtle" style={{ marginTop: 10 }}>No assessment yet.</div>
          )}

          <div className="box">
            <h3>AI: Explain assessment</h3>
            <div className="subtle">Generate a structured explanation based on the assessment.</div>
            <div className="btn-row">
              <button onClick={onExplain} disabled={!assessResult || busyExplain}>
                {busyExplain ? "Generating..." : "Generate explanation"}
              </button>
              <button onClick={clearAI} className="secondary">
                Clear AI output
              </button>
            </div>

            {aiExplain ? <ReadableCard text={aiExplain} /> : <div className="subtle" style={{ marginTop: 10 }}>No explanation yet.</div>}
          </div>

          <div className="box">
            <h3>AI: Deal Q&amp;A</h3>
            <div className="subtle">Ask a question; if an assessment exists, it is used as context.</div>
            <div className="qa-row">
              <input
                value={qaQuestion}
                onChange={(e) => setQaQuestion(e.target.value)}
                placeholder="e.g., Should the RM proceed or decline?"
              />
              <button onClick={onAsk} disabled={busyQA}>
                {busyQA ? "Asking..." : "Ask"}
              </button>
            </div>

            {aiQA ? <ReadableCard text={aiQA} /> : <div className="subtle" style={{ marginTop: 10 }}>No answer yet.</div>}

            <div className="subtle" style={{ marginTop: 10 }}>
              Connection: <code>{API_BASE}</code>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

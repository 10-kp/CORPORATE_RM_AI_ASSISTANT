// frontend/src/App.tsx
import React, { useMemo, useState } from "react";

// Default to same-origin proxy (Vite dev server can proxy if configured),
// otherwise set VITE_API_URL=http://127.0.0.1:8000
const API_BASE = (import.meta.env.VITE_API_URL as string) || "";
const ASSESS_URL = API_BASE ? `${API_BASE}/assess` : "/assess";
const AI_EXPLAIN_URL = API_BASE ? `${API_BASE}/ai/explain` : "/ai/explain";
const AI_QA_URL = API_BASE ? `${API_BASE}/ai/qa` : "/ai/qa";

type Sector =
  | "Manufacturing"
  | "Advanced Technology"
  | "Healthcare"
  | "Food Security"
  | "Renewables"
  | "Other";

type Trend3Y = "Improving" | "Stable" | "Declining";
type MarginTrend = "Improving" | "Stable" | "Under Pressure";
type Leverage = "Low" | "Moderate" | "Elevated";
type Signal3 = "Strong" | "Adequate" | "Weak";
type Volatility = "Low" | "Moderate" | "High";
type Investment = "High" | "Moderate" | "Low";
type Readiness = "Strong" | "Conditional" | "Weak";

type Form = {
  client_name: string;
  group_name: string;
  sector: Sector;

  rating_system: string;
  rating_grade: string;
  rating_outlook: string;
  rating_as_of: string;

  eligibility_score: number; // 0–6
  eligibility_drivers: string; // comma-separated

  revenue_trend_3y: Trend3Y;
  margin_trend_3y: MarginTrend;
  leverage_position: Leverage;
  cashflow_quality: Signal3;
  earnings_volatility: Volatility;
  capex_growth_investment: Investment;
  financial_transparency: Signal3;

  notes: string;
};

type Result = {
  client_name: string;
  group_name?: string | null;
  sector: string;

  deal_readiness: {
    status: Readiness;
    strengths: string[];
    constraints: string[];
  };

  rm_actions: string[];
  talking_points: string[];

  mandate_fit_summary: string;

  // optional fields from backend
  rating_anchor?: any;
  eligibility?: any;
  financial_signals?: any;
};

type AIExplainOut = {
  executive_summary: string;
  key_risks_explained: string[];
  rm_talking_points: string[];
  disclaimer: string;
};

type AIQAOut = {
  answer: string;
  disclaimer: string;
};

// -----------------------------
// Shared UI styles (surgical fix)
// -----------------------------
const pageStyle: React.CSSProperties = {
  maxWidth: 1100,
  margin: "24px auto",
  padding: 16,
  color: "#fff",
};

const panelStyle: React.CSSProperties = {
  border: "1px solid #2a2a2a",
  borderRadius: 12,
  padding: 16,
  background: "#151515",
};

const controlStyle: React.CSSProperties = {
  width: "100%",
  height: 36,
  padding: "6px 10px",
  borderRadius: 8,
  border: "1px solid #3b3b3b",
  background: "#1e1e1e",
  color: "#fff",
  outline: "none",
  boxSizing: "border-box",
};

const textareaStyle: React.CSSProperties = {
  ...controlStyle,
  height: 90,
  resize: "vertical",
};

const primaryBtn: React.CSSProperties = {
  padding: "10px 14px",
  borderRadius: 10,
  border: "1px solid #111",
  background: "#111",
  color: "#fff",
  cursor: "pointer",
  fontWeight: 800,
};

const secondaryBtn: React.CSSProperties = {
  padding: "10px 14px",
  borderRadius: 10,
  border: "1px solid #111",
  background: "#111",
  color: "#fff",
  cursor: "pointer",
  fontWeight: 800,
};

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontSize: 13, fontWeight: 800, margin: "18px 0 10px 0" }}>
      {children}
    </div>
  );
}

function FieldRow({
  label,
  input,
}: {
  label: string;
  input: React.ReactNode;
}) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "200px 1fr",
        gap: 10,
        alignItems: "center",
        marginBottom: 10,
      }}
    >
      <div style={{ fontSize: 12, color: "#b8b8b8" }}>{label}</div>
      <div>{input}</div>
    </div>
  );
}

function Badge({ status }: { status: Readiness }) {
  const bg =
    status === "Strong"
      ? "#153a26"
      : status === "Conditional"
      ? "#3b2a13"
      : "#3b1515";
  const border =
    status === "Strong"
      ? "#2ecc71"
      : status === "Conditional"
      ? "#f39c12"
      : "#e74c3c";
  const color =
    status === "Strong"
      ? "#7CFFB0"
      : status === "Conditional"
      ? "#FFD48A"
      : "#FF9C9C";

  return (
    <span
      style={{
        display: "inline-block",
        padding: "6px 10px",
        borderRadius: 999,
        background: bg,
        border: `1px solid ${border}`,
        color,
        fontSize: 12,
        fontWeight: 900,
        letterSpacing: 0.2,
      }}
    >
      {status}
    </span>
  );
}

function SmallMuted({ children }: { children: React.ReactNode }) {
  return <div style={{ fontSize: 12, color: "#9a9a9a" }}>{children}</div>;
}

export default function App() {
  // ---- form + core result ----
  const [form, setForm] = useState<Form>({
    client_name: "",
    group_name: "",
    sector: "Manufacturing",

    rating_system: "Credit Lens",
    rating_grade: "",
    rating_outlook: "Stable",
    rating_as_of: "",

    eligibility_score: 3.5,
    eligibility_drivers: "",

    revenue_trend_3y: "Stable",
    margin_trend_3y: "Stable",
    leverage_position: "Moderate",
    cashflow_quality: "Adequate",
    earnings_volatility: "Moderate",
    capex_growth_investment: "Moderate",
    financial_transparency: "Adequate",

    notes: "",
  });

  const [result, setResult] = useState<Result | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ---- AI state ----
  const [aiExplain, setAiExplain] = useState<AIExplainOut | null>(null);
  const [aiExplainLoading, setAiExplainLoading] = useState(false);
  const [aiExplainError, setAiExplainError] = useState<string | null>(null);

  const [question, setQuestion] = useState("");
  const [aiAnswer, setAiAnswer] = useState<AIQAOut | null>(null);
  const [aiQaLoading, setAiQaLoading] = useState(false);
  const [aiQaError, setAiQaError] = useState<string | null>(null);

  const canSubmit = useMemo(() => {
    return (
      form.client_name.trim().length > 0 &&
      form.rating_grade.trim().length > 0 &&
      form.eligibility_score >= 0 &&
      form.eligibility_score <= 6
    );
  }, [form]);

  function clearAllOutputs() {
    setResult(null);
    setError(null);
    setAiExplain(null);
    setAiExplainError(null);
    setAiAnswer(null);
    setAiQaError(null);
  }

  async function onAssess() {
    setError(null);
    setLoading(true);
    setResult(null);
    setAiExplain(null);
    setAiExplainError(null);
    setAiAnswer(null);
    setAiQaError(null);

    try {
      const resp = await fetch(ASSESS_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          client_name: form.client_name,
          group_name: form.group_name || null,
          sector: form.sector,

          rating_anchor: {
            system: form.rating_system,
            grade: form.rating_grade,
            outlook: form.rating_outlook || null,
            as_of: form.rating_as_of || null,
          },

          eligibility: {
            score: Number(form.eligibility_score),
            drivers: (form.eligibility_drivers || "")
              .split(",")
              .map((s: string) => s.trim())
              .filter(Boolean),
            breakdown: {},
          },

          financial_signals: {
            revenue_trend_3y: form.revenue_trend_3y,
            margin_trend_3y: form.margin_trend_3y,
            leverage_position: form.leverage_position,
            cashflow_quality: form.cashflow_quality,
            earnings_volatility: form.earnings_volatility,
            capex_growth_investment: form.capex_growth_investment,
            financial_transparency: form.financial_transparency,
          },

          notes: form.notes || null,
        }),
      });

      if (!resp.ok) {
        const txt = await resp.text().catch(() => "");
        throw new Error(`API error ${resp.status}${txt ? `: ${txt}` : ""}`);
      }

      const out: Result = await resp.json();
      setResult(out);
    } catch (e: any) {
      setError(e?.message || "Request failed");
    } finally {
      setLoading(false);
    }
  }

  async function onAiExplain() {
    setAiExplain(null);
    setAiExplainError(null);

    if (!result) {
      setAiExplainError("Run an assessment first.");
      return;
    }

    setAiExplainLoading(true);
    try {
      const resp = await fetch(AI_EXPLAIN_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deal_summary: result }),
      });

      if (!resp.ok) {
        const txt = await resp.text().catch(() => "");
        throw new Error(
          `AI explain error ${resp.status}${txt ? `: ${txt}` : ""}`
        );
      }

      const out: AIExplainOut = await resp.json();
      setAiExplain(out);
    } catch (e: any) {
      setAiExplainError(e?.message || "AI explain failed");
    } finally {
      setAiExplainLoading(false);
    }
  }

  async function onAiAsk() {
    setAiAnswer(null);
    setAiQaError(null);

    const q = question.trim();
    if (!q) {
      setAiQaError("Enter a question.");
      return;
    }

    setAiQaLoading(true);
    try {
      const resp = await fetch(AI_QA_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: q,
          deal_summary: result ?? null,
        }),
      });

      if (!resp.ok) {
        const txt = await resp.text().catch(() => "");
        throw new Error(`AI Q&A error ${resp.status}${txt ? `: ${txt}` : ""}`);
      }

      const out: AIQAOut = await resp.json();
      setAiAnswer(out);
    } catch (e: any) {
      setAiQaError(e?.message || "AI Q&A failed");
    } finally {
      setAiQaLoading(false);
    }
  }

  return (
    <div style={pageStyle}>
      <div style={{ fontSize: 18, fontWeight: 900 }}>
        Corporate RM Deal Readiness &amp; Mandate Fit Assistant
      </div>
      <div style={{ fontSize: 12, color: "#9a9a9a", marginTop: 6 }}>
        /assess + AI explain + deal Q&amp;A
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 20,
          marginTop: 18,
          alignItems: "start",
        }}
      >
        {/* LEFT: INPUTS */}
        <div style={panelStyle}>
          <SectionTitle>Client</SectionTitle>

          <FieldRow
            label="Client name *"
            input={
              <input
                value={form.client_name}
                onChange={(e) =>
                  setForm({ ...form, client_name: e.target.value })
                }
                style={controlStyle}
                placeholder="e.g., ABC Manufacturing LLC"
              />
            }
          />

          <FieldRow
            label="Group name"
            input={
              <input
                value={form.group_name}
                onChange={(e) => setForm({ ...form, group_name: e.target.value })}
                style={controlStyle}
                placeholder="Optional"
              />
            }
          />

          <FieldRow
            label="Strategic sector"
            input={
              <select
                value={form.sector}
                onChange={(e) =>
                  setForm({ ...form, sector: e.target.value as Sector })
                }
                style={controlStyle}
              >
                <option>Manufacturing</option>
                <option>Advanced Technology</option>
                <option>Healthcare</option>
                <option>Food Security</option>
                <option>Renewables</option>
                <option>Other</option>
              </select>
            }
          />

          <SectionTitle>Rating anchor</SectionTitle>

          <FieldRow
            label="System"
            input={
              <select
                value={form.rating_system}
                onChange={(e) =>
                  setForm({ ...form, rating_system: e.target.value })
                }
                style={controlStyle}
              >
                <option>Credit Lens</option>
                <option>External Rating</option>
              </select>
            }
          />

          <FieldRow
            label="Rating grade *"
            input={
              <input
                value={form.rating_grade}
                onChange={(e) =>
                  setForm({ ...form, rating_grade: e.target.value })
                }
                style={controlStyle}
                placeholder="e.g., Baa3 / 6 / BB- (as per system)"
              />
            }
          />

          <FieldRow
            label="Outlook"
            input={
              <input
                value={form.rating_outlook}
                onChange={(e) =>
                  setForm({ ...form, rating_outlook: e.target.value })
                }
                style={controlStyle}
                placeholder="Stable / Negative / Positive"
              />
            }
          />

          <FieldRow
            label="As of (YYYY-MM-DD)"
            input={
              <input
                value={form.rating_as_of}
                onChange={(e) =>
                  setForm({ ...form, rating_as_of: e.target.value })
                }
                style={controlStyle}
                placeholder="Optional"
              />
            }
          />

          <SectionTitle>Eligibility</SectionTitle>

          <FieldRow
            label="Eligibility score (0–6) *"
            input={
              <input
                type="number"
                min={0}
                max={6}
                step={0.1}
                value={form.eligibility_score}
                onChange={(e) =>
                  setForm({
                    ...form,
                    eligibility_score: Number(e.target.value),
                  })
                }
                style={controlStyle}
              />
            }
          />

          <FieldRow
            label="Eligibility drivers (comma-separated)"
            input={
              <input
                value={form.eligibility_drivers}
                onChange={(e) =>
                  setForm({ ...form, eligibility_drivers: e.target.value })
                }
                style={controlStyle}
                placeholder="e.g., Job creation, Exports, ICV"
              />
            }
          />

          <SectionTitle>Financial signals</SectionTitle>

          <FieldRow
            label="Revenue trend (3Y)"
            input={
              <select
                value={form.revenue_trend_3y}
                onChange={(e) =>
                  setForm({
                    ...form,
                    revenue_trend_3y: e.target.value as Trend3Y,
                  })
                }
                style={controlStyle}
              >
                <option>Improving</option>
                <option>Stable</option>
                <option>Declining</option>
              </select>
            }
          />

          <FieldRow
            label="Margin trend (3Y)"
            input={
              <select
                value={form.margin_trend_3y}
                onChange={(e) =>
                  setForm({
                    ...form,
                    margin_trend_3y: e.target.value as MarginTrend,
                  })
                }
                style={controlStyle}
              >
                <option>Improving</option>
                <option>Stable</option>
                <option>Under Pressure</option>
              </select>
            }
          />

          <FieldRow
            label="Leverage position"
            input={
              <select
                value={form.leverage_position}
                onChange={(e) =>
                  setForm({
                    ...form,
                    leverage_position: e.target.value as Leverage,
                  })
                }
                style={controlStyle}
              >
                <option>Low</option>
                <option>Moderate</option>
                <option>Elevated</option>
              </select>
            }
          />

          <FieldRow
            label="Cash flow quality"
            input={
              <select
                value={form.cashflow_quality}
                onChange={(e) =>
                  setForm({
                    ...form,
                    cashflow_quality: e.target.value as Signal3,
                  })
                }
                style={controlStyle}
              >
                <option>Strong</option>
                <option>Adequate</option>
                <option>Weak</option>
              </select>
            }
          />

          <FieldRow
            label="Earnings volatility"
            input={
              <select
                value={form.earnings_volatility}
                onChange={(e) =>
                  setForm({
                    ...form,
                    earnings_volatility: e.target.value as Volatility,
                  })
                }
                style={controlStyle}
              >
                <option>Low</option>
                <option>Moderate</option>
                <option>High</option>
              </select>
            }
          />

          <FieldRow
            label="Capex / growth investment"
            input={
              <select
                value={form.capex_growth_investment}
                onChange={(e) =>
                  setForm({
                    ...form,
                    capex_growth_investment: e.target.value as Investment,
                  })
                }
                style={controlStyle}
              >
                <option>High</option>
                <option>Moderate</option>
                <option>Low</option>
              </select>
            }
          />

          <FieldRow
            label="Financial transparency"
            input={
              <select
                value={form.financial_transparency}
                onChange={(e) =>
                  setForm({
                    ...form,
                    financial_transparency: e.target.value as Signal3,
                  })
                }
                style={controlStyle}
              >
                <option>Strong</option>
                <option>Adequate</option>
                <option>Weak</option>
              </select>
            }
          />

          <SectionTitle>Notes</SectionTitle>
          <textarea
            value={form.notes}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
            style={textareaStyle}
            placeholder="Optional RM notes"
          />

          <div
            style={{ marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap" }}
          >
            <button
              onClick={onAssess}
              disabled={!canSubmit || loading}
              style={{
                ...primaryBtn,
                opacity: !canSubmit || loading ? 0.6 : 1,
                cursor: !canSubmit || loading ? "not-allowed" : "pointer",
              }}
            >
              {loading ? "Assessing..." : "Assess deal"}
            </button>

            <button onClick={clearAllOutputs} style={secondaryBtn}>
              Clear result
            </button>
          </div>

          {error && (
            <div style={{ marginTop: 12, color: "#FF9C9C", fontSize: 12 }}>
              {error}
            </div>
          )}

          <div style={{ marginTop: 14 }}>
            <SmallMuted>
              Backend endpoints (frontend calls): <code>/assess</code>,{" "}
              <code>/ai/explain</code>, <code>/ai/qa</code>
            </SmallMuted>
          </div>
        </div>

        {/* RIGHT: OUTPUTS */}
        <div style={{ display: "grid", gap: 12 }}>
          <div style={panelStyle}>
            <SectionTitle>Assessment output</SectionTitle>

            {!result ? (
              <SmallMuted>
                Run an assessment to see deal readiness, constraints, and RM
                actions.
              </SmallMuted>
            ) : (
              <>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    gap: 12,
                  }}
                >
                  <div>
                    <SmallMuted>Deal readiness</SmallMuted>
                    <div style={{ marginTop: 6 }}>
                      <Badge status={result.deal_readiness.status} />
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <SmallMuted>Client</SmallMuted>
                    <div style={{ fontSize: 13, fontWeight: 900 }}>
                      {result.client_name}
                    </div>
                    {result.group_name ? (
                      <div style={{ fontSize: 12, color: "#9a9a9a" }}>
                        {result.group_name}
                      </div>
                    ) : null}
                  </div>
                </div>

                <div style={{ marginTop: 12, fontSize: 13 }}>
                  <div style={{ fontWeight: 900, marginBottom: 6 }}>
                    Mandate fit summary
                  </div>
                  <div style={{ color: "#d7d7d7" }}>
                    {result.mandate_fit_summary}
                  </div>
                </div>

                <div style={{ marginTop: 14 }}>
                  <div
                    style={{ fontWeight: 900, fontSize: 13, marginBottom: 6 }}
                  >
                    Constraints
                  </div>
                  {result.deal_readiness.constraints?.length ? (
                    <ul
                      style={{
                        margin: 0,
                        paddingLeft: 18,
                        fontSize: 13,
                        color: "#d7d7d7",
                      }}
                    >
                      {result.deal_readiness.constraints.map((c, idx) => (
                        <li key={idx} style={{ marginBottom: 6 }}>
                          {c}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <SmallMuted>None identified.</SmallMuted>
                  )}
                </div>

                <div style={{ marginTop: 14 }}>
                  <div
                    style={{ fontWeight: 900, fontSize: 13, marginBottom: 6 }}
                  >
                    RM actions
                  </div>
                  {result.rm_actions?.length ? (
                    <ul
                      style={{
                        margin: 0,
                        paddingLeft: 18,
                        fontSize: 13,
                        color: "#d7d7d7",
                      }}
                    >
                      {result.rm_actions.map((a, idx) => (
                        <li key={idx} style={{ marginBottom: 6 }}>
                          {a}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <SmallMuted>No actions suggested.</SmallMuted>
                  )}
                </div>

                <div style={{ marginTop: 14 }}>
                  <div
                    style={{ fontWeight: 900, fontSize: 13, marginBottom: 6 }}
                  >
                    Talking points
                  </div>
                  {result.talking_points?.length ? (
                    <ul
                      style={{
                        margin: 0,
                        paddingLeft: 18,
                        fontSize: 13,
                        color: "#d7d7d7",
                      }}
                    >
                      {result.talking_points.map((t, idx) => (
                        <li key={idx} style={{ marginBottom: 6 }}>
                          {t}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <SmallMuted>None generated by /assess.</SmallMuted>
                  )}
                </div>
              </>
            )}
          </div>

          <div style={panelStyle}>
            <SectionTitle>AI: Explain assessment</SectionTitle>
            <SmallMuted>
              Uses <code>/ai/explain</code>. Requires an assessment result.
            </SmallMuted>

            <div
              style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap" }}
            >
              <button
                onClick={onAiExplain}
                disabled={!result || aiExplainLoading}
                style={{
                  ...primaryBtn,
                  opacity: !result || aiExplainLoading ? 0.6 : 1,
                  cursor: !result || aiExplainLoading ? "not-allowed" : "pointer",
                }}
              >
                {aiExplainLoading ? "Generating..." : "Generate explanation"}
              </button>

              <button
                onClick={() => {
                  setAiExplain(null);
                  setAiExplainError(null);
                }}
                style={secondaryBtn}
              >
                Clear AI output
              </button>
            </div>

            {aiExplainError && (
              <div style={{ marginTop: 10, color: "#FF9C9C", fontSize: 12 }}>
                {aiExplainError}
              </div>
            )}

            {aiExplain && (
              <div style={{ marginTop: 12 }}>
                <div style={{ fontWeight: 900, fontSize: 13, marginBottom: 6 }}>
                  Executive summary
                </div>
                <div style={{ fontSize: 13, color: "#d7d7d7" }}>
                  {aiExplain.executive_summary}
                </div>

                <div style={{ marginTop: 12, fontWeight: 900, fontSize: 13, marginBottom: 6 }}>
                  Key risks
                </div>
                {aiExplain.key_risks_explained?.length ? (
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: "#d7d7d7" }}>
                    {aiExplain.key_risks_explained.map((k, idx) => (
                      <li key={idx} style={{ marginBottom: 6 }}>
                        {k}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <SmallMuted>None.</SmallMuted>
                )}

                <div style={{ marginTop: 12, fontWeight: 900, fontSize: 13, marginBottom: 6 }}>
                  RM talking points
                </div>
                {aiExplain.rm_talking_points?.length ? (
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: "#d7d7d7" }}>
                    {aiExplain.rm_talking_points.map((t, idx) => (
                      <li key={idx} style={{ marginBottom: 6 }}>
                        {t}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <SmallMuted>None.</SmallMuted>
                )}

                <div style={{ marginTop: 10, fontSize: 11, color: "#9a9a9a" }}>
                  {aiExplain.disclaimer}
                </div>
              </div>
            )}
          </div>

          <div style={panelStyle}>
            <SectionTitle>AI: Deal Q&amp;A</SectionTitle>
            <SmallMuted>
              Uses <code>/ai/qa</code>. If you ran /assess, it will pass the deal summary to AI.
            </SmallMuted>

            <div
              style={{
                marginTop: 10,
                display: "grid",
                gridTemplateColumns: "1fr auto",
                gap: 10,
              }}
            >
              <input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                style={controlStyle}
                placeholder="e.g., What are the top 3 approval risks?"
              />
              <button
                onClick={onAiAsk}
                disabled={aiQaLoading}
                style={{
                  ...primaryBtn,
                  height: 36,
                  opacity: aiQaLoading ? 0.6 : 1,
                  cursor: aiQaLoading ? "not-allowed" : "pointer",
                }}
              >
                {aiQaLoading ? "..." : "Ask"}
              </button>
            </div>

            {aiQaError && (
              <div style={{ marginTop: 10, color: "#FF9C9C", fontSize: 12 }}>
                {aiQaError}
              </div>
            )}

            {aiAnswer && (
              <div style={{ marginTop: 12 }}>
                <div style={{ fontWeight: 900, fontSize: 13, marginBottom: 6 }}>
                  Answer
                </div>
                <div style={{ fontSize: 13, color: "#d7d7d7", whiteSpace: "pre-wrap" }}>
                  {aiAnswer.answer}
                </div>
                <div style={{ marginTop: 10, fontSize: 11, color: "#9a9a9a" }}>
                  {aiAnswer.disclaimer}
                </div>
              </div>
            )}
          </div>

          <div style={{ fontSize: 11, color: "#7e7e7e" }}>
            Backend endpoints: <code>{ASSESS_URL}</code> •{" "}
            <code>{AI_EXPLAIN_URL}</code> • <code>{AI_QA_URL}</code>
          </div>
        </div>
      </div>

      {/* About section (INSIDE return) */}
      <hr style={{ margin: "2rem 0", opacity: 0.2 }} />

      <section
        style={{
          maxWidth: 900,
          margin: "0 auto",
          lineHeight: 1.6,
          fontSize: "0.95rem",
        }}
      >
        <h3>About this prototype</h3>
        <p>
          This is a prototype Corporate RM Deal Readiness &amp; Mandate Fit Assistant designed to
          support Relationship Managers during early-stage screening.
        </p>
        <p>
          It structures eligibility signals, financial signals, constraints, and RM actions into
          consistent and explainable outputs.
        </p>
      </section>

      {/* Footer disclaimer (INSIDE return) */}
      <footer
        style={{
          marginTop: "2rem",
          padding: "1rem",
          fontSize: "0.75rem",
          color: "#999",
          textAlign: "center",
        }}
      >
        Prototype – RM decision support only. Not a credit decision engine.
      </footer>
    </div>
  );
}

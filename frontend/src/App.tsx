import React, { useState } from "react";

// TEMP: force direct backend URL (bypass Vite proxy)

const API_URL = "http://127.0.0.1:8000/assess";

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

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontSize: 13, fontWeight: 700, margin: "18px 0 10px 0" }}>
      {children}
    </div>
  );
}

function FieldRow({ label, input }: { label: string; input: React.ReactNode }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "220px 1fr",
        gap: 10,
        alignItems: "center",
        marginBottom: 10,
      }}
    >
      <div style={{ fontSize: 13, color: "#555" }}>{label}</div>
      <div>{input}</div>
    </div>
  );
}

function Badge({ status }: { status: Readiness }) {
  const bg =
    status === "Strong"
      ? "#e7f7ee"
      : status === "Conditional"
      ? "#fff6e5"
      : "#ffe9e9";
  const border =
    status === "Strong"
      ? "#2ecc71"
      : status === "Conditional"
      ? "#f39c12"
      : "#e74c3c";
  const color =
    status === "Strong"
      ? "#1e874b"
      : status === "Conditional"
      ? "#a56500"
      : "#b3261e";

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
        fontWeight: 700,
      }}
    >
      {status}
    </span>
  );
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
  const [aiAnswer, setAiAnswer] = useState<AIQAOut | null>(null);
  const [question, setQuestion] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  async function onAssess() {
    setError(null);
    setLoading(true);
    setResult(null);

    // reset AI outputs on new assessment
    setAiExplain(null);
    setAiAnswer(null);
    setAiError(null);

    try {
      const resp = await fetch(API_URL, {
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

  async function onAIExplain() {
    if (!result) return;
    setAiError(null);
    setAiLoading(true);
    setAiExplain(null);

    try {
      const resp = await fetch("/ai/explain", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deal_summary: result }),
      });

      if (!resp.ok) {
        const txt = await resp.text().catch(() => "");
        throw new Error(`AI explain error ${resp.status}${txt ? `: ${txt}` : ""}`);
      }

      const out: AIExplainOut = await resp.json();
      setAiExplain(out);
    } catch (e: any) {
      setAiError(e?.message || "AI explain failed");
    } finally {
      setAiLoading(false);
    }
  }

  async function onAIAsk() {
    if (!result) return;
    if (!question.trim()) return;

    setAiError(null);
    setAiLoading(true);
    setAiAnswer(null);

    try {
      const resp = await fetch("/ai/qa", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deal_summary: result, question }),
      });

      if (!resp.ok) {
        const txt = await resp.text().catch(() => "");
        throw new Error(`AI Q&A error ${resp.status}${txt ? `: ${txt}` : ""}`);
      }

      const out: AIQAOut = await resp.json();
      setAiAnswer(out);
    } catch (e: any) {
      setAiError(e?.message || "AI Q&A failed");
    } finally {
      setAiLoading(false);
    }
  }

  const canSubmit =
    form.client_name.trim().length > 0 &&
    form.rating_grade.trim().length > 0 &&
    form.eligibility_score >= 0 &&
    form.eligibility_score <= 6;

  return (
    <div style={{ maxWidth: 1000, margin: "24px auto", padding: 16 }}>
      <div style={{ fontSize: 18, fontWeight: 800 }}>
        Corporate RM Deal Readiness &amp; Mandate Fit Assistant
      </div>
      <div style={{ fontSize: 13, color: "#666", marginTop: 6 }}>
        Front-office decision support. Interprets existing ratings, eligibility, sector alignment,
        and RM-friendly financial signals.
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
        <div style={{ border: "1px solid #e5e5e5", borderRadius: 10, padding: 16 }}>
          <SectionTitle>Client</SectionTitle>

          <FieldRow
            label="Client name *"
            input={
              <input
                value={form.client_name}
                onChange={(e) => setForm({ ...form, client_name: e.target.value })}
                style={{ width: "100%", padding: 8 }}
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
                style={{ width: "100%", padding: 8 }}
                placeholder="Optional"
              />
            }
          />

          <FieldRow
            label="Strategic sector"
            input={
              <select
                value={form.sector}
                onChange={(e) => setForm({ ...form, sector: e.target.value as Sector })}
                style={{ width: "100%", padding: 8 }}
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
                onChange={(e) => setForm({ ...form, rating_system: e.target.value })}
                style={{ width: "100%", padding: 8 }}
              >
                <option>Credit Lens</option>
                <option>Moody&apos;s Risk Advisor</option>
              </select>
            }
          />

          <FieldRow
            label="Rating grade *"
            input={
              <input
                value={form.rating_grade}
                onChange={(e) => setForm({ ...form, rating_grade: e.target.value })}
                style={{ width: "100%", padding: 8 }}
                placeholder="e.g., Baa3 / 6 / BB- (as per system)"
              />
            }
          />

          <FieldRow
            label="Outlook"
            input={
              <input
                value={form.rating_outlook}
                onChange={(e) => setForm({ ...form, rating_outlook: e.target.value })}
                style={{ width: "100%", padding: 8 }}
                placeholder="Stable / Negative / Positive"
              />
            }
          />

          <FieldRow
            label="As of (YYYY-MM-DD)"
            input={
              <input
                value={form.rating_as_of}
                onChange={(e) => setForm({ ...form, rating_as_of: e.target.value })}
                style={{ width: "100%", padding: 8 }}
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
                onChange={(e) => setForm({ ...form, eligibility_score: Number(e.target.value) })}
                style={{ width: "100%", padding: 8 }}
              />
            }
          />

          <FieldRow
            label="Eligibility drivers (comma-separated)"
            input={
              <input
                value={form.eligibility_drivers}
                onChange={(e) => setForm({ ...form, eligibility_drivers: e.target.value })}
                style={{ width: "100%", padding: 8 }}
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
                onChange={(e) => setForm({ ...form, revenue_trend_3y: e.target.value as Trend3Y })}
                style={{ width: "100%", padding: 8 }}
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
                onChange={(e) => setForm({ ...form, margin_trend_3y: e.target.value as MarginTrend })}
                style={{ width: "100%", padding: 8 }}
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
                onChange={(e) => setForm({ ...form, leverage_position: e.target.value as Leverage })}
                style={{ width: "100%", padding: 8 }}
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
                onChange={(e) => setForm({ ...form, cashflow_quality: e.target.value as Signal3 })}
                style={{ width: "100%", padding: 8 }}
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
                onChange={(e) => setForm({ ...form, earnings_volatility: e.target.value as Volatility })}
                style={{ width: "100%", padding: 8 }}
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
                  setForm({ ...form, capex_growth_investment: e.target.value as Investment })
                }
                style={{ width: "100%", padding: 8 }}
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
                  setForm({ ...form, financial_transparency: e.target.value as Signal3 })
                }
                style={{ width: "100%", padding: 8 }}
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
            style={{ width: "100%", padding: 8, minHeight: 70 }}
            placeholder="Optional RM notes"
          />

          <div style={{ marginTop: 14, display: "flex", gap: 10 }}>
            <button
              onClick={onAssess}
              disabled={!canSubmit || loading}
              style={{
                padding: "10px 14px",
                borderRadius: 8,
                border: "1px solid #111",
                background: loading ? "#eee" : "#111",
                color: loading ? "#111" : "#fff",
                cursor: loading ? "not-allowed" : "pointer",
                fontWeight: 700,
              }}
            >
              {loading ? "Assessing..." : "Assess deal"}
            </button>

            <button
              onClick={() => {
                setResult(null);
                setError(null);
                setAiExplain(null);
                setAiAnswer(null);
                setAiError(null);
              }}
              style={{
                padding: "10px 14px",
                borderRadius: 8,
                border: "1px solid #ccc",
                background: "#fff",
                cursor: "pointer",
              }}
            >
              Clear result
            </button>
          </div>

          {error && (
            <div style={{ marginTop: 12, color: "#b3261e", fontSize: 13 }}>
              {error}
            </div>
          )}
        </div>

        {/* RIGHT: OUTPUTS */}
        <div style={{ border: "1px solid #e5e5e5", borderRadius: 10, padding: 16 }}>
          <SectionTitle>Output</SectionTitle>

          {!result ? (
            <div style={{ fontSize: 13, color: "#666" }}>
              Run an assessment to see deal readiness, constraints, and RM actions.
            </div>
          ) : (
            <>
              {/* 1) Status */}
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                <div>
                  <div style={{ fontSize: 12, color: "#666" }}>Deal readiness</div>
                  <div style={{ marginTop: 6 }}>
                    <Badge status={result.deal_readiness.status} />
                  </div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: 12, color: "#666" }}>Client</div>
                  <div style={{ fontSize: 13, fontWeight: 700 }}>{result.client_name}</div>
                  {result.group_name ? (
                    <div style={{ fontSize: 12, color: "#666" }}>{result.group_name}</div>
                  ) : null}
                </div>
              </div>

              {/* Summary */}
              <div style={{ marginTop: 12, fontSize: 13 }}>
                <div style={{ fontWeight: 700, marginBottom: 6 }}>Mandate fit summary</div>
                <div style={{ color: "#333" }}>{result.mandate_fit_summary}</div>
              </div>

              {/* 2) Constraints */}
              <div style={{ marginTop: 14 }}>
                <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 6 }}>Constraints</div>
                {result.deal_readiness.constraints?.length ? (
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
                    {result.deal_readiness.constraints.map((c, idx) => (
                      <li key={idx} style={{ marginBottom: 6 }}>
                        {c}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div style={{ fontSize: 13, color: "#666" }}>None identified.</div>
                )}
              </div>

              {/* 3) RM actions */}
              <div style={{ marginTop: 14 }}>
                <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 6 }}>RM actions</div>
                {result.rm_actions?.length ? (
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
                    {result.rm_actions.map((a, idx) => (
                      <li key={idx} style={{ marginBottom: 6 }}>
                        {a}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div style={{ fontSize: 13, color: "#666" }}>No actions suggested.</div>
                )}
              </div>

              {/* 4) Talking points */}
              <div style={{ marginTop: 14 }}>
                <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 6 }}>Talking points</div>
                {result.talking_points?.length ? (
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
                    {result.talking_points.map((t, idx) => (
                      <li key={idx} style={{ marginBottom: 6 }}>
                        {t}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div style={{ fontSize: 13, color: "#666" }}>
                    (Optional) Add talking points generation in the AI layer.
                  </div>
                )}
              </div>

              {/* AI block */}
              <div style={{ marginTop: 16, borderTop: "1px solid #eee", paddingTop: 14 }}>
                <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                  <div style={{ fontWeight: 700, fontSize: 13 }}>AI</div>
                  <button
                    onClick={onAIExplain}
                    disabled={aiLoading || !result}
                    style={{
                      padding: "8px 12px",
                      borderRadius: 8,
                      border: "1px solid #111",
                      background: aiLoading ? "#eee" : "#111",
                      color: aiLoading ? "#111" : "#fff",
                      cursor: aiLoading ? "not-allowed" : "pointer",
                      fontWeight: 700,
                    }}
                  >
                    {aiLoading ? "Working..." : "Explain deal (AI)"}
                  </button>
                </div>

                <div style={{ marginTop: 10 }}>
                  <div style={{ fontSize: 12, color: "#666", marginBottom: 6 }}>Ask a question</div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <input
                      value={question}
                      onChange={(e) => setQuestion(e.target.value)}
                      placeholder="e.g., Why is this Conditional and what should I do next?"
                      style={{ width: "100%", padding: 8 }}
                    />
                    <button
                      onClick={onAIAsk}
                      disabled={aiLoading || !question.trim()}
                      style={{
                        padding: "8px 12px",
                        borderRadius: 8,
                        border: "1px solid #ccc",
                        background: "#fff",
                        cursor: aiLoading ? "not-allowed" : "pointer",
                        fontWeight: 700,
                        whiteSpace: "nowrap",
                      }}
                    >
                      Ask
                    </button>
                  </div>
                </div>

                {aiError && (
                  <div style={{ marginTop: 10, color: "#b3261e", fontSize: 13 }}>
                    {aiError}
                  </div>
                )}

                {aiExplain && (
                  <div style={{ marginTop: 12, fontSize: 13 }}>
                    <div style={{ fontWeight: 700, marginBottom: 6 }}>Executive summary</div>
                    <div style={{ color: "#333" }}>{aiExplain.executive_summary}</div>

                    {aiExplain.key_risks_explained?.length ? (
                      <>
                        <div style={{ fontWeight: 700, marginTop: 12, marginBottom: 6 }}>
                          Key risks explained
                        </div>
                        <ul style={{ margin: 0, paddingLeft: 18 }}>
                          {aiExplain.key_risks_explained.map((x, i) => (
                            <li key={i} style={{ marginBottom: 6 }}>
                              {x}
                            </li>
                          ))}
                        </ul>
                      </>
                    ) : null}

                    {aiExplain.rm_talking_points?.length ? (
                      <>
                        <div style={{ fontWeight: 700, marginTop: 12, marginBottom: 6 }}>
                          RM talking points
                        </div>
                        <ul style={{ margin: 0, paddingLeft: 18 }}>
                          {aiExplain.rm_talking_points.map((x, i) => (
                            <li key={i} style={{ marginBottom: 6 }}>
                              {x}
                            </li>
                          ))}
                        </ul>
                      </>
                    ) : null}

                    <div style={{ marginTop: 10, fontSize: 12, color: "#666" }}>
                      {aiExplain.disclaimer}
                    </div>
                  </div>
                )}

                {aiAnswer && (
                  <div style={{ marginTop: 12, fontSize: 13 }}>
                    <div style={{ fontWeight: 700, marginBottom: 6 }}>Answer</div>
                    <div style={{ color: "#333" }}>{aiAnswer.answer}</div>
                    <div style={{ marginTop: 10, fontSize: 12, color: "#666" }}>
                      {aiAnswer.disclaimer}
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      <div style={{ marginTop: 16, fontSize: 12, color: "#666" }}>
        Backend endpoint: <code>{API_URL}</code>
      </div>
    </div>
  );
}

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

/* -------------------- Types (UI) -------------------- */

type StrategicSector =
  | "Manufacturing"
  | "Advanced Technology"
  | "Healthcare"
  | "Food Security"
  | "Renewables"
  | "Other";

type RatingAnchor = {
  system: string;
  grade: string;
  outlook?: string | null;
  as_of?: string | null;
};

/* -------------------- Types (Step 1: PDF Extraction) -------------------- */

interface ParseResponse {
  filename: string;
  pages_scanned: number;
  tables_found: number;
  text: string;
}

interface Financials2Y {
  period_labels: string[];
  currency: string;
  confidence?: string;
  source?: string;

  // P&L
  revenue?: (number | null)[];
  cogs?: (number | null)[];
  gross_profit?: (number | null)[];
  gross_margin_pct?: (number | null)[];
  net_profit?: (number | null)[];
  net_profit_margin_pct?: (number | null)[];

  // Balance sheet anchors
  total_assets?: (number | null)[];
  total_equity?: (number | null)[];

  // Debt service / DSCR
  ebitda?: (number | null)[];
  interest_on_loans?: (number | null)[];
  cpltd?: (number | null)[];
  dscr?: (number | null)[];
}

/* -------------------- Helper functions -------------------- */

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

function pct(numer: number | null | undefined, denom: number | null | undefined): number | null {
  if (numer == null || denom == null) return null;
  if (!Number.isFinite(numer) || !Number.isFinite(denom) || denom === 0) return null;
  return (numer / denom) * 100;
}

/**
 * Number formatter:
 * - Default: integer with commas (financial statement style)
 * - If decimals provided: fixed decimals with commas
 */
function fmt(v: number | null | undefined, opts?: { decimals?: number }): string {
  if (v == null) return "–";
  const n = Number(v);
  if (!Number.isFinite(n)) return "–";

  const decimals = opts?.decimals;

  if (decimals == null) {
    return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
  }

  return n.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/* -------------------- Component -------------------- */

export default function App() {
  // Scroll target: right panel
  const resultRef = useRef<HTMLDivElement | null>(null);

  /* -------- Step 1: PDF Extraction state -------- */
  const [file, setFile] = useState<File | null>(null);
  const [loadingPdf, setLoadingPdf] = useState(false);
  const [parse, setParse] = useState<ParseResponse | null>(null);
  const [fin, setFin] = useState<Financials2Y | null>(null);
  const [showRawFin, setShowRawFin] = useState(false);

  /* -------- Step 2: RM Inputs -------- */
  const [clientName, setClientName] = useState("");
  const [groupName, setGroupName] = useState("");
  const [sector, setSector] = useState<StrategicSector>("Manufacturing");

  const [ratingSystem, setRatingSystem] = useState<RatingAnchor["system"]>("Credit Lens");
  const [ratingGrade, setRatingGrade] = useState<RatingAnchor["grade"]>("6");
  const [outlook, setOutlook] = useState<string>("Stable");
  const [asOf, setAsOf] = useState<string>("");

  const [eligScore, setEligScore] = useState<number>(3.0);
  const [eligDrivers, setEligDrivers] = useState<string>("");

  const [raroc, setRaroc] = useState<number>(4.3);
  const [notes, setNotes] = useState<string>("");

  /* -------- Step 3: Credit Committee report output -------- */
  const [creditMemo, setCreditMemo] = useState<string>("");
  const [busyMemo, setBusyMemo] = useState(false);

  // Copy button UI state
  const [copied, setCopied] = useState(false);

  // General error
  const [errorMsg, setErrorMsg] = useState("");

  const rmPayload = useMemo(() => {
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
    raroc,
    notes,
  ]);

  // Auto-scroll after memo appears
  useEffect(() => {
    if (creditMemo) {
      setTimeout(() => {
        resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 50);
    }
  }, [creditMemo]);

  // Reset copy state when memo changes
  useEffect(() => {
    setCopied(false);
  }, [creditMemo]);

  /* -------------------- Step 1 action: Upload PDF -------------------- */
  async function handleUploadPdf() {
    if (!file) return;

    setErrorMsg("");
    setLoadingPdf(true);
    setParse(null);
    setFin(null);
    setCreditMemo("");

    try {
      const form = new FormData();
      form.append("file", file);

      const parseRes = await fetch(`${API_BASE}/financials/parse-pdf`, {
        method: "POST",
        body: form,
      });

      if (!parseRes.ok) throw new Error("PDF parse failed");
      const parseJson: ParseResponse = await parseRes.json();
      setParse(parseJson);

      const inferRes = await fetch(`${API_BASE}/financials/infer-2y`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: parseJson.text }),
      });

      if (!inferRes.ok) throw new Error("Inference failed");
      const inferJson = await inferRes.json();
      setFin(inferJson.financials_2y ?? inferJson);
    } catch (e: any) {
      setErrorMsg(e?.message || "Unexpected error");
    } finally {
      setLoadingPdf(false);
    }
  }

  /* -------------------- Step 3 action: Generate Credit Committee report -------------------- */
  async function onGenerateCreditMemo() {
    setErrorMsg("");
    setCreditMemo("");

    if (!clientName.trim()) {
      setErrorMsg("Client name is required.");
      return;
    }
    if (!fin) {
      setErrorMsg("Please upload financials (Step 1) first.");
      return;
    }

    setBusyMemo(true);
    try {
      const res = await postJSON<{ credit_application_text: string; source?: string }>(
        "/ai/credit-application",
        {
          rm_inputs: rmPayload,
          financials_2y: fin,
          parse_meta: parse
            ? { filename: parse.filename, pages_scanned: parse.pages_scanned, tables_found: parse.tables_found }
            : null,
        }
      );

      setCreditMemo(res.credit_application_text || "");
    } catch (e: any) {
      setErrorMsg(e?.message || "Credit memo generation failed.");
    } finally {
      setBusyMemo(false);
    }
  }

  async function onCopyMemo() {
    if (!creditMemo) return;
    try {
      await navigator.clipboard.writeText(creditMemo);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      setErrorMsg("Copy failed (browser blocked clipboard). Select the text and copy manually.");
    }
  }

  /* -------------------- Render -------------------- */

  const p1 = fin?.period_labels?.[0] || "FY-1";
  const p2 = fin?.period_labels?.[1] || "FY-2";

  // Prefer backend-computed margins if present; fallback to UI compute
  const gm1 = fin?.gross_margin_pct?.[0] ?? pct(fin?.gross_profit?.[0] ?? null, fin?.revenue?.[0] ?? null);
  const gm2 = fin?.gross_margin_pct?.[1] ?? pct(fin?.gross_profit?.[1] ?? null, fin?.revenue?.[1] ?? null);
  const npm1 = fin?.net_profit_margin_pct?.[0] ?? pct(fin?.net_profit?.[0] ?? null, fin?.revenue?.[0] ?? null);
  const npm2 = fin?.net_profit_margin_pct?.[1] ?? pct(fin?.net_profit?.[1] ?? null, fin?.revenue?.[1] ?? null);

  return (
    <div className="app">
      <header className="app-header">
        <h1>Corporate RM Deal Readiness &amp; Credit Application Assistant</h1>
        <div className="subtle">MVP: PDF extraction + RM inputs + Credit Committee write-up</div>
      </header>

      {errorMsg ? (
        <div className="error" style={{ margin: "10px 0" }}>
          {errorMsg}
        </div>
      ) : null}

      <main className="grid">
        {/* LEFT: Step 1 + Step 2 */}
        <section className="panel">
          <h2>Step 1 — Upload financials (PDF) &amp; extract 2Y</h2>

          <label>Upload Financials (PDF)</label>
          <input type="file" accept="application/pdf" onChange={(e) => setFile(e.target.files?.[0] || null)} />

          <div className="btn-row">
            <button onClick={handleUploadPdf} disabled={!file || loadingPdf}>
              {loadingPdf ? "Processing..." : "Upload & Extract"}
            </button>
            <button
              className="secondary"
              onClick={() => {
                setFile(null);
                setParse(null);
                setFin(null);
                setCreditMemo("");
                setErrorMsg("");
              }}
              disabled={loadingPdf}
            >
              Clear PDF
            </button>
          </div>

          {parse && fin ? (
            <div className="box">
              <div className="subtle">
                File: <strong>{parse.filename}</strong> | Pages: {parse.pages_scanned} | Tables: {parse.tables_found} |
                Currency: <strong>{fin.currency}</strong>
              </div>

              <div style={{ marginTop: 10 }} className="subtle">
                Periods: {fin.period_labels?.join(", ") || "N/A"} | Confidence: {fin.confidence ?? "N/A"} | Source:{" "}
                {fin.source ?? "AI-extracted"}
              </div>

              <div style={{ marginTop: 12, overflowX: "auto" }}>
                <table style={{ width: "100%", minWidth: 560, borderCollapse: "collapse" }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: "left", padding: 6, borderBottom: "1px solid rgba(255,255,255,0.10)" }}>
                        {" "}
                      </th>
                      <th style={{ textAlign: "right", padding: 6, borderBottom: "1px solid rgba(255,255,255,0.10)" }}>
                        {p1}
                      </th>
                      <th style={{ textAlign: "right", padding: 6, borderBottom: "1px solid rgba(255,255,255,0.10)" }}>
                        {p2}
                      </th>
                    </tr>
                  </thead>

                  <tbody>
                    <tr>
                      <td style={{ padding: 6 }}>Revenue</td>
                      <td style={{ padding: 6, textAlign: "right" }}>{fmt(fin.revenue?.[0])}</td>
                      <td style={{ padding: 6, textAlign: "right" }}>{fmt(fin.revenue?.[1])}</td>
                    </tr>

                    <tr>
                      <td style={{ padding: 6 }}>COGS</td>
                      <td style={{ padding: 6, textAlign: "right" }}>{fmt(fin.cogs?.[0])}</td>
                      <td style={{ padding: 6, textAlign: "right" }}>{fmt(fin.cogs?.[1])}</td>
                    </tr>

                    <tr>
                      <td style={{ padding: 6 }}>Gross Profit</td>
                      <td style={{ padding: 6, textAlign: "right" }}>{fmt(fin.gross_profit?.[0])}</td>
                      <td style={{ padding: 6, textAlign: "right" }}>{fmt(fin.gross_profit?.[1])}</td>
                    </tr>

                    <tr>
                      <td style={{ padding: 6 }}>Gross Margin (%)</td>
                      <td style={{ padding: 6, textAlign: "right" }}>
                        {gm1 == null ? "–" : fmt(gm1 as number, { decimals: 2 })}
                      </td>
                      <td style={{ padding: 6, textAlign: "right" }}>
                        {gm2 == null ? "–" : fmt(gm2 as number, { decimals: 2 })}
                      </td>
                    </tr>

                    <tr>
                      <td style={{ padding: 6 }}>EBITDA</td>
                      <td style={{ padding: 6, textAlign: "right" }}>{fmt(fin.ebitda?.[0])}</td>
                      <td style={{ padding: 6, textAlign: "right" }}>{fmt(fin.ebitda?.[1])}</td>
                    </tr>

                    <tr>
                      <td style={{ padding: 6 }}>Net Profit</td>
                      <td style={{ padding: 6, textAlign: "right" }}>{fmt(fin.net_profit?.[0])}</td>
                      <td style={{ padding: 6, textAlign: "right" }}>{fmt(fin.net_profit?.[1])}</td>
                    </tr>

                    <tr>
                      <td style={{ padding: 6 }}>Net Profit Margin (%)</td>
                      <td style={{ padding: 6, textAlign: "right" }}>
                        {npm1 == null ? "–" : fmt(npm1 as number, { decimals: 2 })}
                      </td>
                      <td style={{ padding: 6, textAlign: "right" }}>
                        {npm2 == null ? "–" : fmt(npm2 as number, { decimals: 2 })}
                      </td>
                    </tr>

                    <tr>
                      <td style={{ padding: 6, paddingTop: 10 }}>Total Assets</td>
                      <td style={{ padding: 6, textAlign: "right", paddingTop: 10 }}>{fmt(fin.total_assets?.[0])}</td>
                      <td style={{ padding: 6, textAlign: "right", paddingTop: 10 }}>{fmt(fin.total_assets?.[1])}</td>
                    </tr>

                    <tr>
                      <td style={{ padding: 6 }}>Total Equity</td>
                      <td style={{ padding: 6, textAlign: "right" }}>{fmt(fin.total_equity?.[0])}</td>
                      <td style={{ padding: 6, textAlign: "right" }}>{fmt(fin.total_equity?.[1])}</td>
                    </tr>

                    <tr>
                      <td style={{ padding: 6, paddingTop: 10 }}>Interest (expense)</td>
                      <td style={{ padding: 6, textAlign: "right", paddingTop: 10 }}>
                        {fin.interest_on_loans?.[0] == null
                          ? "–"
                          : fmt(Math.abs(fin.interest_on_loans[0] as number))}
                      </td>
                      <td style={{ padding: 6, textAlign: "right", paddingTop: 10 }}>
                        {fin.interest_on_loans?.[1] == null
                          ? "–"
                          : fmt(Math.abs(fin.interest_on_loans[1] as number))}
                      </td>
                    </tr>

                    <tr>
                      <td style={{ padding: 6 }}>CPLTD</td>
                      <td style={{ padding: 6, textAlign: "right" }}>{fmt(fin.cpltd?.[0])}</td>
                      <td style={{ padding: 6, textAlign: "right" }}>{fmt(fin.cpltd?.[1])}</td>
                    </tr>

                    <tr>
                      <td style={{ padding: 6 }}>DSCR</td>
                      <td style={{ padding: 6, textAlign: "right" }}>
                        {fin.dscr?.[0] == null ? "–" : fmt(fin.dscr?.[0] as number, { decimals: 2 })}
                      </td>
                      <td style={{ padding: 6, textAlign: "right" }}>
                        {fin.dscr?.[1] == null ? "–" : fmt(fin.dscr?.[1] as number, { decimals: 2 })}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div className="btn-row">
                <button className="secondary" onClick={() => setShowRawFin((v) => !v)}>
                  {showRawFin ? "Hide raw JSON" : "Show raw JSON"}
                </button>
              </div>

              {showRawFin ? <pre className="output">{JSON.stringify({ parse, fin }, null, 2)}</pre> : null}
            </div>
          ) : null}

          <hr />

          <h2>Step 2 — RM inputs</h2>

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
            <option>External</option>
            <option>ORR</option>
          </select>

          <label>Rating grade *</label>
          <input value={ratingGrade} onChange={(e) => setRatingGrade(e.target.value)} placeholder="e.g. 6 / BBB / BB+" />

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
          <input type="number" step="0.1" value={eligScore} onChange={(e) => setEligScore(safeNum(e.target.value, 0))} />

          <label>Eligibility drivers (comma-separated)</label>
          <input value={eligDrivers} onChange={(e) => setEligDrivers(e.target.value)} placeholder="e.g., ICV, jobs" />

          <hr />

          <h3>RAROC</h3>

          <label>RAROC (%)</label>
          <input type="number" step="0.1" value={raroc} onChange={(e) => setRaroc(safeNum(e.target.value, 0))} />

          <label>Notes</label>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Optional RM notes" />
        </section>

        {/* RIGHT: Step 3 output */}
        <section className="panel" ref={resultRef}>
          <h2>Step 3 — Credit Committee write-up</h2>
          <div className="subtle">Generates a professionally written credit application using extracted financials + RM inputs.</div>

          <div className="btn-row">
            <button onClick={onGenerateCreditMemo} disabled={busyMemo || loadingPdf}>
              {busyMemo ? "Generating..." : "Generate Credit Application"}
            </button>
            <button className="secondary" onClick={() => setCreditMemo("")} disabled={busyMemo}>
              Clear output
            </button>
          </div>

          {creditMemo ? (
            <>
              <div className="btn-row">
                <button className="secondary" onClick={onCopyMemo}>
                  {copied ? "Copied" : "Copy to clipboard"}
                </button>
              </div>
              <pre className="output">{creditMemo}</pre>
            </>
          ) : (
            <div className="subtle" style={{ marginTop: 10 }}>
              Upload financials (Step 1), complete RM inputs (Step 2), then generate the write-up.
            </div>
          )}

          <div className="subtle" style={{ marginTop: 10 }}>Connection: {API_BASE ? API_BASE : ""}</div>
        </section>
      </main>
    </div>
  );
}

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  Check,
  FileSpreadsheet,
  FileUp,
  Fingerprint,
  LayoutDashboard,
  LockKeyhole,
  LogIn,
  LogOut,
  Mail,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  Wallet,
  X,
} from "lucide-react";

type User = { id: number; email: string; created_at: string };
type Invoice = {
  invoice_id: string;
  client: string;
  invoice_date: string;
  due_date: string;
  amount: number;
  status: string;
  paid_date?: string | null;
  paid: boolean;
};
type Analytics = {
  invoice_count: number;
  outstanding_total: number;
  overdue_total: number;
  overdue_count: number;
  expected_30_day_inflow: number;
  forecast: { date: string; expected_inflow: number; invoice_count: number }[];
  client_signals: {
    client: string;
    paid_invoice_count: number;
    average_days_late: number;
    late_invoice_count: number;
    evidence_note: string;
  }[];
  caveats: string[];
  invoices: Invoice[];
};
type RiskPrediction = {
  invoice_id: string;
  client: string;
  amount: number;
  due_date: string;
  experimental_late_score: number;
  label: string;
  warning: string;
};
type RiskMetric = {
  accuracy?: number;
  balanced_accuracy?: number;
  f1_late?: number;
  roc_auc?: number | null;
  status?: string;
  reason?: string;
};
type PaymentResponse = {
  benchmark: {
    status: "ok" | "insufficient_data";
    labeled_rows: number;
    message?: string;
    caveat?: string;
    models?: Record<string, RiskMetric>;
  };
  payment_risk: {
    status: "ok" | "insufficient_data" | "unavailable";
    message?: string;
    reason?: string;
    labeled_rows?: number;
    predictions: RiskPrediction[];
    caveat?: string;
  };
  notice: string;
};
type CashflowBrief = {
  model: string;
  focus: string;
  headline: string;
  recommendations: string[];
  local_inference: boolean;
  notice: string;
};
const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
const money = (n: number) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n || 0);
const shortDate = (s: string) => {
  if (!s) return "—";
  const d = new Date(s + "T12:00:00");
  return Number.isNaN(+d)
    ? s
    : d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
};

function App() {
  const [token, setToken] = useState(
    () => localStorage.getItem("cashflowlens_token") || "",
  );
  const [user, setUser] = useState<User | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "register">("register");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState("");
  const [data, setData] = useState<Analytics | null>(null);
  const [fileName, setFileName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Invoice | null>(null);
  const [draftOpen, setDraftOpen] = useState(false);
  const [aiBrief, setAiBrief] = useState<CashflowBrief | null>(null);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiError, setAiError] = useState("");
  const [aiModel, setAiModel] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const aiRequestId = useRef(0);
  const riskRequestId = useRef(0);
  const [riskData, setRiskData] = useState<PaymentResponse | null>(null);
  const [riskBusy, setRiskBusy] = useState(false);
  const [riskError, setRiskError] = useState("");
  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const requestHeaders = useMemo(
    () => ({ Authorization: `Bearer ${token}` }),
    [token],
  );
  useEffect(() => {
    if (!token) return;
    fetch(`${API}/api/auth/me`, { headers: requestHeaders })
      .then(async (r) => {
        if (!r.ok) throw new Error("session");
        setUser(await r.json());
      })
      .catch(() => {
        localStorage.removeItem("cashflowlens_token");
        setToken("");
        setUser(null);
      });
  }, [token, requestHeaders]);
  const signOut = () => {
    aiRequestId.current += 1;
    riskRequestId.current += 1;
    localStorage.removeItem("cashflowlens_token");
    setToken("");
    setUser(null);
    setData(null);
    setFileName("");
    setAiBrief(null);
    setAiError("");
    setAiModel("");
    setAiBusy(false);
    setSourceFile(null);
    setRiskBusy(false);
    setRiskData(null);
    setRiskError("");
  };
  const authenticate = async (e: FormEvent) => {
    e.preventDefault();
    setAuthBusy(true);
    setAuthError("");
    try {
      const r = await fetch(`${API}/api/auth/${authMode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const body = await r.json();
      if (!r.ok) throw new Error(body.detail || "Could not authenticate.");
      localStorage.setItem("cashflowlens_token", body.access_token);
      setToken(body.access_token);
      setUser(body.user);
      setPassword("");
    } catch (err) {
      setAuthError(
        err instanceof Error ? err.message : "Something went wrong.",
      );
    } finally {
      setAuthBusy(false);
    }
  };
  const importFile = async (file?: File) => {
    if (!file) return;
    setError("");
    setToast("");
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const r = await fetch(`${API}/api/analytics/upload`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      const body = await r.json();
      if (r.status === 401) {
        signOut();
        throw new Error("Your session expired. Please log in again.");
      }
      if (!r.ok) throw new Error(body.detail || "Could not analyze this file.");
      setData(body);
      setFileName(file.name);
      setSourceFile(file);
      aiRequestId.current += 1;
      setAiBrief(null);
      setAiError("");
      setAiModel("");
      setAiBusy(false);
      riskRequestId.current += 1;
      setRiskBusy(false);
      setRiskData(null);
      setRiskError("");
      setSelected(body.invoices.find((i: Invoice) => !i.paid) || null);
      setToast(
        `Analyzed ${body.invoice_count} invoice rows from ${file.name}.`,
      );
      void explain(body);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };
  const analyzePaymentRisk = async () => {
    if (!sourceFile) return;
    const requestId = ++riskRequestId.current;
    setRiskBusy(true);
    setRiskError("");
    setRiskData(null);
    try {
      const form = new FormData();
      form.append("file", sourceFile);
      const r = await fetch(`${API}/api/payment-risk/upload`, {
        method: "POST",
        headers: requestHeaders,
        body: form,
      });
      const body = await r.json();
      if (requestId !== riskRequestId.current) return;
      if (r.status === 401) {
        signOut();
        throw new Error("Your session expired. Please log in again.");
      }
      if (!r.ok)
        throw new Error(body.detail || "Could not analyze payment risk.");
      if (requestId === riskRequestId.current) setRiskData(body);
    } catch (err) {
      if (requestId === riskRequestId.current) {
        setRiskError(
          err instanceof Error
            ? err.message
            : "Could not analyze payment risk.",
        );
      }
    } finally {
      if (requestId === riskRequestId.current) setRiskBusy(false);
    }
  };
  const unpaid = (data?.invoices || []).filter((i) => !i.paid);
  const rows = unpaid.filter((i) =>
    i.client.toLowerCase().includes(search.toLowerCase()),
  );
  const overdueRows = unpaid.filter(
    (i) => i.due_date < new Date().toISOString().slice(0, 10),
  );
  const chartData = (data?.forecast || []).map((p) => ({
    date: shortDate(p.date),
    amount: p.expected_inflow,
    count: p.invoice_count,
  }));
  const riskByInvoice = useMemo(
    () =>
      new Map(
        (riskData?.payment_risk.predictions || []).map((prediction) => [
          prediction.invoice_id,
          prediction,
        ]),
      ),
    [riskData],
  );
  const draft = selected
    ? `Subject: Quick follow-up on ${selected.invoice_id}\n\nHi ${selected.client},\n\nI hope you’re doing well. I’m checking in on invoice ${selected.invoice_id} for ${money(selected.amount)}, which was due on ${shortDate(selected.due_date)}. Could you let me know when I might expect payment, or if you need anything else from me?\n\nThanks so much,\n[Your name]`
    : "";
  const explain = async (analytics: Analytics) => {
    const requestId = ++aiRequestId.current;
    setAiBusy(true);
    setAiBrief(null);
    setAiError("");
    try {
      const r = await fetch(`${API}/api/explain`, {
        method: "POST",
        headers: { ...requestHeaders, "Content-Type": "application/json" },
        body: JSON.stringify({
          summary: {
            invoice_count: analytics.invoice_count,
            outstanding_total: analytics.outstanding_total,
            overdue_total: analytics.overdue_total,
            overdue_count: analytics.overdue_count,
            expected_30_day_inflow: analytics.expected_30_day_inflow,
            client_signals: analytics.client_signals.map((s) => ({
              paid_invoice_count: s.paid_invoice_count,
              average_days_late: s.average_days_late,
              late_invoice_count: s.late_invoice_count,
            })),
          },
        }),
      });
      const body = await r.json();
      if (requestId !== aiRequestId.current) return;
      if (!r.ok) {
        throw new Error(
          body.detail ||
            "Local Gemma is unavailable. Start Ollama and check its model configuration.",
        );
      }
      if (
        typeof body.headline !== "string" ||
        typeof body.focus !== "string" ||
        !Array.isArray(body.recommendations) ||
        body.recommendations.length === 0 ||
        !body.recommendations.every(
          (recommendation: unknown) => typeof recommendation === "string",
        ) ||
        typeof body.model !== "string" ||
        body.local_inference !== true ||
        typeof body.notice !== "string"
      ) {
        throw new Error(
          "Local Gemma returned an invalid brief. Try generating it again.",
        );
      }
      setAiBrief({
        model: body.model,
        focus: body.focus,
        headline: body.headline,
        recommendations: body.recommendations,
        local_inference: body.local_inference,
        notice: body.notice,
      });
      setAiModel(body.model);
    } catch (err) {
      if (requestId === aiRequestId.current) {
        setAiError(
          err instanceof Error
            ? err.message
            : "Local Gemma could not generate a cash-flow brief.",
        );
      }
    } finally {
      if (requestId === aiRequestId.current) setAiBusy(false);
    }
  };
  if (!token || !user)
    return (
      <div className="auth-shell">
        <div className="auth-visual">
          <div className="auth-brand">
            <div className="brand-mark">
              <Activity size={22} />
            </div>
            <div>
              <b>
                cashflow<span>lens</span>
              </b>
              <small>FINANCIAL CLARITY</small>
            </div>
          </div>
          <div className="auth-copy">
            <div className="eyebrow">
              <span className="eyebrow-line" /> LOCAL GEMMA · PRIVATE BY DESIGN
            </div>
            <h1>
              A calmer way to
              <br />
              <em>read your cash flow.</em>
            </h1>
            <p>
              Turn real invoice data into a clear, locally generated cash-flow
              brief. Your client rows stay out of the model prompt.
            </p>
            <div className="auth-visual-card">
              <div className="mini-card-top">
                <span>Cash-flow clarity</span>
                <span className="green-dot" />{" "}
              </div>
              <div className="mini-bars">
                <i />
                <i />
                <i />
                <i />
                <i />
                <i />
                <i />
                <i />
                <i />
                <i />
                <i />
                <i />
              </div>
              <div className="mini-card-foot">
                <span>Clear numbers. Calmer decisions.</span>
                <ShieldCheck size={16} />
              </div>
            </div>
          </div>
          <div className="auth-bottom">
            PRIVATE BY DESIGN <span>·</span> BUILT FOR INDEPENDENT WORK
          </div>
        </div>
        <div className="auth-panel">
          <form className="auth-form" onSubmit={authenticate}>
            <div className="mobile-brand">
              <div className="brand-mark">
                <Activity size={20} />
              </div>
              <b>
                cashflow<span>lens</span>
              </b>
            </div>
            <div className="auth-kicker">YOUR FINANCIAL WORKSPACE</div>
            <h2>
              {authMode === "register"
                ? "Start with clarity."
                : "Welcome back."}
            </h2>
            <p className="auth-sub">
              {authMode === "register"
                ? "Create your account, then upload your invoice data to begin."
                : "Sign in to continue to your workspace."}
            </p>
            <label htmlFor="email">Email address</label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              placeholder="you@studio.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete={
                authMode === "register" ? "new-password" : "current-password"
              }
              placeholder="At least 8 characters"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={8}
              required
            />
            <div className="auth-security">
              <LockKeyhole size={15} />
              <span>
                Passwords are hashed. Invoice files aren't saved by the API.
              </span>
            </div>
            {authError && <div className="inline-error">{authError}</div>}
            <button
              className="primary-btn auth-submit"
              type="submit"
              disabled={authBusy}
            >
              {authBusy
                ? "Please wait…"
                : authMode === "register"
                  ? "Create account"
                  : "Log in"}{" "}
              <ArrowUpRight size={16} />
            </button>
            <p className="auth-switch">
              {authMode === "register"
                ? "Already have an account?"
                : "New to CashFlowLens?"}{" "}
              <button
                type="button"
                onClick={() => {
                  setAuthMode(authMode === "register" ? "login" : "register");
                  setAuthError("");
                }}
              >
                {authMode === "register" ? "Log in" : "Create an account"}
              </button>
            </p>
            <p className="auth-disclaimer">
              Prototype authentication for local development. Configure a strong
              token secret and HTTPS before public deployment.
            </p>
          </form>
        </div>
      </div>
    );
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Activity size={21} />
          </div>
          <div>
            <b>
              cashflow<span>lens</span>
            </b>
            <small>FINANCIAL CLARITY</small>
          </div>
        </div>
        <div className="workspace">
          <div className="avatar">{user.email[0].toUpperCase()}</div>
          <div className="workspace-copy">
            <b>My workspace</b>
            <small>Personal account</small>
          </div>
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav>
          <button className="nav-item active">
            <LayoutDashboard size={17} /> Overview
          </button>
          <button
            className="nav-item"
            onClick={() =>
              document
                .getElementById("invoices")
                ?.scrollIntoView({ behavior: "smooth" })
            }
          >
            <Wallet size={17} /> Invoices{" "}
            <span className="nav-count">{unpaid.length}</span>
          </button>
          <button
            className="nav-item"
            onClick={() => {
              setSelected(unpaid[0] || null);
              setDraftOpen(true);
            }}
          >
            <Mail size={17} /> Follow-ups
          </button>
          <button
            className="nav-item"
            onClick={() =>
              document
                .getElementById("forecast")
                ?.scrollIntoView({ behavior: "smooth" })
            }
          >
            <ArrowDownRight size={17} /> Forecasts
          </button>
        </nav>
        <div className="nav-label tools-label">PREFERENCES</div>
        <button
          className="nav-item"
          onClick={() =>
            setToast(
              "Uploads are analyzed in the API memory for this request; invoice rows are not persisted.",
            )
          }
        >
          <ShieldCheck size={17} /> Privacy & data
        </button>
        <div className="sidebar-bottom">
          <div className="privacy-card">
            <div className="privacy-icon">
              <LockKeyhole size={16} />
            </div>
            <b>Your numbers stay yours.</b>
            <p>
              Uploads are analyzed on request. The API doesn't save invoice
              rows.
            </p>
            <span>
              <span className="green-dot" /> PRIVACY-FIRST MVP
            </span>
          </div>
          <div className="profile">
            <div className="profile-avatar">
              {user.email.slice(0, 2).toUpperCase()}
            </div>
            <div className="profile-copy">
              <b>{user.email}</b>
              <small>Personal workspace</small>
            </div>
            <button
              className="logout-button"
              aria-label="Log out"
              title="Log out"
              onClick={signOut}
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <span>/</span> <b>Overview</b>
          </div>
          <div className="top-actions">
            <div className="date-chip">
              <span className="green-dot" />{" "}
              {data ? "Analysis complete" : "Ready for your data"}
            </div>
            <button
              className="help-button"
              onClick={() =>
                setToast(
                  "Upload a CSV or XLSX with client, invoice_date, due_date, amount, and status columns.",
                )
              }
            >
              Help
            </button>
          </div>
        </header>
        <div className="content">
          <section className="welcome-row">
            <div>
              <div className="eyebrow">
                <span className="eyebrow-line" /> LOCAL GEMMA · YOUR CASH-FLOW COPILOT
              </div>
              <h1>
                Clear numbers.
                <br />
                <em>Smarter next steps.</em>
              </h1>
              <p className="welcome-sub">
                Upload real invoices for a verified financial snapshot and a
                local Gemma brief. Only qualitative signals derived from
                aggregate analytics—not client names or invoice rows—reach your
                configured Ollama model.
              </p>
            </div>
            <div className="welcome-actions">
              <button
                className="primary-btn"
                onClick={() => fileRef.current?.click()}
                disabled={busy}
              >
                <FileUp size={16} />
                {busy ? "Analyzing…" : "Upload invoice file"}
              </button>
              <input
                ref={fileRef}
                type="file"
                accept=".csv,.xlsx,.xls,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel"
                hidden
                onChange={(e) => importFile(e.target.files?.[0])}
              />
            </div>
          </section>
          <div className="data-note" aria-busy={busy}>
            <div className="note-icon">
              <Fingerprint size={17} />
            </div>
            <div>
              <b>
                {busy
                  ? "Analyzing your file"
                  : fileName
                    ? "Last analyzed file"
                    : "Your workspace is ready"}
              </b>
              <span>
                {fileName
                  ? `${fileName} · ${data?.invoice_count || 0} rows analyzed`
                  : "Upload a CSV or Excel workbook to replace this empty state with real calculations."}
              </span>
            </div>
            <button onClick={() => fileRef.current?.click()}>
              {fileName ? "Replace file" : "Choose file"}{" "}
              <ArrowUpRight size={14} />
            </button>
          </div>
          {error && (
            <div className="upload-error" role="alert">
              <X size={17} />
              <div>
                <b>We couldn't analyze that file</b>
                <span>{error}</span>
              </div>
              <button onClick={() => setError("")}>
                <X size={15} />
              </button>
            </div>
          )}
          {!data ? (
            <section className="upload-empty">
              <div className="upload-illustration">
                <div className="upload-file-icon">
                  <FileSpreadsheet size={28} />
                </div>
                <div className="upload-cloud-icon">
                  <UploadCloud size={23} />
                </div>
              </div>
              <h2>Your numbers, not sample data.</h2>
              <p>
                Start by uploading your invoice export. We'll check the columns,
                validate the rows, and calculate your first cash-flow snapshot.
              </p>
              <button
                className="primary-btn"
                onClick={() => fileRef.current?.click()}
                disabled={busy}
              >
                <UploadCloud size={17} />
                {busy ? "Analyzing your file…" : "Choose CSV or XLSX"}
              </button>
              <div className="file-hints">
                <span>
                  <Check size={13} /> CSV
                </span>
                <span>
                  <Check size={13} /> Excel (.xlsx)
                </span>
                <span>
                  <LockKeyhole size={13} /> Max 8 MB
                </span>
              </div>
              <details className="format-details">
                <summary>What columns do I need?</summary>
                <p>
                  Required: <code>client</code>, <code>invoice_date</code>,{" "}
                  <code>due_date</code>, <code>amount</code>, and{" "}
                  <code>status</code>. Optional: <code>invoice_id</code> and{" "}
                  <code>paid_date</code>. Dates should be recognizable by
                  Excel/Pandas; ISO dates (YYYY-MM-DD) are recommended.
                </p>
                <a href="/sample-data/invoices.csv" download>
                  Download a sample CSV
                </a>
              </details>
            </section>
          ) : (
            <>
              <section className="metric-grid">
                <article className="metric-card main-metric">
                  <div className="metric-head">
                    <span>Outstanding invoices</span>
                    <span className="metric-icon mint">
                      <Wallet size={17} />
                    </span>
                  </div>
                  <div className="metric-value">
                    {money(data.outstanding_total)}
                  </div>
                  <div className="metric-foot">
                    <span className="pill pill-amber">
                      {unpaid.length} unpaid invoices
                    </span>
                    <span className="metric-context">
                      Across {new Set(unpaid.map((i) => i.client)).size} clients
                    </span>
                  </div>
                  <div className="metric-decoration">
                    <div />
                    <div />
                    <div />
                    <div />
                    <div />
                    <div />
                    <div />
                    <div />
                  </div>
                </article>
                <article className="metric-card">
                  <div className="metric-head">
                    <span>Overdue right now</span>
                    <span className="metric-icon rose">
                      <ArrowDownRight size={17} />
                    </span>
                  </div>
                  <div className="metric-value">
                    {money(data.overdue_total)}
                  </div>
                  <div className="metric-foot">
                    <span className="pill pill-rose">
                      {data.overdue_count} overdue
                    </span>
                    <span className="metric-context">Needs attention</span>
                  </div>
                </article>
                <article className="metric-card">
                  <div className="metric-head">
                    <span>Expected in 30 days</span>
                    <span className="metric-icon blue">
                      <ArrowUpRight size={17} />
                    </span>
                  </div>
                  <div className="metric-value">
                    {money(data.expected_30_day_inflow)}
                  </div>
                  <div className="metric-foot">
                    <span className="pill pill-blue">Due-date estimate</span>
                  </div>
                </article>
              </section>
              <section
                className="panel ai-panel ai-core-panel"
                aria-labelledby="ai-brief-heading"
              >
                <div className="ai-panel-icon">
                  <Sparkles size={19} />
                </div>
                <div className="ai-panel-body">
                  <div className="ai-brief-heading">
                    <div>
                      <div className="section-kicker">
                        LOCAL GEMMA · QUALITATIVE SIGNALS ONLY
                      </div>
                      <h2 id="ai-brief-heading">
                        Your AI cash-flow brief
                      </h2>
                    </div>
                    {aiModel && (
                      <span className="ai-model-badge">
                        <span className="green-dot" />
                        {aiModel} · local
                      </span>
                    )}
                  </div>
                  <p className="ai-brief-description">
                    Every invoice upload triggers Gemma to interpret
                    qualitative cash-flow signals and suggest practical
                    follow-ups. Verified figures remain deterministic; the
                    model adds context, not accounting guesses.
                  </p>
                  <div
                    className={`ai-brief-content ${aiBusy ? "is-loading" : ""}`}
                    aria-live="polite"
                    aria-busy={aiBusy}
                  >
                    {aiBusy ? (
                      <>
                        <span className="loading-dot" />
                        <span>
                          Gemma is preparing a brief from aggregate figures…
                        </span>
                      </>
                    ) : aiError ? (
                      <div className="ai-brief-error" role="alert">
                        <b>Local Gemma could not generate the brief.</b>
                        <span>{aiError}</span>
                        <span>
                          Your uploaded invoice analytics are still available
                          above.
                        </span>
                      </div>
                    ) : aiBrief ? (
                      <div className="ai-result">
                        <h3>{aiBrief.headline}</h3>
                        <ul>
                          {aiBrief.recommendations.map((recommendation) => (
                            <li key={recommendation}>{recommendation}</li>
                          ))}
                        </ul>
                        <p>{aiBrief.notice}</p>
                      </div>
                    ) : (
                      <span>
                        Upload a real invoice file to generate your first
                        private brief.
                      </span>
                    )}
                  </div>
                </div>
                <button
                  className="secondary-btn ai-regenerate"
                  onClick={() => void explain(data)}
                  disabled={aiBusy || busy}
                  aria-busy={aiBusy}
                >
                  <Sparkles size={15} />
                  {aiBusy ? "Generating brief…" : "Regenerate with Gemma"}
                </button>
              </section>
              <section className="panel-grid" id="forecast">
                <article className="panel chart-panel">
                  <div className="panel-heading">
                    <div>
                      <div className="section-kicker">NEXT 30 DAYS</div>
                      <h2>Expected inflows</h2>
                    </div>
                    <span className="chart-legend">
                      <i /> Expected
                    </span>
                  </div>
                  {chartData.length ? (
                    <div className="chart-wrap">
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart
                          data={chartData}
                          margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
                        >
                          <defs>
                            <linearGradient
                              id="cashFill"
                              x1="0"
                              y1="0"
                              x2="0"
                              y2="1"
                            >
                              <stop
                                offset="0%"
                                stopColor="#4277e8"
                                stopOpacity={0.25}
                              />
                              <stop
                                offset="95%"
                                stopColor="#4277e8"
                                stopOpacity={0.01}
                              />
                            </linearGradient>
                          </defs>
                          <CartesianGrid
                            strokeDasharray="3 5"
                            vertical={false}
                            stroke="#e4eaf3"
                          />
                          <XAxis
                            dataKey="date"
                            axisLine={false}
                            tickLine={false}
                            tick={{ fill: "#667891", fontSize: 11 }}
                          />
                          <YAxis
                            axisLine={false}
                            tickLine={false}
                            tick={{ fill: "#667891", fontSize: 11 }}
                            tickFormatter={(v) =>
                              `$${v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v}`
                            }
                          />
                          <Tooltip formatter={(v) => money(Number(v))} />
                          <Area
                            type="monotone"
                            dataKey="amount"
                            name="Expected inflow"
                            stroke="#2459d8"
                            strokeWidth={2.5}
                            fill="url(#cashFill)"
                          />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <div className="chart-empty">
                      No unpaid invoices are due in the next 30 days.
                    </div>
                  )}
                  <p className="chart-caveat">
                    Based on unpaid invoice due dates, not a
                    probability-weighted forecast.
                  </p>
                </article>
                <article className="panel signals-panel">
                  <div className="panel-heading">
                    <div>
                      <div className="section-kicker">PAYMENT PATTERNS</div>
                      <h2>Client signals</h2>
                      <p className="signals-description">
                        Understand payment behaviour from your clients' history.
                      </p>
                    </div>

                    <span className="signal-count">
                      {data.client_signals.length} clients
                    </span>
                  </div>

                  {data.client_signals.length > 0 ? (
                    <div className="signals-grid">
                      {data.client_signals.slice(0, 6).map((s) => (
                        <div className="signal-card" key={s.client}>
                          <div className="signal-card-header">
                            <div className="signal-avatar">
                              {s.client.trim().slice(0, 1).toUpperCase() || "C"}
                            </div>

                            <div className="signal-copy">
                              <b>{s.client}</b>
                              <small>
                                {s.paid_invoice_count} paid invoice
                                {s.paid_invoice_count === 1 ? "" : "s"}
                              </small>
                            </div>
                          </div>

                          <div className="signal-metrics">
                            <div className="signal-metric">
                              <small>Late payments</small>
                              <b
                                className={
                                  s.late_invoice_count > 0
                                    ? "signal-late"
                                    : "signal-good"
                                }
                              >
                                {s.late_invoice_count}
                              </b>
                            </div>

                            <div className="signal-metric">
                              <small>Average delay</small>
                              <b>{s.average_days_late.toFixed(1)}d</b>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="no-signals">
                      No paid invoices with a recorded paid date yet. Add{" "}
                      <code>paid_date</code> to unlock historical payment
                      patterns.
                    </p>
                  )}

                  <p className="signal-footnote">
                    Descriptive history only. Small samples may be unreliable.
                  </p>
                </article>
              </section>
              <section
                className="panel risk-panel"
                aria-labelledby="risk-heading"
              >
                <div className="panel-heading risk-heading">
                  <div>
                    <div className="section-kicker">OPTIONAL · EXPERIMENTAL</div>
                    <h2 id="risk-heading">Payment risk signals</h2>
                    <p className="risk-description">
                      Compare unpaid invoices with payment patterns in this
                      file's history. Analysis runs only when you request it.
                    </p>
                  </div>
                  <button
                    className="secondary-btn compact"
                    onClick={analyzePaymentRisk}
                    disabled={!sourceFile || busy || riskBusy}
                    aria-busy={riskBusy}
                  >
                    <Activity size={15} />
                    {riskBusy ? "Analyzing history…" : "Analyze payment risk"}
                  </button>
                </div>
                <div className="risk-notice" role="note">
                  <ShieldCheck size={16} />
                  <span>
                    Experimental model scores are uncalibrated estimates, not
                    probabilities or guarantees of payment.
                  </span>
                </div>
                {riskError && (
                  <div className="upload-error" role="alert">
                    <X size={17} />
                    <div>
                      <b>Payment-risk analysis is unavailable</b>
                      <span>{riskError}</span>
                    </div>
                    <button
                      aria-label="Dismiss payment-risk error"
                      onClick={() => setRiskError("")}
                    >
                      <X size={15} />
                    </button>
                  </div>
                )}
                {riskBusy ? (
                  <div
                    className="risk-state"
                    role="status"
                    aria-live="polite"
                  >
                    <span className="loading-dot" />
                    Evaluating historical payment data…
                  </div>
                ) : !sourceFile ? (
                  <div className="risk-state">
                    Upload an invoice file to make an optional risk analysis
                    available.
                  </div>
                ) : !riskData ? (
                  <div className="risk-state">
                    No risk scores have been run for this file.
                  </div>
                ) : riskData.payment_risk.status !== "ok" ? (
                  <div className="risk-state">
                    <b>
                      {riskData.payment_risk.status === "insufficient_data"
                        ? "More labeled payment history is needed."
                        : "The experimental model is unavailable."}
                    </b>
                    <span>
                      {riskData.payment_risk.message ||
                        riskData.benchmark.message ||
                        riskData.payment_risk.reason ||
                        "Use the deterministic invoice analytics above."}
                    </span>
                  </div>
                ) : riskData.payment_risk.predictions.length === 0 ? (
                  <div className="risk-state">
                    No unpaid invoices were available to score.
                  </div>
                ) : (
                  <>
                    <div className="risk-results-heading">
                      <b>
                        {riskData.payment_risk.predictions.length} invoice
                        {riskData.payment_risk.predictions.length === 1
                          ? ""
                          : "s"}{" "}
                        assessed
                      </b>
                      <span>
                        Based on {riskData.payment_risk.labeled_rows ?? 0}{" "}
                        labeled historical invoices
                      </span>
                    </div>
                    <div className="risk-results">
                      {riskData.payment_risk.predictions.map((prediction) => {
                        const score = Math.min(
                          1,
                          Math.max(0, prediction.experimental_late_score),
                        );
                        const higher =
                          prediction.label === "higher relative score";
                        return (
                          <article
                            className="risk-result"
                            key={prediction.invoice_id}
                          >
                            <div className="risk-result-top">
                              <div>
                                <b>{prediction.client}</b>
                                <small>{prediction.invoice_id}</small>
                              </div>
                              <span
                                className={`risk-badge ${higher ? "risk-badge-high" : "risk-badge-low"}`}
                              >
                                <i />
                                {higher
                                  ? "Higher relative score"
                                  : "Lower relative score"}
                              </span>
                            </div>
                            <div className="risk-result-meta">
                              <span>Due {shortDate(prediction.due_date)}</span>
                              <b>{money(prediction.amount)}</b>
                            </div>
                            <div className="risk-score-label">
                              <span>Experimental model score</span>
                              <b>{Math.round(score * 100)}%</b>
                            </div>
                            <progress
                              className={`risk-progress ${higher ? "risk-progress-high" : ""}`}
                              max={1}
                              value={score}
                              aria-label={`${prediction.invoice_id}: experimental model score, not a probability`}
                            />
                            <small className="risk-warning">
                              {prediction.warning}
                            </small>
                          </article>
                        );
                      })}
                    </div>
                    {riskData.benchmark.status === "ok" &&
                      riskData.benchmark.models && (
                        <div className="risk-benchmark">
                          <h3>Exploratory holdout benchmark</h3>
                          <div className="risk-benchmark-grid">
                            {Object.entries(riskData.benchmark.models).map(
                              ([name, metrics]) =>
                                metrics.balanced_accuracy !== undefined ? (
                                  <div key={name}>
                                    <span>
                                      {name.replace(/_/g, " ")}
                                    </span>
                                    <b>
                                      {Math.round(
                                        metrics.balanced_accuracy * 100,
                                      )}
                                      %
                                    </b>
                                    <small>balanced accuracy</small>
                                  </div>
                                ) : null,
                            )}
                          </div>
                          {riskData.benchmark.caveat && (
                            <p>{riskData.benchmark.caveat}</p>
                          )}
                        </div>
                      )}
                    <p className="risk-disclaimer">
                      {riskData.payment_risk.caveat || riskData.notice}
                    </p>
                  </>
                )}
              </section>
              <section className="panel invoice-panel" id="invoices">
                <div className="panel-heading">
                  <div>
                    <div className="section-kicker">YOUR RECEIVABLES</div>
                    <h2>
                      Unpaid invoices{" "}
                      <span className="heading-count">{unpaid.length}</span>
                    </h2>
                  </div>
                  <div className="table-tools">
                    <input
                      className="invoice-search"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder="Search clients…"
                      aria-label="Search clients"
                    />
                    <button
                      className="secondary-btn compact"
                      onClick={() => fileRef.current?.click()}
                    >
                      <FileUp size={14} /> Replace file
                    </button>
                  </div>
                </div>
                <div
                  className="table-scroll"
                  role="region"
                  tabIndex={0}
                  aria-label="Scrollable unpaid invoices table"
                >
                  <table>
                    <thead>
                      <tr>
                        <th scope="col">Invoice / Client</th>
                        <th scope="col">Due date</th>
                        <th scope="col">Amount</th>
                        <th scope="col">Risk signal</th>
                        <th scope="col">Status</th>
                        <th scope="col">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.slice(0, 12).map((i) => {
                        const late =
                          i.due_date < new Date().toISOString().slice(0, 10);
                        return (
                          <tr key={i.invoice_id}>
                            <td>
                              <b>{i.invoice_id}</b>
                              <small>{i.client}</small>
                            </td>
                            <td>{shortDate(i.due_date)}</td>
                            <td className="amount-cell">{money(i.amount)}</td>
                            <td>
                              {riskByInvoice.has(i.invoice_id) ? (
                                <span
                                  className={`risk-badge risk-badge-table ${riskByInvoice.get(i.invoice_id)?.label === "higher relative score" ? "risk-badge-high" : "risk-badge-low"}`}
                                >
                                  <i />
                                  {riskByInvoice.get(i.invoice_id)?.label ===
                                  "higher relative score"
                                    ? "Higher relative"
                                    : "Lower relative"}
                                </span>
                              ) : (
                                <span className="risk-not-assessed">
                                  Not assessed
                                </span>
                              )}
                            </td>
                            <td>
                              <span
                                className={`status-pill ${late ? "status-late" : "status-pending"}`}
                              >
                                <i />
                                {late ? "Overdue" : "Awaiting payment"}
                              </span>
                            </td>
                            <td>
                              <button
                                className="row-action"
                                onClick={() => {
                                  setSelected(i);
                                  setDraftOpen(true);
                                }}
                              >
                                Follow up <ArrowUpRight size={13} />
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                      {!rows.length && (
                        <tr>
                          <td colSpan={6} className="empty-row">
                            No matching unpaid invoices.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
                <div className="table-footer">
                  <span>
                    Showing {Math.min(rows.length, 12)} of {rows.length} unpaid
                    invoices
                  </span>
                  <span>{data.invoice_count} total rows analyzed</span>
                </div>
              </section>
              <section className="caveats">
                <b>Read this before making decisions</b>
                {data.caveats.map((c) => (
                  <span key={c}>· {c}</span>
                ))}
              </section>
            </>
          )}
          <footer>
            <span>
              © 2026 CashFlowLens <i /> Built for independent work.
            </span>
            <span>
              <LockKeyhole size={13} /> Your finances are personal. Treat them
              that way.
            </span>
          </footer>
        </div>
      </main>
      {draftOpen && (
        <div
          className="modal-backdrop"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setDraftOpen(false);
          }}
        >
          <div className="draft-modal">
            <div className="modal-head">
              <div className="modal-icon">
                <Mail size={19} />
              </div>
              <div>
                <div className="section-kicker">KEEP IT HUMAN</div>
                <h2>Draft a gentle follow-up</h2>
              </div>
              <button
                className="icon-button"
                onClick={() => setDraftOpen(false)}
              >
                <X size={18} />
              </button>
            </div>
            <p className="modal-sub">
              A starting point you can personalise before sending. Nothing is
              sent automatically.
            </p>
            {!selected && (
              <div className="select-invoice">
                <label>Choose an invoice</label>
                <select
                  onChange={(e) =>
                    setSelected(
                      unpaid.find((i) => i.invoice_id === e.target.value) ||
                        null,
                    )
                  }
                  value=""
                >
                  <option value="" disabled>
                    Select an unpaid invoice…
                  </option>
                  {unpaid.map((i) => (
                    <option key={i.invoice_id} value={i.invoice_id}>
                      {i.client} — {money(i.amount)}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <textarea
              className="draft-text"
              value={draft}
              readOnly
              placeholder="Choose an invoice to generate a draft."
            />
            <div className="modal-foot">
              <span>
                <LockKeyhole size={13} /> Drafted in your session · Review
                before sending
              </span>
              <button
                className="primary-btn"
                disabled={!draft}
                onClick={() => {
                  navigator.clipboard?.writeText(draft);
                  setToast(
                    "Draft copied. Give it a quick review before sending.",
                  );
                  setDraftOpen(false);
                }}
              >
                <Check size={16} /> Copy draft
              </button>
            </div>
          </div>
        </div>
      )}
      {toast && (
        <div className="toast">
          <Check size={16} />
          {toast}
          <button onClick={() => setToast("")}>
            <X size={14} />
          </button>
        </div>
      )}
    </div>
  );
}
export default App;

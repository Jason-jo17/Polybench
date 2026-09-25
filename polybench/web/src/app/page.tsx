"use client";

// PolyBench Dashboard — Industrial/Utilitarian dark theme

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

const MODEL_SUGGESTIONS: Record<string, string[]> = {
  anthropic: ["claude-sonnet-4-6", "claude-3-5-sonnet-20241022", "claude-3-haiku-20240307", "claude-opus-4-5"],
  openai: ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1-mini", "o3-mini"],
  groq: ["llama-3.3-70b-versatile", "llama3-70b-8192", "mixtral-8x7b-32768"],
  together: ["meta-llama/Llama-3-70b-chat-hf", "mistralai/Mixtral-8x22B"],
  mistral: ["mistral-large-latest", "mistral-medium-latest"],
  deepseek: ["deepseek-chat", "deepseek-coder"],
  gemini: ["gemini-1.5-pro", "gemini-1.5-flash"],
  ollama: ["llama3.2", "qwen2.5-coder", "codestral"],
  lmstudio: ["local-model"],
  mock: ["demo"],
};

const LANGUAGES = [
  { value: "", label: "All Languages" },
  { value: "python", label: "Python" },
  { value: "javascript", label: "JavaScript" },
  { value: "go", label: "Go" },
  { value: "rust", label: "Rust" },
];

interface Stats {
  total_runs: number;
  providers_used: number;
  avg_pass_at_k: number;
  total_tasks_executed?: number;
  most_used_model?: string;
}

interface Run {
  id: string;
  model: string;
  provider: string;
  status: string;
  pass_at_k: number;
  created_at: string;
  total_tasks: number;
}

export default function Dashboard() {
  const router = useRouter();

  const [provider, setProvider] = useState("mock");
  const [model, setModel] = useState("demo");
  const [samples, setSamples] = useState(2);
  const [k, setK] = useState(1);
  const [temperature, setTemperature] = useState(0.2);
  const [lang, setLang] = useState("");
  const [tags, setTags] = useState("");
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState<Stats>({ total_runs: 0, providers_used: 0, avg_pass_at_k: 0 });
  const [statsLoading, setStatsLoading] = useState(true);
  const [recentRuns, setRecentRuns] = useState<Run[]>([]);

  useEffect(() => {
    fetch("/api/stats")
      .then((r) => r.json())
      .then((d) => { setStats(d); setStatsLoading(false); })
      .catch(() => setStatsLoading(false));

    fetch("/api/runs?limit=5")
      .then((r) => r.json())
      .then((d) => setRecentRuns(Array.isArray(d) ? d : []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    const suggestions = MODEL_SUGGESTIONS[provider];
    if (suggestions?.length) setModel(suggestions[0]);
  }, [provider]);

  const startRun = async () => {
    setLoading(true);
    try {
      const body: Record<string, unknown> = { model, provider, samples, k, temperature };
      if (lang) body.lang = lang;
      if (tags) body.tags = tags;

      const res = await fetch("/api/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to start run.");
      toast.success(`Run ${data.run_id?.substring(0, 8)}… started`);
      if (data.run_id) setTimeout(() => router.push(`/runs/${data.run_id}`), 800);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to start run.");
    }
    setLoading(false);
  };

  const statCards = [
    { label: "Total Runs",      value: statsLoading ? <div className="h-8 w-16 bg-white/5 rounded animate-pulse" /> : String(stats.total_runs),                       sub: "all-time" },
    { label: "Providers Used",  value: statsLoading ? <div className="h-8 w-16 bg-white/5 rounded animate-pulse" /> : String(stats.providers_used),                   sub: "configured" },
    { label: "Avg Pass@k",      value: statsLoading ? <div className="h-8 w-16 bg-white/5 rounded animate-pulse" /> : `${(stats.avg_pass_at_k * 100).toFixed(1)}%`,   sub: "across all runs" },
  ];

  const passColor = (v: number) =>
    v >= 0.8 ? "var(--color-pass)" : v >= 0.4 ? "var(--color-warn)" : "var(--color-fail)";

  return (
    <div className="pb-fade-up">
      {/* Header */}
      <div className="pb-mb-2xl">
        <div className="pb-eyebrow">◈ Benchmark Control</div>
        <h1 className="pb-page-title">
          Evaluate<br />
          <span className="pb-accent">Frontier Models</span>
        </h1>
        <p className="pb-page-desc">
          Send real programming tasks to LLMs, execute their code in hardened Docker sandboxes,
          and score performance with pass@k.
        </p>
      </div>

      {/* Stat cards */}
      <div className="pb-grid-3 pb-mb-2xl">
        {statCards.map((card, i) => (
          <div key={card.label} className={`pb-stat-card pb-fade-up pb-fade-up-${i + 1}`}>
            <div className="pb-label">{card.label}</div>
            <div className="pb-stat-value">{card.value}</div>
            <div className="pb-stat-sub">{card.sub}</div>
          </div>
        ))}
      </div>

      {/* Run form */}
      <div className="pb-card pb-glow-line pb-fade-up pb-fade-up-2 pb-p-card-lg pb-mb-2xl">
        <div className="pb-section-title pb-mb-sm">Launch Benchmark</div>
        <p className="pb-form-desc">Configure the evaluation run parameters below.</p>

        <div className="pb-grid-2-form pb-mb-md">
          {/* Provider */}
          <div className="pb-form-group">
            <label className="pb-label" htmlFor="providerSelect">Provider</label>
            <select
              id="providerSelect"
              className="pb-input"
              title="Select AI provider"
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
            >
              {Object.keys(MODEL_SUGGESTIONS).map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>

          {/* Model */}
          <div className="pb-form-group">
            <label className="pb-label" htmlFor="modelInput">Model</label>
            <input
              id="modelInput"
              type="text"
              className="pb-input"
              title="Model name or identifier"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              list="model-suggestions"
              placeholder="model name"
            />
            <datalist id="model-suggestions">
              {(MODEL_SUGGESTIONS[provider] || []).map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
          </div>

          {/* Language filter */}
          <div className="pb-form-group">
            <label className="pb-label" htmlFor="langSelect">Language Filter</label>
            <select
              id="langSelect"
              className="pb-input"
              title="Filter tasks by programming language"
              value={lang}
              onChange={(e) => setLang(e.target.value)}
            >
              {LANGUAGES.map((l) => (
                <option key={l.value} value={l.value}>{l.label}</option>
              ))}
            </select>
          </div>

          {/* Tags */}
          <div className="pb-form-group">
            <label className="pb-label" htmlFor="tagsInput">Tags Filter (comma-separated)</label>
            <input
              id="tagsInput"
              type="text"
              className="pb-input"
              title="Comma-separated tags to filter tasks"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="e.g. data-structures, concurrency"
            />
          </div>

          {/* Samples */}
          <div className="pb-form-group">
            <label className="pb-label" htmlFor="samplesInput">Samples per Task (n)</label>
            <input
              id="samplesInput"
              type="number"
              className="pb-input"
              title="Number of code samples to generate per task"
              value={samples}
              onChange={(e) => setSamples(Number(e.target.value))}
              min={1}
              max={20}
            />
          </div>

          {/* k */}
          <div className="pb-form-group">
            <label className="pb-label" htmlFor="kInput">Pass@k Value (k)</label>
            <input
              id="kInput"
              type="number"
              className="pb-input"
              title="Value of k for pass@k scoring"
              value={k}
              onChange={(e) => setK(Number(e.target.value))}
              min={1}
              max={samples}
            />
          </div>

          {/* Temperature */}
          <div className="pb-form-group">
            <label className="pb-label" htmlFor="temperatureInput">
              Temperature — {temperature.toFixed(1)}
            </label>
            <input
              id="temperatureInput"
              type="range"
              min={0}
              max={2}
              step={0.1}
              value={temperature}
              title={`Temperature: ${temperature.toFixed(1)}`}
              onChange={(e) => setTemperature(Number(e.target.value))}
              className="pb-range-input"
            />
            <div className="pb-form-hint">
              <span>0.0 deterministic</span>
              <span>2.0 creative</span>
            </div>
          </div>
        </div>

        <div className="pb-form-actions">
          <button
            id="runBenchmarkBtn"
            className="pb-btn-primary"
            onClick={startRun}
            disabled={loading}
          >
            {loading ? <span className="pb-pulse">◈ Launching…</span> : "▶ Run Benchmark"}
          </button>
        </div>
      </div>

      {/* Recent runs */}
      {recentRuns.length > 0 && (
        <div className="pb-fade-up pb-fade-up-3">
          <div className="pb-recent-header">
            <div className="pb-section-title">Recent Runs</div>
            <a href="/runs" className="pb-view-all-link">View all →</a>
          </div>
          <div className="pb-card pb-overflow-hidden">
            <table className="pb-table">
              <thead>
                <tr>
                  <th>Run ID</th>
                  <th>Model</th>
                  <th>Status</th>
                  <th>Pass@k</th>
                  <th>Date</th>
                </tr>
              </thead>
              <tbody>
                {recentRuns.map((run) => {
                  const statusClass =
                    run.status === "RUNNING"   ? "pb-badge-running"  :
                    run.status === "COMPLETED" ? "pb-badge-complete" :
                    run.status === "PENDING"   ? "pb-badge-pending"  :
                    "pb-badge-failed";
                  return (
                    <tr key={run.id}>
                      <td>
                        <a href={`/runs/${run.id}`} className="pb-cell-id">
                          {run.id.substring(0, 8)}
                        </a>
                      </td>
                      <td className="pb-cell-mono">{run.model}</td>
                      <td>
                        <span className={`pb-badge ${statusClass}`}>
                          {run.status === "RUNNING" && <span className="pb-pulse" aria-hidden="true">●</span>}
                          {run.status}
                        </span>
                      </td>
                      <td>
                        <span className="pb-cell-pass-score" style={{ color: passColor(run.pass_at_k) }}>
                          {(run.pass_at_k * 100).toFixed(1)}%
                        </span>
                      </td>
                      <td className="pb-cell-muted">
                        {new Date(run.created_at).toLocaleDateString()}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

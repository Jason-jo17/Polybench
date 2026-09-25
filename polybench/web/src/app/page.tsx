"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { api, isActive, relativeTime, pct, type Run, type RunResults, type Stats } from "@/lib/api";
import { PageHead, ResultStrip, Score, Skeleton, Status, Empty } from "@/components/ui";

const MODEL_SUGGESTIONS: Record<string, string[]> = {
  anthropic: ["claude-sonnet-4-6", "claude-opus-4-5", "claude-3-5-sonnet-20241022", "claude-3-haiku-20240307"],
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

const PROVIDER_NAMES: Record<string, string> = {
  anthropic: "Anthropic", openai: "OpenAI", groq: "Groq", together: "Together",
  mistral: "Mistral", deepseek: "DeepSeek", gemini: "Gemini", ollama: "Ollama (local)",
  lmstudio: "LM Studio (local)", mock: "Mock (no API calls)",
};

const LANGUAGES = [
  { value: "", label: "All" },
  { value: "python", label: "Python" },
  { value: "javascript", label: "JavaScript" },
  { value: "go", label: "Go" },
  { value: "rust", label: "Rust" },
];

type ProviderStatus = Record<string, { configured: boolean; requires_key: boolean }>;
type RecentRun = Run & { taskScores?: number[] };

export default function Overview() {
  const router = useRouter();

  const [provider, setProvider] = useState("mock");
  const [model, setModel] = useState("demo");
  const [samples, setSamples] = useState(5);
  const [k, setK] = useState(1);
  const [temperature, setTemperature] = useState(0.2);
  const [lang, setLang] = useState("");
  const [tags, setTags] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const [stats, setStats] = useState<Stats | null>(null);
  const [recent, setRecent] = useState<RecentRun[] | null>(null);
  const [providers, setProviders] = useState<ProviderStatus>({});

  useEffect(() => {
    api<Stats>("/stats").then(setStats).catch(() => {});
    api<{ providers: ProviderStatus }>("/providers/status").then((d) => setProviders(d.providers)).catch(() => {});

    api<Run[]>("/runs?limit=6")
      .then(async (runs) => {
        setRecent(runs);
        const withScores = await Promise.all(
          runs.map((r) =>
            api<RunResults>(`/runs/${r.id}/results`)
              .then((d) => ({ ...r, taskScores: d.results.map((x) => x.task_pass_at_k) }))
              .catch(() => r),
          ),
        );
        setRecent(withScores);
      })
      .catch(() => setRecent([]));
  }, []);

  const changeProvider = (p: string) => {
    setProvider(p);
    const first = MODEL_SUGGESTIONS[p]?.[0];
    if (first) setModel(first);
  };

  const changeSamples = (n: number) => {
    const clamped = Math.max(1, Math.min(20, n || 1));
    setSamples(clamped);
    if (k > clamped) setK(clamped);
  };

  const missingKey = providers[provider]?.requires_key && !providers[provider]?.configured;

  const startRun = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const body: Record<string, unknown> = { model, provider, samples, k, temperature };
      if (lang) body.lang = lang;
      if (tags.trim()) body.tags = tags;
      const data = await api<{ run_id: string }>("/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      toast.success("Run started", { description: `${model} on ${lang ? lang : "all languages"}` });
      router.push(`/runs/${data.run_id}`);
    } catch (err) {
      toast.error("Couldn't start the run", { description: err instanceof Error ? err.message : undefined });
      setSubmitting(false);
    }
  };

  const figures = useMemo(
    () => [
      { label: "Runs", value: stats ? String(stats.total_runs) : null },
      { label: "Average pass@k", value: stats ? (stats.completed_runs ? pct(stats.avg_pass_at_k) : "—") : null },
      { label: "Task results", value: stats ? stats.total_tasks_executed.toLocaleString() : null },
      { label: "Most-run model", value: stats ? stats.most_used_model ?? "—" : null, small: true },
    ],
    [stats],
  );

  return (
    <>
      <PageHead
        title="Overview"
        lede="Send coding tasks to a model, run what it writes in an isolated sandbox against hidden tests, and score it with pass@k."
      />

      <div className="figures">
        {figures.map((f) => (
          <div className="figure" key={f.label}>
            <div className="figure-label">{f.label}</div>
            <div className={`figure-value${f.small ? " sm" : ""}`} title={f.value ?? undefined}>
              {f.value ?? <Skeleton w={64} h={26} />}
            </div>
          </div>
        ))}
      </div>

      <div className="overview-grid section">
        <form className="panel" onSubmit={startRun} aria-labelledby="new-run-title">
          <div className="panel-head">
            <h2 className="h2" id="new-run-title">New run</h2>
          </div>
          <div className="panel-pad stack" style={{ gap: 22 }}>
            <div className="grid-form">
              <div className="field">
                <label className="field-label" htmlFor="provider">Provider</label>
                <select id="provider" className="input" value={provider} onChange={(e) => changeProvider(e.target.value)}>
                  {Object.keys(MODEL_SUGGESTIONS).map((p) => (
                    <option key={p} value={p}>
                      {PROVIDER_NAMES[p] ?? p}
                      {providers[p]?.requires_key && !providers[p]?.configured ? " — no API key" : ""}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label className="field-label" htmlFor="model">Model</label>
                <input
                  id="model"
                  className="input code"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  list="model-suggestions"
                  placeholder="Model identifier"
                  required
                  autoComplete="off"
                  spellCheck={false}
                />
                <datalist id="model-suggestions">
                  {(MODEL_SUGGESTIONS[provider] ?? []).map((m) => <option key={m} value={m} />)}
                </datalist>
              </div>
            </div>

            {missingKey && (
              <div className="notice notice-part" role="status">
                No API key is set for {PROVIDER_NAMES[provider] ?? provider}. Add it to the backend <code>.env</code> file, or the run will fail.
              </div>
            )}

            <div className="field">
              <span className="field-label" id="lang-label">Language</span>
              <div className="seg" role="group" aria-labelledby="lang-label">
                {LANGUAGES.map((l) => (
                  <button type="button" key={l.value} aria-pressed={lang === l.value} onClick={() => setLang(l.value)}>
                    {l.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="field">
              <label className="field-label" htmlFor="tags">Tags</label>
              <input
                id="tags"
                className="input"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                placeholder="Optional, comma-separated: arrays, concurrency"
              />
            </div>

            <div className="grid-form">
              <div className="field">
                <label className="field-label" htmlFor="samples">Samples per task (n)</label>
                <input id="samples" type="number" className="input" min={1} max={20} value={samples} onChange={(e) => changeSamples(Number(e.target.value))} />
              </div>
              <div className="field">
                <label className="field-label" htmlFor="k">k</label>
                <input id="k" type="number" className="input" min={1} max={samples} value={k} onChange={(e) => setK(Math.max(1, Math.min(samples, Number(e.target.value) || 1)))} />
              </div>
            </div>
            <p className="field-hint" style={{ marginTop: -12 }}>
              pass@{k} is the chance that at least one of {k} sample{k > 1 ? "s" : ""} passes, estimated from {samples} per task.
            </p>

            <div className="field">
              <label className="field-label" htmlFor="temperature">
                Temperature <span className="score" style={{ color: "var(--ink)" }}>{temperature.toFixed(1)}</span>
              </label>
              <input id="temperature" type="range" className="range" min={0} max={2} step={0.1} value={temperature} onChange={(e) => setTemperature(Number(e.target.value))} />
              <div className="row field-hint" style={{ justifyContent: "space-between" }}>
                <span>Deterministic</span><span>Varied</span>
              </div>
            </div>

            <div className="row">
              <button type="submit" className="btn btn-primary" disabled={submitting || !model.trim()}>
                {submitting ? "Starting…" : "Start run"}
              </button>
            </div>
          </div>
        </form>

        <section className="panel" aria-labelledby="recent-title">
          <div className="panel-head">
            <h2 className="h2" id="recent-title">Recent runs</h2>
            <Link href="/runs" className="link">All runs</Link>
          </div>
          {recent === null ? (
            <ul className="recent">
              {[0, 1, 2, 3].map((i) => (
                <li key={i} className="recent-item"><Skeleton w="60%" /><Skeleton w="90%" h={10} /></li>
              ))}
            </ul>
          ) : recent.length === 0 ? (
            <Empty title="No runs yet">Start a run with the mock provider to see how results are reported. It doesn&apos;t call any API.</Empty>
          ) : (
            <ul className="recent">
              {recent.map((r) => (
                <li key={r.id}>
                  <Link href={`/runs/${r.id}`} className="recent-item">
                    <div className="row" style={{ gap: 10 }}>
                      <span className="model">{r.model}</span>
                      <span className="spacer" />
                      {isActive(r.status) ? <Status status={r.status} /> : <Score value={r.pass_at_k} />}
                    </div>
                    <ResultStrip values={r.taskScores ?? []} total={r.total_tasks} />
                    <div className="row sub" style={{ gap: 14 }}>
                      <span>{r.provider}</span>
                      <span>{r.total_tasks} tasks, {r.samples_per_task} samples each</span>
                      <span className="spacer" />
                      <span>{relativeTime(r.created_at)}</span>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}

// Types mirror the FastAPI models in src/polybench/models.py and api/main.py.

export type RunStatus = "PENDING" | "RUNNING" | "COMPLETED" | "FAILED";

export interface Run {
  id: string;
  created_at: string;
  model: string;
  provider: string;
  language_filter: string | null;
  samples_per_task: number;
  k: number;
  temperature: number;
  total_tasks: number;
  pass_at_k: number;
  status: RunStatus;
  git_sha: string | null;
}

export interface TaskScore {
  task_id: string;
  pass_at_k: number;
  /** 0 until the task's first sample finishes */
  samples_done: number;
}

/** A run from `/runs?include=task_scores`. */
export type RunWithScores = Run & { task_scores: TaskScore[] };

export interface TaskResult {
  id: string;
  run_id: string;
  task_id: string;
  language: string;
  difficulty: string;
  samples_generated: number;
  samples_passed: number;
  task_pass_at_k: number;
}

export interface Sample {
  id: string;
  task_result_id: string;
  sample_index: number;
  extracted_code: string | null;
  passed: boolean;
  failure_kind: string | null;
  exit_code: number | null;
  stdout: string;
  stderr: string;
  runtime_ms: number;
  timed_out: boolean;
  input_tokens: number | null;
  output_tokens: number | null;
}

export interface RunResults {
  run: Run;
  results: TaskResult[];
  samples: Sample[];
}

export interface Task {
  id: string;
  title: string;
  language: string;
  difficulty: string;
  tags: string[];
  prompt: string;
  signature: string;
  timeout_seconds: number;
}

export interface Stats {
  total_runs: number;
  completed_runs: number;
  active_runs: number;
  providers_used: number;
  avg_pass_at_k: number;
  most_used_model: string | null;
  total_tasks_executed: number;
}

export interface CompareRow {
  task_id: string;
  /** null when the task wasn't part of that run */
  run_a: number | null;
  run_b: number | null;
  /** run_b - run_a; null unless both runs include the task */
  delta: number | null;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init);
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = body && typeof body.detail === "string" ? body.detail : null;
    throw new Error(detail ?? `The API returned ${res.status} for ${path}.`);
  }
  return body as T;
}

export const isActive = (s: RunStatus) => s === "RUNNING" || s === "PENDING";

export const pct = (v: number | null | undefined, digits = 1) =>
  `${((v ?? 0) * 100).toFixed(digits)}%`;

export const shortId = (id: string) => id.slice(0, 8);

export const humanize = (s: string) => s.replace(/_/g, " ");

export function relativeTime(iso: string): string {
  // The API stores naive UTC timestamps.
  const t = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`).getTime();
  const diff = (Date.now() - t) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} d ago`;
  return new Date(t).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function absoluteTime(iso: string): string {
  const t = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
  return t.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export const LANG_COLORS: Record<string, string> = {
  python: "#3572A5",
  javascript: "#D9B400",
  go: "#00ADD8",
  rust: "#C0592B",
};

export const LANG_NAMES: Record<string, string> = {
  python: "Python",
  javascript: "JavaScript",
  go: "Go",
  rust: "Rust",
};

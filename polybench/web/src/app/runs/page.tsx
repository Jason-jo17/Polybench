"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

interface Run {
  id: string;
  model: string;
  provider: string;
  status: string;
  pass_at_k: number;
  total_tasks: number;
  samples_per_task: number;
  temperature: number;
  created_at: string;
}

function StatusBadge({ status }: { status: string }) {
  const cls =
    status === "RUNNING"   ? "pb-badge-running"  :
    status === "COMPLETED" ? "pb-badge-complete" :
    status === "PENDING"   ? "pb-badge-pending"  :
    "pb-badge-failed";

  return (
    <span className={`pb-badge ${cls}`}>
      {status === "RUNNING" && <span className="pb-pulse" aria-hidden="true">●</span>}
      {status}
    </span>
  );
}

const passColor = (v: number) =>
  v >= 0.8 ? "var(--color-pass)" : v >= 0.4 ? "var(--color-warn)" : "var(--color-fail)";

export default function Runs() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);
  const [limit, setLimit] = useState(20);

  const fetchRuns = () => {
    fetch(`/api/runs?limit=${limit}`)
      .then((r) => r.json())
      .then((data) => { setRuns(Array.isArray(data) ? data : []); setLoading(false); })
      .catch(() => setLoading(false));
  };

  useEffect(() => {
    setLoading(true);
    fetchRuns();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [limit]);

  useEffect(() => {
    const hasActive = runs.some((r) => r.status === "RUNNING" || r.status === "PENDING");
    if (!hasActive) return;
    const interval = setInterval(fetchRuns, 3000);
    return () => clearInterval(interval);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runs]);

  return (
    <div className="pb-fade-up">
      {/* Header */}
      <div className="pb-flex-between pb-mb-xl">
        <div>
          <div className="pb-eyebrow">◈ Execution Log</div>
          <h1 className="pb-page-title">Run History</h1>
        </div>
        <Link href="/" className="pb-new-run-link">+ New Run</Link>
      </div>

      {/* Table */}
      <div className="pb-card pb-overflow-hidden">
        {loading ? (
          <div className="pb-loading">
            <span className="pb-pulse">◈ Loading runs…</span>
          </div>
        ) : runs.length === 0 ? (
          <div className="pb-empty">
            <div className="pb-empty-title">No runs yet</div>
            <p className="pb-empty-body">Start your first benchmark from the dashboard.</p>
            <Link href="/" className="pb-empty-cta">▶ Launch Benchmark</Link>
          </div>
        ) : (
          <table className="pb-table">
            <thead>
              <tr>
                <th>Run ID</th>
                <th>Model</th>
                <th>Provider</th>
                <th>Status</th>
                <th>Pass@k</th>
                <th>Tasks</th>
                <th>Samples</th>
                <th>Date</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id}>
                  <td>
                    <Link href={`/runs/${run.id}`} className="pb-cell-id">
                      {run.id.substring(0, 10)}
                    </Link>
                  </td>
                  <td className="pb-cell-mono">{run.model}</td>
                  <td className="pb-cell-muted">{run.provider}</td>
                  <td><StatusBadge status={run.status} /></td>
                  <td>
                    <span className="pb-cell-pass-score" style={{ color: passColor(run.pass_at_k) }}>
                      {(run.pass_at_k * 100).toFixed(1)}%
                    </span>
                  </td>
                  <td className="pb-cell-muted">{run.total_tasks}</td>
                  <td className="pb-cell-muted">{run.samples_per_task}×</td>
                  <td className="pb-cell-muted-nowrap">
                    {new Date(run.created_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {runs.length === limit && (
        <div className="pb-pagination">
          <button className="pb-btn-ghost" onClick={() => setLimit((l) => l + 20)}>
            Load more
          </button>
        </div>
      )}

      <div className="pb-count-label">
        Showing {runs.length} run{runs.length !== 1 ? "s" : ""}
      </div>
    </div>
  );
}

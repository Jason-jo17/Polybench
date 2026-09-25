"use client";

// Compare Runs page — Industrial dark theme

import { useEffect, useState } from "react";

interface Run {
  id: string;
  model: string;
  provider: string;
  created_at: string;
  pass_at_k: number;
  status: string;
}

interface CompareRow {
  task_id: string;
  run_a: number;
  run_b: number;
}

function ScoreCell({ val }: { val: number }) {
  if (val === 1.0) return <span className="pb-cell-pass-score pb-pass">✓ Pass</span>;
  if (val === 0.0) return <span className="pb-cell-pass-score pb-fail">✗ Fail</span>;
  return <span className="pb-cell-pass-score" style={{ color: "var(--color-warn)" }}>{(val * 100).toFixed(0)}%</span>;
}

function DeltaCell({ delta }: { delta: number }) {
  if (delta === 0) return <span className="pb-cell-muted">—</span>;
  const positive = delta > 0;
  return (
    <span className="pb-cell-pass-score" style={{ color: positive ? "var(--color-pass)" : "var(--color-fail)" }}>
      {positive ? "+" : ""}{(delta * 100).toFixed(0)}%
    </span>
  );
}

export default function CompareRuns() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [runA, setRunA] = useState("");
  const [runB, setRunB] = useState("");
  const [compareData, setCompareData] = useState<CompareRow[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch("/api/runs?limit=50")
      .then((r) => r.json())
      .then((data: Run[]) => {
        const completed = data.filter((r) => r.status === "COMPLETED");
        setRuns(completed);
        if (completed.length >= 2) { setRunA(completed[0].id); setRunB(completed[1].id); }
        else if (completed.length === 1) setRunA(completed[0].id);
      })
      .catch(console.error);
  }, []);

  useEffect(() => {
    if (!runA || !runB || runA === runB) return;
    setLoading(true);
    fetch(`/api/runs/compare?run_a=${runA}&run_b=${runB}`)
      .then((r) => r.json())
      .then((data: CompareRow[]) => { setCompareData(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, [runA, runB]);

  const getRunLabel = (id: string) => {
    const run = runs.find((r) => r.id === id);
    if (!run) return id.substring(0, 8);
    return `${run.model} · ${run.provider} · ${new Date(run.created_at).toLocaleDateString()}`;
  };

  const runAScore = runs.find((r) => r.id === runA)?.pass_at_k ?? 0;
  const runBScore = runs.find((r) => r.id === runB)?.pass_at_k ?? 0;

  return (
    <div className="pb-fade-up">
      {/* Header */}
      <div className="pb-mb-xl">
        <div className="pb-eyebrow">◈ Diff Analysis</div>
        <h1 className="pb-page-title">Compare Runs</h1>
        <p className="pb-page-desc-sm">Side-by-side pass@k analysis across models and providers.</p>
      </div>

      {/* Selector panel */}
      <div className="pb-card pb-p-card pb-mb-lg">
        <div className="pb-compare-selector-panel">
          <div>
            <label className="pb-label" htmlFor="runASelect">Run A — Baseline</label>
            <select
              id="runASelect"
              className="pb-input"
              title="Select baseline run for comparison"
              value={runA}
              onChange={(e) => setRunA(e.target.value)}
            >
              <option value="">Select a run…</option>
              {runs.map((r) => (
                <option key={r.id} value={r.id}>{getRunLabel(r.id)}</option>
              ))}
            </select>
            {runA && (
              <div className="pb-compare-score">{(runAScore * 100).toFixed(1)}%</div>
            )}
          </div>

          <div className="pb-compare-vs">vs</div>

          <div>
            <label className="pb-label" htmlFor="runBSelect">Run B — Comparison</label>
            <select
              id="runBSelect"
              className="pb-input"
              title="Select run to compare against baseline"
              value={runB}
              onChange={(e) => setRunB(e.target.value)}
            >
              <option value="">Select a run…</option>
              {runs.map((r) => (
                <option key={r.id} value={r.id}>{getRunLabel(r.id)}</option>
              ))}
            </select>
            {runB && (
              <div
                className="pb-compare-score"
                style={{
                  color: runBScore > runAScore ? "var(--color-pass)" :
                         runBScore < runAScore ? "var(--color-fail)" :
                         "var(--color-muted)",
                }}
              >
                {(runBScore * 100).toFixed(1)}%
                {runA && runB && runA !== runB && (
                  <span className="pb-compare-delta-inline">
                    <DeltaCell delta={runBScore - runAScore} />
                  </span>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Needs more runs */}
      {runs.length < 2 && (
        <div className="pb-card pb-p-card pb-text-center">
          <div className="pb-empty-title">Need at least 2 completed runs</div>
          <p className="pb-empty-body">Run benchmarks from the Dashboard and come back here to compare them.</p>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="pb-loading">
          <span className="pb-pulse">◈ Computing comparison…</span>
        </div>
      )}

      {/* Same run */}
      {!loading && runA && runB && runA === runB && (
        <div className="pb-card pb-p-card pb-text-center">
          <span className="pb-cell-mono" style={{ color: "var(--color-warn)" }}>
            ⚠ Select two different runs to compare.
          </span>
        </div>
      )}

      {/* Results table */}
      {!loading && compareData.length > 0 && runA !== runB && (
        <div className="pb-card pb-fade-up-1 pb-overflow-hidden">
          <table className="pb-table">
            <thead>
              <tr>
                <th>Task ID</th>
                <th>Run A</th>
                <th>Run B</th>
                <th>Delta</th>
              </tr>
            </thead>
            <tbody>
              {compareData.map((row) => {
                const delta = row.run_b - row.run_a;
                return (
                  <tr
                    key={row.task_id}
                    style={{
                      backgroundColor:
                        delta > 0 ? "rgba(34,211,165,0.05)" :
                        delta < 0 ? "rgba(255,69,69,0.05)" :
                        "transparent",
                    }}
                  >
                    <td>
                      <a href={`/tasks/${encodeURIComponent(row.task_id)}`} className="pb-cell-id">
                        {row.task_id}
                      </a>
                    </td>
                    <td><ScoreCell val={row.run_a} /></td>
                    <td><ScoreCell val={row.run_b} /></td>
                    <td><DeltaCell delta={delta} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="pb-compare-footer">
            <span>{compareData.length} tasks compared</span>
            <span>
              B better: {compareData.filter((r) => r.run_b > r.run_a).length} ·&nbsp;
              A better: {compareData.filter((r) => r.run_a > r.run_b).length} ·&nbsp;
              Tied: {compareData.filter((r) => r.run_a === r.run_b).length}
            </span>
          </div>
        </div>
      )}

      {!loading && runA && runB && runA !== runB && compareData.length === 0 && (
        <div className="pb-card pb-p-card pb-text-center">
          <span className="pb-cell-muted">No common tasks found between these two runs.</span>
        </div>
      )}
    </div>
  );
}

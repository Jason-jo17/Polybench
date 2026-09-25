"use client";

// Run Detail page — Industrial dark theme

import React, { useEffect, useState, use } from "react";
import Link from "next/link";
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend,
} from "recharts";

const FAILURE_COLORS: Record<string, string> = {
  extraction_failed:  "#8B8B85",
  compile_error:      "#F5A623",
  runtime_error:      "#FF4545",
  wrong_output:       "#E87040",
  timeout:            "#B044FF",
  memory_exceeded:    "#FF4545",
  security_violation: "#FF0055",
};

function StatusBadge({ status }: { status: string }) {
  if (status === "RUNNING")   return <span className="pb-badge pb-badge-running"><span className="pb-pulse" aria-hidden="true">●</span> Running</span>;
  if (status === "PENDING")   return <span className="pb-badge pb-badge-pending">◌ Pending</span>;
  if (status === "COMPLETED") return <span className="pb-badge pb-badge-complete">✓ Completed</span>;
  if (status === "FAILED")    return <span className="pb-badge pb-badge-failed">✗ Failed</span>;
  return <span className="pb-badge">{status}</span>;
}

function MetaItem({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <span className="pb-meta-label">{label}</span>
      <div className={mono ? "pb-meta-value-mono" : "pb-meta-value"}>{value}</div>
    </div>
  );
}

const passColor = (v: number) =>
  v >= 0.8 ? "var(--color-pass)" : v > 0 ? "var(--color-warn)" : "var(--color-fail)";

export default function RunDetails({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expandedTasks, setExpandedTasks] = useState<Set<string>>(new Set());

  useEffect(() => {
    let isMounted = true;
    let timeoutId: ReturnType<typeof setTimeout>;

    const fetchData = async () => {
      try {
        const res = await fetch(`/api/runs/${id}/results`);
        if (!res.ok) throw new Error("Failed to fetch run details");
        const d = await res.json();
        if (isMounted) {
          setData(d);
          setLoading(false);
          if (d.run?.status === "PENDING" || d.run?.status === "RUNNING") {
            timeoutId = setTimeout(fetchData, 2000);
          }
        }
      } catch (err: unknown) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : "Error");
          setLoading(false);
        }
      }
    };
    fetchData();
    return () => { isMounted = false; clearTimeout(timeoutId); };
  }, [id]);

  if (loading && !data)
    return <div className="pb-loading"><span className="pb-pulse">◈ Loading run…</span></div>;
  if (error && !data)
    return <div className="pb-error-state">✗ {error}</div>;
  if (!data) return null;

  const { run, results, samples } = data;

  const toggleTask = (taskId: string) => {
    setExpandedTasks((prev) => {
      const next = new Set(prev);
      next.has(taskId) ? next.delete(taskId) : next.add(taskId);
      return next;
    });
  };

  const getSamples = (trId: string) =>
    samples
      .filter((s: any) => s.task_result_id === trId)
      .sort((a: any, b: any) => a.sample_index - b.sample_index);

  const totalExpected = run.total_tasks * run.samples_per_task;
  const samplesRecorded = samples.length;
  const progressPct = totalExpected > 0 ? Math.round((samplesRecorded / totalExpected) * 100) : 0;
  const isActive = run.status === "RUNNING" || run.status === "PENDING";

  const failureCounts: Record<string, number> = {};
  samples.forEach((s: any) => {
    if (!s.passed && s.failure_kind) {
      failureCounts[s.failure_kind] = (failureCounts[s.failure_kind] || 0) + 1;
    }
  });
  const failureChartData = Object.entries(failureCounts).map(([name, value]) => ({ name, value }));

  const totalInputTokens = samples.reduce((acc: number, s: any) => acc + (s.input_tokens || 0), 0);
  const totalOutputTokens = samples.reduce((acc: number, s: any) => acc + (s.output_tokens || 0), 0);
  const hasCharts = failureChartData.length > 0 || totalInputTokens > 0;

  return (
    <div className="pb-fade-up">
      {/* Header */}
      <div className="pb-run-header">
        <div>
          <div className="pb-eyebrow">◈ Run Detail</div>
          <div className="pb-run-title-row">
            <h1 className={`pb-page-title pb-run-title`}>
              {run.id.substring(0, 10)}&hellip;
            </h1>
            <StatusBadge status={run.status} />
          </div>
        </div>
        <Link href="/runs" className="pb-back-link">← Back to Runs</Link>
      </div>

      {/* Progress bar */}
      {isActive && (
        <div className="pb-mb-lg">
          <div className="pb-progress-header">
            <span>Samples completed</span>
            <span>{samplesRecorded} / {totalExpected} ({progressPct}%)</span>
          </div>
          <div className="pb-progress-track">
            <div className="pb-progress-bar" style={{ width: `${progressPct}%` }} />
          </div>
        </div>
      )}

      {/* Metadata grid */}
      <div className="pb-card pb-fade-up-1 pb-p-card pb-mb-lg">
        <div className="pb-grid-4">
          <MetaItem label="Model"        value={run.model}                                                    mono />
          <MetaItem label="Provider"     value={run.provider} />
          <MetaItem label={`Pass@${run.k}`} value={`${run.pass_at_k != null ? (run.pass_at_k * 100).toFixed(1) : "0.0"}%`} mono />
          <MetaItem label="Tasks"        value={`${results.length} / ${run.total_tasks}`}                    mono />
          <MetaItem label="Samples (n)"  value={String(run.samples_per_task)}                                mono />
          <MetaItem label="Temperature"  value={String(run.temperature)}                                     mono />
          <MetaItem label="Status"       value={run.status} />
          <MetaItem label="Started"      value={new Date(run.created_at).toLocaleString()} />
        </div>
      </div>

      {/* Charts */}
      {hasCharts && (
        <div className={failureChartData.length > 0 && totalInputTokens > 0 ? "pb-charts-row-2" : "pb-charts-row-1"}>
          {failureChartData.length > 0 && (
            <div className="pb-card pb-fade-up-2 pb-p-card">
              <div className="pb-section-title pb-mb-md">Failure Taxonomy</div>
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie data={failureChartData} cx="50%" cy="50%" innerRadius={55} outerRadius={85} paddingAngle={3} dataKey="value">
                    {failureChartData.map((entry) => (
                      <Cell key={entry.name} fill={FAILURE_COLORS[entry.name] || "#6B6B65"} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background: "var(--color-panel)", border: "1px solid var(--color-border)", borderRadius: "6px", fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-text)" }}
                    labelStyle={{ color: "var(--color-muted)" }}
                  />
                  <Legend
                    iconType="circle"
                    iconSize={8}
                    wrapperStyle={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}
                    formatter={(value) => value.replace(/_/g, " ")}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}

          {totalInputTokens > 0 && (
            <div className="pb-card pb-fade-up-2 pb-p-card">
              <div className="pb-section-title pb-mb-lg">Token Usage</div>
              <div className="pb-token-section">
                <div>
                  <div className="pb-label">Input Tokens</div>
                  <div className="pb-token-value">{totalInputTokens.toLocaleString()}</div>
                </div>
                <div className="pb-divider" />
                <div>
                  <div className="pb-label">Output Tokens</div>
                  <div className="pb-token-value-secondary">{totalOutputTokens.toLocaleString()}</div>
                </div>
                <div className="pb-divider" />
                <div>
                  <div className="pb-label">Avg per Sample</div>
                  <div className="pb-token-avg">
                    {samples.length > 0 ? Math.round((totalInputTokens + totalOutputTokens) / samples.length).toLocaleString() : "—"} total tokens
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Task results */}
      <div className="pb-section-title pb-mb-md">Task Results</div>
      <div className="pb-card pb-fade-up-3 pb-overflow-hidden">
        {results.length === 0 ? (
          <div className="pb-loading">
            {isActive ? <span className="pb-pulse">◈ Waiting for first results…</span> : "No tasks executed."}
          </div>
        ) : (
          <table className="pb-table">
            <thead>
              <tr>
                <th style={{ width: "32px" }}></th>
                <th>Task ID</th>
                <th>Language</th>
                <th>Difficulty</th>
                <th>Generated</th>
                <th>Passed</th>
                <th>Pass@k</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r: any) => {
                const expanded = expandedTasks.has(r.id);
                const taskSamples = getSamples(r.id);
                return (
                  <React.Fragment key={r.id}>
                    <tr onClick={() => toggleTask(r.id)} style={{ cursor: "pointer" }}>
                      <td className="pb-cell-mono pb-accent" style={{ paddingRight: "8px", fontSize: "10px" }}>
                        {expanded ? "▼" : "▶"}
                      </td>
                      <td className="pb-cell-mono">{r.task_id}</td>
                      <td>
                        <span className="pb-badge pb-badge-running">{r.language}</span>
                      </td>
                      <td>
                        <span className={`pb-badge pb-badge-${r.difficulty}`}>{r.difficulty}</span>
                      </td>
                      <td className="pb-cell-muted">{r.samples_generated}</td>
                      <td className="pb-cell-mono">{r.samples_passed}</td>
                      <td>
                        <span className="pb-cell-pass-score" style={{ color: passColor(r.task_pass_at_k) }}>
                          {(r.task_pass_at_k * 100).toFixed(0)}%
                        </span>
                      </td>
                    </tr>

                    {expanded && (
                      <tr>
                        <td colSpan={7} className="pb-sample-expanded-cell">
                          <div className="pb-sample-expanded-wrapper">
                            <div className="pb-sample-list-header">
                              Samples — {r.task_id}
                            </div>
                            {taskSamples.length === 0 ? (
                              <div className="pb-loading" style={{ padding: "16px" }}>
                                <span className="pb-pulse">◈ Generating…</span>
                              </div>
                            ) : (
                              <div className="pb-sample-list">
                                {taskSamples.map((s: any) => (
                                  <div
                                    key={s.id}
                                    className="pb-sample-card"
                                    style={{
                                      borderLeft: `3px solid ${s.passed ? "var(--color-pass)" : "var(--color-fail)"}`,
                                      border: `1px solid ${s.passed ? "var(--color-pass)" : "var(--color-fail)"}`,
                                    }}
                                  >
                                    <div className="pb-sample-header">
                                      <span className="pb-sample-idx">Sample {s.sample_index + 1}</span>
                                      {s.passed
                                        ? <span className="pb-badge pb-badge-complete">✓ Passed</span>
                                        : <span className="pb-badge pb-badge-failed">✗ {s.failure_kind?.replace(/_/g, " ") || "Failed"}</span>
                                      }
                                      <span className="pb-sample-meta">
                                        {s.runtime_ms}ms{s.timed_out && " · timed out"}
                                      </span>
                                    </div>
                                    <div className="pb-sample-grid">
                                      <div>
                                        <div className="pb-label">Generated Code</div>
                                        <pre className="pb-code">{s.extracted_code || "// Extraction failed"}</pre>
                                      </div>
                                      <div>
                                        <div className="pb-label">Sandbox Output</div>
                                        <pre className="pb-code" style={{ color: s.passed ? "var(--color-pass)" : "var(--color-fail)" }}>
                                          {[s.stdout, s.stderr].filter(Boolean).join("\n") || "No output"}
                                        </pre>
                                      </div>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

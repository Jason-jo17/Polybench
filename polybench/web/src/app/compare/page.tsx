"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeftRight } from "lucide-react";
import { api, relativeTime, pct, type CompareRow, type Run } from "@/lib/api";
import { Empty, PageHead, Score, SkeletonRows } from "@/components/ui";

const runLabel = (r: Run) => `${r.model} (${r.provider}), ${relativeTime(r.created_at)}`;

function Change({ delta }: { delta: number }) {
  if (Math.abs(delta) < 1e-9) return <span className="muted">No change</span>;
  const up = delta > 0;
  return (
    <span className={`score ${up ? "score-hi" : "score-lo"}`}>
      {up ? "+" : "−"}{Math.abs(delta * 100).toFixed(0)} pts
    </span>
  );
}

export default function Compare() {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [fetched, setFetched] = useState<{ key: string; rows: CompareRow[] } | null>(null);
  const [changedOnly, setChangedOnly] = useState(false);

  useEffect(() => {
    api<Run[]>("/runs?limit=100")
      .then((all) => {
        const done = all.filter((r) => r.status === "COMPLETED");
        setRuns(done);
        const q = new URLSearchParams(window.location.search);
        const qa = q.get("a"), qb = q.get("b");
        setA(qa && done.some((r) => r.id === qa) ? qa : done[1]?.id ?? done[0]?.id ?? "");
        setB(qb && done.some((r) => r.id === qb) ? qb : done[1] ? done[0].id : "");
      })
      .catch(() => setRuns([]));
  }, []);

  useEffect(() => {
    if (!a || !b || a === b) return;
    const url = new URL(window.location.href);
    url.searchParams.set("a", a);
    url.searchParams.set("b", b);
    window.history.replaceState(null, "", url);
    const key = `${a}|${b}`;
    api<CompareRow[]>(`/runs/compare?run_a=${a}&run_b=${b}`)
      .then((rows) => setFetched({ key, rows }))
      .catch(() => setFetched({ key, rows: [] }));
  }, [a, b]);

  const rows = fetched?.key === `${a}|${b}` ? fetched.rows : null;

  const runA = runs?.find((r) => r.id === a);
  const runB = runs?.find((r) => r.id === b);

  const summary = useMemo(() => {
    const list = rows ?? [];
    return {
      better: list.filter((r) => r.run_b > r.run_a).length,
      worse: list.filter((r) => r.run_b < r.run_a).length,
      same: list.filter((r) => r.run_b === r.run_a).length,
    };
  }, [rows]);

  const shown = (rows ?? [])
    .filter((r) => !changedOnly || r.run_a !== r.run_b)
    .sort((x, y) => Math.abs(y.run_b - y.run_a) - Math.abs(x.run_b - x.run_a) || x.task_id.localeCompare(y.task_id));

  if (runs && runs.length < 2) {
    return (
      <>
        <PageHead title="Compare runs" />
        <div className="panel">
          <Empty title="You need two completed runs to compare" action={<Link href="/" className="btn btn-primary">Start a run</Link>}>
            {runs.length === 1 ? "You have one completed run so far." : "No runs have completed yet."} Try the same tasks on a second model, then come back.
          </Empty>
        </div>
      </>
    );
  }

  return (
    <>
      <PageHead title="Compare runs" lede="See which tasks one model solves that another doesn't. Pick a baseline and a challenger." />

      <div className="compare-pick panel panel-pad">
        <RunPicker id="run-a" label="Baseline" runs={runs} value={a} onChange={setA} run={runA} />
        <button
          type="button"
          className="btn btn-quiet compare-swap"
          onClick={() => { setA(b); setB(a); }}
          aria-label="Swap baseline and challenger"
          title="Swap"
        >
          <ArrowLeftRight size={16} aria-hidden="true" />
        </button>
        <RunPicker id="run-b" label="Challenger" runs={runs} value={b} onChange={setB} run={runB} delta={runA && runB ? runB.pass_at_k - runA.pass_at_k : undefined} />
      </div>

      {a && b && a === b ? (
        <div className="notice notice-part section">Pick two different runs.</div>
      ) : (
        <section className="section" aria-labelledby="by-task">
          <div className="row" style={{ justifyContent: "space-between", marginBottom: 14 }}>
            <h2 className="h2" id="by-task">By task</h2>
            {rows && rows.length > 0 && (
              <div className="row sub" style={{ gap: 18 }}>
                <span><strong className="score-hi">{summary.better}</strong> improved</span>
                <span><strong className="score-lo">{summary.worse}</strong> regressed</span>
                <span><strong>{summary.same}</strong> unchanged</span>
                <label className="row" style={{ gap: 6, cursor: "pointer" }}>
                  <input type="checkbox" checked={changedOnly} onChange={(e) => setChangedOnly(e.target.checked)} style={{ accentColor: "var(--accent)" }} />
                  Changed only
                </label>
              </div>
            )}
          </div>
          <div className="panel">
            {rows && shown.length === 0 ? (
              <Empty title={rows.length === 0 ? "These runs share no tasks" : "No task changed between these runs"}>
                {rows.length === 0 ? "They were probably filtered to different languages or tags." : undefined}
              </Empty>
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Task</th>
                      <th className="num">Baseline</th>
                      <th className="num">Challenger</th>
                      <th className="num">Change</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows === null ? <SkeletonRows cols={4} rows={6} /> : shown.map((r) => (
                      <tr key={r.task_id}>
                        <td><Link href={`/tasks/${encodeURIComponent(r.task_id)}`} className="mono-id">{r.task_id}</Link></td>
                        <td className="num"><Score value={r.run_a} digits={0} /></td>
                        <td className="num"><Score value={r.run_b} digits={0} /></td>
                        <td className="num"><Change delta={r.run_b - r.run_a} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>
      )}
    </>
  );
}

function RunPicker({
  id, label, runs, value, onChange, run, delta,
}: {
  id: string;
  label: string;
  runs: Run[] | null;
  value: string;
  onChange: (v: string) => void;
  run?: Run;
  delta?: number;
}) {
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>{label}</label>
      <select id={id} className="input" value={value} onChange={(e) => onChange(e.target.value)} disabled={!runs}>
        {!runs && <option>Loading runs…</option>}
        {runs?.map((r) => <option key={r.id} value={r.id}>{runLabel(r)}</option>)}
      </select>
      {run && (
        <div className="row" style={{ marginTop: 8, gap: 12, alignItems: "baseline" }}>
          <span className="compare-score"><Score value={run.pass_at_k} /></span>
          <span className="sub">pass@{run.k}, {run.total_tasks} tasks</span>
          {delta !== undefined && Math.abs(delta) > 1e-9 && (
            <span className={`score ${delta > 0 ? "score-hi" : "score-lo"}`}>
              {delta > 0 ? "+" : "−"}{pct(Math.abs(delta))}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

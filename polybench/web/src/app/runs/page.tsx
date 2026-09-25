"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, absoluteTime, isActive, relativeTime, shortId, type RunStatus, type RunWithScores } from "@/lib/api";
import { Empty, PageHead, ResultStrip, ScoreMeter, SkeletonRows, Status } from "@/components/ui";

const PAGE = 25;
const FILTERS: { value: RunStatus | ""; label: string }[] = [
  { value: "", label: "All" },
  { value: "COMPLETED", label: "Completed" },
  { value: "RUNNING", label: "In progress" },
  { value: "FAILED", label: "Failed" },
];

export default function Runs() {
  const router = useRouter();
  const [runs, setRuns] = useState<RunWithScores[] | null>(null);
  const [error, setError] = useState("");
  const [limit, setLimit] = useState(PAGE);
  const [filter, setFilter] = useState<RunStatus | "">("");

  const load = useCallback(() => {
    api<RunWithScores[]>(`/runs?limit=${limit}&include=task_scores`)
      .then((d) => { setRuns(d); setError(""); })
      .catch((e: Error) => setError(e.message));
  }, [limit]);

  useEffect(() => { load(); }, [load]);

  const anyActive = runs?.some((r) => isActive(r.status)) ?? false;
  useEffect(() => {
    if (!anyActive) return;
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, [anyActive, load]);

  const shown = (runs ?? []).filter((r) =>
    !filter ? true : filter === "RUNNING" ? isActive(r.status) : r.status === filter,
  );

  return (
    <>
      <PageHead title="Runs" lede="Every benchmark run, newest first. Open one to see results for each task and sample.">
        <Link href="/" className="btn btn-primary">New run</Link>
      </PageHead>

      <div className="row" style={{ marginBottom: 16 }}>
        <div className="seg" role="group" aria-label="Filter by status">
          {FILTERS.map((f) => (
            <button key={f.label} type="button" aria-pressed={filter === f.value} onClick={() => setFilter(f.value)}>
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div className="panel">
        {error && !runs ? (
          <Empty title="Couldn't load runs" action={<button className="btn btn-quiet" onClick={load}>Try again</button>}>
            {error}
          </Empty>
        ) : runs && shown.length === 0 ? (
          runs.length === 0 ? (
            <Empty title="No runs yet" action={<Link href="/" className="btn btn-primary">Start a run</Link>}>
              Start a run from the overview. The mock provider works without an API key.
            </Empty>
          ) : (
            <Empty title="No runs with this status" action={<button className="btn btn-quiet" onClick={() => setFilter("")}>Show all runs</button>} />
          )
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Model</th>
                  <th>Status</th>
                  <th>pass@k</th>
                  <th>By task</th>
                  <th className="num">Tasks</th>
                  <th className="num">n / k</th>
                  <th>Started</th>
                  <th>Run</th>
                </tr>
              </thead>
              <tbody>
                {runs === null ? (
                  <SkeletonRows cols={8} />
                ) : (
                  shown.map((r) => (
                    <tr key={r.id} className="row-link" onClick={() => router.push(`/runs/${r.id}`)}>
                      <td>
                        <Link href={`/runs/${r.id}`} className="model" onClick={(e) => e.stopPropagation()}>
                          {r.model}
                          <small>{r.provider}{r.language_filter ? `, ${r.language_filter} only` : ""}</small>
                        </Link>
                      </td>
                      <td><Status status={r.status} /></td>
                      <td><ScoreMeter value={r.pass_at_k} pending={r.status === "PENDING"} /></td>
                      <td><ResultStrip scores={r.task_scores} total={r.total_tasks} /></td>
                      <td className="num">{r.total_tasks}</td>
                      <td className="num muted">{r.samples_per_task} / {r.k}</td>
                      <td className="muted" title={absoluteTime(r.created_at)} style={{ whiteSpace: "nowrap" }}>
                        {relativeTime(r.created_at)}
                      </td>
                      <td><span className="mono-id">{shortId(r.id)}</span></td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {runs && runs.length === limit && (
        <div className="row" style={{ justifyContent: "center", marginTop: 20 }}>
          <button className="btn btn-quiet" onClick={() => setLimit((l) => l + PAGE)}>Load {PAGE} more</button>
        </div>
      )}
    </>
  );
}

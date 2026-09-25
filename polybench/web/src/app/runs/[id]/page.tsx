"use client";

import { use, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  api, absoluteTime, humanize, isActive, pct, shortId,
  type RunResults, type Sample, type TaskResult,
} from "@/lib/api";
import { Difficulty, Empty, Lang, Score, Skeleton, Status } from "@/components/ui";

const FAILURE_HELP: Record<string, string> = {
  extraction_failed: "No code block could be pulled out of the response.",
  compile_error: "The code didn't compile or parse.",
  runtime_error: "The code crashed while the tests ran.",
  wrong_output: "The code ran, but at least one hidden test failed.",
  timeout: "The tests didn't finish within the task's time limit.",
  memory_exceeded: "The sandbox hit its memory limit.",
  security_violation: "The code tried something the sandbox blocks.",
};

export default function RunDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [data, setData] = useState<RunResults | null>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  // ?task=<id> (linked from a task's page) opens that task's sample first.
  const [focusTask] = useState<string | null>(() =>
    typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("task"),
  );

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const load = async () => {
      try {
        const d = await api<RunResults>(`/runs/${id}/results`);
        if (!alive) return;
        setData(d);
        if (isActive(d.run.status)) timer = setTimeout(load, 2000);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : "Couldn't load this run.");
      }
    };
    load();
    return () => { alive = false; clearTimeout(timer); };
  }, [id]);

  const derived = useMemo(() => {
    if (!data) return null;
    const byResult = new Map<string, Sample[]>();
    for (const s of data.samples) {
      const list = byResult.get(s.task_result_id) ?? [];
      list.push(s);
      byResult.set(s.task_result_id, list);
    }
    byResult.forEach((l) => l.sort((a, b) => a.sample_index - b.sample_index));

    const results = [...data.results].sort((a, b) => a.task_id.localeCompare(b.task_id));
    const failures = new Map<string, number>();
    let passedSamples = 0, tokensIn = 0, tokensOut = 0, runtime = 0;
    for (const s of data.samples) {
      if (s.passed) passedSamples++;
      else failures.set(s.failure_kind ?? "unknown", (failures.get(s.failure_kind ?? "unknown") ?? 0) + 1);
      tokensIn += s.input_tokens ?? 0;
      tokensOut += s.output_tokens ?? 0;
      runtime += s.runtime_ms;
    }
    const failureList = [...failures.entries()].sort((a, b) => b[1] - a[1]);
    const focusResult = focusTask ? data.results.find((r) => r.task_id === focusTask) : undefined;
    const pool = focusResult ? byResult.get(focusResult.id) ?? [] : data.samples;
    const firstFail = pool.find((s) => !s.passed) ?? pool[0];
    return {
      byResult, results, failureList, passedSamples, tokensIn, tokensOut,
      avgRuntime: data.samples.length ? Math.round(runtime / data.samples.length) : 0,
      solved: data.results.filter((r) => r.samples_passed > 0).length,
      firstFail: firstFail?.id ?? data.samples[0]?.id ?? null,
    };
  }, [data, focusTask]);

  const current = selected ?? derived?.firstFail ?? null;

  if (error && !data) {
    return (
      <>
        <Crumbs id={id} />
        <div className="panel">
          <Empty title="Couldn't load this run" action={<Link href="/runs" className="btn btn-quiet">Back to runs</Link>}>{error}</Empty>
        </div>
      </>
    );
  }

  if (!data || !derived) {
    return (
      <>
        <Crumbs id={id} />
        <Skeleton w={320} h={40} />
        <div style={{ height: 32 }} />
        <Skeleton h={88} />
        <div style={{ height: 24 }} />
        <Skeleton h={360} />
      </>
    );
  }

  const { run, samples } = data;
  const active = isActive(run.status);
  const expected = run.total_tasks * run.samples_per_task;
  const progress = expected ? Math.min(100, Math.round((samples.length / expected) * 100)) : 0;
  const sample = samples.find((s) => s.id === current) ?? null;
  const sampleResult = sample ? data.results.find((r) => r.id === sample.task_result_id) : undefined;
  const maxFail = derived.failureList[0]?.[1] ?? 1;

  return (
    <>
      <Crumbs id={id} />

      <header className="run-head">
        <div style={{ minWidth: 0 }}>
          <h1 className="page-title" style={{ overflowWrap: "anywhere" }}>{run.model}</h1>
          <div className="row" style={{ marginTop: 12, gap: 18 }}>
            <Status status={run.status} />
            <span className="sub">{run.provider}</span>
            <span className="sub">Started {absoluteTime(run.created_at)}</span>
          </div>
        </div>
        <div className="run-score">
          <div className="figure-label">pass@{run.k}</div>
          {active && !data.results.length ? <span className="run-score-value muted">—</span> : (
            <span className="run-score-value"><Score value={run.pass_at_k} /></span>
          )}
        </div>
      </header>

      {active && (
        <div style={{ marginBottom: 28 }}>
          <div className="row sub" style={{ justifyContent: "space-between", marginBottom: 8 }}>
            <span>{run.status === "PENDING" ? "Waiting to start" : "Generating and testing samples"}</span>
            <span>{samples.length} of {expected} samples ({progress}%)</span>
          </div>
          <div className="progress" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
            <span style={{ width: `${progress}%` }} />
          </div>
        </div>
      )}

      <div className="figures">
        <div className="figure">
          <div className="figure-label">Tasks solved at least once</div>
          <div className="figure-value">{derived.solved}<span className="muted" style={{ fontWeight: 500 }}> / {run.total_tasks}</span></div>
        </div>
        <div className="figure">
          <div className="figure-label">Samples passed</div>
          <div className="figure-value">{derived.passedSamples}<span className="muted" style={{ fontWeight: 500 }}> / {samples.length}</span></div>
        </div>
        <div className="figure">
          <div className="figure-label">Avg sandbox time</div>
          <div className="figure-value">{samples.length ? `${derived.avgRuntime.toLocaleString()} ms` : "—"}</div>
        </div>
        <div className="figure">
          <div className="figure-label">Tokens in / out</div>
          <div className="figure-value sm">
            {derived.tokensIn || derived.tokensOut
              ? `${derived.tokensIn.toLocaleString()} / ${derived.tokensOut.toLocaleString()}`
              : "Not reported"}
          </div>
        </div>
      </div>

      <section className="section" aria-labelledby="matrix-title">
        <div className="row" style={{ marginBottom: 14, justifyContent: "space-between" }}>
          <h2 className="h2" id="matrix-title">Results by task</h2>
          <div className="legend">
            <span><i className="cell p" /> Passed</span>
            <span><i className="cell f" /> Failed</span>
            <span><i className="cell" /> Not run yet</span>
          </div>
        </div>
        <div className="panel panel-pad">
          {derived.results.length === 0 ? (
            <Empty title={active ? "Waiting for the first task" : "No tasks were run"}>
              {active ? "Results appear here as each task finishes." : "The run ended before any task finished. Check the API logs for the cause."}
            </Empty>
          ) : (
            <div className="matrix" role="table" aria-label="Samples by task">
              <div className="matrix-row matrix-head" role="row">
                <span role="columnheader">Task</span>
                <span role="columnheader" className="m-cells">Samples (select one to inspect)</span>
                <span role="columnheader" className="m-score" style={{ textAlign: "right" }}>pass@{run.k}</span>
              </div>
              {derived.results.map((r) => (
                <MatrixRow
                  key={r.id}
                  result={r}
                  samples={derived.byResult.get(r.id) ?? []}
                  n={run.samples_per_task}
                  current={current}
                  onSelect={setSelected}
                />
              ))}
            </div>
          )}
        </div>
      </section>

      {sample && sampleResult && (
        <section className="section" aria-labelledby="sample-title">
          <div className="panel">
            <div className="panel-head" style={{ flexWrap: "wrap" }}>
              <div className="row" style={{ gap: 14 }}>
                <h2 className="h2" id="sample-title">
                  <Link href={`/tasks/${encodeURIComponent(sampleResult.task_id)}`} className="code" style={{ fontSize: 15 }}>
                    {sampleResult.task_id}
                  </Link>
                  <span className="muted" style={{ fontWeight: 500 }}> sample {sample.sample_index + 1}</span>
                </h2>
                <span className={`status ${sample.passed ? "status-completed" : "status-failed"}`}>
                  <span className="status-dot" aria-hidden="true" />
                  {sample.passed ? "Passed" : humanize(sample.failure_kind ?? "failed")}
                </span>
              </div>
              <div className="row sub" style={{ gap: 16 }}>
                <span>{sample.runtime_ms.toLocaleString()} ms{sample.timed_out ? ", timed out" : ""}</span>
                {sample.exit_code !== null && <span>exit {sample.exit_code}</span>}
                {sample.output_tokens !== null && <span>{sample.output_tokens.toLocaleString()} output tokens</span>}
              </div>
            </div>
            <div className="panel-pad stack" style={{ gap: 16 }}>
              {!sample.passed && sample.failure_kind && FAILURE_HELP[sample.failure_kind] && (
                <p className="sub">{FAILURE_HELP[sample.failure_kind]}</p>
              )}
              <div className="grid-2">
                <div className="stack" style={{ gap: 8 }}>
                  <span className="field-label">Extracted code</span>
                  <pre className="code-block">{sample.extracted_code || "No code could be extracted from the response."}</pre>
                </div>
                <div className="stack" style={{ gap: 8 }}>
                  <span className="field-label">Sandbox output</span>
                  <pre className={`code-block ${sample.passed ? "out-pass" : "out-fail"}`}>
                    {[sample.stdout, sample.stderr].filter(Boolean).join("\n") || "The sandbox produced no output."}
                  </pre>
                </div>
              </div>
            </div>
          </div>
        </section>
      )}

      <div className="grid-2 section">
        <section className="panel" aria-labelledby="fail-title">
          <div className="panel-head"><h2 className="h2" id="fail-title">Why samples failed</h2></div>
          <div className="panel-pad">
            {derived.failureList.length === 0 ? (
              <p className="sub">{samples.length ? "Every sample passed." : "No samples yet."}</p>
            ) : (
              <ul className="bars">
                {derived.failureList.map(([kind, count]) => (
                  <li key={kind} title={FAILURE_HELP[kind]}>
                    <span className="bars-label">{humanize(kind)}</span>
                    <span className="bars-track"><span style={{ width: `${(count / maxFail) * 100}%` }} /></span>
                    <span className="bars-value">{count}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>

        <section className="panel" aria-labelledby="config-title">
          <div className="panel-head"><h2 className="h2" id="config-title">Configuration</h2></div>
          <dl className="panel-pad kv">
            <dt>Provider</dt><dd>{run.provider}</dd>
            <dt>Languages</dt><dd>{run.language_filter ?? "All"}</dd>
            <dt>Samples per task</dt><dd>{run.samples_per_task}</dd>
            <dt>k</dt><dd>{run.k}</dd>
            <dt>Temperature</dt><dd>{run.temperature}</dd>
            <dt>Mean task pass@k</dt><dd>{data.results.length ? pct(run.pass_at_k) : "—"}</dd>
            <dt>Commit</dt><dd className="code">{run.git_sha ? run.git_sha.slice(0, 10) : "—"}</dd>
            <dt>Run ID</dt><dd className="code" style={{ overflowWrap: "anywhere" }}>{run.id}</dd>
          </dl>
        </section>
      </div>
    </>
  );
}

function Crumbs({ id }: { id: string }) {
  return (
    <nav className="crumbs" aria-label="Breadcrumb">
      <Link href="/runs">Runs</Link>
      <span aria-hidden="true">/</span>
      <span className="code">{shortId(id)}</span>
    </nav>
  );
}

function MatrixRow({
  result, samples, n, current, onSelect,
}: {
  result: TaskResult;
  samples: Sample[];
  n: number;
  current: string | null;
  onSelect: (id: string) => void;
}) {
  const slots = Array.from({ length: Math.max(n, samples.length) }, (_, i) => samples[i]);
  return (
    <div className="matrix-row" role="row">
      <span className="m-task" role="cell">
        <span className="row" style={{ gap: 10, flexWrap: "nowrap" }}>
          <Lang lang={result.language} />
          <Link href={`/tasks/${encodeURIComponent(result.task_id)}`} className="mono-id" title={result.task_id}>
            {result.task_id.split("/").slice(1).join("/") || result.task_id}
          </Link>
        </span>
      </span>
      <span className="m-cells" role="cell">
        {slots.map((s, i) =>
          s ? (
            <button
              key={s.id}
              type="button"
              className={`cell ${s.passed ? "p" : "f"}`}
              aria-pressed={current === s.id}
              aria-label={`${result.task_id} sample ${i + 1}: ${s.passed ? "passed" : humanize(s.failure_kind ?? "failed")}`}
              title={`Sample ${i + 1}: ${s.passed ? "passed" : humanize(s.failure_kind ?? "failed")}`}
              onClick={() => onSelect(s.id)}
            />
          ) : (
            <span key={`empty-${i}`} className="cell" aria-hidden="true" />
          ),
        )}
        <span className="m-diff"><Difficulty level={result.difficulty} /></span>
      </span>
      <span className="m-score" role="cell" style={{ textAlign: "right" }}>
        {result.samples_generated === 0
          ? <span className="muted" title="No samples finished yet">—</span>
          : <Score value={result.task_pass_at_k} digits={0} />}
      </span>
    </div>
  );
}

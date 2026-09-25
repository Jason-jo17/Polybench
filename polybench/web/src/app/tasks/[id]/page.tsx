"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { EyeOff } from "lucide-react";
import { api, absoluteTime, humanize, relativeTime, type Task, type TaskHistory } from "@/lib/api";
import { Difficulty, Empty, Lang, Score, Skeleton, Status } from "@/components/ui";

export default function TaskDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const taskId = decodeURIComponent(id);
  const [task, setTask] = useState<Task | null>(null);
  const [error, setError] = useState("");
  const [history, setHistory] = useState<TaskHistory | null>(null);

  useEffect(() => {
    api<Task>(`/tasks/${encodeURIComponent(taskId)}`).then(setTask).catch((e: Error) => setError(e.message));
    api<TaskHistory>(`/tasks/${encodeURIComponent(taskId)}/results`)
      .then(setHistory)
      .catch(() => setHistory({ task_id: taskId, runs: [], failures: {} }));
  }, [taskId]);

  const crumbs = (
    <nav className="crumbs" aria-label="Breadcrumb">
      <Link href="/tasks">Tasks</Link>
      <span aria-hidden="true">/</span>
      <span className="code">{taskId}</span>
    </nav>
  );

  if (error) {
    return (
      <>
        {crumbs}
        <div className="panel">
          <Empty title="Task not found" action={<Link href="/tasks" className="btn btn-quiet">Browse tasks</Link>}>
            No task has the ID <code>{taskId}</code>. It may have been renamed or removed from the tasks directory.
          </Empty>
        </div>
      </>
    );
  }

  if (!task) {
    return (
      <>
        {crumbs}
        <Skeleton w={360} h={40} />
        <div style={{ height: 28 }} />
        <Skeleton h={240} />
      </>
    );
  }

  return (
    <>
      {crumbs}
      <header style={{ marginBottom: 32 }}>
        <h1 className="page-title">{task.title || task.id}</h1>
        <div className="row" style={{ marginTop: 14, gap: 20 }}>
          <Lang lang={task.language} />
          <Difficulty level={task.difficulty} />
          <span className="sub">{task.timeout_seconds}s time limit</span>
          {task.tags.length > 0 && (
            <span className="row" style={{ gap: 6 }}>
              {task.tags.map((t) => <span key={t} className="chip">{t}</span>)}
            </span>
          )}
        </div>
      </header>

      <div className="task-body">
        <section className="panel panel-pad" aria-labelledby="prompt-title">
          <h2 className="h2" id="prompt-title" style={{ marginBottom: 12 }}>Prompt</h2>
          <div className="prose">{task.prompt}</div>
        </section>

        <div className="stack" style={{ gap: 16 }}>
          <section className="panel panel-pad" aria-labelledby="sig-title">
            <h2 className="h2" id="sig-title" style={{ marginBottom: 12 }}>Required signature</h2>
            <pre className="code-block" style={{ maxHeight: "none" }}>{task.signature}</pre>
          </section>
          <div className="notice">
            <EyeOff size={16} style={{ flexShrink: 0, marginTop: 2 }} aria-hidden="true" />
            <span>
              The test suite stays hidden. The model sees only the prompt and signature, so it can&apos;t
              write code that targets specific test cases.
            </span>
          </div>
        </div>
      </div>

      <TaskResults history={history} taskId={taskId} />
    </>
  );
}

function TaskResults({ history, taskId }: { history: TaskHistory | null; taskId: string }) {
  const failures = Object.entries(history?.failures ?? {}).sort((a, b) => b[1] - a[1]);
  const totalFailed = failures.reduce((n, [, c]) => n + c, 0);
  return (
    <section className="section" aria-labelledby="history-title">
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 14 }}>
        <h2 className="h2" id="history-title">Results across runs</h2>
        {totalFailed > 0 && (
          <div className="row" style={{ gap: 6 }} aria-label="Why samples failed, across all runs">
            <span className="sub" style={{ marginRight: 4 }}>Failed samples:</span>
            {failures.map(([kind, count]) => (
              <span key={kind} className="chip">{humanize(kind)} {count}</span>
            ))}
          </div>
        )}
      </div>
      <div className="panel">
        {history && history.runs.length === 0 ? (
          <Empty title="No run has included this task yet">
            Start a run that covers this task&apos;s language to see how models do on it.
          </Empty>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Model</th>
                  <th>Status</th>
                  <th className="num">Samples passed</th>
                  <th className="num">pass@k</th>
                  <th>Run</th>
                </tr>
              </thead>
              <tbody>
                {history === null ? (
                  <tr><td colSpan={5}><Skeleton w="60%" /></td></tr>
                ) : history.runs.map((r) => (
                  <tr key={r.run_id}>
                    <td>
                      <Link href={`/runs/${r.run_id}?task=${encodeURIComponent(taskId)}`} className="model">
                        {r.model}
                        <small>{r.provider}</small>
                      </Link>
                    </td>
                    <td><Status status={r.status} /></td>
                    <td className="num">{r.samples_passed} / {r.samples_done}</td>
                    <td className="num">
                      {r.samples_done === 0 ? <span className="muted">—</span> : <Score value={r.pass_at_k} digits={0} />}
                      <span className="muted" style={{ fontSize: 12.5 }}> @{r.k}</span>
                    </td>
                    <td className="muted" title={absoluteTime(r.created_at)} style={{ whiteSpace: "nowrap" }}>
                      {relativeTime(r.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}

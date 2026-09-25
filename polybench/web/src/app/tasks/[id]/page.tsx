"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { EyeOff } from "lucide-react";
import { api, type Task } from "@/lib/api";
import { Difficulty, Empty, Lang, Skeleton } from "@/components/ui";

export default function TaskDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const taskId = decodeURIComponent(id);
  const [task, setTask] = useState<Task | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Task>(`/tasks/${encodeURIComponent(taskId)}`).then(setTask).catch((e: Error) => setError(e.message));
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
    </>
  );
}

"use client";

// Task Detail page — fixes 404 from compare page /tasks/[id] links

import { useEffect, useState, use } from "react";
import Link from "next/link";

interface TaskDetail {
  id: string;
  title: string;
  language: string;
  difficulty: string;
  tags: string[];
  prompt: string;
  signature: string;
}

const LANG_COLORS: Record<string, string> = {
  python:     "var(--color-accent)",
  javascript: "#F5A623",
  go:         "#22D3A5",
  rust:       "#E87040",
};

export default function TaskDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const taskId = decodeURIComponent(id);

  const [task, setTask] = useState<TaskDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`/api/tasks/${encodeURIComponent(taskId)}`)
      .then((r) => {
        if (!r.ok) throw new Error(`Task not found: ${taskId}`);
        return r.json();
      })
      .then((d) => { setTask(d); setLoading(false); })
      .catch((e) => { setError(e.message); setLoading(false); });
  }, [taskId]);

  if (loading)
    return <div className="pb-loading"><span className="pb-pulse">◈ Loading task…</span></div>;

  if (error || !task)
    return (
      <div className="pb-fade-up">
        <div className="pb-breadcrumb pb-mb-lg">
          <Link href="/tasks" className="pb-back-link">← Back to Tasks</Link>
        </div>
        <div className="pb-card pb-p-card pb-text-center">
          <div className="pb-cell-mono" style={{ color: "var(--color-fail)", marginBottom: "8px" }}>
            ✗ {error || "Task not found"}
          </div>
          <p className="pb-cell-muted">
            Task ID: <code className="pb-cell-mono pb-accent">{taskId}</code>
          </p>
        </div>
      </div>
    );

  const langColor = LANG_COLORS[task.language] || "var(--color-accent)";

  return (
    <div className="pb-fade-up">
      {/* Breadcrumb */}
      <div className="pb-breadcrumb">
        <Link href="/tasks" className="pb-breadcrumb-link">Tasks</Link>
        <span className="pb-breadcrumb-sep">/</span>
        <span className="pb-breadcrumb-active">{taskId}</span>
      </div>

      {/* Header */}
      <div className="pb-task-header">
        <div className="pb-task-badge-row">
          <span className="pb-badge" style={{ background: `${langColor}20`, color: langColor }}>
            {task.language}
          </span>
          <span className={`pb-badge pb-badge-${task.difficulty}`}>{task.difficulty}</span>
          {task.tags?.map((tag) => (
            <span key={tag} className="pb-tag-chip">{tag}</span>
          ))}
        </div>
        <h1 className="pb-page-title">{task.title || taskId}</h1>
        <div className="pb-task-id-label">{taskId}</div>
      </div>

      <div className="pb-grid-2 pb-mb-md">
        {/* Problem Statement */}
        <div className="pb-card pb-fade-up-1 pb-p-card">
          <div className="pb-label pb-mb-md">Problem Statement</div>
          <div style={{ fontSize: "14px", lineHeight: 1.7, color: "var(--color-text)" }}>
            {task.prompt}
          </div>
        </div>

        {/* Required Signature */}
        <div className="pb-card pb-fade-up-2 pb-p-card">
          <div className="pb-label pb-mb-md">Required Signature</div>
          <pre className="pb-code" style={{ maxHeight: "none" }}>
            {task.signature}
          </pre>
          <div className="pb-info-box">
            <div className="pb-info-box-warn">⚠ Test suite is hidden</div>
            The model is evaluated against a private test suite that is never included in the prompt.
            Extraction failure, compile errors, and wrong output are all scored automatically.
          </div>
        </div>
      </div>

      <Link href="/tasks" className="pb-back-link">← Back to Tasks Library</Link>
    </div>
  );
}

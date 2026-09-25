"use client";

// Tasks Library page — Industrial dark theme

import { useEffect, useState } from "react";
import Link from "next/link";

interface Task {
  id: string;
  title: string;
  language: string;
  difficulty: string;
  tags: string[];
}

const LANG_COLORS: Record<string, string> = {
  python:     "var(--color-accent)",
  javascript: "#F5A623",
  go:         "#22D3A5",
  rust:       "#E87040",
};

export default function Tasks() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [langFilter, setLangFilter] = useState("");
  const [diffFilter, setDiffFilter] = useState("");

  useEffect(() => {
    fetch("/api/tasks")
      .then((r) => r.json())
      .then((data) => { setTasks(Array.isArray(data) ? data : []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const filtered = tasks.filter((t) => {
    const matchSearch = !search ||
      t.id.toLowerCase().includes(search.toLowerCase()) ||
      (t.title || "").toLowerCase().includes(search.toLowerCase()) ||
      t.tags.some((tag) => tag.toLowerCase().includes(search.toLowerCase()));
    const matchLang = !langFilter || t.language === langFilter;
    const matchDiff = !diffFilter || t.difficulty === diffFilter;
    return matchSearch && matchLang && matchDiff;
  });

  const languages = [...new Set(tasks.map((t) => t.language))].sort();
  const difficulties = ["easy", "medium", "hard"];
  const clearFilters = () => { setSearch(""); setLangFilter(""); setDiffFilter(""); };

  return (
    <div className="pb-fade-up">
      {/* Header */}
      <div className="pb-mb-xl">
        <div className="pb-eyebrow">◈ Task Registry</div>
        <h1 className="pb-page-title">Benchmark Tasks</h1>
        <p className="pb-page-desc-sm">
          {tasks.length} programming problems across {languages.length} languages.
        </p>
      </div>

      {/* Filters */}
      <div className="pb-filters-row">
        <input
          id="taskSearch"
          type="text"
          className="pb-input"
          style={{ maxWidth: "280px" }}
          placeholder="Search tasks, tags…"
          title="Search by task ID, title, or tag"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <label htmlFor="taskLangFilter" className="pb-label" style={{ display: "none" }}>Language</label>
        <select
          id="taskLangFilter"
          className="pb-input"
          style={{ maxWidth: "160px" }}
          title="Filter by programming language"
          value={langFilter}
          onChange={(e) => setLangFilter(e.target.value)}
        >
          <option value="">All Languages</option>
          {languages.map((l) => (
            <option key={l} value={l}>{l}</option>
          ))}
        </select>
        <label htmlFor="taskDiffFilter" className="pb-label" style={{ display: "none" }}>Difficulty</label>
        <select
          id="taskDiffFilter"
          className="pb-input"
          style={{ maxWidth: "160px" }}
          title="Filter by difficulty level"
          value={diffFilter}
          onChange={(e) => setDiffFilter(e.target.value)}
        >
          <option value="">All Difficulties</option>
          {difficulties.map((d) => (
            <option key={d} value={d}>{d.charAt(0).toUpperCase() + d.slice(1)}</option>
          ))}
        </select>
        {(search || langFilter || diffFilter) && (
          <button className="pb-btn-ghost" onClick={clearFilters}>Clear filters</button>
        )}
      </div>

      {/* Table */}
      <div className="pb-card pb-overflow-hidden">
        {loading ? (
          <div className="pb-loading">
            <span className="pb-pulse">◈ Loading tasks…</span>
          </div>
        ) : filtered.length === 0 ? (
          <div className="pb-empty">
            <div className="pb-empty-title">No tasks match your filters</div>
            <button className="pb-btn-ghost" onClick={clearFilters}>Clear filters</button>
          </div>
        ) : (
          <table className="pb-table">
            <thead>
              <tr>
                <th>Task ID</th>
                <th>Title</th>
                <th>Language</th>
                <th>Difficulty</th>
                <th>Tags</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((task) => {
                const langColor = LANG_COLORS[task.language] || "var(--color-accent)";
                return (
                  <tr key={task.id}>
                    <td className="pb-cell-muted">{task.id}</td>
                    <td style={{ fontWeight: 500 }}>
                      {task.title || task.id.split("/")[1]?.replace(/_/g, " ")}
                    </td>
                    <td>
                      <span
                        className="pb-badge"
                        style={{
                          background: `${langColor}20`,
                          color: langColor,
                        }}
                      >
                        {task.language}
                      </span>
                    </td>
                    <td>
                      <span className={`pb-badge pb-badge-${task.difficulty}`}>
                        {task.difficulty}
                      </span>
                    </td>
                    <td>
                      <div className="pb-flex pb-flex-wrap pb-flex-gap-sm">
                        {task.tags?.map((tag) => (
                          <button
                            key={tag}
                            className="pb-tag-chip"
                            onClick={() => setSearch(tag)}
                            title={`Filter by tag: ${tag}`}
                          >
                            {tag}
                          </button>
                        ))}
                      </div>
                    </td>
                    <td>
                      <Link href={`/tasks/${encodeURIComponent(task.id)}`} className="pb-task-view-btn">
                        View →
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <div className="pb-count-label">
        {filtered.length} task{filtered.length !== 1 ? "s" : ""}{tasks.length !== filtered.length ? ` of ${tasks.length}` : ""}
      </div>
    </div>
  );
}

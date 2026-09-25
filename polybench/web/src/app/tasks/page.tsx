"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import { api, LANG_NAMES, type Task } from "@/lib/api";
import { Difficulty, Empty, Lang, PageHead, SkeletonRows } from "@/components/ui";

const DIFFICULTIES = ["easy", "medium", "hard"];

export default function Tasks() {
  const router = useRouter();
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [lang, setLang] = useState("");
  const [diff, setDiff] = useState("");

  useEffect(() => {
    api<Task[]>("/tasks").then(setTasks).catch((e: Error) => { setError(e.message); setTasks([]); });
  }, []);

  const languages = useMemo(() => [...new Set((tasks ?? []).map((t) => t.language))].sort(), [tasks]);

  const q = search.trim().toLowerCase();
  const shown = (tasks ?? []).filter(
    (t) =>
      (!q || t.id.toLowerCase().includes(q) || t.title?.toLowerCase().includes(q) || t.tags.some((g) => g.toLowerCase().includes(q))) &&
      (!lang || t.language === lang) &&
      (!diff || t.difficulty === diff),
  );
  const filtered = Boolean(q || lang || diff);
  const clear = () => { setSearch(""); setLang(""); setDiff(""); };

  return (
    <>
      <PageHead
        title="Tasks"
        lede={
          tasks && tasks.length
            ? `${tasks.length} programming problems in ${languages.length} languages. Each one is scored against a hidden test suite the model never sees.`
            : "Programming problems scored against a hidden test suite the model never sees."
        }
      />

      <div className="task-filters">
        <label className="search">
          <Search size={16} aria-hidden="true" />
          <span className="sr-only">Search tasks</span>
          <input
            type="search"
            className="input"
            placeholder="Search by name or tag"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <div className="seg" role="group" aria-label="Language">
          <button type="button" aria-pressed={!lang} onClick={() => setLang("")}>All</button>
          {languages.map((l) => (
            <button type="button" key={l} aria-pressed={lang === l} onClick={() => setLang(l)}>{LANG_NAMES[l] ?? l}</button>
          ))}
        </div>
        <div className="seg" role="group" aria-label="Difficulty">
          <button type="button" aria-pressed={!diff} onClick={() => setDiff("")}>Any</button>
          {DIFFICULTIES.map((d) => (
            <button type="button" key={d} aria-pressed={diff === d} onClick={() => setDiff(d)}>
              {d.charAt(0).toUpperCase() + d.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div className="panel">
        {error ? (
          <Empty title="Couldn't load tasks">{error}</Empty>
        ) : tasks && shown.length === 0 ? (
          <Empty title="No tasks match" action={filtered ? <button className="btn btn-quiet" onClick={clear}>Clear filters</button> : undefined}>
            {filtered ? "Try a different search, or clear the filters." : "No task files were found in the tasks directory."}
          </Empty>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Language</th>
                  <th>Difficulty</th>
                  <th>Tags</th>
                </tr>
              </thead>
              <tbody>
                {tasks === null ? <SkeletonRows cols={4} rows={8} /> : shown.map((t) => {
                  const href = `/tasks/${encodeURIComponent(t.id)}`;
                  return (
                    <tr key={t.id} className="row-link" onClick={() => router.push(href)}>
                      <td>
                        <Link href={href} className="model" onClick={(e) => e.stopPropagation()}>
                          {t.title || t.id}
                          <small className="code">{t.id}</small>
                        </Link>
                      </td>
                      <td><Lang lang={t.language} /></td>
                      <td><Difficulty level={t.difficulty} /></td>
                      <td>
                        <div className="row" style={{ gap: 6 }}>
                          {t.tags.map((tag) => (
                            <button
                              key={tag}
                              type="button"
                              className="chip"
                              onClick={(e) => { e.stopPropagation(); setSearch(tag); }}
                              title={`Show tasks tagged ${tag}`}
                            >
                              {tag}
                            </button>
                          ))}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {tasks && filtered && shown.length > 0 && (
        <p className="sub" style={{ marginTop: 12 }}>
          Showing {shown.length} of {tasks.length}.{" "}
          <button className="link" style={{ background: "none", border: 0, cursor: "pointer", font: "inherit" }} onClick={clear}>Clear filters</button>
        </p>
      )}
    </>
  );
}

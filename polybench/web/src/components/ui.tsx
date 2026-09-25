import type { ReactNode } from "react";
import { LANG_COLORS, LANG_NAMES, pct, type RunStatus, type TaskScore } from "@/lib/api";

const STATUS_LABEL: Record<RunStatus, string> = {
  PENDING: "Queued",
  RUNNING: "Running",
  COMPLETED: "Completed",
  FAILED: "Failed",
};

export function Status({ status }: { status: RunStatus }) {
  return (
    <span className={`status status-${status.toLowerCase()}`}>
      <span className="status-dot" aria-hidden="true" />
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

export const scoreTone = (v: number) => (v >= 0.8 ? "score-hi" : v >= 0.4 ? "score-mid" : "score-lo");

export function Score({ value, digits = 1 }: { value: number; digits?: number }) {
  return <span className={`score ${scoreTone(value)}`}>{pct(value, digits)}</span>;
}

export function ScoreMeter({ value, pending = false }: { value: number; pending?: boolean }) {
  if (pending) return <span className="muted">—</span>;
  return (
    <div className={`score-cell ${scoreTone(value)}`}>
      <div className="meter" role="presentation">
        <span style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} />
      </div>
      <Score value={value} />
    </div>
  );
}

export function Lang({ lang }: { lang: string }) {
  return (
    <span className="lang">
      <span className="lang-swatch" style={{ background: LANG_COLORS[lang] ?? "var(--ink-3)" }} aria-hidden="true" />
      {LANG_NAMES[lang] ?? lang}
    </span>
  );
}

export function Difficulty({ level }: { level: string }) {
  return (
    <span className={`diff diff-${level}`}>
      <span className="diff-bars" aria-hidden="true"><i /><i /><i /></span>
      {level.charAt(0).toUpperCase() + level.slice(1)}
    </span>
  );
}

export function Skeleton({ w = "100%", h = 14 }: { w?: number | string; h?: number }) {
  return <span className="skeleton" style={{ width: w, height: h }} aria-hidden="true" />;
}

export function SkeletonRows({ rows = 5, cols }: { rows?: number; cols: number }) {
  return (
    <>
      {Array.from({ length: rows }, (_, r) => (
        <tr key={r} aria-hidden="true">
          {Array.from({ length: cols }, (_, c) => (
            <td key={c}><Skeleton w={c === 0 ? "70%" : "50%"} /></td>
          ))}
        </tr>
      ))}
    </>
  );
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      <div className="empty-title">{title}</div>
      {children && <p className="empty-body">{children}</p>}
      {action}
    </div>
  );
}

export function PageHead({ title, lede, children }: { title: ReactNode; lede?: ReactNode; children?: ReactNode }) {
  return (
    <header className="page-head">
      <div>
        <h1 className="page-title">{title}</h1>
        {lede && <p className="page-lede">{lede}</p>}
      </div>
      {children}
    </header>
  );
}

/** Pass/fail cells for a run: one per task, shaded by task pass rate.
 *  Tasks with no finished sample, or not reported yet, are left grey. */
export function ResultStrip({ scores, total }: { scores: TaskScore[]; total: number }) {
  const values = scores.map((s) => (s.samples_done > 0 ? s.pass_at_k : undefined));
  const cells = Array.from({ length: Math.max(total, values.length) }, (_, i) => values[i]);
  return (
    <span className="strip" aria-hidden="true">
      {cells.map((v, i) => (
        <span key={i} className={`cell ${v === undefined ? "" : v >= 1 ? "p" : v <= 0 ? "f" : "h"}`} />
      ))}
    </span>
  );
}

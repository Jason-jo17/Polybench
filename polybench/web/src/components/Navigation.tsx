"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { LayoutGrid, History, GitCompareArrows, BookOpen } from "lucide-react";
import { api, type Stats } from "@/lib/api";

const NAV_ITEMS = [
  { href: "/", label: "Overview", icon: LayoutGrid, exact: true },
  { href: "/runs", label: "Runs", icon: History },
  { href: "/compare", label: "Compare", icon: GitCompareArrows },
  { href: "/tasks", label: "Tasks", icon: BookOpen },
];

type ApiState = "checking" | "ok" | "down";

export default function Navigation() {
  const pathname = usePathname();
  const [activeRuns, setActiveRuns] = useState(0);
  const [apiState, setApiState] = useState<ApiState>("checking");

  useEffect(() => {
    const poll = () =>
      api<Stats>("/stats")
        .then((s) => {
          setActiveRuns(s.active_runs ?? 0);
          setApiState("ok");
        })
        .catch(() => setApiState("down"));
    poll();
    const id = setInterval(poll, 5000);
    return () => clearInterval(id);
  }, []);

  const isCurrent = (href: string, exact?: boolean) =>
    exact ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);

  return (
    <nav className="side" aria-label="Main">
      <Link href="/" className="brand" aria-label="PolyBench overview">
        <span className="brand-mark" aria-hidden="true">
          <span /><span /><span className="f" />
          <span /><span className="i" /><span />
          <span className="f" /><span /><span />
        </span>
        <span className="brand-name">PolyBench</span>
      </Link>

      <div className="side-links">
        {NAV_ITEMS.map(({ href, label, icon: Icon, exact }) => (
          <Link
            key={href}
            href={href}
            className="side-link"
            aria-current={isCurrent(href, exact) ? "page" : undefined}
          >
            <Icon size={16} strokeWidth={1.8} aria-hidden="true" />
            {label}
            {href === "/runs" && activeRuns > 0 && (
              <span className="count" aria-label={`${activeRuns} in progress`}>{activeRuns}</span>
            )}
          </Link>
        ))}
      </div>

      <div className="side-foot">
        <div className="api-state" role="status">
          <span className={`api-dot ${apiState === "ok" ? "ok" : apiState === "down" ? "down" : ""}`} aria-hidden="true" />
          {apiState === "ok" ? "API online" : apiState === "down" ? "API unreachable" : "Checking API…"}
        </div>
      </div>
    </nav>
  );
}

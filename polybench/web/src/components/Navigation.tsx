"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const NAV_ITEMS = [
  {
    href: "/",
    label: "Dashboard",
    exact: true,
    icon: (
      <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
        <rect x="1" y="1" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.2" />
        <rect x="9" y="1" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.2" />
        <rect x="1" y="9" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.2" />
        <rect x="9" y="9" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.2" />
      </svg>
    ),
  },
  {
    href: "/runs",
    label: "Run History",
    exact: false,
    icon: (
      <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
        <circle cx="7.5" cy="7.5" r="6" stroke="currentColor" strokeWidth="1.2" />
        <path d="M7.5 4V7.5L9.5 9.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    href: "/compare",
    label: "Compare Runs",
    exact: false,
    icon: (
      <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
        <path d="M5 2L2 7.5L5 13" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M10 2L13 7.5L10 13" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    href: "/tasks",
    label: "Tasks Library",
    exact: false,
    icon: (
      <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
        <rect x="2" y="2" width="11" height="11" rx="1.5" stroke="currentColor" strokeWidth="1.2" />
        <path d="M5 5.5H10M5 7.5H10M5 9.5H8" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
      </svg>
    ),
  },
];

export default function Navigation() {
  const pathname = usePathname();
  const [activeRuns, setActiveRuns] = useState(0);

  useEffect(() => {
    const fetchRuns = () => {
      fetch("/api/runs")
        .then((r) => r.json())
        .then((data: { status: string }[]) => {
          const active = data.filter(
            (r) => r.status === "RUNNING" || r.status === "PENDING"
          ).length;
          setActiveRuns(active);
        })
        .catch(() => {});
    };
    fetchRuns();
    const interval = setInterval(fetchRuns, 5000);
    return () => clearInterval(interval);
  }, []);

  const isActive = (item: (typeof NAV_ITEMS)[0]) => {
    if (item.exact) return pathname === item.href;
    if (item.href === "/runs") {
      return pathname.startsWith("/runs") && pathname !== "/compare";
    }
    return pathname.startsWith(item.href);
  };

  return (
    <nav className="pb-nav" aria-label="Main navigation">
      {/* Logo */}
      <div className="pb-nav-logo">
        <div className="pb-nav-logo-prefix">⬡ System</div>
        <div className="pb-nav-logo-text">
          Poly<span className="pb-accent">Bench</span>
        </div>
      </div>

      {/* Nav links */}
      <div className="pb-nav-links">
        {NAV_ITEMS.map((item) => {
          const active = isActive(item);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`pb-nav-link${active ? " pb-nav-link-active" : ""}`}
              aria-current={active ? "page" : undefined}
            >
              <span className={active ? "pb-nav-link-icon-active" : "pb-nav-link-icon"}>
                {item.icon}
              </span>
              <span className="pb-nav-link-text">{item.label}</span>
              {item.href === "/runs" && activeRuns > 0 && (
                <span className="pb-nav-run-badge pb-pulse" aria-label={`${activeRuns} active runs`}>
                  {activeRuns}
                </span>
              )}
            </Link>
          );
        })}
      </div>

      {/* Footer */}
      <div className="pb-nav-footer">
        <div className="pb-nav-status-row">
          <span className="pb-nav-status-dot" aria-hidden="true" />
          API CONNECTED
        </div>
        <div className="pb-nav-version">v0.1.0 — polyglot harness</div>
      </div>
    </nav>
  );
}

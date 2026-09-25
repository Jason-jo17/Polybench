"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="pb-fade-up pb-p-card-lg pb-mb-2xl flex flex-col items-center justify-center min-h-[50vh]">
      <div className="pb-section-title pb-mb-sm" style={{ color: "var(--color-fail)" }}>Something went wrong!</div>
      <p className="pb-form-desc mb-6 text-center max-w-md">
        We encountered a critical error while trying to render this page.
        {error.message && <span className="block mt-2 font-mono text-xs opacity-75">{error.message}</span>}
      </p>
      <button
        onClick={() => reset()}
        className="pb-btn-primary"
      >
        Try again
      </button>
    </div>
  );
}

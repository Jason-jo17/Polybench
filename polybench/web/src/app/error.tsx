"use client";

import { useEffect } from "react";
import { Empty } from "@/components/ui";

export default function PageError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="panel">
      <Empty
        title="This page failed to load"
        action={<button className="btn btn-primary" onClick={() => reset()}>Reload page</button>}
      >
        {error.message || "An unexpected error stopped the page from rendering."}
      </Empty>
    </div>
  );
}

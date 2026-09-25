import Link from "next/link";
import { Empty } from "@/components/ui";

export default function NotFound() {
  return (
    <div className="panel">
      <Empty title="Page not found" action={<Link href="/" className="btn btn-primary">Go to overview</Link>}>
        The address doesn&apos;t match any page in PolyBench.
      </Empty>
    </div>
  );
}

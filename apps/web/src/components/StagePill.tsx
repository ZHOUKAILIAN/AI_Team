import type { WorkflowStatus } from "../lib/api";

type Props = {
  status: WorkflowStatus;
  label: string;
};

export function StagePill({ status, label }: Props) {
  const className =
    status === "blocked"
      ? "bg-red-100 text-console-red"
      : status === "waiting_human"
        ? "bg-amber-100 text-amber-800"
        : status === "done"
          ? "bg-blue-100 text-console-blue"
          : "bg-emerald-100 text-console-green";
  return <span className={`inline-flex min-h-8 items-center rounded-full px-3 text-xs font-semibold ${className}`}>{label}</span>;
}

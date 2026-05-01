import type { SocketState } from "../lib/socket";

type Props = {
  state: SocketState;
  label: string;
};

export function SocketIndicator({ state, label }: Props) {
  const color = state === "connected" ? "bg-console-green" : state === "connecting" ? "bg-console-amber" : "bg-console-red";
  return (
    <div className="flex items-center gap-2 text-sm text-console-muted" aria-live="polite">
      <span className={`h-2.5 w-2.5 rounded-full ${color} ${state === "connected" ? "animate-pulse" : ""}`} />
      <span>{label}</span>
    </div>
  );
}

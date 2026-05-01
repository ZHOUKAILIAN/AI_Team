import { useEffect, useState } from "react";

export type SocketState = "connecting" | "connected" | "disconnected" | "fallback";

export function useRuntimeSocket(onRuntimeEvent: () => void) {
  const [state, setState] = useState<SocketState>("connecting");

  useEffect(() => {
    let stopped = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | undefined;

    const connect = () => {
      if (stopped) return;
      setState("connecting");
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      socket = new WebSocket(`${protocol}//${window.location.host}/ws/runtime`);

      socket.addEventListener("open", () => {
        if (!stopped) setState("connected");
      });
      socket.addEventListener("message", () => {
        if (!stopped) onRuntimeEvent();
      });
      socket.addEventListener("close", () => {
        if (stopped) return;
        setState("disconnected");
        reconnectTimer = window.setTimeout(connect, 2000);
      });
      socket.addEventListener("error", () => {
        if (!stopped) setState("fallback");
      });
    };

    connect();

    return () => {
      stopped = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [onRuntimeEvent]);

  return state;
}

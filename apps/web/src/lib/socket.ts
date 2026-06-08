import { useEffect, useState } from "react";

export type SocketState = "connecting" | "connected" | "disconnected" | "fallback";

// 维护 runtime websocket 连接，并在收到事件时触发刷新。
// Maintains the runtime websocket connection and triggers refreshes on events.
export function useRuntimeSocket(onRuntimeEvent: () => void) {
  const [state, setState] = useState<SocketState>("connecting");

  // 建立 websocket、处理重连，并在组件卸载时清理连接。
  // Opens the websocket, handles reconnects, and cleans up on unmount.
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

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite 配置：构建 React 控制台，并在开发模式代理 runtime API/WS。
// Vite config: builds the React console and proxies runtime API/WS in dev mode.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/ws": {
        target: "ws://127.0.0.1:8765",
        ws: true
      }
    }
  }
});

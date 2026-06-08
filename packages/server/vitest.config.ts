import path from "node:path";
import { defineConfig } from "vitest/config";

// Vitest 配置：把 workspace 包别名指向源码，方便 server 测试直接跑 TS。
// Vitest config: points workspace aliases at source files so server tests run TS directly.
export default defineConfig({
  resolve: {
    alias: {
      "@agent-team-runtime/runtime": path.resolve(__dirname, "../runtime/src/index.ts"),
      "@agent-team-runtime/server": path.resolve(__dirname, "src/index.ts"),
    },
  },
});

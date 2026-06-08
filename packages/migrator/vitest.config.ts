import { defineConfig } from "vitest/config";
import path from "node:path";

// Vitest 配置：把 runtime/migrator 包别名指向源码，方便迁移测试直接跑 TS。
// Vitest config: points runtime/migrator package aliases at source files for direct TS tests.
export default defineConfig({
  resolve: {
    alias: {
      "@agent-team-runtime/runtime": path.resolve(__dirname, "../runtime/src/index.ts"),
      "@agent-team-runtime/migrator": path.resolve(__dirname, "src/index.ts"),
    },
  },
});

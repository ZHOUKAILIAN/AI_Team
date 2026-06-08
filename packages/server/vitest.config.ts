import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@agent-team-runtime/runtime": path.resolve(__dirname, "../runtime/src/index.ts"),
      "@agent-team-runtime/server": path.resolve(__dirname, "src/index.ts"),
    },
  },
});

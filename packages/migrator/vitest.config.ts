import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  resolve: {
    alias: {
      "@agent-team-runtime/runtime": path.resolve(__dirname, "../runtime/src/index.ts"),
      "@agent-team-runtime/migrator": path.resolve(__dirname, "src/index.ts"),
    },
  },
});

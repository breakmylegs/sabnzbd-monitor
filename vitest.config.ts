import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // Shared tests run from the monorepo. Mirrors carry only the plugin's own.
    include: ["src/**/*.test.ts", "../../shared/ts/**/*.test.ts"],
    exclude: ["**/node_modules/**", "src/shared/**"],
  },
});

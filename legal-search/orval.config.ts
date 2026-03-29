import { defineConfig } from "orval";

export default defineConfig({
  legalSearchApi: {
    input: {
      // Spec lives in contracts/ (monorepo root), not inside this app.
      // See ADR-0007 and ADR-0004 for rationale.
      target: "../contracts/api/legal-search.openapi.yaml",
    },
    output: {
      // Types and fetch-based client — usable in Server Components and client code.
      target: "./src/lib/api/generated/client.ts",
      schemas: "./src/lib/api/generated/model",
      client: "fetch",
      mode: "split",
    },
  },
  legalSearchApiHooks: {
    input: {
      target: "../contracts/api/legal-search.openapi.yaml",
    },
    output: {
      // React Query hooks — only import these in client components.
      // See ADR-0007: server-side code uses the fetch client above directly.
      target: "./src/lib/api/generated/hooks.ts",
      schemas: "./src/lib/api/generated/model",
      client: "react-query",
      mode: "split",
    },
  },
});

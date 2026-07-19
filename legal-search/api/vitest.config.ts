import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    root: './',
    globals: true,
    include: ['src/**/*.spec.ts'],
    // Integration specs need Docker (Testcontainers OpenSearch) and run in
    // their own project via `npm run test:integration`, which `npm run check`
    // invokes right after this one. Excluded here only so the unit layer stays
    // fast — NOT so it can be skipped.
    exclude: ['src/modules/health/health.smoke.spec.ts', 'src/**/*.integration.spec.ts'],
  },
});

import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    root: './',
    globals: true,
    include: ['src/**/*.spec.ts'],
    exclude: ['src/modules/health/health.smoke.spec.ts'],
  },
});

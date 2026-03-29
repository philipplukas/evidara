import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    include: ['src/**/*.integration.spec.ts'],
    testTimeout: 60000, // Testcontainers need time to pull/start
  },
});

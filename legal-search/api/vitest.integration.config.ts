import { defineConfig } from 'vitest/config';

/**
 * Integration layer: the real adapters against a REAL OpenSearch started by
 * Testcontainers. Requires a working Docker daemon.
 *
 * This layer exists because #672/#673/#675 were all convention mismatches
 * between the query we build and the index we query, and every other layer of
 * the suite mocks the backend away. Do not add a skip-when-Docker-is-missing
 * escape hatch — a silently skipped integration test is exactly the green
 * suite that let those three ship.
 */
export default defineConfig({
  test: {
    globals: true,
    include: ['src/**/*.integration.spec.ts'],
    testTimeout: 60000, // Testcontainers need time to pull/start
    hookTimeout: 240000, // container pull + boot on a cold runner
    // One container, reused across the mapping-shape suites.
    fileParallelism: false,
  },
});

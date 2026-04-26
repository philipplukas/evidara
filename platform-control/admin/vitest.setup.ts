/**
 * Vitest setup for the platform-control admin surface.
 *
 * Admin unit tests run in jsdom (see `vitest.config.ts`) so React Testing
 * Library can render admin components. This file wires up the matchers
 * from `@testing-library/jest-dom` (e.g. `toBeInTheDocument`,
 * `toHaveClass`) and registers an `afterEach` cleanup so tests don't
 * leak DOM state between assertions. Keep this file minimal — per-test
 * providers (react-admin, router) belong next to the test that needs them.
 */
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});

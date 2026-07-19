/**
 * A structural guard for a failure no behavioural test in this repo can see.
 *
 * `@Query() query: CoverageQueryDto` only works if the DTO is imported as a
 * VALUE. Import it as a type and TypeScript erases the class, `design:paramtypes`
 * loses it, and Nest's ValidationPipe silently hands the handler an empty object
 * — every query parameter is dropped and every request answers 200.
 *
 * The reason this needs a structural test is that it is INVISIBLE to the test
 * suite. Under Vitest the transform emits no decorator metadata at all, so the
 * raw query object flows through and the integration tests pass. Only the
 * `tsc`-compiled application drops the parameters. Verified on 2026-07-19: with
 * a type import, a built app answered `?group_by=topic` and `?level=galactic`
 * with 200 and ignored both, while `coverage.integration.spec.ts` was green.
 *
 * That is ADR-0040's concern exactly — a gate reporting green over work it never
 * did — so the convention is pinned here rather than trusted to review.
 *
 * NOTE: `/v1/norm-hierarchy` has this defect live on `main`, which makes
 * ADR-0033's `in_force_at` as-of-date filtering inert in the deployed app. It is
 * out of this change's scope and is reported separately.
 */
import * as fs from 'node:fs';
import * as path from 'node:path';
import { describe, expect, it } from 'vitest';

const CONTROLLER = path.join(__dirname, 'coverage.controller.ts');

describe('CoverageController query binding', () => {
  const source = fs.readFileSync(CONTROLLER, 'utf-8');

  it('imports the query DTO as a value, not as a type', () => {
    // If this fails because the import was "tidied" to `import type`: that
    // change silently disables every query parameter on this endpoint. Keep the
    // `biome-ignore` comment above the import — it is load-bearing, not noise.
    expect(source).toMatch(/^import \{ CoverageQueryDto \}/m);
    expect(source).not.toMatch(/import type \{ CoverageQueryDto \}/);
  });

  it('keeps the biome-ignore that stops the linter erasing it', () => {
    expect(source).toMatch(/biome-ignore lint\/style\/useImportType/);
  });
});

/**
 * Proves the #728 guard actually fires.
 *
 * `scripts/check-validation-metadata.mjs` is the only thing standing between us
 * and a repeat of #728 — a `@Query()` DTO erased at compile time, silently
 * dropping every query parameter in the built app. A guard that never fires
 * would be indistinguishable from a passing one, which is the exact
 * coverage-honesty failure (ADR-0040) the guard exists to close. So the guard
 * gets its own test.
 *
 * These specs build the `design:paramtypes` / `__routeArguments__` shapes by
 * hand rather than by compiling a fixture, because Vitest emits no decorator
 * metadata at all — the very reason the real bug was invisible here. The shapes
 * asserted against are the ones observed in `dist/` on 2026-07-19:
 *
 *   broken: [String, Function, String]           (import type — erased)
 *   fixed:  [String, NormHierarchyQueryDto, String]
 */
import 'reflect-metadata';
import { describe, expect, it } from 'vitest';
// @ts-expect-error — plain-JS guard script, intentionally not part of the build.
import { findViolationsInController } from '../../../scripts/check-validation-metadata.mjs';

const ROUTE_ARGS_METADATA = '__routeArguments__';
const QUERY = 4;
const HEADERS = 6;
const PARAM = 5;

class FakeQueryDto {
  in_force_at?: string;
}

/**
 * A controller shaped exactly like `NormHierarchyController.getNormHierarchy`:
 * `@Param('jurisdiction_id') id, @Query() query, @Headers('accept-language') lang`.
 */
function controllerWithQueryMetatype(metatype: unknown) {
  class TestController {
    getNormHierarchy(_id: string, _query: unknown, _lang?: string) {
      return null;
    }
  }

  Reflect.defineMetadata(
    ROUTE_ARGS_METADATA,
    {
      [`${PARAM}:0`]: { index: 0, data: 'jurisdiction_id', pipes: [] },
      [`${QUERY}:1`]: { index: 1, pipes: [] },
      [`${HEADERS}:2`]: { index: 2, data: 'accept-language', pipes: [] },
    },
    TestController,
    'getNormHierarchy',
  );
  Reflect.defineMetadata(
    'design:paramtypes',
    [String, metatype, String],
    TestController.prototype,
    'getNormHierarchy',
  );
  return TestController;
}

const violations = (metatype: unknown): string[] =>
  findViolationsInController(controllerWithQueryMetatype(metatype), 'test.controller.js');

describe('the erased-ValidationPipe-target guard', () => {
  it('flags the exact shape #728 shipped — `import type` erases the DTO to Function', () => {
    const found = violations(Function);
    expect(found).toHaveLength(1);
    expect(found[0]).toContain('@Query()');
    expect(found[0]).toContain('parameter 1');
    expect(found[0]).toContain('Function');
  });

  it('flags an interface or type alias, which erases to Object', () => {
    // Not the form #728 took, but the same class of bug: anything that leaves
    // ValidationPipe without a real class to instantiate.
    expect(violations(Object)).toHaveLength(1);
  });

  it('flags a binding whose metatype is missing entirely', () => {
    expect(violations(undefined)).toHaveLength(1);
  });

  it('passes a DTO class that survived compilation', () => {
    expect(violations(FakeQueryDto)).toEqual([]);
  });

  it('ignores named bindings like `@Query("q") q: string`, which are not DTO targets', () => {
    class NamedOnlyController {
      resolve(_q?: string) {
        return null;
      }
    }
    Reflect.defineMetadata(
      ROUTE_ARGS_METADATA,
      { [`${QUERY}:0`]: { index: 0, data: 'q', pipes: [] } },
      NamedOnlyController,
      'resolve',
    );
    Reflect.defineMetadata('design:paramtypes', [String], NamedOnlyController.prototype, 'resolve');

    expect(findViolationsInController(NamedOnlyController, 'citations.controller.js')).toEqual([]);
  });

  it('ignores a handler with no route bindings at all', () => {
    class PlainController {
      health() {
        return 'ok';
      }
    }
    expect(findViolationsInController(PlainController, 'health.controller.js')).toEqual([]);
  });
});

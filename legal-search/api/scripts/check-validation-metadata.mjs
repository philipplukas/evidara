#!/usr/bin/env node
/**
 * Guard: every whole-object `@Query()` / `@Body()` / `@Param()` binding must
 * resolve to a real DTO class **in the compiled output**.
 *
 * ## Why this runs against `dist/`, not `src/`
 *
 * This is the #728 defect, and it is invisible to every layer below a built app:
 *
 *   import type { NormHierarchyQueryDto } from './dto/norm-hierarchy-query.dto';
 *   //     ^^^^ erases the class at compile time
 *
 * `tsc` then emits `design:paramtypes: [String, Function, String]` instead of
 * `[String, NormHierarchyQueryDto, String]`. Nest's global `ValidationPipe` gets
 * a `metatype` that carries no `class-validator` metadata, and with
 * `whitelist: true` it strips every property and hands the handler an **empty
 * object**. No error, no warning — every query parameter is silently dropped.
 *
 * On `/v1/norm-hierarchy` that made `in_force_at` — ADR-0033 §2's temporal
 * validity, "the 2019 ban judged against 2019 law" — completely inert in
 * production, while the endpoint kept returning a well-formed, plausible answer
 * to a different question.
 *
 * **Vitest cannot see this.** It transpiles with SWC and emits no decorator
 * metadata at all, so `metatype` is `undefined`, `ValidationPipe` passes the raw
 * query object straight through, and the parameters flow. The tests are not
 * wrong; they are structurally incapable of observing the bug. Per ADR-0040 that
 * makes this a coverage-honesty problem, so the guard must inspect the same
 * artifact production runs — `dist/` — and nothing else.
 *
 * ## Why a lint rule is not sufficient on its own
 *
 * `biome.json` disables `style/useImportType` for controllers (that rule's
 * autofix is what rewrites the value import back to `import type` on every
 * `npm run format`, which is how the bug survives being fixed). But a lint rule
 * only catches one *syntactic* form. This check catches the *class* of bug —
 * an interface, a type alias, a barrel re-export, or any future construct that
 * erases the class produces a non-class metatype and fails here too.
 */
import { readdirSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import 'reflect-metadata';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);

const API_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const DIST = join(API_ROOT, 'dist');

const ROUTE_ARGS_METADATA = '__routeArguments__';
/** From `@nestjs/common/enums/route-paramtypes.enum`. */
const BINDINGS = { 3: '@Body()', 4: '@Query()', 5: '@Param()' };

/**
 * Types that mean "the DTO class did not survive compilation". `Function` is
 * what `tsc` emits for a type-only import; `Object` is what it emits for an
 * interface or type alias. Both leave `ValidationPipe` with nothing to validate.
 */
const NOT_A_DTO = new Set([Object, Function, String, Number, Boolean, Array, Date, Buffer]);

function walk(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else if (entry.endsWith('.controller.js')) out.push(full);
  }
  return out;
}

/**
 * The detection itself, over an already-loaded controller class. Exported so
 * `validation-metadata-guard.spec.ts` can prove the guard actually fires — an
 * unverified guard is the same coverage-honesty problem it exists to solve.
 *
 * @param controller a controller class as it exists at runtime
 * @param origin label used in the message (a file path, in the CLI)
 * @returns human-readable violations; empty when every DTO binding survived
 */
export function findViolationsInController(controller, origin) {
  const violations = [];
  if (typeof controller !== 'function' || !controller.prototype) return violations;

  const methods = Object.getOwnPropertyNames(controller.prototype).filter(
    (name) => name !== 'constructor' && typeof controller.prototype[name] === 'function',
  );

  for (const method of methods) {
    const routeArgs = Reflect.getMetadata(ROUTE_ARGS_METADATA, controller, method);
    if (!routeArgs) continue;
    const paramTypes =
      Reflect.getMetadata('design:paramtypes', controller.prototype, method) ?? [];

    for (const [key, binding] of Object.entries(routeArgs)) {
      const paramtype = Number(key.split(':')[0]);
      const decorator = BINDINGS[paramtype];
      // `data` set means a single named value (`@Query('q') q: string`) —
      // a primitive, correctly typed, and not a ValidationPipe DTO target.
      if (!decorator || binding.data !== undefined) continue;

      const metatype = paramTypes[binding.index];
      if (metatype && !NOT_A_DTO.has(metatype)) continue;

      violations.push(
        `${origin}: ${controller.name}.${method}() parameter ${binding.index} ` +
          `is bound with ${decorator} but compiles to \`${metatype?.name ?? 'undefined'}\`, ` +
          'not a DTO class.',
      );
    }
  }
  return violations;
}

function findViolations(file) {
  const mod = require(file);
  return Object.values(mod).flatMap((exported) =>
    findViolationsInController(exported, relative(API_ROOT, file)),
  );
}

/** CLI: scan every compiled controller under `dist/`. */
function main() {
  let controllers;
  try {
    controllers = walk(DIST);
  } catch {
    console.error(`✗ ${relative(API_ROOT, DIST)}/ not found — run \`npm run build\` first.`);
    process.exit(1);
  }

  const violations = controllers.flatMap(findViolations);

  if (violations.length > 0) {
    console.error('\n✗ Erased ValidationPipe targets in the compiled app:\n');
    for (const violation of violations) console.error(`  - ${violation}`);
    console.error(
      '\n  The class was erased at compile time, so ValidationPipe has nothing to\n' +
        '  instantiate and hands the handler an EMPTY OBJECT. Every parameter on\n' +
        '  these endpoints is silently dropped at runtime — no error is raised, and\n' +
        '  no Vitest layer can observe it (see #728).\n\n' +
        "  Fix: import the DTO as a value (`import { Dto } from './dto/...'`), not\n" +
        '  with `import type`, and make sure nothing between it and the handler\n' +
        '  erases the class.\n',
    );
    process.exit(1);
  }

  console.log(
    `✓ ${controllers.length} compiled controllers: every @Query()/@Body()/@Param() DTO binding resolves to a real class.`,
  );
}

// Only scan when run as a CLI; importing this module (the spec does) must not
// walk dist/ or call process.exit.
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main();
}

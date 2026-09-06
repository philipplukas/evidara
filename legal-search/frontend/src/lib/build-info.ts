/**
 * What commit this bundle was built from.
 *
 * Production ran 27 commits behind `main` for two days, and 35 behind for six
 * weeks before that. Neither was visible from the product — answering "what is
 * actually deployed?" meant asking the cluster which image tag was running. This
 * puts the answer in the UI.
 *
 * The value is the same `github.sha` the image is tagged with, baked as
 * `NEXT_PUBLIC_BUILD_SHA` in the Dockerfile.
 *
 * CRITICAL — the literal-member-expression rule: Next.js only substitutes
 * `NEXT_PUBLIC_*` into the CLIENT bundle when it sees `process.env.NEXT_PUBLIC_FOO`
 * spelled out at build time. Reading it through a variable leaves it `undefined`
 * in the browser. This module is the one place those literals appear, for the same
 * reason `publicConfig.ts` exists in the admin.
 *
 * Unset reports `null`, and the UI then renders nothing rather than an empty
 * version. A blank where a version belongs reads as "no version"; absent is
 * honest.
 */

const RAW_SHA = process.env.NEXT_PUBLIC_BUILD_SHA;
const RAW_DATE = process.env.NEXT_PUBLIC_BUILD_DATE;

export interface BuildInfo {
  /** Full commit SHA. */
  readonly sha: string;
  /** First 8 characters — how commits are cited in this repo. */
  readonly shortSha: string;
  /** RFC 3339 UTC build timestamp, or `null` when not baked. */
  readonly builtAt: string | null;
  /** Commit permalink on GitHub. */
  readonly commitUrl: string;
}

const REPO_URL = "https://github.com/philipplukas/evidara";

/**
 * A blank or whitespace-only value is unset, not a version.
 *
 * The Dockerfile defaults both ARGs to `""`, so an image built without
 * `--build-arg` sets the variable to the empty string rather than leaving it
 * absent — a plain truthiness check on `process.env.X !== undefined` would pass
 * and render an empty string.
 */
function clean(value: string | undefined): string | null {
  const trimmed = value?.trim();
  return trimmed ? trimmed : null;
}

/**
 * Build provenance, or `null` when this bundle was not built from a tagged image
 * (local `npm run dev`, a test run). Callers render nothing for `null`.
 */
export function getBuildInfo(): BuildInfo | null {
  const sha = clean(RAW_SHA);
  if (!sha) {
    return null;
  }
  return {
    sha,
    shortSha: sha.slice(0, 8),
    builtAt: clean(RAW_DATE),
    commitUrl: `${REPO_URL}/commit/${sha}`,
  };
}

/**
 * Short human label: `4932ec2c · 2026-09-06`. The date is rendered as its UTC
 * calendar day rather than localised — a build timestamp is a fact about the
 * release, not about the reader's timezone, and two operators comparing notes
 * should read the same string.
 */
export function formatBuildLabel(info: BuildInfo): string {
  if (!info.builtAt) {
    return info.shortSha;
  }
  const day = info.builtAt.slice(0, 10);
  // Only append something that actually looks like a date; an upstream format
  // change should degrade to the SHA, not print a fragment.
  return /^\d{4}-\d{2}-\d{2}$/.test(day) ? `${info.shortSha} · ${day}` : info.shortSha;
}

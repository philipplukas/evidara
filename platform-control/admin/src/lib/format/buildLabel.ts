/**
 * The short "which build am I looking at" label.
 *
 * Production ran 27 commits behind `main` for two days, and 35 behind for six
 * weeks before that. Neither was visible from the product — answering "what is
 * actually deployed?" meant asking the cluster which image tag was running.
 *
 * The inputs come from `publicConfig` (never `process.env` directly — that
 * module's literal snapshot is what makes `NEXT_PUBLIC_*` reach the browser at
 * all), and are baked in the Dockerfile from the same `github.sha` the image is
 * tagged with.
 */

/**
 * `4932ec2c · 2026-09-06`, or `null` when there is no build to name.
 *
 * `null` — not an empty string and not a placeholder — because the caller must
 * render *nothing*. A blank where a version belongs reads as "this build has no
 * version"; absent reads as "not applicable here", which is the truth under
 * `npm run dev`.
 *
 * @param sha full commit SHA, or undefined outside a released image
 * @param date RFC 3339 UTC build timestamp, or undefined
 */
export function formatBuildLabel(sha: string | undefined, date: string | undefined): string | null {
  const cleanSha = sha?.trim();
  if (!cleanSha) {
    return null;
  }
  const shortSha = cleanSha.slice(0, 8);

  const day = date?.trim().slice(0, 10) ?? "";
  // Append the date only when it really is one. An upstream format change should
  // degrade to the SHA, never print a truncated fragment beside it.
  return /^\d{4}-\d{2}-\d{2}$/.test(day) ? `${shortSha} · ${day}` : shortSha;
}

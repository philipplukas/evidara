/**
 * Shared `RepositoryLink` — the AGPL-3.0 section 13 affordance.
 *
 * Section 13 requires that a user interacting with the software over a network
 * be offered its Corresponding Source. This link is how every network-facing
 * surface discharges that, so it is a product requirement rather than a
 * decoration: removing it from a surface puts that surface out of compliance.
 * `/LICENSE-HISTORY.md` lists where it is rendered on each one.
 *
 * ── Why this lives in `@evidara/shell` ──
 *
 * `platform-control/admin` and `marketing` both need it and neither should own
 * a private copy of the mark. `legal-search/frontend` predates this component
 * (#995) and keeps its own at `src/components/layout/RepositoryLink.tsx`,
 * because it reads its label through `next-intl` and this module must stay
 * i18n-free to be importable from a surface that has no message catalogue.
 * Consolidating the two is a follow-up, not a blocker — both point at the same
 * URL and both render the same mark.
 *
 * ── The mark ──
 *
 * An inline SVG, not a lucide component, because lucide-react v1 removed its
 * brand icons: it exports 5,816 symbols and none of them is `Github`. Importing
 * one typechecks as `undefined` and renders nothing, which is the silent-empty
 * failure this repo keeps filing bugs about. The geometry is carried here
 * instead, and the tests assert the path is actually drawn.
 *
 * `fill="currentColor"` on purpose: the mark inherits whatever colour the host
 * sets, so it themes in light and dark without a second asset and without a
 * hardcoded colour (AGENTS.md design-token rule). Both consuming surfaces run a
 * parity test that fails on a colour literal anywhere in their own source.
 */

/** The public repository this deployment is built from. */
export const REPOSITORY_URL = "https://github.com/philipplukas/evidara";

/** Official GitHub mark, authored on a 16x16 grid. */
const GITHUB_MARK =
  "M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.012 8.012 0 0016 8c0-4.42-3.58-8-8-8z";

export interface RepositoryLinkProps {
  /**
   * The accessible name. Required, not defaulted: each surface writes its own
   * copy (and `legal-search/frontend` translates it), and a default would let a
   * surface ship an unlabelled link by forgetting to pass one.
   */
  label: string;
  /**
   * Host-supplied classes — including layout. This component adds none of its
   * own beyond `sr-only`, deliberately: Tailwind v4 discovers utilities by
   * scanning source files, and `styles/` sits outside every surface's package
   * root, so a utility written *here* is not guaranteed to be generated *there*.
   * `sr-only` is the one exception, and it is safe only because both consuming
   * surfaces already use it in their own source.
   */
  className?: string;
  /** Mark size in px. 16 matches the search header. */
  size?: number;
}

export function RepositoryLink({ label, className = "", size = 16 }: RepositoryLinkProps) {
  return (
    <a
      href={REPOSITORY_URL}
      target="_blank"
      // `noopener` is the security half and `noreferrer` the privacy half; both
      // are required on a `target="_blank"` to an external origin.
      rel="noopener noreferrer"
      title={label}
      className={className}
    >
      <svg
        width={size}
        height={size}
        viewBox="0 0 16 16"
        fill="currentColor"
        aria-hidden="true"
        focusable="false"
      >
        <path d={GITHUB_MARK} />
      </svg>
      {/*
        Visually-hidden text, not `aria-label`: the only child is an
        `aria-hidden` SVG, so without this the link has no accessible name in
        the tree at all. Real text also survives translation and reads correctly
        when CSS fails to load.
      */}
      <span className="sr-only">{label}</span>
    </a>
  );
}

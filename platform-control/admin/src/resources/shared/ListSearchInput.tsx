/**
 * `ListSearchInput` — a name filter for a `useListController`-backed list.
 *
 * Not a form input: `TextInput` binds through `useInput` and needs a `<Form>`
 * around it, which a list does not have. This writes straight to the list
 * controller's filter, debounced by `ra-core`.
 *
 * The reason it exists: the jurisdictions list is 2,169 rows over 44
 * alphabetical pages with no search, so finding Zürich meant paging. The
 * registry has always been searchable — `/v1/reference-data/jurisdictions`
 * takes `q` — the admin simply never sent it. Filtering on the server (rather
 * than over the loaded page) is what keeps the pager and the row count honest:
 * a client-side filter over 50 loaded rows would report "3 jurisdictions" for a
 * search that actually matches 60.
 */
"use client";

import { Search, X } from "lucide-react";
import { useEffect, useId, useState } from "react";

interface ListSearchInputProps {
  /** Current committed filter value, so the box reflects an externally cleared filter. */
  value: string;
  onChange: (next: string) => void;
  label: string;
  placeholder?: string;
  /** Says what the search matches. Operators paste ids as often as they type names. */
  hint?: string;
}

export function ListSearchInput({
  value,
  onChange,
  label,
  placeholder,
  hint,
}: ListSearchInputProps) {
  const id = useId();
  // Local state so typing stays responsive while the committed filter is
  // debounced by the caller; re-synced when the filter changes from elsewhere
  // (a "clear filters" control, a back navigation).
  const [draft, setDraft] = useState(value);

  useEffect(() => {
    setDraft(value);
  }, [value]);

  const commit = (next: string) => {
    setDraft(next);
    onChange(next);
  };

  return (
    <div className="flex flex-col gap-1">
      <label
        htmlFor={id}
        className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--foreground-subtle)]"
      >
        {label}
      </label>
      <div className="relative w-full max-w-[420px]">
        <span
          aria-hidden
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--foreground-subtle)]"
        >
          <Search size={15} strokeWidth={2} />
        </span>
        <input
          id={id}
          type="search"
          value={draft}
          placeholder={placeholder}
          onChange={(event) => commit(event.target.value)}
          className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface-input)] py-2.5 pl-9 pr-9 text-sm text-[var(--foreground)] placeholder:text-[var(--foreground-subtle)] shadow-[var(--shadow-inset-surface)] transition-[border-color] hover:border-[var(--accent-core)]/30 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]"
        />
        {draft ? (
          <button
            type="button"
            onClick={() => commit("")}
            aria-label="Clear search"
            className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full p-1 text-[var(--foreground-subtle)] hover:bg-[var(--interactive-accent-subtle)] hover:text-[var(--foreground)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]"
          >
            <X size={14} strokeWidth={2.2} aria-hidden />
          </button>
        ) : null}
      </div>
      {hint ? <p className="text-[12px] text-[var(--foreground-subtle)]">{hint}</p> : null}
    </div>
  );
}

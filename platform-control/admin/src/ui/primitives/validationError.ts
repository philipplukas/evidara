/**
 * Render a react-hook-form field error the way react-admin's own
 * `<ValidationError>` does.
 *
 * Found while driving the source-create wizard for #671: every required field on
 * every Tailwind input primitive rendered
 *
 *     @@react-admin@@"ra.validation.required"
 *
 * instead of "Required". `ra-core`'s validators cannot return plain strings —
 * they carry a message plus interpolation args — so `useInput` serializes them
 * into a prefixed JSON envelope and expects the renderer to unwrap and translate
 * it. The MUI inputs did that via `<ValidationError>`; the Tailwind ports
 * (`TextInput`, `Select`, and now `Combobox`) read `fieldState.error.message`
 * raw, so the envelope reached the operator verbatim.
 *
 * This is the same defect as the toast keys in #671 — a developer identifier
 * shown at exactly the moment the operator is already confused — one layer down.
 */

const SPECIAL_FORMAT_PREFIX = "@@react-admin@@";

type TranslateFn = (key: string, options: Record<string, unknown> & { _: string }) => string;

/**
 * @param translate `useTranslate()` from ra-core.
 * @param error `fieldState.error?.message`, in any of the shapes RHF allows.
 * @returns a human string, or `null` when there is no error.
 */
export function translateValidationError(translate: TranslateFn, error: unknown): string | null {
  if (error === null || error === undefined || error === "") {
    return null;
  }

  if (typeof error !== "string") {
    // Some validators hand back `{ message, args }` directly.
    const candidate = error as { message?: unknown; args?: Record<string, unknown> };
    if (typeof candidate.message === "string") {
      return safeTranslate(translate, candidate.message, candidate.args);
    }
    return null;
  }

  if (error.startsWith(SPECIAL_FORMAT_PREFIX)) {
    try {
      const parsed: unknown = JSON.parse(error.slice(SPECIAL_FORMAT_PREFIX.length));
      if (typeof parsed === "string") {
        return safeTranslate(translate, parsed);
      }
      const envelope = parsed as { message?: unknown; args?: Record<string, unknown> };
      if (typeof envelope.message === "string") {
        return safeTranslate(translate, envelope.message, envelope.args);
      }
    } catch {
      // Malformed envelope: fall through and show the raw string rather than
      // dropping the only signal the operator has.
    }
  }

  return safeTranslate(translate, error);
}

function safeTranslate(
  translate: TranslateFn,
  message: string,
  args?: Record<string, unknown>,
): string {
  try {
    return translate(message, { _: message, ...(args ?? {}) });
  } catch {
    return message;
  }
}

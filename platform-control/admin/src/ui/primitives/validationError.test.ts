import { describe, expect, it, vi } from "vitest";
import { translateValidationError } from "./validationError";

/**
 * Found by driving the source-create wizard for #671: submitting the form with a
 * required field empty rendered `@@react-admin@@"ra.validation.required"` under
 * the field — ra-core's serialized validator envelope, shown verbatim.
 */

const CATALOGUE: Record<string, string> = {
  "ra.validation.required": "Required",
  "ra.validation.minLength": "Must be %{min} characters at least",
};

const translate = (key: string, options: Record<string, unknown> & { _: string }) => {
  const template = CATALOGUE[key] ?? options._;
  return template.replace(/%\{(\w+)\}/g, (_m, name) => String(options[name] ?? `%{${name}}`));
};

describe("translateValidationError", () => {
  it("unwraps and translates the @@react-admin@@ envelope", () => {
    expect(translateValidationError(translate, '@@react-admin@@"ra.validation.required"')).toBe(
      "Required",
    );
  });

  it("interpolates args carried in the envelope", () => {
    expect(
      translateValidationError(
        translate,
        `@@react-admin@@${JSON.stringify({ message: "ra.validation.minLength", args: { min: 3 } })}`,
      ),
    ).toBe("Must be 3 characters at least");
  });

  it("translates a bare key with no envelope", () => {
    expect(translateValidationError(translate, "ra.validation.required")).toBe("Required");
  });

  it("passes an app-authored literal through unchanged", () => {
    const literal = "Select an authority within the chosen jurisdiction or a global authority.";
    expect(translateValidationError(translate, literal)).toBe(literal);
  });

  it("handles a { message, args } object validator result", () => {
    expect(
      translateValidationError(translate, { message: "ra.validation.minLength", args: { min: 8 } }),
    ).toBe("Must be 8 characters at least");
  });

  it("returns null when there is no error", () => {
    expect(translateValidationError(translate, undefined)).toBeNull();
    expect(translateValidationError(translate, "")).toBeNull();
  });

  it("shows the raw string rather than dropping a malformed envelope", () => {
    expect(translateValidationError(translate, "@@react-admin@@{not json")).toBe(
      "@@react-admin@@{not json",
    );
  });

  it("never returns a string still containing the envelope prefix for valid input", () => {
    const rendered = translateValidationError(translate, '@@react-admin@@"ra.validation.required"');
    expect(rendered).not.toContain("@@react-admin@@");
    expect(rendered).not.toContain("ra.validation");
  });

  it("falls back to the message when translate throws", () => {
    const throwing = vi.fn(() => {
      throw new Error("no i18n provider");
    });
    expect(translateValidationError(throwing, "ra.validation.required")).toBe(
      "ra.validation.required",
    );
  });
});

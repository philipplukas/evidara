import { describe, expect, it, vi } from "vitest";
import { translateNotificationMessage } from "./ToastAdapter";

/**
 * #671: `ra-core` publishes the i18n **key** as the notification message and
 * expects the renderer to translate it. `ToastAdapter` rendered it raw, so
 * operators saw `ra.notification.item_doesnt_exist` and `ra.message.invalid_form`
 * as toast titles.
 */

const CATALOGUE: Record<string, string> = {
  "ra.notification.item_doesnt_exist": "Element does not exist",
  "ra.message.invalid_form": "The form is not valid. Please check for errors",
};

const translate = (key: string, options: { _: string }) => CATALOGUE[key] ?? options._;

describe("translateNotificationMessage", () => {
  it.each(Object.keys(CATALOGUE))("never renders the raw key %s", (key) => {
    const rendered = translateNotificationMessage(translate, key);

    expect(rendered).toBe(CATALOGUE[key]);
    expect(rendered).not.toContain("ra.");
  });

  it("passes app-authored literals through untouched", () => {
    const literal = "Could not create source: connection refused";
    expect(translateNotificationMessage(translate, literal)).toBe(literal);
  });

  it("leaves non-string messages (ReactNode) alone", () => {
    const node = { type: "span" } as unknown as React.ReactNode;
    expect(translateNotificationMessage(translate, node)).toBe(node);
  });

  it("falls back to the raw message rather than losing it when translate throws", () => {
    const throwing = vi.fn(() => {
      throw new Error("no i18n provider");
    });

    expect(translateNotificationMessage(throwing, "something happened")).toBe("something happened");
  });
});

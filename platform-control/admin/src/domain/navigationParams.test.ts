import { describe, expect, it } from "vitest";
import { HandoffOriginValue, NavigationParam } from "./navigationParams";

describe("NavigationParam", () => {
  it("preserves the legal-search handoff URL contract", () => {
    // These values are part of the cross-surface URL contract with
    // legal-search; renaming them on one side without the other breaks
    // the operator handoff silently (see navigationContext.ts).
    expect(NavigationParam.HandoffOrigin).toBe("from");
    expect(NavigationParam.HandoffReturnTo).toBe("ls_return_to");
    expect(NavigationParam.HandoffQuery).toBe("ls_query");
    expect(NavigationParam.HandoffScope).toBe("ls_scope");
    expect(NavigationParam.HandoffItem).toBe("ls_item");
  });

  it("exposes every param name as a unique value", () => {
    const values = Object.values(NavigationParam);
    expect(new Set(values).size).toBe(values.length);
  });
});

describe("HandoffOriginValue", () => {
  it("matches the origin discriminator legal-search writes", () => {
    expect(HandoffOriginValue.LegalSearch).toBe("legal-search");
  });
});

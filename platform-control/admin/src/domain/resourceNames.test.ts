import { describe, expect, it } from "vitest";
import { ResourceName } from "./resourceNames";

describe("ResourceName", () => {
  it("preserves the string values the dataProvider and AdminApp expect", () => {
    // These values are the HTTP-visible route names — any drift here is a
    // breaking change to the dataProvider and every <Resource> registration.
    expect(ResourceName.Jurisdictions).toBe("jurisdictions");
    expect(ResourceName.Authorities).toBe("authorities");
    expect(ResourceName.Sources).toBe("sources");
    expect(ResourceName.PreviewReview).toBe("preview-review");
    expect(ResourceName.Runs).toBe("runs");
    expect(ResourceName.CommentaryInsights).toBe("commentary-insights");
    expect(ResourceName.Corrections).toBe("corrections");
  });

  it("exposes every resource name as a unique value", () => {
    const values = Object.values(ResourceName);
    expect(new Set(values).size).toBe(values.length);
  });
});

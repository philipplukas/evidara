/**
 * Jurisdiction-filter helper tests.
 *
 * WHY THIS TEST EXISTS:
 * The filter helper is the frontend's single entrypoint for translating
 * the OpenAPI `jurisdiction` query param into filter UI state. It must
 * accept both plain country codes and ISO 3166-2 subdivision codes per
 * contracts/api/legal-search.openapi.yaml.
 */

import { describe, expect, it } from "vitest";
import {
  labelForSubdivisionToken,
  parseJurisdictionToken,
  subdivisionsForCountry,
} from "@/lib/jurisdiction-filter";

describe("parseJurisdictionToken", () => {
  it("parses country codes", () => {
    expect(parseJurisdictionToken("CH")).toEqual({ country: "CH" });
    expect(parseJurisdictionToken("EU")).toEqual({ country: "EU" });
  });

  it("parses subdivision codes and keeps the ISO 3166-2 form", () => {
    expect(parseJurisdictionToken("CH-ZH")).toEqual({
      country: "CH",
      subdivision: "CH-ZH",
    });
    expect(parseJurisdictionToken("IT-25")).toEqual({
      country: "IT",
      subdivision: "IT-25",
    });
  });

  it("normalizes lowercased + trimmed input", () => {
    expect(parseJurisdictionToken("  ch-zh  ")).toEqual({
      country: "CH",
      subdivision: "CH-ZH",
    });
  });

  it("rejects malformed tokens", () => {
    expect(parseJurisdictionToken("")).toBeNull();
    expect(parseJurisdictionToken("CHH")).toBeNull();
    expect(parseJurisdictionToken("CH-")).toBeNull();
    expect(parseJurisdictionToken("CH-ZH-XX")).toBeNull();
  });
});

describe("subdivisionsForCountry", () => {
  it("returns 26 entries for CH", () => {
    const ch = subdivisionsForCountry("CH", "en");
    expect(ch).toHaveLength(26);
  });

  it("returns 9 entries for AT", () => {
    const at = subdivisionsForCountry("AT", "de");
    expect(at).toHaveLength(9);
  });

  it("picks the preferred language from prefLabel", () => {
    const ch = subdivisionsForCountry("CH", "de");
    const zh = ch.find((entry) => entry.iso === "CH-ZH");
    expect(zh?.label).toBe("Zürich");

    const chFr = subdivisionsForCountry("CH", "fr");
    const zhFr = chFr.find((entry) => entry.iso === "CH-ZH");
    expect(zhFr?.label).toBe("Zurich");
  });

  it("falls back to English when the preferred language is missing", () => {
    // CH-AI has no "fr" label today; helper should fall back to en.
    const ch = subdivisionsForCountry("CH", "fr");
    const ai = ch.find((entry) => entry.iso === "CH-AI");
    expect(ai?.label).toBe("Appenzell Innerrhoden");
  });

  it("returns empty array for countries without subdivisions", () => {
    expect(subdivisionsForCountry("EU")).toEqual([]);
    expect(subdivisionsForCountry("LI")).toEqual([]);
    expect(subdivisionsForCountry("ZZ")).toEqual([]);
  });
});

describe("labelForSubdivisionToken", () => {
  it("returns the localized label for a subdivision token", () => {
    const token = parseJurisdictionToken("IT-25");
    expect(token).not.toBeNull();
    if (token) expect(labelForSubdivisionToken(token, "it")).toBe("Lombardia");
  });

  it("returns null for a country-only token (consumer uses country vocab)", () => {
    const token = parseJurisdictionToken("CH");
    expect(token).not.toBeNull();
    if (token) expect(labelForSubdivisionToken(token, "en")).toBeNull();
  });
});

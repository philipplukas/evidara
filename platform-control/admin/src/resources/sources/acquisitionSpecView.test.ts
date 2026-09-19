/**
 * The partition must account for EVERY key, and the summary must be lossy.
 *
 * Those are the two halves of one claim: the panel is worth having because
 * `summarizeAcquisitionSpec` hides fields, and it is only worth having while it
 * hides none itself. Both are asserted, so the panel cannot quietly become
 * another partial view — which is the defect it exists to fix.
 */
import { describe, expect, it } from "vitest";
import { buildAcquisitionSpec } from "../../lib/admin/__fixtures__/acquisitionSpecs";
import {
  formatSpecEntryValue,
  partitionAcquisitionSpec,
  partitionedKeys,
  unreadableSpecLines,
} from "./acquisitionSpecView";
import { summarizeAcquisitionSpec } from "./sourceVersionForm";

/** A provider the version form has no widgets for — seven of eleven are like this. */
const cantonSpec = buildAcquisitionSpec({
  provider: "canton_http",
  canton_code: "CH-ZH",
  seed_url: "https://www.zh.ch/de/politik-staat/gesetze-beschluesse.html",
  seed_urls: [],
});

/** One the form does render, so the summary takes its bespoke branch. */
const firecrawlSpec = buildAcquisitionSpec({
  provider: "firecrawl",
  mode: "crawl",
  seed_url: "https://example.test",
  seed_urls: [],
  limit: 10,
  max_discovery_depth: 2,
  scrape_formats: ["markdown"],
  zero_data_retention: true,
});

describe("partitionAcquisitionSpec", () => {
  it.each([
    ["canton_http", cantonSpec],
    ["firecrawl", firecrawlSpec],
  ])("accounts for every key of a %s spec", (_name, spec) => {
    const keys = partitionedKeys(partitionAcquisitionSpec(spec));
    expect(new Set(keys)).toEqual(new Set(Object.keys(spec)));
  });

  it("puts identity and scope fields in their own group", () => {
    const { identity, providerConfig } = partitionAcquisitionSpec(cantonSpec);
    const identityKeys = identity.map((e) => e.key);

    expect(identityKeys).toContain("corpus_id");
    expect(identityKeys).toContain("trust_tier");
    expect(identityKeys).toContain("scope_type");
    // ...and the provider's own settings are not mixed in with them.
    expect(providerConfig.map((e) => e.key)).toContain("canton_code");
    expect(identityKeys).not.toContain("canton_code");
  });

  it("orders identity fields by declaration, not by serialisation order", () => {
    const { identity } = partitionAcquisitionSpec(cantonSpec);
    const keys = identity.map((e) => e.key);
    expect(keys.indexOf("tenant_id")).toBeLessThan(keys.indexOf("corpus_id"));
    expect(keys.indexOf("corpus_id")).toBeLessThan(keys.indexOf("trust_tier"));
  });
});

describe("what the table summary leaves out", () => {
  /**
   * The justification for the panel, asserted rather than claimed.
   *
   * If someone makes `summarizeAcquisitionSpec` complete, this goes red — and at
   * that point the honest response is to delete the panel, not to weaken the
   * test. Either way the repo stops carrying two views that disagree about how
   * much they show.
   */
  it.each([
    ["canton_http", cantonSpec],
    ["firecrawl", firecrawlSpec],
  ])("hides identity and scope for a %s spec, and the panel does not", (_name, spec) => {
    const summary = summarizeAcquisitionSpec(spec).join("\n");
    const panelKeys = partitionedKeys(partitionAcquisitionSpec(spec));

    for (const hidden of ["corpus_id", "tenant_id", "trust_tier", "scope_type"]) {
      expect(summary).not.toContain(hidden);
      expect(panelKeys).toContain(hidden);
    }
  });
});

describe("formatSpecEntryValue", () => {
  it("distinguishes an empty field from an absent one", () => {
    // A field that exists and is empty is a different fact from a field that is
    // not there. Rendering both as blank is how "declared with no producer" hides.
    expect(formatSpecEntryValue(null)).toBe("not set");
    expect(formatSpecEntryValue([])).toBe("empty list");
  });

  it("renders lists and booleans the way an operator reads them", () => {
    expect(formatSpecEntryValue(["de", "fr"])).toBe("de, fr");
    expect(formatSpecEntryValue(true)).toBe("yes");
    expect(formatSpecEntryValue(false)).toBe("no");
  });
});

/**
 * #953 — the API reports a stored spec it cannot parse as `acquisition_spec:
 * null` plus a reason, rather than answering 500. Every surface that renders a
 * spec has to say so, and none of them may render it as an empty configuration.
 */
describe("unreadableSpecLines", () => {
  it("says the spec could not be read, not that there is none", () => {
    const lines = unreadableSpecLines("<root>: Unable to extract tag using discriminator").join(
      "\n",
    );

    expect(lines).toContain("could not be read");
    // The failure mode this whole issue is about: a defect rendered as a finding.
    expect(lines).not.toMatch(/\bno spec\b|\bempty configuration\b|\(empty\)/i);
  });

  it("carries the API's reason through when there is one", () => {
    expect(unreadableSpecLines("HTTP 500").join("\n")).toContain("HTTP 500");
  });

  it("says the reason is missing rather than implying there was none", () => {
    const lines = unreadableSpecLines(null).join("\n");

    expect(lines).toContain("not stated by the API");
    expect(lines).toContain("could not be read");
  });
});

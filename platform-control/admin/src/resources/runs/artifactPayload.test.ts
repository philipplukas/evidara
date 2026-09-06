import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  consumedPayloadKeys,
  extractArtifactContent,
  remainingPayload,
  summarizeArtifactPayload,
} from "./artifactPayload";

/** Shape of a Firecrawl page as `firecrawl_webhook_service.py` stores it. */
const firecrawlPage = {
  markdown: "# Hundegesetz\n\nDer Regierungsrat…",
  rawHtml: "<h1>Hundegesetz</h1>",
  metadata: {
    sourceURL: "https://zh.ch/erlass/554.5",
    title: "Hundegesetz",
    statusCode: 200,
    contentType: "text/html",
  },
};

describe("summarizeArtifactPayload", () => {
  it("lifts nested Firecrawl metadata fields", () => {
    expect(summarizeArtifactPayload(firecrawlPage)).toEqual([
      { label: "Title", value: "Hundegesetz" },
      { label: "Source URL", value: "https://zh.ch/erlass/554.5" },
      { label: "HTTP status", value: "200" },
      { label: "Content type", value: "text/html" },
    ]);
  });

  it("reads flat payloads too (the normalized run_service path)", () => {
    expect(
      summarizeArtifactPayload({
        title: "Flat",
        byte_size: 1024,
        checksum: "abc",
        checksum_algorithm: "sha256",
      }),
    ).toEqual([
      { label: "Title", value: "Flat" },
      { label: "Byte size", value: "1024" },
      { label: "Checksum", value: "abc" },
      { label: "Checksum algorithm", value: "sha256" },
    ]);
  });

  it("prefers a top-level key over the same key nested", () => {
    expect(summarizeArtifactPayload({ title: "top", metadata: { title: "nested" } })).toEqual([
      { label: "Title", value: "top" },
    ]);
  });

  // Guard: a truthiness check here silently drops both of these, and
  // `statusCode: 0` is exactly the case an operator is hunting.
  it("keeps falsy-but-meaningful scalars", () => {
    const fields = summarizeArtifactPayload({ statusCode: 0, title: "t" });
    expect(fields).toContainEqual({ label: "HTTP status", value: "0" });
  });

  it("omits absent fields rather than rendering placeholders", () => {
    expect(summarizeArtifactPayload({ title: "only" })).toHaveLength(1);
  });

  it("ignores container and empty values", () => {
    expect(
      summarizeArtifactPayload({ title: { nested: true }, url: [], contentType: "   " }),
    ).toEqual([]);
  });

  it.each([
    [null],
    [undefined],
    ["a string"],
    [42],
    [["an", "array"]],
  ])("returns [] for non-object payload %s", (payload) => {
    expect(summarizeArtifactPayload(payload)).toEqual([]);
  });
});

describe("extractArtifactContent", () => {
  it("prefers markdown over html", () => {
    expect(extractArtifactContent(firecrawlPage)).toEqual({
      key: "markdown",
      value: firecrawlPage.markdown,
    });
  });

  it("falls back through the key order", () => {
    expect(extractArtifactContent({ rawHtml: "<p>x</p>" })).toEqual({
      key: "rawHtml",
      value: "<p>x</p>",
    });
    expect(extractArtifactContent({ text: "plain" })?.key).toBe("text");
  });

  it("reports which key it used so the view is not a guess", () => {
    expect(extractArtifactContent({ html: "<p>x</p>" })?.key).toBe("html");
  });

  it("returns null when there is no body", () => {
    expect(extractArtifactContent({ metadata: { title: "t" } })).toBeNull();
    expect(extractArtifactContent({ markdown: "   " })).toBeNull();
    expect(extractArtifactContent(null)).toBeNull();
  });
});

describe("remainingPayload", () => {
  it("omits what the summary and body already showed", () => {
    const rest = remainingPayload(firecrawlPage);
    expect(rest).not.toBeNull();
    expect(Object.keys(rest ?? {})).not.toContain("markdown");
    expect(Object.keys(rest ?? {})).toContain("rawHtml");
  });

  it("keeps `metadata` even when the summary drew from it", () => {
    // Only a handful of metadata's keys are lifted; dropping the object would
    // hide the rest.
    expect(Object.keys(remainingPayload(firecrawlPage) ?? {})).toContain("metadata");
  });

  it("returns null when nothing is left over", () => {
    expect(remainingPayload({ title: "t", markdown: "body" })).toBeNull();
  });

  it("returns null for a non-object payload", () => {
    expect(remainingPayload("nope")).toBeNull();
  });
});

describe("consumedPayloadKeys", () => {
  it("covers the summary keys present and the chosen body key", () => {
    const consumed = consumedPayloadKeys(firecrawlPage);
    expect(consumed.has("markdown")).toBe(true);
    expect(consumed.has("rawHtml")).toBe(false);
  });
});

/**
 * Guard for the security property the panel depends on.
 *
 * `extractArtifactContent` can select `html` or `rawHtml`, so the body it
 * returns may be arbitrary third-party markup captured from the open web.
 * Rendering it as markup would execute scraped script inside the operator's
 * authenticated admin session. Introduce `dangerouslySetInnerHTML` into the
 * run detail sections and this test goes red.
 */
describe("captured page bodies are never rendered as markup", () => {
  it("RunDetailSectionsV2 never uses dangerouslySetInnerHTML", () => {
    const source = readFileSync(join(__dirname, "RunDetailSectionsV2.tsx"), "utf8");
    // Matches the JSX attribute / object property, not the identifier appearing
    // in prose — the file's own security comment names it, and a bare substring
    // check fails on that comment while proving nothing about the code.
    expect(source).not.toMatch(/dangerouslySetInnerHTML\s*[=:]/);
  });
});

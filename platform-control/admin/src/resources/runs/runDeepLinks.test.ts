import { describe, expect, it } from "vitest";
import { buildDocumentSearchHref, buildMinioObjectHref, parseS3Uri } from "./runDeepLinks";

describe("parseS3Uri", () => {
  it("splits bucket and key", () => {
    expect(parseS3Uri("s3://evidara-raw-artifacts-prod/runs/run_123/art_123.json")).toEqual({
      bucket: "evidara-raw-artifacts-prod",
      key: "runs/run_123/art_123.json",
    });
  });

  it("keeps the whole remainder as the key, including nested prefixes", () => {
    expect(parseS3Uri("s3://b/a/b/c/d.pdf")?.key).toBe("a/b/c/d.pdf");
  });

  // Guard: delete the `startsWith("s3://")` check and these go green with a
  // nonsense bucket, which is how a link to a non-existent object gets rendered.
  it.each([
    ["", "empty"],
    ["   ", "whitespace"],
    ["/local/path/art.json", "a POSIX path"],
    ["https://example.com/art.json", "an http URL"],
    ["s3://", "scheme only"],
    ["s3://bucket", "bucket with no key"],
    ["s3://bucket/", "bucket with empty key"],
    ["s3:///key", "empty bucket"],
  ])("returns null for %s (%s)", (input) => {
    expect(parseS3Uri(input)).toBeNull();
  });

  it("returns null for nullish input", () => {
    expect(parseS3Uri(null)).toBeNull();
    expect(parseS3Uri(undefined)).toBeNull();
  });
});

describe("buildDocumentSearchHref", () => {
  it("builds legal-search's own /?item= deep-link shape", () => {
    expect(buildDocumentSearchHref("https://search.example.dev", "doc_001")).toBe(
      "https://search.example.dev/?item=doc_001",
    );
  });

  it("strips exactly one trailing slash rather than emitting //", () => {
    expect(buildDocumentSearchHref("https://search.example.dev/", "doc_001")).toBe(
      "https://search.example.dev/?item=doc_001",
    );
  });

  it("encodes ids that would otherwise alter the query string", () => {
    expect(buildDocumentSearchHref("https://s.dev", "doc/1&x=2")).toBe(
      "https://s.dev/?item=doc%2F1%26x%3D2",
    );
  });

  // Guard: this is the whole reason the function returns `string | null`.
  // Make it fall back to a default origin and this test fails — which is the
  // point, because a deployed admin linking to localhost is a dead link that
  // claims the document is reachable.
  it("returns null when the base URL is unconfigured", () => {
    expect(buildDocumentSearchHref(undefined, "doc_001")).toBeNull();
    expect(buildDocumentSearchHref("", "doc_001")).toBeNull();
    expect(buildDocumentSearchHref("   ", "doc_001")).toBeNull();
  });

  it("returns null when there is no document id", () => {
    expect(buildDocumentSearchHref("https://s.dev", null)).toBeNull();
    expect(buildDocumentSearchHref("https://s.dev", "  ")).toBeNull();
  });
});

describe("buildMinioObjectHref", () => {
  it("builds the console object-browser route with the key encoded whole", () => {
    expect(buildMinioObjectHref("https://minio.example.dev", "s3://raw/runs/run_1/a.json")).toBe(
      "https://minio.example.dev/browser/raw/runs%2Frun_1%2Fa.json",
    );
  });

  it("strips a trailing slash on the console base", () => {
    expect(buildMinioObjectHref("https://minio.example.dev/", "s3://raw/a.json")).toBe(
      "https://minio.example.dev/browser/raw/a.json",
    );
  });

  // Guard: both null paths matter independently.
  it("returns null when the console is unconfigured", () => {
    expect(buildMinioObjectHref(undefined, "s3://raw/a.json")).toBeNull();
  });

  it("returns null when the storage path is not an s3 URI", () => {
    expect(buildMinioObjectHref("https://minio.example.dev", "/var/data/a.json")).toBeNull();
  });
});

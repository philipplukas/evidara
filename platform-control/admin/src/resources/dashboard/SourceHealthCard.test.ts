/**
 * #953 — a failed version fetch must not render as "this source has no version".
 *
 * `/v1/sources/{id}/versions` answered 500 for one seeded source, and this card
 * did `if (!res.ok) return []` and then rendered a missing label as a dash — the
 * same dash two genuinely version-less rows already carried. A failure and an
 * absence produced byte-identical output, so nothing could have caught it
 * regressing. ADR-0052: unknown is not zero.
 *
 * The load-bearing test is `renders a failed fetch differently from an empty one`.
 * Collapse the distinction anywhere in the chain — in `fetchSourceVersions`, in
 * `computeSourceHealth`, or in `formatVersionInfo` — and it goes red.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import {
  computeSourceHealth,
  fetchSourceVersions,
  formatVersionInfo,
  type SourceVersionsFetch,
} from "./SourceHealthCard";

const originalFetch = global.fetch;

afterEach(() => {
  global.fetch = originalFetch;
  vi.restoreAllMocks();
});

const jsonResponse = (body: unknown, status: number): Response =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });

const source = (source_id: string) => ({ source_id, name: source_id, status: "active" });

const version = (source_id: string) => ({
  source_version_id: `sv_${source_id}`,
  source_id,
  version_label: "v1",
  status: "approved",
});

describe("fetchSourceVersions", () => {
  it("reports a 500 as a failure, not as an empty list", async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValue(jsonResponse({ detail: "Internal Server Error" }, 500)) as typeof fetch;

    const result = await fetchSourceVersions("src_broken");

    expect(result.ok).toBe(false);
    // The reason is what tells an operator this is a defect and not a finding.
    expect(result).toMatchObject({ source_id: "src_broken", reason: "HTTP 500" });
  });

  it("reports a rejected request as a failure", async () => {
    global.fetch = vi.fn().mockRejectedValue(new TypeError("network")) as typeof fetch;

    await expect(fetchSourceVersions("src_offline")).resolves.toMatchObject({ ok: false });
  });

  it("reports a 200 whose body is not the documented shape as a failure", async () => {
    global.fetch = vi.fn().mockResolvedValue(jsonResponse({}, 200)) as typeof fetch;

    await expect(fetchSourceVersions("src_weird")).resolves.toMatchObject({
      ok: false,
      reason: "unrecognised response body",
    });
  });

  it("reports a genuinely empty list as a success", async () => {
    global.fetch = vi.fn().mockResolvedValue(jsonResponse({ data: [] }, 200)) as typeof fetch;

    await expect(fetchSourceVersions("src_empty")).resolves.toEqual({
      source_id: "src_empty",
      ok: true,
      versions: [],
    });
  });
});

describe("computeSourceHealth", () => {
  const fetches: SourceVersionsFetch[] = [
    { source_id: "src_broken", ok: false, reason: "HTTP 500" },
    { source_id: "src_empty", ok: true, versions: [] },
    { source_id: "src_ok", ok: true, versions: [version("src_ok")] },
  ];

  const rows = computeSourceHealth(
    [source("src_broken"), source("src_empty"), source("src_ok")],
    [],
    fetches,
  );

  const byId = (id: string) => {
    const row = rows.find((candidate) => candidate.source_id === id);
    if (!row) throw new Error(`no row for ${id}`);
    return row;
  };

  it("keeps a failed fetch on the row that failed", () => {
    expect(byId("src_broken").versionUnavailableReason).toBe("HTTP 500");
    expect(byId("src_broken").versionLabel).toBeNull();
  });

  it("leaves a source with no versions unmarked", () => {
    expect(byId("src_empty").versionUnavailableReason).toBeNull();
    expect(byId("src_empty").versionLabel).toBeNull();
  });

  it("still resolves the latest version for a source that answered", () => {
    expect(byId("src_ok").versionLabel).toBe("v1");
    expect(byId("src_ok").versionStatus).toBe("approved");
    expect(byId("src_ok").versionUnavailableReason).toBeNull();
  });

  it("does not let one source's failure reach another row", () => {
    expect(byId("src_ok").versionUnavailableReason).toBeNull();
    expect(byId("src_empty").versionUnavailableReason).toBeNull();
  });
});

describe("formatVersionInfo", () => {
  const unavailable = {
    versionLabel: null,
    versionStatus: null,
    versionUnavailableReason: "HTTP 500",
  };
  const none = { versionLabel: null, versionStatus: null, versionUnavailableReason: null };

  it("renders a failed fetch differently from an empty one", () => {
    // The whole issue in one assertion. Before #953 both sides were "-".
    expect(formatVersionInfo(unavailable)).not.toBe(formatVersionInfo(none));
  });

  it("says unavailable rather than showing a bare dash for a failed fetch", () => {
    expect(formatVersionInfo(unavailable)).toContain("unavailable");
  });

  it("renders a bare em dash for a source that genuinely has no version", () => {
    expect(formatVersionInfo(none)).toBe("—");
  });

  it("renders label and status when both are known", () => {
    expect(
      formatVersionInfo({
        versionLabel: "v1",
        versionStatus: "approved",
        versionUnavailableReason: null,
      }),
    ).toBe("v1 (approved)");
  });
});

describe("the whole chain, from response to cell", () => {
  it("a 500 and an empty 200 do not produce the same cell", async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ detail: "boom" }, 500))
      .mockResolvedValueOnce(jsonResponse({ data: [] }, 200)) as typeof fetch;

    const results = await Promise.all([
      fetchSourceVersions("src_broken"),
      fetchSourceVersions("src_empty"),
    ]);
    const rows = computeSourceHealth([source("src_broken"), source("src_empty")], [], results);

    const cells = rows.map(formatVersionInfo);
    expect(new Set(cells).size).toBe(2);
  });
});

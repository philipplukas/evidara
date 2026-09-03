import { describe, expect, it } from "vitest";
import {
  groupRefusalsByReason,
  isUnverifiedMirrorStatus,
  readCaptureLedger,
  readMirrorFidelity,
} from "./providerJobPayload";

/**
 * Real payload shapes, copied from the three producers on `main`:
 *
 * - `lexfind_api_provider.py:1053-1062` — `captured` / `published` / `skipped` as
 *   an ARRAY / `mirror_fidelity`.
 * - `portal_http_provider_base.py:151-159` — `skipped` as a COUNT, list under
 *   `skipped_documents`.
 * - `gemeinde_http_provider.py:414-422` — list under `skipped_manifestations`.
 */
const lexfindPayload = {
  captured: 4,
  published: 0,
  skipped: [
    { tol_id: 1, url: "/a.pdf", reason: "below_size_floor", detail: "142 bytes, floor is 2000" },
    { tol_id: 2, url: "/b.pdf", reason: "below_size_floor", detail: "300 bytes, floor is 2000" },
    { tol_id: 3, url: "/c.pdf", reason: "original_url_missing", detail: "no original_url" },
  ],
  failures: [],
  mirror_fidelity: {
    sampled: 1,
    candidates: 4,
    identical: 0,
    diverged: 1,
    unverified: 0,
    proven: false,
    checks: [
      {
        status: "diverged",
        source_url: "https://zh.ch/erlass",
        tol_id: 22871,
        mirror_md5: "aaa",
        source_md5: "bbb",
        detail: "md5 differs",
      },
    ],
  },
};

const portalPayload = {
  provider: "canton_http",
  requested: 3,
  captured: 1,
  failed: 0,
  skipped: 2,
  failures: [],
  skipped_documents: [
    { url: "https://x/1", reason: "no_legal_text_markers", detail: "0 markers in 900 chars" },
    { url: "https://x/2", reason: "no_legal_text_markers", detail: "0 markers in 120 chars" },
  ],
};

describe("readCaptureLedger", () => {
  it("keeps captured and published as separate numbers so a discard is legible", () => {
    // #853 and the LexFind mirror discard both hinge on this: one number makes a
    // whole-batch discard indistinguishable from an empty run.
    const ledger = readCaptureLedger([lexfindPayload]);
    expect(ledger.captured).toBe(4);
    expect(ledger.published).toBe(0);
    expect(ledger.disagrees).toBe(true);
  });

  it("reports an unrecorded published count as unknown, never as zero", () => {
    // The portal provider records no `published` key at all. Rendering that as 0
    // would claim it published nothing — the lie the caller cannot detect.
    const ledger = readCaptureLedger([portalPayload]);
    expect(ledger.captured).toBe(1);
    expect(ledger.published).toBeNull();
    // Unknown can neither agree nor disagree.
    expect(ledger.disagrees).toBe(false);
  });

  it("counts refusals from a list, not from the provider's own count, when both exist", () => {
    // `skipped` is a COUNT for the portal provider and the list lives under
    // `skipped_documents`; double-counting would report 4 refusals over 2.
    expect(readCaptureLedger([portalPayload]).refused).toBe(2);
    expect(readCaptureLedger([portalPayload]).hasRefusalDetail).toBe(true);
  });

  it("still reports a refusal count when only the provider's number was recorded", () => {
    const ledger = readCaptureLedger([{ captured: 5, skipped: 3 }]);
    expect(ledger.refused).toBe(3);
    expect(ledger.hasRefusalDetail).toBe(false);
  });

  it("reports every count as unknown when there is no payload to read", () => {
    const ledger = readCaptureLedger([null, undefined, "not-an-object", 7]);
    expect(ledger.captured).toBeNull();
    expect(ledger.published).toBeNull();
    expect(ledger.refused).toBeNull();
    expect(ledger.disagrees).toBe(false);
  });

  it("sums across provider jobs", () => {
    const ledger = readCaptureLedger([
      { captured: 2, published: 2 },
      { captured: 3, published: 1 },
    ]);
    expect(ledger.captured).toBe(5);
    expect(ledger.published).toBe(3);
    expect(ledger.disagrees).toBe(true);
  });
});

describe("groupRefusalsByReason", () => {
  it("groups the artifact_guard slugs and carries a remedy for each known one", () => {
    const groups = groupRefusalsByReason([lexfindPayload]);
    expect(groups.map((g) => [g.reason, g.count])).toEqual([
      ["below_size_floor", 2],
      ["original_url_missing", 1],
    ]);
    expect(groups[0].remedy).toContain("floor");
    expect(groups[0].sampleDetail).toBe("142 bytes, floor is 2000");
  });

  it("reads all three producers' list keys", () => {
    const groups = groupRefusalsByReason([
      portalPayload,
      { skipped_manifestations: [{ url: "u", reason: "unsupported_manifestation_content_type" }] },
    ]);
    expect(groups.map((g) => g.reason)).toEqual([
      "no_legal_text_markers",
      "unsupported_manifestation_content_type",
    ]);
  });

  it("keeps an unrecognised slug rather than dropping it", () => {
    // A refusal the panel does not know about is still a refusal, and silently
    // discarding it would under-report what the run turned away.
    const groups = groupRefusalsByReason([{ skipped: [{ reason: "some_new_slug" }] }]);
    expect(groups).toEqual([
      {
        reason: "some_new_slug",
        count: 1,
        remedy: null,
        sampleDetail: null,
        sampleUrl: null,
      },
    ]);
  });

  it("does not mistake a numeric skipped count for a refusal list", () => {
    expect(groupRefusalsByReason([{ skipped: 4 }])).toEqual([]);
  });
});

describe("readMirrorFidelity", () => {
  it("returns null when no provider job carried a check", () => {
    // An absent key means the check DID NOT RUN. It must never read as verified.
    expect(readMirrorFidelity([portalPayload])).toBeNull();
  });

  it("reads the producer's own `proven` boolean rather than re-deriving it", () => {
    const fidelity = readMirrorFidelity([lexfindPayload]);
    expect(fidelity?.proven).toBe(false);
    expect(fidelity?.diverged).toBe(1);
    expect(fidelity?.sampled).toBe(1);
    expect(fidelity?.checks[0].status).toBe("diverged");
  });

  it("treats a missing `proven` as unproven", () => {
    const fidelity = readMirrorFidelity([{ mirror_fidelity: { sampled: 1, identical: 1 } }]);
    expect(fidelity?.proven).toBe(false);
  });
});

describe("isUnverifiedMirrorStatus", () => {
  it("classifies an unreachable source as unverified, not as a pass", () => {
    // `source_unreachable` is not `identical`; conflating them restores exactly
    // the trust-on-assertion the check exists to end.
    expect(isUnverifiedMirrorStatus("source_unreachable")).toBe(true);
    expect(isUnverifiedMirrorStatus("source_document_not_found")).toBe(true);
    expect(isUnverifiedMirrorStatus("check_error")).toBe(true);
    expect(isUnverifiedMirrorStatus("identical")).toBe(false);
    expect(isUnverifiedMirrorStatus("diverged")).toBe(false);
  });
});

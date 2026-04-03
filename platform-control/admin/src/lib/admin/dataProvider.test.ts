import { afterEach, describe, expect, it, vi } from "vitest";
import { controlPlaneActions, controlPlaneDataProvider } from "./dataProvider";

const originalFetch = global.fetch;

afterEach(() => {
  global.fetch = originalFetch;
  vi.restoreAllMocks();
});

describe("controlPlaneDataProvider", () => {
  it("maps run list filters onto the platform-control API", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          data: [
            {
              run_id: "run_01",
              source_id: "src_01",
              source_version_id: "sv_01",
              mode: "production",
              status: "running",
              started_at: "2026-04-03T09:00:00Z",
              completed_at: null,
              artifacts_count: 4,
              captured_resources_count: 4,
              failure_reason: null,
              created_at: "2026-04-03T09:00:00Z",
              updated_at: "2026-04-03T09:01:00Z",
              source_name: "Zurich decisions",
              version_label: "v1",
            },
          ],
        }),
        {
          status: 200,
          headers: {
            "content-type": "application/json",
          },
        },
      ),
    ) as typeof fetch;

    const result = await controlPlaneDataProvider.getList("runs", {
      pagination: { page: 1, perPage: 25 },
      sort: { field: "created_at", order: "DESC" },
      filter: { mode: "production", status: "running" },
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/platform-control/v1/runs?mode=production&status=running",
      expect.objectContaining({
        cache: "no-store",
        headers: {
          Accept: "application/json",
        },
      }),
    );
    expect(result.total).toBe(1);
    expect(result.data[0]).toMatchObject({
      id: "run_01",
      run_id: "run_01",
      source_name: "Zurich decisions",
      version_label: "v1",
    });
  });

  it("maps run-scoped diagnostics resources onto run detail endpoints", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          data: [
            {
              provider_job_id: "pjob_01",
              run_id: "run_01",
              provider: "firecrawl",
              external_job_id: "crawl_01",
              status: "completed",
              last_event_type: "crawl.completed",
              request_payload: { url: "https://example.com" },
              response_payload: { success: true },
              created_at: "2026-04-03T09:00:00Z",
              updated_at: "2026-04-03T09:01:00Z",
            },
          ],
        }),
        {
          status: 200,
          headers: {
            "content-type": "application/json",
          },
        },
      ),
    ) as typeof fetch;

    const result = await controlPlaneDataProvider.getList("run-provider-jobs", {
      pagination: { page: 1, perPage: 100 },
      sort: { field: "created_at", order: "DESC" },
      filter: { run_id: "run_01" },
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/platform-control/v1/runs/run_01/provider-jobs",
      expect.objectContaining({
        cache: "no-store",
        headers: {
          Accept: "application/json",
        },
      }),
    );
    expect(result.total).toBe(1);
    expect(result.data[0]).toMatchObject({
      id: "pjob_01",
      provider_job_id: "pjob_01",
      status: "completed",
      last_event_type: "crawl.completed",
    });
  });

  it("maps preview-review lists onto preview run queries", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          data: [
            {
              run_id: "run_preview_01",
              source_id: "src_01",
              source_version_id: "sv_01",
              mode: "preview",
              status: "completed",
              started_at: "2026-04-03T09:00:00Z",
              completed_at: "2026-04-03T09:05:00Z",
              artifacts_count: 5,
              captured_resources_count: 5,
              failure_reason: null,
              created_at: "2026-04-03T09:00:00Z",
              updated_at: "2026-04-03T09:05:00Z",
              source_name: "Zurich decisions",
              version_label: "preview-v1",
            },
          ],
        }),
        {
          status: 200,
          headers: {
            "content-type": "application/json",
          },
        },
      ),
    ) as typeof fetch;

    const result = await controlPlaneDataProvider.getList("preview-review", {
      pagination: { page: 1, perPage: 25 },
      sort: { field: "created_at", order: "DESC" },
      filter: { status: "completed" },
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/platform-control/v1/runs?mode=preview&status=completed",
      expect.objectContaining({
        headers: {
          Accept: "application/json",
        },
      }),
    );
    expect(result.data[0]).toMatchObject({
      id: "run_preview_01",
      mode: "preview",
      status: "completed",
    });
  });

  it("rejects preview-review getOne responses that are not preview runs", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          run_id: "run_prod_01",
          source_id: "src_01",
          source_version_id: "sv_01",
          mode: "production",
          status: "running",
          started_at: "2026-04-03T09:00:00Z",
          completed_at: null,
          artifacts_count: 0,
          captured_resources_count: 0,
          failure_reason: null,
          created_at: "2026-04-03T09:00:00Z",
          updated_at: "2026-04-03T09:00:00Z",
        }),
        {
          status: 200,
          headers: {
            "content-type": "application/json",
          },
        },
      ),
    ) as typeof fetch;

    await expect(
      controlPlaneDataProvider.getOne("preview-review", {
        id: "run_prod_01",
      }),
    ).rejects.toMatchObject({
      status: 404,
    });
  });

  it("returns an empty source-version list before a source is selected", async () => {
    global.fetch = vi.fn() as typeof fetch;

    const result = await controlPlaneDataProvider.getList("source-versions", {
      pagination: { page: 1, perPage: 25 },
      sort: { field: "created_at", order: "DESC" },
      filter: { source_id: "__none__" },
    });

    expect(global.fetch).not.toHaveBeenCalled();
    expect(result).toEqual({
      data: [],
      total: 0,
    });
  });

  it("creates source versions through the nested source endpoint", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          source_version_id: "sv_01",
          source_id: "src_01",
          extractor_profile_id: null,
          version_label: "v2",
          status: "draft",
          acquisition_spec: {
            seed_url: "https://example.com/decisions",
            seed_urls: [],
            mode: "crawl",
            include_paths: [],
            exclude_paths: [],
            limit: 20,
            max_discovery_depth: 2,
            scrape_formats: ["markdown", "html"],
            zero_data_retention: false,
          },
          created_at: "2026-04-03T09:00:00Z",
          updated_at: "2026-04-03T09:00:00Z",
        }),
        {
          status: 201,
          headers: {
            "content-type": "application/json",
          },
        },
      ),
    ) as typeof fetch;

    const result = await controlPlaneDataProvider.create("source-versions", {
      data: {
        source_id: "src_01",
        version_label: "v2",
        extractor_profile_id: "",
        acquisition_spec: {
          seed_url: "https://example.com/decisions",
          seed_urls: [],
          mode: "crawl",
          include_paths: [],
          exclude_paths: [],
          limit: 20,
          max_discovery_depth: 2,
          scrape_formats: ["markdown", "html"],
          zero_data_retention: false,
        },
      },
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/platform-control/v1/sources/src_01/versions",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          version_label: "v2",
          extractor_profile_id: null,
          acquisition_spec: {
            seed_url: "https://example.com/decisions",
            seed_urls: [],
            mode: "crawl",
            include_paths: [],
            exclude_paths: [],
            limit: 20,
            max_discovery_depth: 2,
            scrape_formats: ["markdown", "html"],
            zero_data_retention: false,
          },
        }),
      }),
    );
    expect(result.data).toMatchObject({
      id: "sv_01",
      source_version_id: "sv_01",
      version_label: "v2",
    });
  });

  it("does not send version_label when updating source versions without it", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          source_version_id: "sv_01",
          source_id: "src_01",
          extractor_profile_id: "exp_custom",
          version_label: "v-existing",
          status: "draft",
          acquisition_spec: {
            seed_url: "https://example.com/decisions",
            seed_urls: [],
            mode: "crawl",
            include_paths: [],
            exclude_paths: [],
            limit: 20,
            max_discovery_depth: 2,
            scrape_formats: ["markdown", "html"],
            zero_data_retention: false,
          },
          created_at: "2026-04-03T09:00:00Z",
          updated_at: "2026-04-03T09:00:00Z",
        }),
        {
          status: 200,
          headers: {
            "content-type": "application/json",
          },
        },
      ),
    ) as typeof fetch;

    await controlPlaneDataProvider.update("source-versions", {
      id: "sv_01",
      data: {
        source_id: "src_01",
        acquisition_spec: {
          seed_url: "https://example.com/decisions",
          seed_urls: [],
          mode: "crawl",
          include_paths: [],
          exclude_paths: [],
          limit: 20,
          max_discovery_depth: 2,
          scrape_formats: ["markdown", "html"],
          zero_data_retention: false,
        },
      },
      previousData: {
        id: "sv_01",
        source_version_id: "sv_01",
        source_id: "src_01",
        extractor_profile_id: "exp_default",
        version_label: "v-existing",
        status: "draft",
        acquisition_spec: {
          seed_url: "https://example.com/decisions",
          seed_urls: [],
          mode: "crawl",
          include_paths: [],
          exclude_paths: [],
          limit: 20,
          max_discovery_depth: 2,
          scrape_formats: ["markdown", "html"],
          zero_data_retention: false,
        },
        created_at: "2026-04-03T09:00:00Z",
        updated_at: "2026-04-03T09:00:00Z",
      },
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/platform-control/v1/versions/sv_01",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({
          acquisition_spec: {
            seed_url: "https://example.com/decisions",
            seed_urls: [],
            mode: "crawl",
            include_paths: [],
            exclude_paths: [],
            limit: 20,
            max_discovery_depth: 2,
            scrape_formats: ["markdown", "html"],
            zero_data_retention: false,
          },
        }),
      }),
    );
  });

  it("creates runs through the runs endpoint", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          run_id: "run_01",
          source_id: "src_01",
          source_version_id: "sv_01",
          mode: "preview",
          status: "running",
          started_at: "2026-04-03T09:00:00Z",
          completed_at: null,
          artifacts_count: 0,
          captured_resources_count: 0,
          failure_reason: null,
          created_at: "2026-04-03T09:00:00Z",
          updated_at: "2026-04-03T09:00:00Z",
        }),
        {
          status: 201,
          headers: {
            "content-type": "application/json",
          },
        },
      ),
    ) as typeof fetch;

    const result = await controlPlaneDataProvider.create("runs", {
      data: {
        source_id: "src_01",
        source_version_id: "sv_01",
        mode: "preview",
      },
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/platform-control/v1/runs",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          source_id: "src_01",
          source_version_id: "sv_01",
          mode: "preview",
        }),
      }),
    );
    expect(result.data).toMatchObject({
      id: "run_01",
      run_id: "run_01",
      status: "running",
    });
  });

  it("updates authorities through the reference-data patch route", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          authority_id: "auth_01",
          jurisdiction_id: "jur_01",
          name: "Federal Court",
          slug: "federal-court",
          created_at: "2026-04-03T09:00:00Z",
          updated_at: "2026-04-03T09:05:00Z",
        }),
        {
          status: 200,
          headers: {
            "content-type": "application/json",
          },
        },
      ),
    ) as typeof fetch;

    const result = await controlPlaneDataProvider.update("authorities", {
      id: "auth_01",
      data: {
        authority_id: "auth_01",
        jurisdiction_id: "jur_01",
        name: "Federal Court",
        slug: "federal-court",
      },
      previousData: {
        id: "auth_01",
        authority_id: "auth_01",
        jurisdiction_id: "jur_01",
        name: "Federal Supreme Court",
        slug: "federal-supreme-court",
        created_at: "2026-04-03T09:00:00Z",
        updated_at: "2026-04-03T09:00:00Z",
      },
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/platform-control/v1/reference-data/authorities/auth_01",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({
          jurisdiction_id: "jur_01",
          name: "Federal Court",
          slug: "federal-court",
        }),
      }),
    );
    expect(result.data).toMatchObject({
      id: "auth_01",
      authority_id: "auth_01",
      name: "Federal Court",
    });
  });

  it("cancels runs through the cancel action endpoint", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          run_id: "run_01",
          source_id: "src_01",
          source_version_id: "sv_01",
          mode: "preview",
          status: "cancelled",
          started_at: "2026-04-03T09:00:00Z",
          completed_at: "2026-04-03T09:05:00Z",
          artifacts_count: 1,
          captured_resources_count: 1,
          failure_reason: "Cancelled by operator.",
          created_at: "2026-04-03T09:00:00Z",
          updated_at: "2026-04-03T09:05:00Z",
        }),
        {
          status: 200,
          headers: {
            "content-type": "application/json",
          },
        },
      ),
    ) as typeof fetch;

    const result = await controlPlaneActions.cancelRun("run_01");

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/platform-control/v1/runs/run_01/cancel",
      expect.objectContaining({
        method: "POST",
      }),
    );
    expect(result).toMatchObject({
      id: "run_01",
      status: "cancelled",
      failure_reason: "Cancelled by operator.",
    });
  });

  it("loads preview summaries through the preview-summary endpoint", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          run_id: "run_01",
          captured_url_count: 5,
          artifacts_count: 5,
          captured_resources_count: 5,
          pdf_count: 1,
          likely_decision_page_count: 3,
          likely_boilerplate_page_count: 1,
          likely_duplicate_page_count: 1,
          content_type_breakdown: [{ content_type: "text/html", count: 4 }],
          likely_decision_pages: [],
          likely_boilerplate_pages: [],
          likely_duplicate_pages: [],
          drift_checks: [
            { name: "artifact-count", status: "ok", detail: "Artifacts were captured." },
          ],
        }),
        {
          status: 200,
          headers: {
            "content-type": "application/json",
          },
        },
      ),
    ) as typeof fetch;

    const result = await controlPlaneActions.getRunPreviewSummary("run_01");

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/platform-control/v1/runs/run_01/preview-summary",
      expect.objectContaining({
        headers: {
          Accept: "application/json",
        },
      }),
    );
    expect(result).toMatchObject({
      run_id: "run_01",
      captured_url_count: 5,
      likely_decision_page_count: 3,
    });
  });
});

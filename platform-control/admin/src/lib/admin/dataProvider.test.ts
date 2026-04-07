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

  it("applies client pagination and sort to unbounded run lists", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          data: [
            {
              run_id: "run_old",
              source_id: "src_01",
              source_version_id: "sv_01",
              mode: "preview",
              status: "completed",
              started_at: "2026-04-03T08:00:00Z",
              completed_at: "2026-04-03T08:05:00Z",
              artifacts_count: 1,
              captured_resources_count: 1,
              failure_reason: null,
              created_at: "2026-04-03T08:00:00Z",
              updated_at: "2026-04-03T08:05:00Z",
              source_name: "Older",
              version_label: "v0",
            },
            {
              run_id: "run_new",
              source_id: "src_01",
              source_version_id: "sv_01",
              mode: "preview",
              status: "completed",
              started_at: "2026-04-03T10:00:00Z",
              completed_at: "2026-04-03T10:05:00Z",
              artifacts_count: 2,
              captured_resources_count: 2,
              failure_reason: null,
              created_at: "2026-04-03T10:00:00Z",
              updated_at: "2026-04-03T10:05:00Z",
              source_name: "Newer",
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
      pagination: { page: 1, perPage: 1 },
      sort: { field: "created_at", order: "DESC" },
      filter: {},
    });

    expect(result.total).toBe(2);
    expect(result.data).toHaveLength(1);
    expect(result.data[0]?.run_id).toBe("run_new");
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
          total: 1,
          limit: 100,
          offset: 0,
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
      "/api/platform-control/v1/runs/run_01/provider-jobs?limit=100&offset=0",
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

  it("creates source and initial version through the wizard endpoint", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          source: {
            source_id: "src_99",
            name: "AT Combined Wizard Source",
            description: null,
            jurisdiction_id: "jur_ch",
            authority_id: "auth_bger",
            source_type: "website",
            document_family: null,
            status: "active",
            created_at: "2026-04-07T10:00:00Z",
            updated_at: "2026-04-07T10:00:00Z",
          },
          source_version: {
            source_version_id: "sv_99",
            source_id: "src_99",
            extractor_profile_id: null,
            version_label: "v1",
            status: "draft",
            acquisition_spec: {
              provider: "ris_ogd",
              base_url: "https://data.bka.gv.at/ris/api/v2.6/Bundesrecht",
              preferred_formats: ["Xml", "Html"],
              page_size: 20,
              max_pages: 50,
            },
            created_at: "2026-04-07T10:00:00Z",
            updated_at: "2026-04-07T10:00:00Z",
          },
        }),
        {
          status: 201,
          headers: {
            "content-type": "application/json",
          },
        },
      ),
    ) as typeof fetch;

    const result = await controlPlaneDataProvider.create("source-create-wizard", {
      data: {
        source: {
          name: "AT Combined Wizard Source",
          jurisdiction_id: "jur_ch",
          authority_id: "auth_bger",
          source_type: "website",
        },
        source_version: {
          version_label: "v1",
          overlay_id: "at",
          provider_template_id: "ris_ogd_bundesrecht",
        },
      },
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/platform-control/v1/sources/with-version",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          source: {
            name: "AT Combined Wizard Source",
            jurisdiction_id: "jur_ch",
            authority_id: "auth_bger",
            source_type: "website",
            description: undefined,
            document_family: undefined,
          },
          source_version: {
            version_label: "v1",
            overlay_id: "at",
            provider_template_id: "ris_ogd_bundesrecht",
          },
        }),
      }),
    );
    expect(result.data).toMatchObject({
      id: "src_99",
      source_id: "src_99",
      source_version: {
        source_version_id: "sv_99",
      },
    });
  });

  it("supports end-to-end wizard data flow: templates -> preview -> create", async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            data: [
              {
                overlay_id: "at",
                provider_template_id: "ris_ogd_bundesrecht",
                provider: "ris_ogd",
              },
            ],
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            overlay_id: "at",
            provider_template_id: "ris_ogd_bundesrecht",
            acquisition_spec: {
              provider: "ris_ogd",
              base_url: "https://data.bka.gv.at/ris/api/v2.6/Bundesrecht",
            },
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            source: {
              source_id: "src_flow",
              name: "Flow source",
              description: null,
              jurisdiction_id: "jur_ch",
              authority_id: "auth_bger",
              source_type: "website",
              document_family: null,
              status: "active",
              created_at: "2026-04-07T10:00:00Z",
              updated_at: "2026-04-07T10:00:00Z",
            },
            source_version: {
              source_version_id: "sv_flow",
              source_id: "src_flow",
              extractor_profile_id: null,
              version_label: "v1",
              status: "draft",
              acquisition_spec: {
                provider: "ris_ogd",
                base_url: "https://data.bka.gv.at/ris/api/v2.6/Bundesrecht",
                preferred_formats: ["Xml", "Html"],
                page_size: 20,
                max_pages: 50,
              },
              created_at: "2026-04-07T10:00:00Z",
              updated_at: "2026-04-07T10:00:00Z",
            },
          }),
          { status: 201, headers: { "content-type": "application/json" } },
        ),
      ) as typeof fetch;

    const templates = await controlPlaneActions.listSourceBlueprintTemplates();
    expect(templates[0]?.provider_template_id).toBe("ris_ogd_bundesrecht");

    const preview = await controlPlaneActions.previewSourceBlueprint({
      overlay_id: "at",
      provider_template_id: templates[0]!.provider_template_id,
    });
    expect(preview.acquisition_spec.provider).toBe("ris_ogd");

    const created = await controlPlaneDataProvider.create("source-create-wizard", {
      data: {
        source: {
          name: "Flow source",
          jurisdiction_id: "jur_ch",
          authority_id: "auth_bger",
          source_type: "website",
        },
        source_version: {
          version_label: "v1",
          overlay_id: "at",
          provider_template_id: templates[0]!.provider_template_id,
        },
      },
    });
    expect(created.data).toMatchObject({
      source_id: "src_flow",
      source_version: { source_version_id: "sv_flow" },
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

  it("loads run readiness through the readiness endpoint", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          source_id: "src_01",
          source_version_id: "sv_01",
          mode: "production",
          ready: false,
          checks: [
            {
              code: "acquisition_seed_present",
              ok: false,
              detail: "Acquisition spec must define seed_url or seed_urls.",
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

    const result = await controlPlaneActions.getRunReadiness({
      source_id: "src_01",
      source_version_id: "sv_01",
      mode: "production",
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/platform-control/v1/runs/readiness?source_id=src_01&source_version_id=sv_01&mode=production",
      expect.objectContaining({
        headers: {
          Accept: "application/json",
        },
      }),
    );
    expect(result).toMatchObject({
      ready: false,
      checks: [{ code: "acquisition_seed_present", ok: false }],
    });
  });

  it("loads pipeline health through the run pipeline-health endpoint", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          run_id: "run_01",
          source_id: "src_01",
          source_version_id: "sv_01",
          mode: "preview",
          run_status: "running",
          overall_status: "in_progress",
          stages: [
            {
              stage: "acquisition",
              status: "in_progress",
              detail: "Acquisition provider run is in progress.",
              updated_at: "2026-04-06T10:00:00Z",
            },
          ],
          processing_status_event_count: 0,
          document_lifecycle_event_count: 0,
        }),
        {
          status: 200,
          headers: {
            "content-type": "application/json",
          },
        },
      ),
    ) as typeof fetch;

    const result = await controlPlaneActions.getRunPipelineHealth("run_01");

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/platform-control/v1/runs/run_01/pipeline-health",
      expect.objectContaining({
        headers: {
          Accept: "application/json",
        },
      }),
    );
    expect(result).toMatchObject({
      run_id: "run_01",
      overall_status: "in_progress",
      stages: [{ stage: "acquisition", status: "in_progress" }],
    });
  });

  it("loads source blueprint previews through the preview endpoint", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          overlay_id: "de",
          provider_template_id: "deterministic_http_bundesrecht",
          acquisition_spec: {
            provider: "deterministic_http",
            seed_urls: ["https://www.gesetze-im-internet.de/"],
            seed_url: null,
          },
        }),
        {
          status: 200,
          headers: {
            "content-type": "application/json",
          },
        },
      ),
    ) as typeof fetch;

    const result = await controlPlaneActions.previewSourceBlueprint({
      overlay_id: "de",
      provider_template_id: "deterministic_http_bundesrecht",
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/platform-control/v1/sources/blueprint-preview",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          overlay_id: "de",
          provider_template_id: "deterministic_http_bundesrecht",
        }),
      }),
    );
    expect(result).toMatchObject({
      acquisition_spec: { provider: "deterministic_http" },
    });
  });

  it("loads source blueprint templates through the templates endpoint", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          data: [
            {
              overlay_id: "at",
              provider_template_id: "ris_ogd_bundesrecht",
              provider: "ris_ogd",
            },
            {
              overlay_id: "de",
              provider_template_id: "deterministic_http_bundesrecht",
              provider: "deterministic_http",
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

    const result = await controlPlaneActions.listSourceBlueprintTemplates();

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/platform-control/v1/sources/blueprint-templates",
      expect.objectContaining({
        headers: {
          Accept: "application/json",
        },
      }),
    );
    expect(result).toHaveLength(2);
    expect(result[0]?.overlay_id).toBe("at");
  });

  it("fills missing preview summary collections and normalizes drift status", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          run_id: "run_01",
          captured_url_count: 0,
          artifacts_count: 0,
          captured_resources_count: 0,
          pdf_count: 0,
          likely_decision_page_count: 0,
          likely_boilerplate_page_count: 0,
          likely_duplicate_page_count: 0,
          drift_checks: [{ name: "x", status: "unknown", detail: "y" }],
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

    expect(result.content_type_breakdown).toEqual([]);
    expect(result.likely_decision_pages).toEqual([]);
    expect(result.drift_checks[0]?.status).toBe("ok");
  });
});

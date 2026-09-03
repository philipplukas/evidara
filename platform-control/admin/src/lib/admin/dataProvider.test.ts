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
          total: 137,
          limit: 25,
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

    const result = await controlPlaneDataProvider.getList("runs", {
      pagination: { page: 1, perPage: 25 },
      sort: { field: "created_at", order: "DESC" },
      filter: { mode: "production", status: "running" },
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/platform-control/v1/runs?mode=production&status=running&limit=25&offset=0",
      expect.objectContaining({
        cache: "no-store",
        headers: {
          Accept: "application/json",
        },
      }),
    );
    // #616: the hit count comes from the server, not from the page length.
    expect(result.total).toBe(137);
    expect(result.data[0]).toMatchObject({
      id: "run_01",
      run_id: "run_01",
      source_name: "Zurich decisions",
      version_label: "v1",
    });
  });

  /**
   * ADR-0035 built the refusal record and #634 built `GET /v1/runs?refused=true`
   * — explicitly so refusals could be audited "without them polluting failure
   * triage". No client ever sent the parameter, so the filter existed and the
   * refusal log did not. These two cases pin the wire.
   */
  it.each([
    [true, "refused=true"],
    // `false` is a real filter value ("exclude refusals"), not an absence, so it
    // must reach the server rather than being dropped as falsy.
    [false, "refused=false"],
  ])("forwards the ADR-0030 refusal filter (%s)", async (refused, expected) => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ data: [], total: 0, limit: 25, offset: 0 }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    ) as typeof fetch;

    await controlPlaneDataProvider.getList("runs", {
      pagination: { page: 1, perPage: 25 },
      sort: { field: "created_at", order: "DESC" },
      filter: { refused },
    });

    expect(global.fetch).toHaveBeenCalledWith(
      `/api/platform-control/v1/runs?${expected}&limit=25&offset=0`,
      expect.anything(),
    );
  });

  it("omits the refusal filter entirely when it is not set", async () => {
    // An absent filter means "both", not "false"; sending `refused=false` by
    // default would hide every refusal from the default queue.
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ data: [], total: 0, limit: 25, offset: 0 }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    ) as typeof fetch;

    await controlPlaneDataProvider.getList("runs", {
      pagination: { page: 1, perPage: 25 },
      sort: { field: "created_at", order: "DESC" },
      filter: {},
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/platform-control/v1/runs?limit=25&offset=0",
      expect.anything(),
    );
  });

  /**
   * #616 — `/v1/runs` is server-paginated (`{data, limit, offset, total}`,
   * default `limit=100`). This test previously asserted the opposite premise
   * ("unbounded run lists") and so pinned the bug: the provider sent no
   * pagination and re-derived `total` from the page, making run 101+
   * unreachable. It now asserts the paginated contract.
   */
  it("sends limit/offset for run list pages and trusts the server total", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          data: [
            {
              run_id: "run_page_3",
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
          ],
          total: 512,
          limit: 50,
          offset: 100,
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
      pagination: { page: 3, perPage: 50 },
      sort: { field: "created_at", order: "DESC" },
      filter: {},
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/platform-control/v1/runs?limit=50&offset=100",
      expect.objectContaining({ cache: "no-store" }),
    );
    expect(result.total).toBe(512);
    expect(result.data).toHaveLength(1);
    expect(result.data[0]?.run_id).toBe("run_page_3");
  });

  /**
   * #695 — the contract requires only `data` on `RunListResponse`; `total`,
   * `limit` and `offset` are each `integer | null`. The admin used to declare
   * all three as required `number`, so the `total ?? records.length` fallback
   * was unreachable in the type system and untested — the one branch the
   * contract explicitly permits and the suite never exercised. It is the #616
   * behaviour (re-deriving the count from the page), so it must degrade
   * visibly rather than crash.
   */
  it("falls back to the page length when the server sends a null total", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          data: [
            {
              run_id: "run_no_total",
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
              source_name: "No total",
              version_label: "v0",
            },
          ],
          total: null,
          limit: null,
          offset: null,
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    ) as typeof fetch;

    const result = await controlPlaneDataProvider.getList("runs", {
      pagination: { page: 1, perPage: 25 },
      sort: { field: "created_at", order: "DESC" },
      filter: {},
    });

    expect(result.total).toBe(1);
    expect(result.data).toHaveLength(1);
    expect(result.data[0]?.run_id).toBe("run_no_total");
  });

  /** #695 — same branch, with the keys absent entirely rather than null. */
  it("falls back to the page length when the server omits total entirely", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          data: [
            {
              run_id: "run_absent_total",
              source_id: "src_01",
              source_version_id: "sv_01",
              mode: "preview",
              status: "completed",
              started_at: null,
              completed_at: null,
              artifacts_count: 0,
              captured_resources_count: 0,
              failure_reason: null,
              created_at: "2026-04-03T08:00:00Z",
              updated_at: "2026-04-03T08:05:00Z",
              source_name: "Absent total",
              version_label: "v0",
            },
          ],
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    ) as typeof fetch;

    const result = await controlPlaneDataProvider.getList("runs", {
      pagination: { page: 1, perPage: 25 },
      sort: { field: "created_at", order: "DESC" },
      filter: {},
    });

    expect(result.total).toBe(1);
    expect(result.data[0]?.run_id).toBe("run_absent_total");
  });

  it("sends limit/offset and the q search for source list pages", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          data: [
            {
              source_id: "src_page_2",
              name: "Gemeinde Adliswil",
              description: null,
              jurisdiction_id: "jur_ch_zh",
              authority_id: "auth_zh",
              source_type: "website",
              document_family: null,
              status: "active",
              created_at: "2026-04-03T08:00:00Z",
              updated_at: "2026-04-03T08:05:00Z",
            },
          ],
          total: 2110,
          limit: 50,
          offset: 50,
        }),
        {
          status: 200,
          headers: {
            "content-type": "application/json",
          },
        },
      ),
    ) as typeof fetch;

    const result = await controlPlaneDataProvider.getList("sources", {
      pagination: { page: 2, perPage: 50 },
      sort: { field: "updated_at", order: "DESC" },
      filter: { q: "  Adliswil  " },
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/platform-control/v1/sources?q=Adliswil&limit=50&offset=50",
      expect.objectContaining({ cache: "no-store" }),
    );
    expect(result.total).toBe(2110);
    expect(result.data[0]).toMatchObject({ id: "src_page_2", source_id: "src_page_2" });
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
      "/api/platform-control/v1/runs?mode=preview&status=completed&limit=25&offset=0",
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

  it("loads fedlex sparql source blueprint previews through the preview endpoint", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          overlay_id: "ch",
          provider_template_id: "fedlex_sparql_constitution_de",
          acquisition_spec: {
            provider: "fedlex_sparql",
            seed_url: "https://fedlex.data.admin.ch/eli/cc/1999/404",
            seed_urls: [],
            sparql_endpoint: "https://fedlex.data.admin.ch/sparqlendpoint",
            preferred_languages: ["de"],
            query_mode: "work_to_expression",
            max_expressions: 1,
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
      overlay_id: "ch",
      provider_template_id: "fedlex_sparql_constitution_de",
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/platform-control/v1/sources/blueprint-preview",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          overlay_id: "ch",
          provider_template_id: "fedlex_sparql_constitution_de",
        }),
      }),
    );
    expect(result.acquisition_spec).toMatchObject({
      provider: "fedlex_sparql",
      seed_url: "https://fedlex.data.admin.ch/eli/cc/1999/404",
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
            {
              overlay_id: "ch",
              provider_template_id: "fedlex_sparql_constitution_de",
              provider: "fedlex_sparql",
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
    expect(result).toHaveLength(3);
    expect(result[0]?.overlay_id).toBe("at");
    expect(result[2]?.provider).toBe("fedlex_sparql");
  });

  describe("corrections + commentary-insights (#428)", () => {
    it("filters corrections list query by status, type, and target", async () => {
      const fetchMock = vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            data: [
              {
                correction_id: "cor_01",
                target_entity_type: "commentary_insight",
                target_entity_id: "ins_01jq7c1ny0ffv8qdr1xwbejqb6",
                correction_type: "field_edit",
                payload: { field: "claim", value: "x" },
                original_snapshot: null,
                operator_id: "op_01",
                pipeline_run_id: null,
                rationale: null,
                status: "pending",
                created_at: "2026-04-25T09:00:00Z",
                applied_at: null,
              },
            ],
            total: 1,
            limit: 25,
            offset: 0,
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      );
      global.fetch = fetchMock as unknown as typeof fetch;

      const result = await controlPlaneDataProvider.getList("corrections", {
        pagination: { page: 1, perPage: 25 },
        sort: { field: "created_at", order: "DESC" },
        filter: {
          status: "pending",
          correction_type: "field_edit",
          target_entity_type: "commentary_insight",
        },
      });

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const url = fetchMock.mock.calls[0]?.[0] as string;
      expect(url).toContain("/v1/corrections?");
      expect(url).toContain("status=pending");
      expect(url).toContain("correction_type=field_edit");
      expect(url).toContain("target_entity_type=commentary_insight");
      expect(url).toContain("limit=25");
      expect(result.total).toBe(1);
      expect(result.data[0]?.id).toBe("cor_01");
    });

    it("creates a correction via POST /v1/corrections and forwards X-Operator-Id when supplied", async () => {
      const fetchMock = vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            correction_id: "cor_99",
            target_entity_type: "commentary_insight",
            target_entity_id: "ins_01jq7c1ny0ffv8qdr1xwbejqb6",
            correction_type: "field_edit",
            payload: { field: "claim", value: "Sharper claim" },
            original_snapshot: { claim: "Old claim" },
            operator_id: "op_01jqs7p1bcvz2tw5kxh9mq80fg",
            pipeline_run_id: null,
            rationale: "Editor sharpened it.",
            status: "pending",
            created_at: "2026-04-25T09:00:00Z",
            applied_at: null,
          }),
          { status: 201, headers: { "content-type": "application/json" } },
        ),
      );
      global.fetch = fetchMock as unknown as typeof fetch;

      const result = await controlPlaneDataProvider.create("corrections", {
        data: {
          target_entity_type: "commentary_insight",
          target_entity_id: "ins_01jq7c1ny0ffv8qdr1xwbejqb6",
          correction_type: "field_edit",
          payload: { field: "claim", value: "Sharper claim" },
          original_snapshot: { claim: "Old claim" },
          rationale: "Editor sharpened it.",
          operator_id: "op_01jqs7p1bcvz2tw5kxh9mq80fg",
        },
      });

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
      expect(init.method).toBe("POST");
      const headers = init.headers as Record<string, string>;
      expect(headers["X-Operator-Id"]).toBe("op_01jqs7p1bcvz2tw5kxh9mq80fg");
      expect(JSON.parse(init.body as string)).toEqual({
        target_entity_type: "commentary_insight",
        target_entity_id: "ins_01jq7c1ny0ffv8qdr1xwbejqb6",
        correction_type: "field_edit",
        payload: { field: "claim", value: "Sharper claim" },
        original_snapshot: { claim: "Old claim" },
        rationale: "Editor sharpened it.",
      });
      expect(result.data.id).toBe("cor_99");
    });

    it("transitions correction status via PATCH /v1/corrections/{id}", async () => {
      const fetchMock = vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            correction_id: "cor_99",
            target_entity_type: "commentary_insight",
            target_entity_id: "ins_01jq7c1ny0ffv8qdr1xwbejqb6",
            correction_type: "field_edit",
            payload: {},
            original_snapshot: null,
            operator_id: "op_01",
            pipeline_run_id: null,
            rationale: "OK",
            status: "applied",
            created_at: "2026-04-25T09:00:00Z",
            applied_at: "2026-04-25T09:01:00Z",
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      );
      global.fetch = fetchMock as unknown as typeof fetch;

      const result = await controlPlaneDataProvider.update("corrections", {
        id: "cor_99",
        data: { status: "applied", rationale: "OK" },
        previousData: { id: "cor_99", correction_id: "cor_99", status: "pending" },
      });

      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(fetchMock.mock.calls[0]?.[0]).toContain("/v1/corrections/cor_99");
      const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
      expect(init.method).toBe("PATCH");
      expect(JSON.parse(init.body as string)).toEqual({ status: "applied", rationale: "OK" });
      expect(result.data.status).toBe("applied");
    });

    it("filters commentary-insights list query by review_state and document_id", async () => {
      const fetchMock = vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ data: [], total: 0, limit: 25, offset: 0 }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
      global.fetch = fetchMock as unknown as typeof fetch;

      await controlPlaneDataProvider.getList("commentary-insights", {
        pagination: { page: 2, perPage: 25 },
        sort: { field: "updated_at", order: "DESC" },
        filter: { review_state: "machine_verified", document_id: "doc_01" },
      });

      const url = fetchMock.mock.calls[0]?.[0] as string;
      expect(url).toContain("/v1/commentary-insights?");
      expect(url).toContain("review_state=machine_verified");
      expect(url).toContain("document_id=doc_01");
      expect(url).toContain("limit=25");
      expect(url).toContain("offset=25");
    });

    it("fetches a single commentary insight by id", async () => {
      const fetchMock = vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            insight_id: "ins_01",
            document_id: "doc_01",
            document_revision: 1,
            processing_manifest_id: "pm_01",
            section_id: null,
            citation_id: null,
            record_kind: "commentary_insight",
            insight_type: "referenced_provision",
            claim: "x",
            display_text: "x",
            support: [],
            referenced_authorities: [],
            language: "de",
            jurisdiction_id: "jur_ch_federal",
            jurisdiction_ids: ["jur_ch_federal"],
            authority_ids: ["auth_fedlex"],
            source_document_ids: ["doc_01"],
            confidence: 0.5,
            review_state: "machine_verified",
            generator: { name: "x", version: "v1" },
            scores: {},
            metadata: null,
            overlay_revision: 1,
            last_correction_id: null,
            created_at: "2026-04-25T09:00:00Z",
            updated_at: "2026-04-25T09:00:00Z",
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      );
      global.fetch = fetchMock as unknown as typeof fetch;

      const result = await controlPlaneDataProvider.getOne("commentary-insights", {
        id: "ins_01",
      });

      expect(fetchMock.mock.calls[0]?.[0]).toContain("/v1/commentary-insights/ins_01");
      expect(result.data.id).toBe("ins_01");
    });
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

  describe("getCorrectionMetrics (#432)", () => {
    it("fetches the metrics aggregate without query params by default", async () => {
      const fetchMock = vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            window_weeks: 8,
            operator_throughput_window_days: 30,
            weekly_by_target_entity_type: [],
            weekly_by_correction_type: [],
            operator_throughput: [],
            rescore_outcomes: {
              pending: 0,
              applied_total: 0,
              rejected: 0,
              changed: 0,
              unchanged: 0,
              failed: 0,
            },
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      );
      global.fetch = fetchMock as unknown as typeof fetch;

      const result = await controlPlaneActions.getCorrectionMetrics();

      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/platform-control/v1/corrections/metrics");
      expect(result.window_weeks).toBe(8);
    });

    it("forwards window options as query parameters", async () => {
      const fetchMock = vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            window_weeks: 4,
            operator_throughput_window_days: 14,
            weekly_by_target_entity_type: [
              {
                key: "commentary_insight",
                buckets: [
                  { week_start: "2026-04-06", count: 0 },
                  { week_start: "2026-04-13", count: 1 },
                  { week_start: "2026-04-20", count: 2 },
                  { week_start: "2026-04-27", count: 1 },
                ],
              },
            ],
            weekly_by_correction_type: [],
            operator_throughput: [{ operator_id: "op_01", total: 4, applied: 3, rejected: 1 }],
            rescore_outcomes: {
              pending: 0,
              applied_total: 0,
              rejected: 0,
              changed: 0,
              unchanged: 0,
              failed: 0,
            },
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      );
      global.fetch = fetchMock as unknown as typeof fetch;

      const result = await controlPlaneActions.getCorrectionMetrics({
        windowWeeks: 4,
        operatorThroughputWindowDays: 14,
        operatorThroughputTopN: 5,
      });

      const url = fetchMock.mock.calls[0]?.[0] as string;
      expect(url).toContain("/v1/corrections/metrics?");
      expect(url).toContain("window_weeks=4");
      expect(url).toContain("operator_throughput_window_days=14");
      expect(url).toContain("operator_throughput_top_n=5");
      expect(result.weekly_by_target_entity_type[0]?.buckets).toHaveLength(4);
      expect(result.operator_throughput[0]?.total).toBe(4);
    });
  });
});

/**
 * `/v1/reference-data/*` is server-paginated as of #616.
 *
 * This block previously asserted the opposite premise — "unbounded reference
 * lists", the whole table in one response — and so pinned the remaining half of
 * #616 as correct: 2,169 jurisdictions fetched on every list render, with the
 * client windowing them itself.
 *
 * The two callers must both stay right, and they pull in opposite directions:
 * the list views want one server page and the true hit count, while the
 * reference pickers want every jurisdiction or Zürich is unselectable (#666).
 * Raising the picker's `perPage` cannot serve the second, because the server
 * clamps `limit` to 500 and says nothing — which is how #666 happened.
 */
describe("reference-data list pagination (#616)", () => {
  const jurisdictions = Array.from({ length: 2169 }, (_, index) => ({
    jurisdiction_id: `jur_${String(index).padStart(4, "0")}`,
    name: `Jurisdiction ${String(index).padStart(4, "0")}`,
    slug: `jur-${index}`,
  }));

  /** A fetch mock that honours `limit`/`offset` the way the API does. */
  const mockPagedJurisdictions = () =>
    vi.fn().mockImplementation((url: string) => {
      const query = new URL(url, "http://localhost").searchParams;
      const limit = Number(query.get("limit") ?? "100");
      const offset = Number(query.get("offset") ?? "0");
      return Promise.resolve(
        new Response(
          JSON.stringify({
            data: jurisdictions.slice(offset, offset + limit),
            total: jurisdictions.length,
            limit,
            offset,
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      );
    });

  it("requests one server page for a list view and trusts the server total", async () => {
    const fetchMock = mockPagedJurisdictions();
    global.fetch = fetchMock as unknown as typeof fetch;

    const result = await controlPlaneDataProvider.getList("jurisdictions", {
      pagination: { page: 2, perPage: 50 },
      sort: { field: "name", order: "ASC" },
      filter: {},
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "/api/platform-control/v1/reference-data/jurisdictions?limit=50&offset=50",
    );
    expect(result.data).toHaveLength(50);
    // The hit count, not the page length — the #616 assertion.
    expect(result.total).toBe(2169);
    expect(result.data[0].jurisdiction_id).toBe("jur_0050");
  });

  it("pages the whole collection out when the picker asks for everything", async () => {
    const fetchMock = mockPagedJurisdictions();
    global.fetch = fetchMock as unknown as typeof fetch;

    const result = await controlPlaneDataProvider.getList("jurisdictions", {
      pagination: { page: 1, perPage: 25_000 },
      sort: { field: "name", order: "ASC" },
      filter: {},
    });

    // 2169 rows at 500 per request: four full pages plus a short one.
    expect(fetchMock).toHaveBeenCalledTimes(5);
    expect(result.total).toBe(2169);
    expect(result.data).toHaveLength(2169);
    // #666: the last jurisdiction must be reachable, not truncated at 500.
    expect(result.data.map((record) => record.jurisdiction_id)).toContain("jur_2168");
  });

  it("resolves getMany ids from beyond the first server page", async () => {
    const fetchMock = mockPagedJurisdictions();
    global.fetch = fetchMock as unknown as typeof fetch;

    // There is no by-id endpoint, so this must page out rather than read page 1.
    const result = await controlPlaneDataProvider.getMany("jurisdictions", {
      ids: ["jur_0001", "jur_2168"],
    });

    expect(result.data.map((record) => record.jurisdiction_id)).toEqual(["jur_0001", "jur_2168"]);
  });

  /**
   * A server that ignores `limit` must not spin the paging loop forever. The
   * loop continues only on an exactly-full page, so an over-full one stops it.
   */
  it("terminates when the server ignores limit and returns everything", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ data: jurisdictions }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    global.fetch = fetchMock as unknown as typeof fetch;

    const result = await controlPlaneDataProvider.getList("jurisdictions", {
      pagination: { page: 1, perPage: 25_000 },
      sort: { field: "name", order: "ASC" },
      filter: {},
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(result.data).toHaveLength(2169);
  });
});

import type { Page, Route } from "@playwright/test";

type JsonBody = Record<string, unknown> | Array<unknown>;

const API_PREFIX = "/api/platform-control";

async function fulfillJson(route: Route, body: JsonBody, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

export async function mockAdminRunFlowApi(page: Page) {
  await page.route("**/api/platform-control/**", async (route) => {
    const requestUrl = new URL(route.request().url());
    const apiPath = requestUrl.pathname.replace(API_PREFIX, "");

    if (apiPath === "/v1/runs") {
      await fulfillJson(route, {
        data: [
          {
            run_id: "run_01",
            source_id: "src_01",
            source_version_id: "sv_01",
            mode: "production",
            status: "running",
            started_at: "2026-04-06T10:00:00Z",
            completed_at: null,
            artifacts_count: 3,
            captured_resources_count: 3,
            failure_reason: null,
            created_at: "2026-04-06T10:00:00Z",
            updated_at: "2026-04-06T10:02:00Z",
            source_name: "Swiss Federal Court",
            version_label: "2026.04.06",
          },
        ],
      });
      return;
    }

    if (apiPath === "/v1/sources") {
      await fulfillJson(route, {
        data: [
          {
            source_id: "src_01",
            name: "Swiss Federal Court",
            description: "Mocked source for screenshot evidence",
            jurisdiction_id: "jur_ch",
            authority_id: "auth_bger",
            source_type: "website",
            document_family: null,
            status: "active",
            created_at: "2026-04-06T09:00:00Z",
            updated_at: "2026-04-06T09:00:00Z",
          },
        ],
      });
      return;
    }

    if (apiPath === "/v1/sources/src_01/versions") {
      await fulfillJson(route, {
        data: [
          {
            source_version_id: "sv_03",
            source_id: "src_01",
            extractor_profile_id: null,
            version_label: "2026.04.06",
            status: "approved",
            acquisition_spec: {
              seed_url: null,
              seed_urls: [],
              mode: "crawl",
              include_paths: [],
              exclude_paths: [],
              limit: 25,
              max_discovery_depth: 2,
              scrape_formats: ["markdown", "html"],
              zero_data_retention: false,
            },
            created_at: "2026-04-06T09:20:00Z",
            updated_at: "2026-04-06T09:20:00Z",
          },
          {
            source_version_id: "sv_02",
            source_id: "src_01",
            extractor_profile_id: null,
            version_label: "2026.03.28",
            status: "pending_approval",
            acquisition_spec: {
              seed_url: null,
              seed_urls: [],
              mode: "crawl",
              include_paths: ["/de/jurisprudence/"],
              exclude_paths: ["/static/"],
              limit: 50,
              max_discovery_depth: 3,
              scrape_formats: ["markdown"],
              zero_data_retention: false,
            },
            created_at: "2026-03-28T14:00:00Z",
            updated_at: "2026-03-30T11:15:00Z",
          },
          {
            source_version_id: "sv_01",
            source_id: "src_01",
            extractor_profile_id: null,
            version_label: "2026.03.15",
            status: "draft",
            acquisition_spec: {
              seed_url: null,
              seed_urls: [],
              mode: "crawl",
              include_paths: [],
              exclude_paths: [],
              limit: 10,
              max_discovery_depth: 1,
              scrape_formats: ["html"],
              zero_data_retention: true,
            },
            created_at: "2026-03-15T08:30:00Z",
            updated_at: "2026-03-15T08:30:00Z",
          },
        ],
      });
      return;
    }

    if (apiPath === "/v1/runs/readiness") {
      await fulfillJson(route, {
        source_id: "src_01",
        source_version_id: "sv_01",
        mode: "production",
        ready: false,
        checks: [
          {
            code: "mode_compatible_with_version_status",
            ok: false,
            detail: "Production mode requires an approved source version.",
          },
        ],
      });
      return;
    }

    if (apiPath === "/v1/runs/run_01") {
      await fulfillJson(route, {
        run_id: "run_01",
        source_id: "src_01",
        source_version_id: "sv_01",
        mode: "production",
        status: "running",
        started_at: "2026-04-06T10:00:00Z",
        completed_at: null,
        artifacts_count: 3,
        captured_resources_count: 3,
        failure_reason: null,
        created_at: "2026-04-06T10:00:00Z",
        updated_at: "2026-04-06T10:02:00Z",
      });
      return;
    }

    if (
      apiPath === "/v1/runs/run_01/pipeline-health" ||
      apiPath === "/v1/runs/run_02/pipeline-health" ||
      apiPath === "/v1/runs/run_03/pipeline-health"
    ) {
      const runId = apiPath.split("/")[3];
      await fulfillJson(route, {
        run_id: runId,
        source_id: "src_01",
        source_version_id: "sv_01",
        mode: "production",
        run_status: "running",
        overall_status: "in_progress",
        stages: [
          {
            stage: "acquisition",
            status: "ok",
            detail: "Acquisition completed successfully.",
            updated_at: "2026-04-06T10:01:00Z",
          },
          {
            stage: "document_intelligence",
            status: "in_progress",
            detail: "DI ingestion is processing pages.",
            updated_at: "2026-04-06T10:02:00Z",
          },
          {
            stage: "projection",
            status: "pending",
            detail: "Projection awaits DI completion.",
            updated_at: null,
          },
          {
            stage: "search",
            status: "pending",
            detail: "Search publish waits for projection updates.",
            updated_at: null,
          },
        ],
        processing_status_event_count: 2,
        document_lifecycle_event_count: 1,
      });
      return;
    }

    const runSubResourceMatch = apiPath.match(
      /^\/v1\/runs\/run_\d+\/(provider-jobs|captured-resources|raw-artifacts|processing-status|document-lifecycle)$/,
    );
    if (runSubResourceMatch) {
      await fulfillJson(route, {
        data: [],
        total: 0,
        limit: Number(requestUrl.searchParams.get("limit") ?? "100"),
        offset: Number(requestUrl.searchParams.get("offset") ?? "0"),
      });
      return;
    }

    if (apiPath === "/v1/sources/src_01") {
      await fulfillJson(route, {
        source_id: "src_01",
        name: "Swiss Federal Court",
        description:
          "Official publication platform for decisions of the Swiss Federal Court (Bundesgericht / Tribunal fédéral).",
        jurisdiction_id: "jur_ch",
        authority_id: "auth_bger",
        source_type: "website",
        document_family: null,
        status: "active",
        created_at: "2026-03-15T08:00:00Z",
        updated_at: "2026-04-06T09:00:00Z",
      });
      return;
    }

    if (apiPath === "/v1/reference-data/jurisdictions") {
      await fulfillJson(route, {
        data: [
          {
            jurisdiction_id: "jur_ch",
            name: "Switzerland",
            slug: "ch",
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
          },
        ],
      });
      return;
    }

    if (apiPath === "/v1/reference-data/authorities") {
      await fulfillJson(route, {
        data: [
          {
            authority_id: "auth_bger",
            jurisdiction_id: "jur_ch",
            name: "Bundesgericht",
            slug: "bger",
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
          },
        ],
      });
      return;
    }

    if (apiPath === "/stats") {
      await fulfillJson(route, {
        source_count: 4,
        total_runs: 12,
        run_by_status: {
          completed: 8,
          running: 1,
          failed: 2,
          pending: 1,
        },
        total_artifacts: 1847,
        recent_runs: [
          {
            run_id: "run_01",
            status: "running",
            artifacts_count: 3,
            created_at: "2026-04-06T10:00:00Z",
            completed_at: null,
          },
          {
            run_id: "run_02",
            status: "completed",
            artifacts_count: 247,
            created_at: "2026-04-05T14:30:00Z",
            completed_at: "2026-04-05T15:12:00Z",
          },
          {
            run_id: "run_03",
            status: "failed",
            artifacts_count: 0,
            created_at: "2026-04-04T09:00:00Z",
            completed_at: "2026-04-04T09:02:00Z",
          },
        ],
      });
      return;
    }

    await route.fallback();
  });
}

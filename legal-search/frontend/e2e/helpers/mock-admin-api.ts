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
  // One warning per distinct unmocked path per page — react-admin retries and
  // refetches, so warning per request would bury the signal it exists to give.
  const warnedPaths = new Set<string>();

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

    if (apiPath === "/v1/corrections/metrics") {
      await fulfillJson(route, {
        window_weeks: 8,
        operator_throughput_window_days: 30,
        weekly_by_target_entity_type: [],
        weekly_by_correction_type: [],
        operator_throughput: [],
        rescore_outcomes: {
          pending: 0,
          applied_total: 9,
          rejected: 0,
          changed: 0,
          unchanged: 5,
          failed: 4,
        },
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

    // #693 gave the admin a Blueprints resource, and `SourceCreate` calls
    // `listSourceBlueprintTemplates()` on mount. Without a branch here the
    // request fell through to `route.fallback()` below, was proxied to a
    // platform-control the screenshot harness never starts, and surfaced as
    // `ECONNREFUSED 127.0.0.1:8000` in the shared WebServer log — where it sat
    // next to an unrelated failure and got read as its cause (#732).
    //
    // The three rows cover the states ADR-0030's two-key lock can be in, so a
    // screenshot of this surface shows the lock rather than one happy row:
    // shipped-default enabled, shipped-default disabled (fail-closed), and an
    // operator override. `launchable` is always `enabled && live_ready`.
    if (apiPath === "/v1/sources/blueprint-templates") {
      await fulfillJson(route, {
        data: [
          {
            overlay_id: "at",
            provider_template_id: "ris_ogd_bundesrecht",
            provider: "ris_ogd",
            enabled: true,
            live_ready: true,
            launchable: true,
            default_enabled: true,
            source: "default",
            notes: [],
            note: null,
            updated_by: null,
            updated_at: null,
          },
          {
            overlay_id: "ch",
            provider_template_id: "fedlex_sparql_federal",
            provider: "fedlex_sparql",
            // Config key off while the code key is on: the fail-closed default
            // is the only thing standing between an operator and this run.
            enabled: false,
            live_ready: true,
            launchable: false,
            default_enabled: false,
            source: "default",
            notes: [],
            note: null,
            updated_by: null,
            updated_at: null,
          },
          {
            overlay_id: "de",
            provider_template_id: "gesetze_im_internet",
            provider: "gemeinde_http",
            enabled: true,
            live_ready: false,
            launchable: false,
            default_enabled: false,
            source: "override",
            notes: [],
            note: "Enabled after acceptance-run evidence.",
            // Key-shaped, never person-shaped — see describeProvenance in
            // platform-control/admin/src/domain/blueprintLock.ts.
            updated_by: "op_scoped_operator_key",
            updated_at: "2026-04-06T09:30:00Z",
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

    // Falling back proxies to a platform-control the harness does not start, so
    // an unmocked admin endpoint becomes `ECONNREFUSED` in the WebServer log
    // rather than anything that names itself. That is how #693's new endpoint
    // stayed invisible and then got blamed for an unrelated test failure
    // (#732). The fallback is kept — some paths legitimately pass through —
    // but it no longer does so silently.
    const signature = `${route.request().method()} ${apiPath}`;
    if (!warnedPaths.has(signature)) {
      warnedPaths.add(signature);
      console.warn(
        `[mock-admin-api] no branch for ${signature} — falling through to the real ` +
          "backend, which the screenshot harness does not run. Add a branch in " +
          "legal-search/frontend/e2e/helpers/mock-admin-api.ts.",
      );
    }
    await route.fallback();
  });
}

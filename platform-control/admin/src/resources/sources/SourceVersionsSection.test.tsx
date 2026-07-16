/**
 * Render coverage for the unknown-provider guard in the source-version editor.
 *
 * The API serves eleven acquisition providers; this dialog has widgets for four
 * (`PROVIDER_CHOICES`). Opening Edit on one of the other seven used to render
 * the firecrawl fields and — because every firecrawl default is valid — save a
 * silently rewritten spec, losing the field that defines the source
 * (`canton_code`). Proves the dialog now refuses to edit what it cannot model
 * and shows the spec read-only instead (#614).
 */
import { QueryClient } from "@tanstack/react-query";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { CoreAdminContext, testDataProvider } from "ra-core";
import { describe, expect, it } from "vitest";
import type {
  AcquisitionSpec,
  SourceRecord,
  SourceVersionRecord,
} from "../../lib/admin/dataProvider";
import { SourceVersionsSection } from "./SourceVersionsSection";

const source: SourceRecord = {
  id: "src_zh",
  source_id: "src_zh",
  name: "Kanton Zürich",
  description: null,
  jurisdiction_id: "jur_ch_zh",
  authority_id: "auth_zh",
  source_type: "website",
  document_family: null,
  status: "active",
  created_at: "2026-05-01T09:00:00Z",
  updated_at: "2026-05-01T09:00:00Z",
};

/** A real canton_http spec — a provider this form has no widgets for. */
const cantonVersion: SourceVersionRecord = {
  id: "sv_zh",
  source_version_id: "sv_zh",
  source_id: "src_zh",
  extractor_profile_id: null,
  version_label: "v1",
  status: "draft",
  acquisition_spec: {
    provider: "canton_http",
    canton_code: "CH-ZH",
    seed_url: "https://www.zh.ch/de/politik-staat/gesetze-beschluesse.html",
    seed_urls: [],
  } as unknown as AcquisitionSpec,
  created_at: "2026-05-01T09:00:00Z",
  updated_at: "2026-05-01T09:00:00Z",
};

function renderSection() {
  const dataProvider = testDataProvider({
    getList: (async () => ({ data: [cantonVersion], total: 1 })) as unknown as ReturnType<
      typeof testDataProvider
    >["getList"],
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  return render(
    <CoreAdminContext dataProvider={dataProvider} queryClient={queryClient}>
      <SourceVersionsSection source={source} />
    </CoreAdminContext>,
  );
}

describe("SourceVersionsSection — unknown acquisition provider", () => {
  it("summarizes the version from its own fields rather than firecrawl's", async () => {
    const { container } = renderSection();

    await waitFor(() => {
      expect(container.textContent).toContain("provider: canton_http");
    });

    expect(container.textContent).toContain("canton_code: CH-ZH");
    expect(container.textContent).not.toContain("mode: undefined");
  });

  it("shows the spec read-only in the edit dialog instead of firecrawl fields", async () => {
    const { container, getByRole, queryByLabelText, findByText } = renderSection();

    await waitFor(() => {
      expect(container.textContent).toContain("v1");
    });
    fireEvent.click(getByRole("button", { name: "Edit" }));

    await findByText("This acquisition spec is read-only.");
    // The provider select and its firecrawl fields are what rewrote the spec.
    expect(queryByLabelText("Provider")).toBeNull();
    expect(queryByLabelText("Mode")).toBeNull();
    // The version label stays editable — only the spec is frozen.
    expect(queryByLabelText("Version label")).not.toBeNull();
  });
});

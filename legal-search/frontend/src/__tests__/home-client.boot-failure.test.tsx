/**
 * HomeClient — boot failure (#678)
 *
 * A *rejected* boot request (network/DNS/CORS failure, aborted request) used to
 * be swallowed by `void load()`: `bootState` stayed null and the loading
 * skeleton rendered forever, which is indistinguishable from a slow network. It
 * must instead surface as an error so `app/error.tsx` can render a real state.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import { Component, type ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import HomeClient from "@/app/HomeClient";
import { MESSAGES } from "@/i18n/messages";

const getSearchContext = vi.fn();
const searchDocuments = vi.fn();

vi.mock("@/lib/api/generated/client", () => ({
  getSearchContext: (...args: unknown[]) => getSearchContext(...args),
  searchDocuments: (...args: unknown[]) => searchDocuments(...args),
}));

// The desktop workspace mounts react-resizable-panels, which needs real layout
// and cannot mount under jsdom ("Group … not found"). This suite is about what
// HomeClient does with the boot result, so stub the rendered workspace.
vi.mock("@/app/WorkspaceClient", () => ({
  default: () => <div data-testid="workspace" />,
}));

class CatchBoundary extends Component<{ children: ReactNode }, { message: string | null }> {
  state = { message: null as string | null };

  static getDerivedStateFromError(error: Error) {
    return { message: error.message };
  }

  render() {
    if (this.state.message) {
      return <div data-testid="boundary">{this.state.message}</div>;
    }
    return this.props.children;
  }
}

function renderHome() {
  return render(
    <NuqsTestingAdapter searchParams={{}}>
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <NextIntlClientProvider locale="de" messages={MESSAGES.de}>
          <CatchBoundary>
            <HomeClient showControlPlaneEntry={false} />
          </CatchBoundary>
        </NextIntlClientProvider>
      </QueryClientProvider>
    </NuqsTestingAdapter>,
  );
}

describe("HomeClient boot failure", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // React logs the re-thrown error via the boundary; keep test output readable.
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  it("surfaces a rejected boot to the error boundary instead of hanging on the skeleton", async () => {
    getSearchContext.mockRejectedValue(new Error("Failed to fetch"));
    searchDocuments.mockRejectedValue(new Error("Failed to fetch"));

    renderHome();

    await waitFor(() => {
      expect(screen.getByTestId("boundary")).toHaveTextContent("Failed to fetch");
    });
  });

  it("still degrades to an empty workspace on a non-200 response", async () => {
    getSearchContext.mockResolvedValue({ status: 500, data: {} });
    searchDocuments.mockResolvedValue({ status: 500, data: {} });

    renderHome();

    // Non-200 is a handled, non-error path: the skeleton clears into an empty
    // workspace rather than escalating to the error boundary.
    await waitFor(() => {
      expect(screen.getByTestId("workspace")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("boundary")).not.toBeInTheDocument();
  });
});

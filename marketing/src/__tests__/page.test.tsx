import { REPOSITORY_URL } from "@evidara/shell";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { describe, expect, it } from "vitest";
import Home from "@/app/page";
import { CAPABILITIES, NOT_YET } from "@/lib/content";

describe("waitlist page", () => {
  it("has no detectable accessibility violations", async () => {
    const { container } = render(<Home />);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("has exactly one h1 and no skipped heading levels", () => {
    render(<Home />);

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);

    const levels = screen.getAllByRole("heading").map((h) => Number(h.tagName.slice(1)));

    // Walking the document order, a heading may go one level deeper at a
    // time but may jump back out any number of levels.
    for (let i = 1; i < levels.length; i++) {
      expect(levels[i]).toBeLessThanOrEqual(levels[i - 1] + 1);
    }
  });

  /**
   * This is a product decision with a test behind it, not a style nit.
   *
   * Search has unmerged correctness fixes (#672 deep links return no results,
   * #673 official_only=false silently narrows, #675 empty facets) and there is
   * no end-user authentication — both UIs sit behind one shared BasicAuth
   * password. Linking a stranger into that is the failure mode this page
   * exists to avoid. When ADR-0038 (#676) lands and there is a real
   * design-partner flow, delete this test deliberately.
   */
  it("links to no live product surface", () => {
    render(<Home />);

    const hrefs = screen.queryAllByRole("link").map((link) => link.getAttribute("href") ?? "");

    for (const href of hrefs) {
      expect(href).not.toMatch(/search\.evidara|admin\.evidara/);
    }
    expect(screen.queryByRole("link", { name: /try|demo|log ?in|sign ?in/i })).toBeNull();
  });

  /**
   * AGPL-3.0 section 13: anyone interacting with this software over a network
   * must be offered its source. This page is served over a network, so the
   * footer link is a licence obligation rather than decoration — delete
   * `<RepositoryLink>` from `page.tsx` and this test goes red, which is the
   * whole point of it existing.
   *
   * Note the tension with the test above, and that it is real rather than
   * accidental: this page links to *source*, never to a running deployment.
   * The assertions below pin the distinction so a future edit cannot quietly
   * turn one into the other.
   *
   * The drawn-path check mirrors `legal-search/frontend`'s (#995): an icon that
   * resolves to `undefined` renders an empty anchor, which satisfies "a link
   * exists" while showing the user nothing.
   */
  it("offers its source, as AGPL section 13 requires", () => {
    render(<Home />);

    const link = screen.getByRole("link", { name: /source code on github/i });

    expect(link).toHaveAttribute("href", REPOSITORY_URL);
    expect(link).toHaveAttribute("target", "_blank");

    const rel = link.getAttribute("rel") ?? "";
    expect(rel).toContain("noopener");
    expect(rel).toContain("noreferrer");

    const path = link.querySelector("svg path");
    expect(path).not.toBeNull();
    expect(path?.getAttribute("d") ?? "").not.toHaveLength(0);
  });

  it("renders every capability and every stated limitation", () => {
    render(<Home />);

    for (const claim of [...CAPABILITIES, ...NOT_YET]) {
      expect(
        screen.getByRole("heading", { name: claim.title }),
        `claim ${claim.id} is missing from the page`,
      ).toBeInTheDocument();
    }
  });

  it("states the limitations section — the page must never ship as capabilities-only", () => {
    render(<Home />);
    expect(screen.getByRole("heading", { name: /what it does not do yet/i })).toBeInTheDocument();
    expect(NOT_YET.length).toBeGreaterThanOrEqual(4);
  });
});

describe("waitlist form", () => {
  it("labels every visible control", () => {
    render(<Home />);
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/what you work on/i)).toBeInTheDocument();
  });

  it("keeps the honeypot out of the accessibility tree and the tab order", () => {
    const { container } = render(<Home />);
    const honeypot = container.querySelector('input[name="company_website"]');

    expect(honeypot).not.toBeNull();
    expect(honeypot?.closest("[aria-hidden='true']")).not.toBeNull();
    expect(honeypot).toHaveAttribute("tabindex", "-1");
    // A screen-reader user must never be offered it. `queryByRole` honours
    // aria-hidden (unlike `queryByLabelText`), so this asserts absence from
    // the accessibility tree rather than absence from the DOM.
    expect(screen.queryByRole("textbox", { name: /company website/i })).toBeNull();
  });

  it("reports an invalid address without submitting", async () => {
    const user = userEvent.setup();
    render(<Home />);

    await user.type(screen.getByLabelText(/email address/i), "not-an-email");
    await user.click(screen.getByRole("button", { name: /join the waitlist/i }));

    const email = screen.getByLabelText(/email address/i);
    expect(email).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText(/enter a valid email address/i)).toBeInTheDocument();
  });

  it("does not scold before the first submit attempt", async () => {
    const user = userEvent.setup();
    render(<Home />);

    await user.type(screen.getByLabelText(/email address/i), "partial@");

    expect(screen.queryByText(/enter a valid email address/i)).toBeNull();
  });

  it("says signups are not open when no store is configured, rather than faking success", async () => {
    // No NEXT_PUBLIC_WAITLIST_ENDPOINT is set in the test env — the same
    // state the page ships in today.
    const user = userEvent.setup();
    render(<Home />);

    await user.type(screen.getByLabelText(/email address/i), "someone@firm.example");
    await user.click(screen.getByRole("button", { name: /join the waitlist/i }));

    const status = await screen.findByRole("status");
    expect(within(status).getByText(/signups are not open yet/i)).toBeInTheDocument();
    // Crucially, it must NOT claim to have stored the address.
    expect(screen.queryByText(/we have your address/i)).toBeNull();
  });

  it("is reachable by keyboard alone", async () => {
    const user = userEvent.setup();
    render(<Home />);

    await user.tab();
    // Nothing before the email field should trap focus; walk until we reach it.
    const email = screen.getByLabelText(/email address/i);
    for (let i = 0; i < 10 && document.activeElement !== email; i++) {
      await user.tab();
    }
    expect(document.activeElement).toBe(email);

    await user.tab();
    expect(document.activeElement).toBe(screen.getByLabelText(/what you work on/i));

    // The honeypot must be skipped: next stop is the submit button.
    await user.tab();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: /join the waitlist/i }));
  });
});

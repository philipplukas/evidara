import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it } from "vitest";
import { ResultsControlRegion } from "@/components/results/ResultsControlRegion";
import { MESSAGES } from "@/i18n/messages";

describe("ResultsControlRegion", () => {
  it("exposes a localized region landmark for result controls", () => {
    render(
      <NextIntlClientProvider locale="de" messages={MESSAGES.de}>
        <ResultsControlRegion>
          <span>child</span>
        </ResultsControlRegion>
      </NextIntlClientProvider>,
    );

    expect(
      screen.getByRole("region", { name: "Suchergebnisse und Steuerelemente" }),
    ).toBeInTheDocument();
    expect(screen.getByText("child")).toBeInTheDocument();
  });
});

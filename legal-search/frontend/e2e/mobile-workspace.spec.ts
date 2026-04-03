import { expect, test } from "@playwright/test";
import { mockSearchApi } from "./helpers/mock-api";

test.describe("Mobile workspace interactions", () => {
  test.use({ viewport: { width: 430, height: 932 } });

  test("opens and closes filters sheet", async ({ page }) => {
    await mockSearchApi(page);
    await page.goto("/");

    await page.getByRole("button", { name: "Filters" }).click();
    await expect(page.getByRole("heading", { name: "Filters" })).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(page.getByRole("heading", { name: "Filters" })).not.toBeVisible();
  });

  test("opens and closes detail sheet from result tap", async ({ page }) => {
    await mockSearchApi(page);
    await page.goto("/");

    await page.getByText("Result for Bundesgericht").click();
    await expect(page).toHaveURL(/item=decision-1/);
    await expect(page.getByRole("heading", { name: "Mocked detail title" }).last()).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(
      page.getByRole("heading", { name: "Mocked detail title" }).last(),
    ).not.toBeVisible();
  });
});

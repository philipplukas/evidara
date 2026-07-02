import type { Page } from "@playwright/test";

/**
 * react-resizable-panels can leave the desktop detail panel at sub-`minSize`
 * width in headless Playwright after navigation/tab switches even though the
 * product fix (`resize(32)` in WorkspaceClient) works in real browsers. The
 * race is most reproducible when the detail surface is opened via URL state
 * (`?item=…`) instead of a click — the SSR-hydrated panel boots at width 0
 * and the imperative `resize(32)` from `useEffect` lands after the screenshot
 * settles.
 *
 * This helper forces the panel to ~40% via direct flex manipulation; it's a
 * no-op when the panel is already wide enough. Mirrors the equivalent
 * workaround in `screenshot-pack.spec.ts` so visual baselines and screenshot
 * captures stay framed identically.
 */
export async function forceExpandDetailPanel(page: Page) {
  await page.evaluate(() => {
    const el = document.querySelector('[data-testid="detail-panel"]');
    const panelDiv = el?.parentElement?.parentElement as HTMLElement | null;
    if (!panelDiv?.hasAttribute("data-panel")) return;
    const currentFlex = Number.parseFloat(panelDiv.style.flex) || 0;
    if (currentFlex >= 20) return;
    panelDiv.style.flex = "40 1 0px";
    const group = panelDiv.parentElement;
    if (!group) return;
    for (const sib of Array.from(group.children)) {
      const s = sib as HTMLElement;
      if (s.hasAttribute("data-panel") && s !== panelDiv) {
        const current = Number.parseFloat(s.style.flex) || 50;
        s.style.flex = `${current * 0.5} 1 0px`;
      }
    }
  });
  await page.waitForTimeout(100);
}

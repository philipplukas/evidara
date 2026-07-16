import type { Page } from "@playwright/test";

/**
 * Ensures the desktop detail panel is at a readable width before a visual
 * capture.
 *
 * Historically the panel opened as a ~32px sliver, mis-attributed here to a
 * headless-Playwright "race" — it was actually the react-resizable-panels v4
 * units bug: WorkspaceClient passed bare numbers (`resize(32)`, `minSize={25}`),
 * which v4 reads as PIXELS, so the panel was 32px in *every* browser, not just
 * headless. That is now fixed (percent strings), so the panel opens at ~32% on
 * its own and this helper is a defensive no-op whenever it is already ≥20% wide.
 *
 * Kept (as a no-op guard) so that if a future units regression shrinks the
 * panel again, visual baselines still frame consistently rather than silently
 * capturing a sliver. The real guard is the width assertion in
 * `workspace-panels.spec.ts`.
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

// Drive the platform-control admin panel and verify list/table behaviour.
//
// Prereqs: admin running (prod build) on http://localhost:3000, backend on :8000.
// Playwright is a dep of platform-control/admin (chromium is cached). Because this
// script lives outside that package, import Playwright by ABSOLUTE path (CommonJS
// default import) — ESM won't resolve a bare `playwright` from here.
//
// Usage: node .claude/skills/run-admin-panel/drive.mjs
// Edit ADMIN_DIR if the repo/worktree path differs, and OUT for screenshot output.

import { createRequire } from "node:module";
import path from "node:path";

const ADMIN_DIR =
  process.env.ADMIN_DIR ||
  path.resolve(process.cwd(), "platform-control/admin");
const OUT = process.env.OUT || "/tmp";
const BASE = process.env.BASE || "http://localhost:3000";

const require = createRequire(path.join(ADMIN_DIR, "package.json"));
const { chromium } = require("playwright");

const steps = [
  { hash: "#/jurisdictions", name: "jurisdictions" },
  { hash: "#/authorities", name: "authorities" },
  { hash: "#/runs-v2", name: "runs-v2" },
  { hash: "#/sources", name: "sources" },
];

const results = [];
const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
const page = await ctx.newPage();
page.on("pageerror", (e) => results.push({ pageerror: String(e) }));

for (const step of steps) {
  const rec = { step: step.name, url: `${BASE}/${step.hash}` };
  try {
    await page.goto(`${BASE}/${step.hash}`, { waitUntil: "domcontentloaded", timeout: 20000 });
    await page.waitForSelector("table, h1", { timeout: 20000 });
    await page.waitForTimeout(1500);
    rec.info = await page.evaluate(() => {
      const bodyText = document.body.innerText;
      const table = document.querySelector("table");
      let scroll = null;
      if (table) {
        const wrap = table.parentElement;
        scroll = {
          tableClass: table.className,
          wrapClass: wrap?.className ?? null,
          wrapScrollW: wrap?.scrollWidth ?? null,
          wrapClientW: wrap?.clientWidth ?? null,
          overflows: wrap ? wrap.scrollWidth > wrap.clientWidth + 1 : null,
          rowCount: table.querySelectorAll("tbody tr").length,
          headers: [...table.querySelectorAll("thead th")].map((th) => th.innerText.trim()),
        };
      }
      const caption = (bodyText.match(/\n\s*(\d[\d,]*\s+(jurisdiction|authorit|source)\w*)/i) || [])[1] || null;
      const pager = (bodyText.match(/Page\s+\d+\s+of\s+\d+[^\n]*/i) || [])[0] || null;
      return { caption, pager, scroll };
    });
    await page.screenshot({ path: `${OUT}/shot-${step.name}.png` });
    rec.ok = true;
  } catch (e) {
    rec.ok = false;
    rec.error = String(e).split("\n")[0];
  }
  results.push(rec);
}

// Pagination smoke: Next on jurisdictions advances the page.
try {
  await page.goto(`${BASE}/#/jurisdictions`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("table", { timeout: 15000 });
  await page.waitForTimeout(1200);
  const pager = () => page.evaluate(() => (document.body.innerText.match(/Page\s+\d+\s+of\s+\d+/i) || [null])[0]);
  const before = await pager();
  await page.getByRole("button", { name: /next/i }).click();
  await page.waitForTimeout(1000);
  const after = await pager();
  results.push({ paginationCheck: { before, after, advanced: before !== after } });
} catch (e) {
  results.push({ paginationCheck: { error: String(e).split("\n")[0] } });
}

console.log(JSON.stringify(results, null, 2));
await browser.close();

import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

import { JSDOM } from "jsdom";

const DEFAULT_ROOTS = ["docs", "legal-search/frontend/docs"];
const MARKDOWN_SUFFIX = ".md";

function createDom() {
  const dom = new JSDOM("<body></body>", { pretendToBeVisual: true });

  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.Element = dom.window.Element;
  globalThis.HTMLElement = dom.window.HTMLElement;
  globalThis.SVGElement = dom.window.SVGElement;
  globalThis.Node = dom.window.Node;
  globalThis.DOMParser = dom.window.DOMParser;
  globalThis.XMLSerializer = dom.window.XMLSerializer;
  globalThis.MutationObserver = dom.window.MutationObserver;
  globalThis.getComputedStyle = dom.window.getComputedStyle.bind(dom.window);
  globalThis.requestAnimationFrame = dom.window.requestAnimationFrame.bind(dom.window);
  globalThis.cancelAnimationFrame = dom.window.cancelAnimationFrame.bind(dom.window);
  globalThis.performance = dom.window.performance;
  Object.defineProperty(globalThis, "navigator", {
    value: dom.window.navigator,
    configurable: true,
  });

  if (!dom.window.SVGElement.prototype.getBBox) {
    dom.window.SVGElement.prototype.getBBox = function getBBox() {
      const widthAttr = Number.parseFloat(this.getAttribute("width") ?? "0");
      const heightAttr = Number.parseFloat(this.getAttribute("height") ?? "0");
      const text = this.textContent ?? "";
      const lineCount = text.split("\n").filter(Boolean).length || 1;
      const width = widthAttr || Math.max(text.length * 8, 16);
      const height = heightAttr || Math.max(lineCount * 16, 16);
      return { x: 0, y: 0, width, height };
    };
  }

  if (!dom.window.SVGElement.prototype.getComputedTextLength) {
    dom.window.SVGElement.prototype.getComputedTextLength = function getComputedTextLength() {
      return Math.max((this.textContent ?? "").length * 8, 16);
    };
  }

  return dom;
}

async function collectMarkdownFiles(targets) {
  const files = [];

  for (const target of targets) {
    const resolved = path.resolve(target);
    let entries;

    try {
      entries = await readdir(resolved, { withFileTypes: true });
    } catch (error) {
      if (error && error.code === "ENOENT") {
        continue;
      }
      throw error;
    }

    for (const entry of entries) {
      const entryPath = path.join(resolved, entry.name);

      if (entry.isDirectory()) {
        files.push(...(await collectMarkdownFiles([entryPath])));
        continue;
      }

      if (entry.isFile() && entry.name.endsWith(MARKDOWN_SUFFIX)) {
        files.push(entryPath);
      }
    }
  }

  return files.sort();
}

function extractMermaidBlocks(source) {
  const blocks = [];
  const lines = source.split("\n");
  let index = 0;

  while (index < lines.length) {
    if (!lines[index].startsWith("```mermaid")) {
      index += 1;
      continue;
    }

    const startLine = index + 1;
    index += 1;
    const blockLines = [];

    while (index < lines.length && lines[index] !== "```") {
      blockLines.push(lines[index]);
      index += 1;
    }

    if (index === lines.length) {
      blocks.push({
        code: blockLines.join("\n"),
        line: startLine,
        unterminated: true,
      });
      break;
    }

    blocks.push({
      code: blockLines.join("\n"),
      line: startLine,
      unterminated: false,
    });
    index += 1;
  }

  return blocks;
}

function formatErrorMessage(error) {
  if (error instanceof Error && error.message) {
    return error.message.trim();
  }

  return String(error);
}

async function validateDiagram(mermaid, code, id) {
  await mermaid.parse(code, { suppressErrors: false });

  const container = document.createElement("div");
  document.body.append(container);

  try {
    await mermaid.render(id, code, container);
  } finally {
    container.remove();
  }
}

async function main() {
  const targets = process.argv.slice(2);
  const markdownFiles =
    targets.length > 0 ? targets.map((target) => path.resolve(target)) : await collectMarkdownFiles(DEFAULT_ROOTS);

  if (markdownFiles.length === 0) {
    console.log("No Markdown files found for Mermaid validation.");
    return;
  }

  const dom = createDom();
  const { default: mermaid } = await import("mermaid");
  mermaid.initialize({ startOnLoad: false, securityLevel: "strict" });

  const failures = [];
  let validatedCount = 0;

  for (const markdownFile of markdownFiles) {
    const source = await readFile(markdownFile, "utf8");
    const blocks = extractMermaidBlocks(source);

    for (const [blockIndex, block] of blocks.entries()) {
      const relativePath = path.relative(process.cwd(), markdownFile);

      if (block.unterminated) {
        failures.push(`${relativePath}:${block.line}: Unterminated Mermaid code fence`);
        continue;
      }

      try {
        await validateDiagram(mermaid, block.code, `mermaid-check-${validatedCount}-${blockIndex}`);
        validatedCount += 1;
      } catch (error) {
        failures.push(`${relativePath}:${block.line}: ${formatErrorMessage(error)}`);
      }
    }
  }

  dom.window.close();

  if (failures.length > 0) {
    console.error("Mermaid validation failed:");
    for (const failure of failures) {
      console.error(`  ${failure}`);
    }
    process.exitCode = 1;
    return;
  }

  console.log(`Validated ${validatedCount} Mermaid diagram(s).`);
}

main().catch((error) => {
  console.error(formatErrorMessage(error));
  process.exitCode = 1;
});

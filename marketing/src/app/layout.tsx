import type { Metadata } from "next";
import { Inter, Source_Serif_4 } from "next/font/google";
import "./globals.css";

// Same two faces as the workspace surface. Per ADR-0027 the base font stacks
// are shared and each surface chooses which to foreground; marketing is a
// reading surface, so it foregrounds the serif at display sizes like workspace
// does, and stays sans for body copy.
const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

const sourceSerif = Source_Serif_4({
  variable: "--font-serif-display",
  subsets: ["latin"],
  weight: ["400", "600"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Evidara — legal data infrastructure",
  description:
    "Evidara acquires legal texts from official publishers, processes them into a canonical form, and connects them into a citation graph with norm hierarchy and in-force dates.",
  // No Open Graph image yet — shipping a broken/placeholder card is worse
  // than shipping none. Flagged for the human review pass.
  robots: { index: true, follow: true },
};

/**
 * Dark mode. The canonical tokens expose dark values under a `.dark` class
 * (styles/tokens/tokens.css), so rather than duplicating those values behind
 * a `prefers-color-scheme` media query — which would drift the moment the
 * palette changes — we set the class from the OS preference before first
 * paint.
 *
 * This runs blocking in <head> deliberately: deferring it produces a
 * light-mode flash for dark-mode users. Without JS the page renders in light
 * mode, which is a correct and fully legible fallback, not a broken one.
 */
const THEME_SCRIPT = `
try {
  if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
    document.documentElement.classList.add('dark');
  }
} catch (_) {}
`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${inter.variable} ${sourceSerif.variable} h-full antialiased`}
    >
      <head>
        {/* biome-ignore lint/security/noDangerouslySetInnerHtml: pre-paint theme script, static string */}
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-full font-sans">
        <a
          href="#main-content"
          className="sr-only rounded-br-lg bg-[var(--accent-core)] px-4 py-2 text-[var(--accent-core-foreground)] focus-visible:not-sr-only focus-visible:fixed focus-visible:top-0 focus-visible:left-0 focus-visible:z-[var(--z-modal)]"
        >
          Skip to main content
        </a>
        {children}
      </body>
    </html>
  );
}

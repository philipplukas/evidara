import type { Metadata } from "next";
import { Inter, Source_Serif_4 } from "next/font/google";
import { THEME_PRE_PAINT_SCRIPT } from "../lib/admin/theme";
import "./globals.css";

const inter = Inter({
  variable: "--font-admin-sans",
  subsets: ["latin"],
});

const sourceSerif = Source_Serif_4({
  variable: "--font-admin-serif",
  subsets: ["latin"],
  weight: ["400", "600"],
});

export const metadata: Metadata = {
  title: "Evidara Control Plane",
  description: "Code-managed operator admin for source lifecycle, runs, and DI monitoring.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    /*
     * `suppressHydrationWarning` is required, not cosmetic: the inline script
     * below mutates this element's `class` and `style.colorScheme` before React
     * hydrates, so the server HTML and the live DOM genuinely differ by design.
     * Without it React logs a hydration mismatch on every load. It suppresses
     * the warning for this element's own attributes only, not for its subtree.
     */
    <html
      lang="en"
      suppressHydrationWarning
      className={`${inter.variable} ${sourceSerif.variable} h-full antialiased`}
    >
      <head>
        {/*
         * Applies the theme before first paint. React-admin resolves the same
         * value once it mounts (see `ThemeSync`), but it cannot mount before
         * the document paints — without this an operator on a dark OS gets a
         * white flash of the light theme on every load. `beforeInteractive`
         * scripts and `next/script` both run too late for that; a plain inline
         * script in <head> is the only thing that does not.
         *
         * The content is a module constant, not markup assembled here, so the
         * one thing it must agree with — what "apply the dark theme" means — is
         * asserted by `theme.test.ts`.
         */}
        {/* biome-ignore lint/security/noDangerouslySetInnerHtml: static, non-user-derived constant; see THEME_PRE_PAINT_SCRIPT */}
        <script dangerouslySetInnerHTML={{ __html: THEME_PRE_PAINT_SCRIPT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}

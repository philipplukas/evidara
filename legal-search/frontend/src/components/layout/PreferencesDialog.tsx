"use client";

import { Monitor, Moon, Settings, Sun } from "lucide-react";
import type { ReactNode } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  type PreferredLanguage,
  type ResultsPerPage,
  type SortOrder,
  type Theme,
  usePreferences,
} from "@/hooks/use-preferences";

// ─── Option definitions ───

const RESULTS_PER_PAGE_OPTIONS: ResultsPerPage[] = [10, 25, 50];

const SORT_ORDER_OPTIONS: { value: SortOrder; label: string }[] = [
  { value: "relevance", label: "Relevanz" },
  { value: "date-desc", label: "Neueste zuerst" },
  { value: "date-asc", label: "\u00c4lteste zuerst" },
];

const THEME_OPTIONS: { value: Theme; label: string; icon: ReactNode }[] = [
  { value: "light", label: "Hell", icon: <Sun className="h-3.5 w-3.5" /> },
  { value: "dark", label: "Dunkel", icon: <Moon className="h-3.5 w-3.5" /> },
  { value: "system", label: "System", icon: <Monitor className="h-3.5 w-3.5" /> },
];

const LANGUAGE_OPTIONS: { value: PreferredLanguage; label: string }[] = [
  { value: "de", label: "Deutsch" },
  { value: "fr", label: "Fran\u00e7ais" },
  { value: "it", label: "Italiano" },
];

// ─── Sub-components ───

function SectionHeading({ children }: { children: ReactNode }) {
  return (
    <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
      {children}
    </h3>
  );
}

function FieldRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-sm text-foreground">{label}</span>
      {children}
    </div>
  );
}

// ─── Dialog ───

interface PreferencesDialogProps {
  children: ReactNode;
}

export function PreferencesDialog({ children }: PreferencesDialogProps) {
  const { preferences, setPreferences } = usePreferences();

  return (
    <Dialog>
      <DialogTrigger asChild>{children}</DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Settings className="h-4 w-4 text-muted-foreground" />
            Einstellungen
          </DialogTitle>
          <DialogDescription>
            Passen Sie die Anzeige und das Verhalten der Suche an.
          </DialogDescription>
        </DialogHeader>

        {/* ── Display ── */}
        <div className="flex flex-col gap-3">
          <SectionHeading>Anzeige</SectionHeading>

          <FieldRow label="Ergebnisse pro Seite">
            <ToggleGroup
              type="single"
              variant="outline"
              size="sm"
              value={String(preferences.resultsPerPage)}
              onValueChange={(v) => {
                if (v) setPreferences({ resultsPerPage: Number(v) as ResultsPerPage });
              }}
            >
              {RESULTS_PER_PAGE_OPTIONS.map((n) => (
                <ToggleGroupItem key={n} value={String(n)} aria-label={`${n} Ergebnisse`}>
                  {n}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </FieldRow>

          <FieldRow label="Sortierung">
            <ToggleGroup
              type="single"
              variant="outline"
              size="sm"
              value={preferences.sortOrder}
              onValueChange={(v) => {
                if (v) setPreferences({ sortOrder: v as SortOrder });
              }}
            >
              {SORT_ORDER_OPTIONS.map((opt) => (
                <ToggleGroupItem key={opt.value} value={opt.value} aria-label={opt.label}>
                  {opt.label}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </FieldRow>
        </div>

        <Separator />

        {/* ── Appearance ── */}
        <div className="flex flex-col gap-3">
          <SectionHeading>Erscheinungsbild</SectionHeading>

          <FieldRow label="Theme">
            <ToggleGroup
              type="single"
              variant="outline"
              size="sm"
              value={preferences.theme}
              onValueChange={(v) => {
                if (v) setPreferences({ theme: v as Theme });
              }}
            >
              {THEME_OPTIONS.map((opt) => (
                <ToggleGroupItem key={opt.value} value={opt.value} aria-label={opt.label}>
                  {opt.icon}
                  <span className="ml-1">{opt.label}</span>
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </FieldRow>
        </div>

        <Separator />

        {/* ── Language ── */}
        <div className="flex flex-col gap-3">
          <SectionHeading>Sprache</SectionHeading>

          <FieldRow label="Inhaltssprache">
            <ToggleGroup
              type="single"
              variant="outline"
              size="sm"
              value={preferences.language}
              onValueChange={(v) => {
                if (v) setPreferences({ language: v as PreferredLanguage });
              }}
            >
              {LANGUAGE_OPTIONS.map((opt) => (
                <ToggleGroupItem key={opt.value} value={opt.value} aria-label={opt.label}>
                  {opt.value.toUpperCase()}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </FieldRow>
        </div>
      </DialogContent>
    </Dialog>
  );
}

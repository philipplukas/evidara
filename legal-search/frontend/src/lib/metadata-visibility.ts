import type { MetadataField, MetadataRow, MetadataVisibility } from "./types";

type FieldVisibilityRule = {
  labelPattern: string | RegExp;
  visibility: MetadataVisibility;
};

const SHARED_RULES: FieldVisibilityRule[] = [
  { labelPattern: /^(court|jurisdiction|date|enacted)$/i, visibility: "always" },
  {
    labelPattern: /^(docket|publication|chamber|edition|article|law|document type)$/i,
    visibility: "default",
  },
];

const DOCUMENT_TYPE_RULES: Record<string, FieldVisibilityRule[]> = {
  decision: [
    { labelPattern: /^outcome$/i, visibility: "always" },
    { labelPattern: /^chamber$/i, visibility: "default" },
  ],
  law: [{ labelPattern: /^(in force|systematic number|last revision)$/i, visibility: "always" }],
  commentary: [{ labelPattern: /^(edition|article)$/i, visibility: "always" }],
};

function matchesRule(label: string, rule: FieldVisibilityRule): boolean {
  if (typeof rule.labelPattern === "string") {
    return label.toLowerCase() === rule.labelPattern.toLowerCase();
  }
  return rule.labelPattern.test(label);
}

function resolveVisibility(label: string, documentType: string): MetadataVisibility {
  const typeRules = DOCUMENT_TYPE_RULES[documentType] ?? [];
  for (const rule of typeRules) {
    if (matchesRule(label, rule)) return rule.visibility;
  }
  for (const rule of SHARED_RULES) {
    if (matchesRule(label, rule)) return rule.visibility;
  }
  return "expanded";
}

export function enrichMetadataRows(rows: MetadataRow[], documentType: string): MetadataField[] {
  return rows.map((row) => ({
    ...row,
    visibility: row.visibility ?? resolveVisibility(row.label, documentType),
  }));
}

export function filterByDensity(
  fields: MetadataField[],
  density: "compact" | "default" | "expanded",
): MetadataField[] {
  return fields.filter((field) => {
    if (density === "expanded") return true;
    if (density === "default") return field.visibility !== "expanded";
    return field.visibility === "always";
  });
}

const FLAG_KEYS: Record<string, string> = {
  ch: "/flags/ch.svg",
  at: "/flags/at.svg",
};

const FLAG_ALT: Record<string, string> = {
  ch: "Switzerland",
  at: "Austria",
};

const textIconMap: Record<string, string> = {
  "ch-zh": "ZH",
  "ch-be": "BE",
  "ch-lu": "LU",
  "ch-sg": "SG",
  "ch-ag": "AG",
  "ch-ge": "GE",
  "ch-vd": "VD",
  "ch-ti": "TI",
  "dtype-law": "§",
  "dtype-decision": "⚖",
  "dtype-commentary": "💬",
  "dtype-rechtssatz": "≡",
  "meta-status": "●",
  "meta-calendar": "📅",
  "meta-citation": "↗",
  "meta-official": "✓",
  "meta-language": "🌐",
  "meta-authority": "🏛",
};

export function isFlagIcon(iconKey?: string): boolean {
  return !!iconKey && iconKey in FLAG_KEYS;
}

export function getFlagSrc(iconKey: string): string | null {
  return FLAG_KEYS[iconKey] ?? null;
}

export function getFlagAlt(iconKey: string): string {
  return FLAG_ALT[iconKey] ?? iconKey.toUpperCase();
}

export function getIcon(iconKey?: string): string | null {
  if (!iconKey) return null;
  return textIconMap[iconKey] ?? null;
}

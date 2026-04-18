/**
 * `clsx` + `tailwind-merge` helper — canonical class-name composition for
 * admin UI primitives. Mirrors the convention used in `legal-search/frontend`
 * so the two surfaces stay visually continuous. Currently internal to
 * `platform-control/admin`; promotes to a shared workspace package once
 * `legal-search` is ready to consume (see ADR-0025).
 */
import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

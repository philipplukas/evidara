/**
 * `@evidara/admin-ui/shell` — Tailwind shell for the admin app.
 *
 * Exported from one barrel to keep the shell-import footprint of `AdminApp`
 * small and to surface the shape of P4a at a glance. `AppShell` is the
 * only required entry; the rest are re-exported for tests and for the
 * rare case a page needs to re-use a shell sub-component (e.g. a custom
 * header variant).
 */
export { AppBar } from "./AppBar";
export { AppShell } from "./AppShell";
export { SidebarMenu, type SidebarMenuExtraItem } from "./SidebarMenu";
export { Toast } from "./Toast";
export { type NotificationType, ToastAdapter } from "./ToastAdapter";

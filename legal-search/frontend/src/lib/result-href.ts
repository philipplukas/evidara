/** URL query parameter that selects the open document. Mirrors `useQueryState("item")`. */
export const SELECTED_ITEM_PARAM = "item";

/**
 * Deep link to a result, preserving the current search state.
 *
 * Result cards used to be `<button>`s with no `href`, so a legal researcher
 * could not middle-click, open in a new tab, or copy the link address of a
 * document — for a citation-driven tool that is close to a core affordance
 * (#648). The app already deep-links (`/?q=…&item=…` renders correctly), so
 * this only exposes the capability that routing already had.
 *
 * @param currentSearch `location.search`-style query string of the current page
 * @param resultId id of the result the link should open
 */
export function buildResultHref(currentSearch: string, resultId: string): string {
  const params = new URLSearchParams(currentSearch);
  params.set(SELECTED_ITEM_PARAM, resultId);
  return `/?${params.toString()}`;
}

/**
 * True when a click should be left to the browser (new tab / new window /
 * download) instead of being intercepted for client-side selection.
 */
export function isModifiedClick(event: {
  metaKey: boolean;
  ctrlKey: boolean;
  shiftKey: boolean;
  altKey: boolean;
  button: number;
}): boolean {
  return event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0;
}

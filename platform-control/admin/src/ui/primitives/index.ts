/**
 * `@evidara/admin-ui` primitives (currently internal to `platform-control/admin`;
 * promotes to a workspace package once `legal-search` is ready to consume).
 *
 * Every v2 resource page imports from here; keeping the barrel thin keeps
 * tree-shaking friendly.
 */
export {
  AccordionContent,
  AccordionItem,
  AccordionRoot,
  AccordionTrigger,
} from "./Accordion";
export { Button } from "./Button";
export { cn } from "./cn";
export {
  DataTable,
  type DataTableColumn,
  type DataTableProps,
  type SortOrder,
} from "./DataTable";
export { DetailGrid, FieldCell } from "./DetailGrid";
export { FormField } from "./FormField";
export { InlineAlert } from "./InlineAlert";
export { Panel } from "./Panel";
export { Pill, type PillLevel } from "./Pill";
export { Select, type SelectChoice } from "./Select";
export { Spinner } from "./Spinner";
export { TextInput } from "./TextInput";

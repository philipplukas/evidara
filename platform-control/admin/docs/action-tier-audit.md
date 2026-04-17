# Action tier audit

Maps admin actions to consequence tiers for the ConfirmButton system (ADR-0016, Contract 8).

## Tier definitions

| Tier | Behavior | Confirmation |
|---|---|---|
| safe | No confirmation | None |
| notable | Inline popover | "Are you sure?" with confirm/cancel |
| destructive | Modal dialog | Explicit action label required |

## Admin actions

| Action | Location | Tier | Rationale |
|---|---|---|---|
| Preview Run (launch dialog) | RunLaunchDialog | safe | Reversible; low consequence |
| Preview Run (version table) | SourceVersionsSection | safe | Reversible; low consequence |
| Production Run (launch dialog) | RunLaunchDialog | notable | Irreversible; creates real pipeline work |
| Production Run (version table) | SourceVersionsSection | notable | Irreversible; creates real pipeline work |
| Cancel Run | RunActions | destructive | Stops in-progress work; data loss possible |
| Approve Version | SourceVersionsSection | notable | Changes version lifecycle state; enables production |
| Reject Version | SourceVersionsSection | destructive | Permanently blocks version from production |
| Edit Version | SourceVersionsSection | safe | Reversible metadata change; only draft/rejected |
| Create Version | SourceVersionsSection | safe | Additive; starts in draft |
| Edit Source | SourceShow | safe | Reversible metadata change |
| Create Source | SourceCreate | safe | Additive; no side effects |
| Reference edits | AuthorityEdit, JurisdictionEdit | safe | Reversible metadata changes via SimpleForm |

## Implementation

All tiers above are implemented via `ConfirmButton` (`platform-control/admin/src/resources/shared/ConfirmButton.tsx`), which mirrors the legal-search `Button` tier contract (ADR-0016 Contract 8) using MUI primitives.

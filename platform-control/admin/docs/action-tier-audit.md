# Action tier audit

Maps admin actions to consequence tiers for the ConfirmButton system (ADR-0016, Contract 8).

## Tier definitions

| Tier | Behavior | Confirmation |
|---|---|---|
| safe | No confirmation | None |
| notable | Inline popover | "Are you sure?" with confirm/cancel |
| destructive | Modal dialog | Explicit action label required |

## Admin actions

| Action | Location | Current tier | Target tier | Rationale |
|---|---|---|---|---|
| Preview Run (launch) | RunLaunchDialog, SourceVersionsSection | safe | safe | Reversible; low consequence |
| Production Run (launch) | RunLaunchDialog, SourceVersionsSection | safe | notable | Irreversible; creates real pipeline work |
| Cancel Run | RunActions | safe | destructive | Stops in-progress work; data loss possible |
| Approve Version | SourceVersionsSection | safe | notable | Changes version lifecycle state |
| Reject Version | SourceVersionsSection | safe | destructive | Permanently blocks version from production |
| Edit Source | SourceShow | safe | safe | Reversible metadata change |
| Create Source | SourceCreate | safe | safe | Additive; no side effects |
| Create Version | SourceVersionsSection | safe | safe | Additive; starts in draft |

## Migration plan

1. Import `ConfirmButton` from `@evidara/legal-search-frontend` or copy to admin
2. Replace each action button with `ConfirmButton` using the target tier
3. Add contextual confirm messages per action

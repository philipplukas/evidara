# Status level vocabulary (admin + legal-search)

Maps **pipeline and UI domain states** to the shared `StatusLevel` type used by `StatusBadge` and related components. Default **English** labels below; override in UI when i18n requires.

| StatusLevel | Meaning | Typical admin labels | Token (legal-search) |
|-------------|---------|----------------------|----------------------|
| `healthy` | Succeeded, approved, live, OK | Active, Approved, Healthy, Completed | `--status-healthy` |
| `degraded` | In progress, pending, blocked, warning | Pending, In progress, Blocked, Degraded | `--status-degraded` |
| `critical` | Failed, rejected, error | Failed, Rejected, Error | `--status-critical` |
| `neutral` | Archived, superseded, idle, unknown | Archived, Superseded, Unknown | `--status-neutral` |
| `info` | Running, draft, informational | Running, Draft, Preview | `--status-info` |

## Usage rules

1. **Never encode meaning by color alone** — always pair `StatusBadge` with icon + label (WCAG 1.4.1).
2. **Map domain enums in one place** per surface (admin resource vs legal-search) and keep this table aligned when adding states.
3. **MUI admin** may wrap the same levels with different presentation; the **semantic level** should still match this table.

## Related

- [ADR-0016 — Design-system component contracts](../../../../docs/adr/adr-0016-design-system-component-contracts.md) (Contract 5: `StatusBadge`)
- Linear epic [TAR-243](https://linear.app/tart-baozi/issue/TAR-243) / task [TAR-251](https://linear.app/tart-baozi/issue/TAR-251)

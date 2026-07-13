#!/usr/bin/env python3
"""Fail the build when a GitHub Actions workflow references a `vars.X`
value that isn't declared in `infra/env/github.repo_settings.tfvars.example`.

Background: Incident #311 (2026-04-20) — PR #303 migrated workflows to
reference `vars.LIGHT_RUNNER_SCALE_SET` / `vars.HEAVY_RUNNER_SCALE_SET`, but
those repo-level variables were never declared in terraform, so
`runs-on: ${{ vars.LIGHT_RUNNER_SCALE_SET || 'evidara-light' }}` resolved to
an empty scale-set label and the runner pool picked up a non-existent
`runner_id: 0` target, failing jobs in ~2s. See issue #313.

Source of truth for repo variables is
`infra/env/github.repo_settings.tfvars.example`:
- `repository_variables = { ... }`
- `environment_variables = { dev = { ... }, staging = { ... }, prod = { ... } }`

Design notes:
- Stdlib only. We intentionally do not depend on PyYAML — GitHub Actions
  expression syntax (`${{ vars.X }}`) can be extracted with a regex, and
  the tfvars map grammar we need to read is also simple enough for regex.
- Matches both `${{ vars.FOO }}` and bare `vars.FOO` references (the
  latter appears inside `if:` expressions).

Exit codes: 0 on success, 1 on any undeclared reference.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
TFVARS_FILE = REPO_ROOT / "infra" / "env" / "github.repo_settings.tfvars.example"

# Allowlist: variables referenced by workflows but intentionally NOT declared
# in the terraform-managed tfvars. Each entry MUST document why. Keep this
# list small and well-justified — when in doubt, add the var to the tfvars
# file instead of here.
ALLOWLIST: dict[str, str] = {
    # --- Deploy flags (operator-managed kill switches) ------------------
    # These are intentional operator kill-switches for `terraform apply`
    # steps. They default to "false" in-workflow (safe no-op) and are only
    # flipped to "true" by an operator in the GitHub UI once a stack is
    # ready for auto-apply. Declaring them in tfvars would let a routine
    # `terraform apply` of the repo_settings stack silently *reset* them,
    # which is the opposite of what we want.
    "TERRAFORM_APPLY_ENABLED": "operator-managed auto-apply kill switch (main infra stack)",
    "TERRAFORM_APPLY_ENABLED_STAGING": "operator-managed auto-apply kill switch (main infra, staging env)",
    "TERRAFORM_APPLY_ENABLED_PROD": "operator-managed auto-apply kill switch (main infra, prod env)",
    # --- Release readiness overrides -----------------------------------
    # Documented as optional in
    # `infra/terraform/github/repo_settings/README.md` — the workflow has
    # in-place string defaults (`staging`, `E2E Smoke Staging`, env-based
    # regex) and the var only exists if an operator wants to flip the
    # job's target environment.
    "RELEASE_READINESS_GITHUB_ENVIRONMENT": "optional override documented in repo_settings/README.md",
    "RELEASE_READINESS_E2E_SMOKE_WORKFLOW": "optional override documented in repo_settings/README.md",
    "RELEASE_READINESS_DLQ_SUBSCRIPTION_REGEX": "optional override documented in repo_settings/README.md",
    # --- Interaction-flow evidence roots -------------------------------
    # Workflow falls back to `DI_SURFACES_ROOT_URI_*` when the evidence
    # bucket is colocated with published surfaces (the common case). Only
    # declared when an operator splits evidence onto a separate bucket.
    "INTERACTION_FLOW_EVIDENCE_GCS_ROOT_DEV": "optional override, falls back to DI_SURFACES_ROOT_URI_DEV",
    "INTERACTION_FLOW_EVIDENCE_GCS_ROOT_STAGING": "optional override, falls back to DI_SURFACES_ROOT_URI_STAGING",
    # --- Legacy service-name overrides (staging-only) -------------------
    # Workflow has concrete string defaults baked in; only present if an
    # operator renames a Cloud Run service without a corresponding
    # tfvars bump (intentionally manual today, see #311-style concerns).
    "LEGAL_SEARCH_FRONTEND_SERVICE_STAGING": "optional Cloud Run service name override, has workflow fallback",
    "PLATFORM_CONTROL_ADMIN_SERVICE_STAGING": "optional Cloud Run service name override, has workflow fallback",
}

# Regex for `vars.FOO` references inside workflow files. We match both the
# `${{ vars.FOO }}` template form and the bare `vars.FOO` form that appears
# inside `if:` conditionals. We do NOT match `env.FOO` or `secrets.FOO`.
VARS_REF_RE = re.compile(r"\bvars\.([A-Z][A-Z0-9_]*)")

# Regex to locate a top-level HCL-ish map key block in the tfvars example,
# e.g. `repository_variables = {` ... matching `}`. The file is small and
# regular enough that we don't need a real HCL parser.
BLOCK_OPEN_RE = re.compile(
    r"^(?P<name>[a-z_]+)\s*=\s*\{\s*$",
    re.MULTILINE,
)
# Regex for an identifier key inside a map block, e.g. `GCP_REGION = "x"` or
# `LIGHT_RUNNER_SCALE_SET                = "evidara-light"`.
KEY_RE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=", re.MULTILINE)


def _extract_block_body(text: str, block_name: str) -> str | None:
    """Return the inner body of a top-level `<block_name> = { ... }` block,
    or None if the block is not found. Handles nested braces by counting.
    """
    m = re.search(rf"^{re.escape(block_name)}\s*=\s*\{{", text, re.MULTILINE)
    if not m:
        return None
    depth = 0
    start = m.end() - 1  # position of the opening '{'
    i = start
    while i < len(text):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i]
        i += 1
    return None


def load_declared_vars(tfvars_path: Path) -> set[str]:
    """Return the set of variable names declared in the tfvars example.

    Combines keys from `repository_variables` and every sub-map of
    `environment_variables` (dev/staging/prod).
    """
    if not tfvars_path.exists():
        raise SystemExit(f"check_workflow_vars: tfvars file not found: {tfvars_path}")

    text = tfvars_path.read_text(encoding="utf-8")
    declared: set[str] = set()

    repo_body = _extract_block_body(text, "repository_variables")
    if repo_body is None:
        raise SystemExit(
            "check_workflow_vars: could not locate `repository_variables = { ... }` block "
            f"in {tfvars_path}"
        )
    for m in KEY_RE.finditer(repo_body):
        declared.add(m.group(1))

    env_body = _extract_block_body(text, "environment_variables")
    if env_body is not None:
        # Inside environment_variables, each env is its own nested block.
        # Grab every identifier-looking key from the whole body; a var
        # declared for any env is "declared" for our purposes.
        for m in KEY_RE.finditer(env_body):
            declared.add(m.group(1))

    return declared


def load_referenced_vars(workflows_dir: Path) -> dict[str, list[Path]]:
    """Return a mapping of `vars.X` name -> sorted list of workflow files
    that reference it."""
    if not workflows_dir.exists():
        raise SystemExit(f"check_workflow_vars: workflows dir not found: {workflows_dir}")

    refs: dict[str, set[Path]] = {}
    for path in sorted(workflows_dir.glob("*.yml")) + sorted(workflows_dir.glob("*.yaml")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise SystemExit(f"check_workflow_vars: failed to read {path}: {exc}") from exc
        for m in VARS_REF_RE.finditer(text):
            refs.setdefault(m.group(1), set()).add(path)
    return {k: sorted(v) for k, v in refs.items()}


def main(argv: list[str]) -> int:
    declared = load_declared_vars(TFVARS_FILE)
    referenced = load_referenced_vars(WORKFLOWS_DIR)

    undeclared: dict[str, list[Path]] = {}
    for name, paths in referenced.items():
        if name in declared:
            continue
        if name in ALLOWLIST:
            continue
        undeclared[name] = paths

    if undeclared:
        print("check_workflow_vars: FAIL", file=sys.stderr)
        print(
            f"  {len(undeclared)} undeclared vars.* reference(s) found in "
            f".github/workflows/. Each must either be added to "
            f"repository_variables/environment_variables in "
            f"{TFVARS_FILE.relative_to(REPO_ROOT)} or added to the ALLOWLIST "
            f"in scripts/check_workflow_vars.py with a justifying comment.",
            file=sys.stderr,
        )
        for name in sorted(undeclared):
            paths = undeclared[name]
            print(f"  - vars.{name}", file=sys.stderr)
            for p in paths:
                print(f"      referenced in: {p.relative_to(REPO_ROOT)}", file=sys.stderr)
        return 1

    total_refs = sum(len(v) for v in referenced.values())
    print(
        f"check_workflow_vars: OK "
        f"({len(referenced)} unique vars.* across "
        f"{total_refs} references; "
        f"{len(declared)} declared in tfvars, "
        f"{len(ALLOWLIST)} allowlisted)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
"""Fail the build when a test file exists that no CI job can reach.

Background (#686, #688): a green suite is only evidence about the tests CI actually
runs. This repo accumulated specs that are written, linted, typechecked, and
committed — and never executed by anything. They look like coverage in the
file tree and provide none.

The two cases that motivated this check:

- `legal-search/frontend` runs Playwright four ways in CI. Three are tag
  filters (`-g @smoke`, `-g @contract`, `-g @screenshots`); the fourth,
  `e2e:visual`, names **one file by path**. A spec that carries no matching
  tag and is not that one file is invisible to CI.
- `e2e/workspace-panels.spec.ts` carries no tag at all. It sat 4-of-6 red on
  `main` unnoticed, and the panel-geometry guard added by #605 has been inert
  since the day it landed.

Design (deliberately mirrors `scripts/ci_skip_guard.py`):

- **Derive, do not declare.** A hand-maintained list of "what CI runs" is the
  same class of artifact that rotted in the first place. This script reads the
  workflows, follows `bash scripts/*.sh` and `npm run <script>` indirection,
  and resolves the terminal `vitest` / `playwright` / `pytest` / `unittest`
  commands. The only hand-maintained thing is the debt register below, and
  every entry in it must carry a reason.
- **Check the outcome, not the syntax.** Reachability is "would some CI
  command collect this file", not "does this file look tagged".

**What this does NOT check.** Reachability is decided per *file*. A file that
CI collects can still contain a test that never executes — `e2e/smoke.spec.ts`
guards its only real-backend test with
`test.skip(!USE_REAL_BACKEND, ...)`, and no CI job sets that variable (#686
case 3). That is a skip, not a reachability gap, and it is the JS analogue of
what `scripts/ci_skip_guard.py` catches on the Python side.
There is no equivalent for vitest/Playwright yet. Do not read a passing run of
this check as "everything in these files executed".

Known-unreachable files are recorded in `KNOWN_UNREACHABLE` with a reason, so
the check is green on a repo that still has debt while **new** unreachable
specs fail immediately. Entries are printed on every run — this is a debt
register, not a mute button.

Stdlib only (same rationale as `scripts/check_workflow_vars.py`): this runs in
the contract-validation job, which installs no test tooling.

Exit codes: 0 when every discovered test file is reachable or registered,
1 otherwise (including when a register entry has become stale).
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# `TEST_REACHABILITY_REPO_ROOT` exists so this check's own self-test
# (scripts/tests/test_check_test_reachability.py) can point it at a fixture tree
# and assert BOTH directions — a reachability check that only ever ran against a
# passing repo would be exactly the kind of evidence this script exists to
# distrust. Unset in every real invocation.
REPO_ROOT = Path(os.environ.get("TEST_REACHABILITY_REPO_ROOT") or Path(__file__).resolve().parent.parent).resolve()
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

# ---------------------------------------------------------------------------
# Debt register
# ---------------------------------------------------------------------------
# Files that exist, are not reachable by any CI job, and are knowingly left
# that way for now. Adding an entry requires a reason; the reason is printed
# on every run. Removing a file or making it reachable requires deleting its
# entry (a stale entry fails the check, so this cannot silently rot).
KNOWN_UNREACHABLE: dict[str, str] = {
    "legal-search/frontend/e2e/demo-queries.spec.ts": (
        "Tagged `@demo`; no CI command filters on `@demo`. Written for manual demo "
        "rehearsal, never wired to a job."
    ),
    "legal-search/api/src/modules/health/health.smoke.spec.ts": (
        "Excluded from `vitest.config.ts`. A `vitest.smoke.config.ts` that would collect "
        "it does exist — but no npm script passes `--config` to it, and the "
        "`npm run test:smoke` the spec's own header documents is not in package.json. "
        "Needs a running app on :3102, so it needs a job that starts one."
    ),
    # The six `platform-control/admin/e2e/*.spec.ts` entries that stood here are
    # gone, not moved: the `Admin e2e (Playwright)` job in
    # `.github/workflows/platform-control.yml` now runs them. Their reason —
    # "admin Playwright has no CI job", and the note that it "needs a running
    # backend" — was true when written and stopped being true twice over: every
    # one of those specs mocks platform-control with `page.route`, so the job
    # needs no backend at all.
    "infra/coordinator/tests/test_app.py": (
        "`infra/coordinator` is a standalone uv package with its own pyproject; "
        "no workflow runs pytest in that directory."
    ),
    "infra/coordinator/tests/test_gates.py": (
        "Same as test_app.py — `infra/coordinator` has no CI job."
    ),
    "tools/zed-evidara-mcp/tests/test_catalog.py": (
        "`tools/zed-evidara-mcp` has no CI job; only `tools/evidara-cli` is gated "
        "(`scripts/check-evidara-cli.sh`)."
    ),
}

# Directories never scanned for test files.
PRUNE_DIRS = {
    "node_modules",
    ".venv",
    "venv",
    ".git",
    "dist",
    "build",
    ".next",
    "__pycache__",
    ".pytest_cache",
    "target",
    "retool",
}

PY_TEST_GLOBS = ("test_*.py", "*_test.py")
JS_TEST_SUFFIXES = (".spec.ts", ".spec.tsx", ".test.ts", ".test.tsx")


def iter_files(root: Path):
    """Walk `root`, skipping PRUNE_DIRS at any depth."""
    if not root.is_dir():
        return
    stack = [root]
    while stack:
        current = stack.pop()
        for entry in sorted(current.iterdir()):
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name not in PRUNE_DIRS:
                    stack.append(entry)
            else:
                yield entry


def rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


# ---------------------------------------------------------------------------
# Step 1 — what does CI invoke?
# ---------------------------------------------------------------------------


@dataclass
class Invocation:
    """A terminal test command, with the directory it runs in."""

    cwd: Path
    argv: list[str]
    source: str

    @property
    def tool(self) -> str:
        return self.argv[0] if self.argv else ""


# `working-directory:` and `run:` live at the same indent inside a step. We do
# not depend on PyYAML (see module docstring), so steps are recovered from
# indentation, which GitHub Actions workflows use consistently.
#
# Two things set the directory, and missing either one makes every command in
# the job look like it runs at the repo root:
#   - `jobs.<id>.defaults.run.working-directory` (applies to the whole job)
#   - a step-level `working-directory:` (overrides it for that step)
STEP_START = re.compile(r"^(\s*)-\s+(name|uses|run|id):")
JOB_START = re.compile(r"^  ([A-Za-z_][\w-]*):\s*$")
DEFAULTS_KEY = re.compile(r"^\s{4}defaults:\s*$")
WORKING_DIR = re.compile(r"^\s*working-directory:\s*(.+?)\s*$")
# Both `run:` (after a `- name:` line) and the inline `- run:` step form.
RUN_KEY = re.compile(r"^(\s*(?:-\s+)?)run:\s*(\|-?|>-?)?\s*(.*)$")


def workflow_commands(path: Path) -> list[tuple[Path, str]]:
    """Extract (cwd, command-line) pairs from one workflow file."""
    out: list[tuple[Path, str]] = []
    lines = path.read_text(encoding="utf-8").splitlines()

    job_cwd = REPO_ROOT
    step_cwd = REPO_ROOT
    in_defaults = False
    i = 0
    while i < len(lines):
        line = lines[i]

        if JOB_START.match(line):
            job_cwd = step_cwd = REPO_ROOT
            in_defaults = False
        if DEFAULTS_KEY.match(line):
            in_defaults = True
        if STEP_START.match(line):
            in_defaults = False
            step_cwd = job_cwd  # a new step falls back to the job default

        wd = WORKING_DIR.match(line)
        if wd:
            resolved = (REPO_ROOT / wd.group(1).strip("\"'")).resolve()
            if in_defaults:
                job_cwd = step_cwd = resolved
            else:
                step_cwd = resolved

        run = RUN_KEY.match(line)
        if run:
            indent, block, inline = run.group(1), run.group(2), run.group(3)
            if block:
                # Block scalar: consume more-indented lines.
                body: list[str] = []
                i += 1
                while i < len(lines):
                    nxt = lines[i]
                    if nxt.strip() and (len(nxt) - len(nxt.lstrip())) <= len(indent):
                        break
                    body.append(nxt)
                    i += 1
                # A `working-directory:` sibling may follow the block.
                for look in lines[i : i + 3]:
                    wd2 = WORKING_DIR.match(look)
                    if wd2:
                        step_cwd = (REPO_ROOT / wd2.group(1).strip("\"'")).resolve()
                for b in body:
                    out.append((step_cwd, b))
                continue
            if inline:
                out.append((step_cwd, inline))
        i += 1

    return out


CD_RE = re.compile(r"""^cd\s+["']?([^"'&;|]+)["']?\s*$""")
SUBSHELL_CD = re.compile(r"""^\(\s*cd\s+["']?([^"'&;|]+)["']?\s*&&\s*(.+?)\s*\)\s*$""")


def resolve_shell_path(raw: str, cwd: Path) -> Path | None:
    """Resolve a `cd` target, understanding the repo's `$REPO_ROOT` idiom."""
    text = raw.strip().strip("\"'")
    text = text.replace("${REPO_ROOT}", str(REPO_ROOT)).replace("$REPO_ROOT", str(REPO_ROOT))
    text = text.replace("${GITHUB_WORKSPACE}", str(REPO_ROOT))
    if "$" in text:
        return None
    candidate = Path(text) if Path(text).is_absolute() else cwd / text
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    return resolved if resolved.is_dir() else None


def split_commands(line: str) -> list[str]:
    """Split a shell line on `&&`, `||`, `;` — enough for our command shapes."""
    parts = re.split(r"&&|\|\||;", line)
    return [p.strip() for p in parts if p.strip()]


TEST_TOOLS = ("vitest", "playwright", "pytest", "unittest")

SHELL_KEYWORDS = {"if", "then", "else", "elif", "fi", "while", "until", "do", "done", "!", "time"}


@dataclass
class Collector:
    invocations: list[Invocation] = field(default_factory=list)
    _seen_scripts: set[tuple[str, str]] = field(default_factory=set)

    def feed_line(self, cwd: Path, line: str, source: str, depth: int = 0) -> Path:
        """Process one shell line; returns the (possibly changed) cwd."""
        if depth > 12:
            return cwd
        line = line.strip()
        if not line or line.startswith("#"):
            return cwd

        sub = SUBSHELL_CD.match(line)
        if sub:
            inner = resolve_shell_path(sub.group(1), cwd)
            if inner:
                for cmd in split_commands(sub.group(2)):
                    self.feed_command(inner, cmd, source, depth + 1)
            return cwd

        for cmd in split_commands(line):
            cd = CD_RE.match(cmd)
            if cd:
                moved = resolve_shell_path(cd.group(1), cwd)
                if moved:
                    cwd = moved
                continue
            self.feed_command(cwd, cmd, source, depth + 1)
        return cwd

    def feed_command(self, cwd: Path, cmd: str, source: str, depth: int) -> None:
        if depth > 12:
            return
        argv = cmd.split()
        # Strip shell keywords so `if npm run e2e:smoke; then` is still seen as
        # an invocation — CI wraps its Playwright steps in exactly that shape.
        while argv and argv[0] in SHELL_KEYWORDS:
            argv = argv[1:]
        if not argv:
            return

        # `bash scripts/foo.sh` / `sh scripts/foo.sh` — follow it.
        if argv[0] in {"bash", "sh"} and len(argv) >= 2 and argv[1].endswith(".sh"):
            script = resolve_file(argv[1], cwd)
            if script:
                self.feed_script(script, depth + 1)
            return

        # `npm run <name>` / `npm run --silent <name>` — expand from package.json.
        if argv[0] in {"npm", "pnpm", "yarn"} and len(argv) >= 2:
            rest = [a for a in argv[1:] if not a.startswith("-")]
            if rest and rest[0] == "run" and len(rest) >= 2:
                self.feed_npm_script(cwd, rest[1], source, depth + 1)
                return
            if rest and rest[0] == "ci":
                return

        # Drop leading env assignments and runner prefixes.
        while argv and ("=" in argv[0] and not argv[0].startswith("-")):
            argv = argv[1:]
        argv = strip_runner_prefix(argv)
        if not argv:
            return

        if argv[0] in TEST_TOOLS:
            self.invocations.append(Invocation(cwd=cwd, argv=argv, source=source))

    def feed_npm_script(self, cwd: Path, name: str, source: str, depth: int) -> None:
        pkg = cwd / "package.json"
        if not pkg.is_file():
            return
        key = (str(pkg), name)
        if key in self._seen_scripts:
            return
        self._seen_scripts.add(key)
        try:
            scripts = json.loads(pkg.read_text(encoding="utf-8")).get("scripts", {})
        except (json.JSONDecodeError, OSError):
            return
        body = scripts.get(name)
        if not isinstance(body, str):
            return
        self.feed_line(cwd, body, f"{source} -> {rel(pkg)}:{name}", depth)
        self._seen_scripts.discard(key)

    def feed_script(self, script: Path, depth: int) -> None:
        try:
            text = script.read_text(encoding="utf-8")
        except OSError:
            return
        cwd = REPO_ROOT
        for raw in text.splitlines():
            cwd = self.feed_line(cwd, raw, rel(script), depth)


def strip_runner_prefix(argv: list[str]) -> list[str]:
    """`npx playwright test` -> `playwright test`, `python -m pytest` -> `pytest`."""
    while argv:
        head = argv[0]
        if head in {"npx", "uvx"}:
            argv = [a for a in argv[1:] if a not in {"-y", "--yes", "--no-install"}]
            continue
        if head in {"uv", "poetry", "pdm", "hatch"} and len(argv) > 1 and argv[1] == "run":
            argv = argv[2:]
            continue
        if head.startswith("python") and len(argv) > 2 and argv[1] == "-m":
            argv = argv[2:]
            continue
        if head.startswith("python") and len(argv) > 1 and argv[1].startswith("-m"):
            argv = argv[1:]
            continue
        break
    return argv


def resolve_file(raw: str, cwd: Path) -> Path | None:
    for base in (cwd, REPO_ROOT):
        candidate = (base / raw).resolve()
        if candidate.is_file():
            return candidate
    return None


def collect_invocations() -> list[Invocation]:
    collector = Collector()
    for wf in sorted(WORKFLOWS_DIR.glob("*.yml")) + sorted(WORKFLOWS_DIR.glob("*.yaml")):
        for cwd, line in workflow_commands(wf):
            collector.feed_line(cwd, line, rel(wf))
    return collector.invocations


# ---------------------------------------------------------------------------
# Step 2 — what test files exist, and which invocation collects them?
# ---------------------------------------------------------------------------

ARRAY_RE = r"{key}\s*:\s*\[(?P<body>[^\]]*)\]"


def config_string_array(text: str, key: str) -> list[str]:
    match = re.search(ARRAY_RE.format(key=key), text, re.DOTALL)
    if not match:
        return []
    return re.findall(r"""["'`]([^"'`]+)["'`]""", match.group("body"))


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate the subset of glob used in vitest configs (`**`, `*`, `{a,b}`)."""
    out = ""
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif ch == "*":
            out += "[^/]*"
            i += 1
        elif ch == "{":
            close = pattern.index("}", i)
            alts = pattern[i + 1 : close].split(",")
            out += "(?:" + "|".join(re.escape(a) for a in alts) + ")"
            i = close + 1
        elif ch == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(ch)
            i += 1
    return re.compile("^" + out + "$")


def literal_prefix(pattern: str) -> str:
    """The glob-free leading directory of a pattern (`src/**/*.test.ts` -> `src`)."""
    parts: list[str] = []
    for segment in pattern.split("/"):
        if any(ch in segment for ch in "*?{["):
            break
        parts.append(segment)
    return "/".join(parts) or "."


@dataclass
class Surface:
    """One test-runner root: a vitest or playwright config and its test files."""

    kind: str
    config: Path
    root: Path
    files: list[Path]
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)


def discover_vitest_surfaces() -> list[Surface]:
    """Every `vitest*.config.ts`, not just the default one.

    `legal-search/api` runs three vitest projects off three configs — the
    default, `vitest.integration.config.ts` (Testcontainers, selected with
    `--config`), and `vitest.smoke.config.ts`. Modelling only `vitest.config.ts`
    made the integration specs look unreachable, because the default config
    excludes exactly what the integration config includes.
    """
    surfaces = []
    for cfg in sorted(REPO_ROOT.rglob("vitest*.config.ts")):
        if any(part in PRUNE_DIRS for part in cfg.parts):
            continue
        text = cfg.read_text(encoding="utf-8")
        include = config_string_array(text, "include") or ["src/**/*.{test,spec}.{ts,tsx}"]
        exclude = config_string_array(text, "exclude")
        base = cfg.parent
        # Scan every directory an include pattern points at, not just `src/`:
        # `legal-search/frontend` also collects `../../styles/ui/**`, and a new
        # test file there must be checked against the includes too.
        roots = {(base / literal_prefix(p)).resolve() for p in include}
        files = sorted(
            {f for root in roots for f in iter_files(root) if f.name.endswith(JS_TEST_SUFFIXES)}
        )
        surfaces.append(
            Surface("vitest", cfg, base, sorted(files), include=include, exclude=exclude)
        )
    return surfaces


TESTDIR_RE = re.compile(r"""testDir\s*:\s*["'`]([^"'`]+)["'`]""")


def discover_playwright_surfaces() -> list[Surface]:
    surfaces = []
    for cfg in sorted(REPO_ROOT.rglob("playwright.config.ts")):
        if any(part in PRUNE_DIRS for part in cfg.parts):
            continue
        text = cfg.read_text(encoding="utf-8")
        match = TESTDIR_RE.search(text)
        test_dir = (cfg.parent / (match.group(1) if match else ".")).resolve()
        files = [f for f in iter_files(test_dir) if f.name.endswith((".spec.ts", ".spec.tsx"))]
        surfaces.append(Surface("playwright", cfg, test_dir, sorted(files)))
    return surfaces


def discover_python_tests(claimed: set[Path]) -> list[Path]:
    found = []
    for f in iter_files(REPO_ROOT):
        if f.suffix != ".py" or f in claimed:
            continue
        if f.name.startswith("test_") or f.name.endswith("_test.py"):
            found.append(f)
    return sorted(found)


# --- Playwright title extraction -------------------------------------------

TITLE_RE = re.compile(
    r"""\b(?:test|it)(?:\.describe)?(?:\.(?:only|skip|fixme|serial|parallel))*\s*\(\s*["'`]([^"'`]*)["'`]"""
)
DYNAMIC_TITLE_RE = re.compile(r"""\b(?:test|it)\s*\(\s*(?!["'`])[A-Za-z_$]""")


def spec_titles(path: Path) -> tuple[list[str], bool]:
    text = path.read_text(encoding="utf-8")
    return TITLE_RE.findall(text), bool(DYNAMIC_TITLE_RE.search(text))


def playwright_reaches(inv: Invocation, surface: Surface, spec: Path) -> bool:
    args = inv.argv[1:]
    if not args or args[0] != "test":
        return False

    # An invocation only reaches the surface whose config it would actually
    # load. Playwright resolves `playwright.config.ts` from the working
    # directory, so `cd legal-search/frontend && playwright test` can never
    # collect a spec belonging to `platform-control/admin`.
    #
    # Without this the surfaces leaked into each other, and the leak was
    # invisible for exactly as long as *every* CI Playwright command carried a
    # `-g` filter: an unfiltered invocation falls through to `return True`
    # below, which — matched against every surface — marked every spec in the
    # repo reachable. The first unfiltered command (the admin's `npm run e2e`)
    # made `legal-search/frontend/e2e/demo-queries.spec.ts` report as reachable
    # by a job in a different package that cannot see it. A reachability check
    # that answers "yes" for the wrong reason is worse than one that answers
    # "no": it retires debt that is still owed.
    if surface.config.parent != inv.cwd:
        return False

    args = args[1:]

    grep: list[str] = []
    paths: list[str] = []
    skip_next = False
    for idx, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if arg in {"-g", "--grep"}:
            if idx + 1 < len(args):
                grep.append(args[idx + 1])
            skip_next = True
        elif arg.startswith("--grep="):
            grep.append(arg.split("=", 1)[1])
        elif arg.startswith("-"):
            continue
        else:
            paths.append(arg)

    if paths:
        # Positional args are path substrings, matched against the file path.
        target = spec.relative_to(inv.cwd).as_posix() if is_within(spec, inv.cwd) else rel(spec)
        if not any(p.strip("./") in target for p in paths):
            return False

    if not grep:
        return True

    titles, dynamic = spec_titles(spec)
    for pattern in grep:
        try:
            compiled = re.compile(pattern)
        except re.error:
            compiled = re.compile(re.escape(pattern))
        if any(compiled.search(t) for t in titles):
            return True
        if dynamic and any(compiled.search(t) for t in titles):
            return True
    return False


def is_within(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True


def vitest_config_arg(inv: Invocation) -> str:
    """Which config this invocation selects; vitest defaults to `vitest.config.ts`."""
    args = inv.argv[1:]
    for idx, arg in enumerate(args):
        if arg in {"-c", "--config"} and idx + 1 < len(args):
            return Path(args[idx + 1]).name
        if arg.startswith("--config="):
            return Path(arg.split("=", 1)[1]).name
    return "vitest.config.ts"


def vitest_reaches(inv: Invocation, surface: Surface, spec: Path) -> bool:
    if surface.root != inv.cwd:
        return False
    # A `--config` invocation only collects through THAT config's include/exclude.
    if vitest_config_arg(inv) != surface.config.name:
        return False
    # `os.path.relpath`, not `Path.relative_to`: include patterns may escape the
    # surface (the frontend collects `../../styles/ui/**`).
    relpath = os.path.relpath(spec, surface.root).replace(os.sep, "/")
    for pattern in surface.exclude:
        if glob_to_regex(pattern).match(relpath):
            return False
    return any(glob_to_regex(p).match(relpath) for p in surface.include)


def pytest_reaches(inv: Invocation, test_file: Path) -> bool:
    args = [a for a in inv.argv[1:] if not a.startswith("-")]
    # Drop values that belong to option flags (`-k EXPR`, `-p name`, ...).
    values_of_flags = set()
    for idx, arg in enumerate(inv.argv[1:]):
        if arg in {"-k", "-m", "-p", "-n", "--tb", "--rootdir"} and idx + 1 < len(inv.argv[1:]):
            values_of_flags.add(inv.argv[1:][idx + 1])
    args = [a for a in args if a not in values_of_flags]

    if not args:
        return is_within(test_file, inv.cwd)
    for arg in args:
        target = (inv.cwd / arg).resolve()
        if target == test_file or (target.is_dir() and is_within(test_file, target)):
            return True
    return False


def unittest_reaches(inv: Invocation, test_file: Path) -> bool:
    argv = inv.argv[1:]
    if not argv or argv[0] != "discover":
        return False
    start = "."
    pattern = "test*.py"
    for idx, arg in enumerate(argv):
        if arg in {"-s", "--start-directory"} and idx + 1 < len(argv):
            start = argv[idx + 1]
        if arg in {"-p", "--pattern"} and idx + 1 < len(argv):
            pattern = argv[idx + 1].strip("\"'")
    root = (inv.cwd / start).resolve()
    if not is_within(test_file, root):
        return False
    return bool(glob_to_regex(pattern).match(test_file.name))


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def main() -> int:
    invocations = [
        inv
        for inv in collect_invocations()
        # `playwright install` is setup, not a test run; counting it would
        # overstate how much CI actually executes.
        if not (inv.tool == "playwright" and inv.argv[1:2] != ["test"])
    ]
    if not invocations:
        print(
            "FAIL: parsed 0 test invocations from .github/workflows — the parser is "
            "broken, and a check that finds nothing would report everything reachable.",
            file=sys.stderr,
        )
        return 1

    unreachable: list[tuple[str, str]] = []
    total = 0

    playwright_surfaces = discover_playwright_surfaces()
    vitest_surfaces = discover_vitest_surfaces()

    for surface in playwright_surfaces:
        for spec in surface.files:
            total += 1
            if not any(
                playwright_reaches(inv, surface, spec)
                for inv in invocations
                if inv.tool == "playwright"
            ):
                unreachable.append((rel(spec), "playwright: no CI command selects this spec"))

    # A surface may see a file another surface owns (`legal-search/api` has
    # three vitest configs over one `src/`), so reachability is the union over
    # every (surface, invocation) pair and each file is counted exactly once.
    vitest_files: dict[Path, list[Surface]] = {}
    for surface in vitest_surfaces:
        for spec in surface.files:
            vitest_files.setdefault(spec, []).append(surface)

    for spec, surfaces in sorted(vitest_files.items()):
        total += 1
        if not any(
            vitest_reaches(inv, surface, spec)
            for surface in surfaces
            for inv in invocations
            if inv.tool == "vitest"
        ):
            configs = ", ".join(rel(s.config) for s in surfaces)
            unreachable.append((rel(spec), f"vitest: not collected by any of {configs}"))

    claimed = {f for s in playwright_surfaces + vitest_surfaces for f in s.files}
    for test_file in discover_python_tests(claimed):
        total += 1
        reached = any(
            pytest_reaches(inv, test_file) for inv in invocations if inv.tool == "pytest"
        ) or any(unittest_reaches(inv, test_file) for inv in invocations if inv.tool == "unittest")
        if not reached:
            unreachable.append((rel(test_file), "python: no CI pytest/unittest invocation collects it"))

    unreachable_paths = {p for p, _ in unreachable}
    new = [(p, why) for p, why in unreachable if p not in KNOWN_UNREACHABLE]
    stale = sorted(set(KNOWN_UNREACHABLE) - unreachable_paths)

    print(f"Scanned {total} test files against {len(invocations)} CI test invocations.")
    print(f"Unreachable: {len(unreachable)} ({len(KNOWN_UNREACHABLE)} registered as known debt).")

    if KNOWN_UNREACHABLE:
        print("\nKnown-unreachable register (these run nowhere; the count is the point):")
        for path in sorted(KNOWN_UNREACHABLE):
            marker = " " if path in unreachable_paths else " [STALE]"
            print(f"  - {path}{marker}\n      {KNOWN_UNREACHABLE[path]}")

    if new:
        print(
            f"\nFAIL: {len(new)} test file(s) that no CI job can reach and that are "
            "not registered:\n",
            file=sys.stderr,
        )
        for path, why in sorted(new):
            print(f"  {path}\n    {why}", file=sys.stderr)
        print(
            "\nA committed test that never runs is not coverage — it is the appearance\n"
            "of coverage, which is worse, because it stops anyone from looking.\n"
            "Either wire it into a CI job (tag it, add it to a script's path list, or\n"
            "give its surface a job), or register it in KNOWN_UNREACHABLE in\n"
            "scripts/check_test_reachability.py with a reason. See ADR-0040.\n",
            file=sys.stderr,
        )

    if stale:
        print(
            f"\nFAIL: {len(stale)} KNOWN_UNREACHABLE entr(y/ies) are stale — the file is "
            "now reachable or gone. Delete them:\n",
            file=sys.stderr,
        )
        for path in stale:
            print(f"  {path}", file=sys.stderr)

    if new or stale:
        return 1

    print("\nTest reachability: OK (no unregistered unreachable test files).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

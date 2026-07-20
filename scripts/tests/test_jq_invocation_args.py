"""Every `$var` in a jq program must be declared by its own invocation.

jq aborts with `$x is not defined` at RUN time. `bash -n` and `shellcheck` both
pass such a script — they see well-formed shell around an opaque string — so
nothing in the repo caught it when `--arg run_mode` was attached to the wrong
`jq -n` call in `ch-fedlex-compose-e2e.sh`: declared on the source-creation
payload that never referenced it, missing from the summary payload that did.

The failure mode is the expensive one. That script runs on a nightly cron, and
the summary is the LAST step: it created a source, executed a live run, polled
document-intelligence and asserted searchability, then died while writing the
evidence — burning the whole run to report a variable typo.

This gate parses each `jq` invocation and checks the program only references
variables that invocation declares. It is deliberately conservative: anything it
cannot parse confidently is skipped, and it asserts a floor on how many
invocations it found so a broken parser fails loudly instead of passing
vacuously (the #605/#675/#744 pattern).
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]

# jq builtins that are not caller-supplied.
_BUILTIN_VARS = {"ENV", "__loc__", "ARGS"}

# `--arg name value` / `--argjson name value` / `--slurpfile` / `--rawfile`.
_DECLARE_RE = re.compile(r"--(?:arg|argjson|slurpfile|rawfile)\s+([A-Za-z_][A-Za-z0-9_]*)")
# `$name` inside the program.
_REFERENCE_RE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")
# A jq invocation: `jq` + flags, then a single-quoted program. Shell single
# quotes cannot contain an escaped single quote, so `'[^']*'` is exact.
#
# The flags may only cross a newline via an explicit `\` continuation. Without
# that restriction the match runs from a `jq` on one line to an unrelated
# single-quoted string many lines later (a `trap 'rm -f "$TMP"'`, say) and
# reports variables that were never part of a jq program at all.
_INVOCATION_RE = re.compile(r"\bjq\b(?P<flags>(?:[^'\n]|\\\n)*?)'(?P<program>[^']*)'")
# jq string literals may legitimately contain a `$` — `."$comment"` selects a key
# named `$comment`. Strip them before looking for variable references.
_JQ_STRING_RE = re.compile(r'"(?:[^"\\]|\\.)*"')


def _invocations(text: str):
    for match in _INVOCATION_RE.finditer(text):
        flags, program = match.group("flags"), match.group("program")
        # `--args`/`--jsonargs` feed $ARGS.positional; `-r`/`-n` etc. are noise.
        declared = set(_DECLARE_RE.findall(flags))
        referenced = set(_REFERENCE_RE.findall(_JQ_STRING_RE.sub('""', program))) - _BUILTIN_VARS
        # A jq program may bind its own variables with `... as $x`. Treat those
        # as declared so a legitimate binding is not reported.
        bound = set(re.findall(r"as\s+\$([A-Za-z_][A-Za-z0-9_]*)", program))
        yield declared, referenced - bound, program


class JqInvocationArgTests(unittest.TestCase):
    def test_every_referenced_jq_variable_is_declared_by_its_own_invocation(self) -> None:
        failures: list[str] = []
        checked = 0

        for path in sorted(SCRIPTS_DIR.glob("*.sh")):
            text = path.read_text(encoding="utf-8")
            for declared, referenced, program in _invocations(text):
                checked += 1
                missing = referenced - declared
                if missing:
                    excerpt = " ".join(program.split())[:120]
                    failures.append(
                        f"{path.name}: jq program references {sorted(missing)} "
                        f"but its invocation declares {sorted(declared) or 'nothing'} "
                        f"— program starts: {excerpt!r}"
                    )

        # A parser that silently matches nothing would make this test vacuous.
        # The repo has many jq invocations across the harnesses; require a floor.
        self.assertGreater(
            checked,
            40,
            f"Only parsed {checked} jq invocations — the parser is probably broken. "
            f"Fix it rather than lowering this floor.",
        )
        self.assertEqual(
            failures,
            [],
            "jq will abort at run time with '$x is not defined':\n" + "\n".join(failures),
        )


if __name__ == "__main__":
    unittest.main()

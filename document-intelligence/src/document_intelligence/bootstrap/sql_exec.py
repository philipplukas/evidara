"""Execute multi-statement SQL scripts (with line comments) against Spark.

The bootstrap scripts rendered by ``bronze_schemas``, ``register_surfaces``
and ``governance`` contain SQL line comments. A naive ``script.split(';')``
breaks on two edge cases: line comments that contain an embedded semicolon
(e.g. "Safe to run; re-runs are idempotent."), and semicolon-delimited
chunks whose first non-blank line is a header comment preceding the real
DDL. Both are handled here by stripping line comments before splitting.
"""


def strip_sql_line_comments(sql_script: str) -> str:
    """Return ``sql_script`` with every ``--``-style line comment removed.

    Block comments (``/* ... */``) are left intact; we do not emit them in
    the renderers.
    """

    return "\n".join(line for line in sql_script.splitlines() if not line.lstrip().startswith("--"))


def iter_sql_statements(sql_script: str):
    """Yield non-empty semicolon-delimited statements from ``sql_script``."""

    for raw_statement in strip_sql_line_comments(sql_script).split(";"):
        statement = raw_statement.strip()
        if statement:
            yield statement


def execute_sql_script(spark, sql_script: str) -> None:
    """Execute every statement in ``sql_script`` via ``spark.sql``."""

    for statement in iter_sql_statements(sql_script):
        spark.sql(statement)

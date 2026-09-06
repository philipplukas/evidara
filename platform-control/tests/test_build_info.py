"""Build provenance must be honest about not knowing.

The whole value of `/health` reporting a version is that it can be trusted to say
what is deployed. A version that is silently wrong — an empty string rendered as a
blank, or a developer's working tree reported as production — is worse than
`unknown`, because it looks like an answer.
"""

from __future__ import annotations

import pytest

from platform_control.build_info import UNKNOWN, BuildInfo, get_build_info


@pytest.fixture(autouse=True)
def _clear_cache():
    """`get_build_info` is `lru_cache`d, so each test must start from empty."""
    get_build_info.cache_clear()
    yield
    get_build_info.cache_clear()


def test_reads_the_baked_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVIDARA_GIT_SHA", "4932ec2c29ee31ab591bd9dbb9caa3f59a1e0b13")
    monkeypatch.setenv("EVIDARA_BUILD_DATE", "2026-09-06T10:25:00Z")

    info = get_build_info()

    assert info.git_sha == "4932ec2c29ee31ab591bd9dbb9caa3f59a1e0b13"
    assert info.build_date == "2026-09-06T10:25:00Z"
    assert info.short_sha == "4932ec2c"


def test_absent_env_reports_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVIDARA_GIT_SHA", raising=False)
    monkeypatch.delenv("EVIDARA_BUILD_DATE", raising=False)

    info = get_build_info()

    assert info.git_sha == UNKNOWN
    assert info.build_date == UNKNOWN
    assert info.short_sha == UNKNOWN


@pytest.mark.parametrize("blank", ["", "   ", "\n", "\t "])
def test_blank_env_reports_unknown_not_empty_string(
    monkeypatch: pytest.MonkeyPatch, blank: str
) -> None:
    """The Dockerfiles default both ARGs to `""`.

    An image built without `--build-arg` therefore SETS the variable to empty
    rather than leaving it absent. Without `_clean`, `/health` would answer with
    an empty `git_sha` and the UI would render a blank where a version belongs —
    which reads as "no version" rather than "version unknown". Delete the
    whitespace handling in `_clean` and this test goes red.
    """
    monkeypatch.setenv("EVIDARA_GIT_SHA", blank)
    monkeypatch.setenv("EVIDARA_BUILD_DATE", blank)

    info = get_build_info()

    assert info.git_sha == UNKNOWN
    assert info.build_date == UNKNOWN


def test_never_falls_back_to_the_local_git_checkout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guard against "helpfully" resolving the version at runtime.

    Reading `git rev-parse` when the env is unset would make a developer's working
    tree report as the deployed version, and would make this very test suite report
    a version. `unknown` is the only correct answer without a bake.
    """
    monkeypatch.delenv("EVIDARA_GIT_SHA", raising=False)

    assert get_build_info().git_sha == UNKNOWN


def test_short_sha_truncates_to_repo_citation_length() -> None:
    info = BuildInfo(git_sha="0123456789abcdef" * 2 + "01234567", build_date="2026-01-01T00:00:00Z")
    assert info.short_sha == "01234567"
    assert len(info.short_sha) == 8

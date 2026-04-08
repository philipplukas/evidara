from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer

from evidara_cli.main import pc_ris_bootstrap


def test_ris_bootstrap_exits_when_script_missing(tmp_path: Path) -> None:
    with pytest.raises(typer.Exit) as exc_info:
        pc_ris_bootstrap(
            max_pages=1,
            applikation=None,
            process_di=False,
            repo_root=tmp_path,
        )
    assert exc_info.value.exit_code == 1


def test_ris_bootstrap_invokes_bootstrap_script(tmp_path: Path) -> None:
    (tmp_path / "contracts" / "api").mkdir(parents=True)
    script = tmp_path / "scripts" / "bootstrap-ris-source.py"
    script.parent.mkdir(parents=True)
    script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    env = {
        "EVIDARA_PLATFORM_CONTROL_URL": "http://pc.test",
        "EVIDARA_PLATFORM_CONTROL_API_KEY": "secret",
    }
    with patch.dict(os.environ, env, clear=False):
        with patch("evidara_cli.main.subprocess.run") as run_mock:
            run_mock.return_value = MagicMock(returncode=0)
            pc_ris_bootstrap(
                max_pages=2,
                applikation="Vfgh",
                process_di=True,
                repo_root=tmp_path,
            )
    run_mock.assert_called_once()
    _args, kwargs = run_mock.call_args
    assert kwargs["cwd"] == tmp_path
    cmd = run_mock.call_args[0][0]
    assert str(script) in cmd
    assert cmd[cmd.index("--max-pages") + 1] == "2"
    assert "--applikation" in cmd and cmd[cmd.index("--applikation") + 1] == "Vfgh"
    assert "--process-di" in cmd
    assert "--api-key" in cmd and cmd[cmd.index("--api-key") + 1] == "secret"

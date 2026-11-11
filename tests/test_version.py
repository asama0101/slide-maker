"""バージョンの表記は plugin.json（正本）とコードで一致させる。"""

# ruff: noqa: S101  # pytest の assert
import json
import os
import subprocess
import sys

import pytest
import slide_maker


@pytest.fixture
def manifest_version(pkg) -> str:
    manifest = json.loads((pkg / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    return manifest["version"]


def _run_cli(pkg, home, *args):
    """入口を実際に子プロセスで起動する。環境変数 SLIDE_MAKER_HOME は tmp_path の下を指す。"""
    env = {**os.environ, "SLIDE_MAKER_HOME": str(home), "PYTHONUTF8": "1"}
    return subprocess.run(  # noqa: S603  # 自分の入口を sys.executable で起動する（外部入力なし）
        [sys.executable, "-m", "slide_maker", *args], cwd=pkg, capture_output=True, text=True, encoding="utf-8", env=env
    )


def test_コードの版は_plugin_json_と一致する(manifest_version):
    assert slide_maker.__version__ == manifest_version


def test_version_フラグは終了コード0で_plugin_json_の版を表示する(pkg, tmp_path, manifest_version):
    r = _run_cli(pkg, tmp_path / "home", "--version")
    assert (r.returncode, r.stdout.strip()) == (0, f"slide-maker {manifest_version}")


def test_doctor_は_plugin_json_の版を報告する(pkg, tmp_path, manifest_version):
    r = _run_cli(pkg, tmp_path / "home", "doctor")
    assert r.returncode == 0
    assert any(x.startswith(f"[情報] プラグインのバージョン: v{manifest_version}") for x in r.stdout.splitlines())

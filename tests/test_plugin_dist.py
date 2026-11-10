"""配布物の検査（plugin-rules F1 の 5・7・8）と、空白・日本語を含む置き場での入口の動作（H5）。"""

# ruff: noqa: S101  # pytest の assert
import json
import shutil
import subprocess

import pytest

from tests._paths import PKG, REPO
from tests.test_run_entry import make_venv, run_entry, text

# 配布に必要なファイル（リポジトリ直下からの相対パス）
DIST_FILES = [
    "plugins/slide-maker/.claude-plugin/plugin.json",
    "plugins/slide-maker/skills/create/SKILL.md",
    "plugins/slide-maker/run.py",
    "plugins/slide-maker/requirements.txt",
]
CLAUDE = shutil.which("claude")


def git_files() -> set[str] | None:
    """git ls-files の一覧。git が使えない・リポジトリでないときは None。"""
    git = shutil.which("git")
    if git is None:
        return None
    r = subprocess.run(  # noqa: S603  # 引数は配列、実行ファイルは PATH 上の git
        [git, "-C", str(REPO), "ls-files"], capture_output=True, text=True, encoding="utf-8", check=False
    )
    return set(r.stdout.splitlines()) if r.returncode == 0 else None


def test_MCP_を同梱していない():
    assert not (PKG / ".mcp.json").exists()
    assert not (REPO / ".mcp.json").exists()
    for f in (PKG / ".claude-plugin" / "plugin.json", REPO / ".claude-plugin" / "marketplace.json"):
        assert "mcpServers" not in json.loads(f.read_text(encoding="utf-8")), f.name


def test_配布に必要なファイルが_git_管理下にある():
    tracked = git_files()
    if tracked is None:
        pytest.skip("git で調べられない（環境要因）")
    missing = [f for f in DIST_FILES if f not in tracked]
    missing += [
        p.relative_to(REPO).as_posix()
        for p in sorted((PKG / "pptx_deck").glob("*.py"))
        if p.relative_to(REPO).as_posix() not in tracked
    ]
    assert missing == []


@pytest.mark.skipif(CLAUDE is None, reason="claude コマンドがない（環境要因）")
@pytest.mark.parametrize(
    ("target", "extra"), [(PKG, ["--strict"]), (REPO, [])], ids=["プラグイン_strict", "リポジトリ直下"]
)
def test_claude_plugin_validate_が通る(target, extra):
    r = subprocess.run(  # noqa: S603  # 引数は配列、実行ファイルは PATH 上の claude
        [CLAUDE, "plugin", "validate", str(target), *extra],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=120,
    )
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.slow
def test_空白と日本語を含む置き場でも_doctor_が動く(tmp_path):
    """置き場（--data）を空白・日本語を含むパスにして run.py doctor を実際に起動する。"""
    home = tmp_path / "ユーザー 名" / "data dir"
    make_venv(home, with_deps=True)
    r = run_entry("--data", str(home), "doctor", cwd=tmp_path)
    assert r.returncode == 0, text(r.stderr)
    assert json.loads(text(r.stdout))["venv"] == str(home / "venv")

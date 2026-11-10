"""入口 run.py: --data / SLIDE_MAKER_HOME の解釈、専用 venv の Python での実行、案内と終了コード。

run.py は実際に子プロセスとして起動する。専用 venv は tmp_path の下に本物の venv を作り、
実行中の環境の site-packages を .pth で見せて「そろっている venv」にする（空のままなら「不足している venv」）。
"""

# ruff: noqa: S101  # pytest の assert
import importlib.util
import json
import os
import subprocess
import sys
import sysconfig
import venv
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parent.parent / "plugins" / "slide-maker"
RUN_PY = PKG / "run.py"


@pytest.fixture(scope="module")
def run():
    """run.py を import したモジュール。
    split_data・check_data の単体確認と setup の配線の確認に使う。値は変更しない。"""
    spec = importlib.util.spec_from_file_location("pptx_run_entry", RUN_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_venv(home: Path, with_deps: bool) -> Path:
    """home/venv に本物の venv を作る。
    with_deps なら、実行中の環境の site-packages を見せる（そろっている venv になる）。"""
    target = home / "venv"
    venv.EnvBuilder(with_pip=False).create(target)
    if with_deps:
        (target / "Lib" / "site-packages" / "deps.pth").write_text(
            sysconfig.get_paths()["purelib"] + "\n", encoding="utf-8"
        )
    return target / "Scripts" / "python.exe"


@pytest.fixture
def good_home(tmp_path) -> Path:
    home = tmp_path / "home"
    make_venv(home, with_deps=True)
    return home


def run_entry(*argv, env=None, cwd=None, drop_utf8=False):
    """python run.py <argv> を子プロセスで実行する。SLIDE_MAKER_HOME は env で渡したときだけ設定する。"""
    drop = {"SLIDE_MAKER_HOME"} | ({"PYTHONUTF8", "PYTHONIOENCODING"} if drop_utf8 else set())
    e = {**{k: v for k, v in os.environ.items() if k not in drop}, **(env or {})}
    return subprocess.run(  # noqa: S603  # 自分の入口を sys.executable で起動する（外部入力なし）
        [sys.executable, str(RUN_PY), *argv], capture_output=True, env=e, cwd=cwd
    )


def text(data: bytes) -> str:
    return data.decode("utf-8")


# ---- split_data / check_data ----


def test_先頭の_data_は取り除かれて残りの引数が返る(run):
    assert run.split_data(["--data", "C:/d", "build", "x"]) == ("C:/d", ["build", "x"])


def test_先頭以外の_data_はサブコマンドの引数として残る(run):
    argv = ["build", "--data", "C:/d"]
    assert run.split_data(argv) == (None, argv)


def test_値のない_data_は_ValueError(run):
    with pytest.raises(ValueError, match="置き場のパスがありません"):
        run.split_data(["--data"])


@pytest.mark.parametrize(
    "value",
    ["C:/Users/x/data", r"C:\Users\x\data", "C:/Users/日本語 name/data"],
    ids=["スラッシュ", "バックスラッシュ", "日本語と空白"],
)
def test_絶対パスはそのまま通る(run, value):
    assert run.check_data(value) == value


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("${CLAUDE_PLUGIN_DATA}", "置き換わっていません"),
        ("C:/${CLAUDE_PLUGIN_DATA}", "置き換わっていません"),
        ("", "絶対パスで指定"),
        ("  ", "絶対パスで指定"),
        ("rel/dir", "絶対パスで指定"),
        ("/no/drive", "絶対パスで指定"),
    ],
    ids=["未置換", "途中に未置換", "空", "空白のみ", "相対パス", "ドライブなし"],
)
def test_不正な置き場は_ValueError(run, value, message):
    with pytest.raises(ValueError, match=message):
        run.check_data(value)


# ---- 置き場の解釈 ----


def test_置き場の指定がなければ終了コード3で指定方法を案内する(tmp_path):
    r = run_entry("doctor", cwd=tmp_path)
    out = text(r.stdout)
    assert r.returncode == 3
    assert "setup" in out
    assert "--data" in out
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "argv",
    [["--data", "rel", "doctor"], ["--data", "${CLAUDE_PLUGIN_DATA}", "doctor"], ["--data"]],
    ids=["相対パス", "未置換", "値なし"],
)
def test_不正な_data_は何もせず終了コード2(argv, tmp_path):
    r = run_entry(*argv, cwd=tmp_path)
    assert r.returncode == 2
    assert "エラー" in text(r.stderr)
    assert text(r.stdout) == ""
    assert list(tmp_path.iterdir()) == []


def test_不正な_data_の_setup_は何も作らず終了コード2(tmp_path):
    r = run_entry("--data", "rel", "setup", "--yes", cwd=tmp_path)
    assert r.returncode == 2
    assert list(tmp_path.iterdir()) == []  # 相対パスのまま進めば cwd の下に作られてしまう


@pytest.mark.parametrize("value", ["rel/dir", "${X}"], ids=["相対パス", "未置換"])
def test_環境変数の置き場が不正なら何もせず終了コード2(value, tmp_path):
    r = run_entry("--data", str(tmp_path / "d"), "doctor", env={"SLIDE_MAKER_HOME": value}, cwd=tmp_path)
    assert r.returncode == 2
    assert "SLIDE_MAKER_HOME" in text(r.stderr)
    assert text(r.stdout) == ""
    assert not (tmp_path / "d").exists()


# ---- 専用 venv の Python での実行 ----


@pytest.mark.slow
def test_システムの_python_ではなく専用_venv_の_python_で_slide_maker_を実行する(good_home):
    r = run_entry("--data", str(good_home), "doctor")
    assert r.returncode == 0, text(r.stderr)
    out = json.loads(text(r.stdout))
    assert Path(out["python"]["path"]).samefile(good_home / "venv" / "Scripts" / "python.exe")
    assert not Path(out["python"]["path"]).samefile(sys.executable)
    assert out["venv"] == str(good_home / "venv")  # 置き場が子プロセスへ渡っている


@pytest.mark.slow
def test_環境変数の置き場だけでも実行できる(good_home):
    r = run_entry("doctor", env={"SLIDE_MAKER_HOME": str(good_home)})
    assert r.returncode == 0, text(r.stderr)
    assert json.loads(text(r.stdout))["venv"] == str(good_home / "venv")


@pytest.mark.slow
def test_環境変数の置き場は_data_より優先される(good_home, tmp_path):
    other = tmp_path / "other"
    r = run_entry("--data", str(other), "doctor", env={"SLIDE_MAKER_HOME": str(good_home)})
    assert r.returncode == 0, text(r.stderr)
    assert json.loads(text(r.stdout))["venv"] == str(good_home / "venv")
    assert not other.exists()


@pytest.mark.slow
def test_子プロセスの終了コードを返し_端末の文字コードによらず_UTF8_で出す(good_home, tmp_path):
    r = run_entry("--data", str(good_home), "lint-script", str(tmp_path / "nai.md"), drop_utf8=True)
    assert r.returncode == 2
    assert "エラー" in text(r.stderr)  # 子プロセスに PYTHONUTF8=1 が渡っていなければ UTF-8 にならない


@pytest.mark.slow
def test_先頭以外の_data_はサブコマンドへ渡り_argparse_が拒否する(good_home):
    r = run_entry("doctor", "--data", "C:/d", env={"SLIDE_MAKER_HOME": str(good_home)})
    assert r.returncode == 2
    assert "unrecognized arguments: --data C:/d" in text(r.stderr)


@pytest.mark.slow
def test_doctor_だけがキャッシュを使わず調べ直して更新する(good_home):
    cache = good_home / "probe-cache.json"
    run_entry("--data", str(good_home), "lint-script", "nai.md")
    first = cache.stat().st_mtime_ns
    run_entry("--data", str(good_home), "lint-script", "nai.md")
    assert cache.stat().st_mtime_ns == first  # 通常の実行はキャッシュを使い、書き直さない
    r = run_entry("--data", str(good_home), "doctor")
    assert r.returncode == 0
    assert cache.stat().st_mtime_ns > first  # doctor は調べ直して書き直す


# ---- 実行できない venv ----


def test_venv_がなければ終了コード3で_setup_yes_を案内し何も実行しない(tmp_path):
    home = tmp_path / "d"
    r = run_entry("--data", str(home), "build", "x", cwd=tmp_path)
    out = text(r.stdout)
    assert r.returncode == 3
    assert "仮想環境がありません" in out
    assert "setup --yes" in out
    assert str(home / "venv") in out
    assert not home.exists()


def test_missing_venv_exit_3_and_guides_setup(tmp_path):
    r = run_entry("--data", str(tmp_path / "d"), "build", "x", cwd=tmp_path)
    out = text(r.stdout)
    assert r.returncode == 3
    assert "setup --yes" in out
    assert "--system" not in out


def test_導入が不足している_venv_は終了コード3で不足を案内する(tmp_path):
    home = tmp_path / "d"
    make_venv(home, with_deps=False)
    r = run_entry("--data", str(home), "doctor")
    out = text(r.stdout)
    assert r.returncode == 3
    assert "playwright が未導入です" in out
    assert "setup --yes" in out


@pytest.mark.parametrize("legacy", [True, False], ids=["旧い_venv_あり", "旧い_venv_なし"])
def test_旧い_venv_があれば使わないと一言案内する(tmp_path, legacy):
    local = tmp_path / "local"
    (local / ("pptx-deck" if legacy else "other") / "venv").mkdir(parents=True)
    r = run_entry("--data", str(tmp_path / "d"), "doctor", env={"LOCALAPPDATA": str(local)})
    out = text(r.stdout)
    assert r.returncode == 3
    assert ("使いません" in out) is legacy
    assert out.count("使いません") == int(legacy)


# ---- setup は run.py が直接処理する ----


def test_承認なしの_setup_は子プロセスに渡さず案内だけして終了コード3(tmp_path):
    home = tmp_path / "d"
    r = run_entry("--data", str(home), "setup", cwd=tmp_path)
    assert r.returncode == 3  # 子プロセスに渡れば argparse の終了コード 2 になる
    assert str(home / "venv") in text(r.stdout)
    assert not home.exists()


@pytest.mark.slow
def test_yes_付きの_setup_は_venv_を作らずに_pip_と_chromium_の導入へ進む(run, good_home, pkg, monkeypatch, capsys):
    monkeypatch.setenv("SLIDE_MAKER_HOME", str(good_home))  # run.main が環境変数を書き換えるので、あとで元に戻す
    commands = []
    monkeypatch.setattr(run.subprocess, "call", lambda cmd, *a, **k: commands.append(list(cmd)) or 0)
    rc = run.main(["--data", str(good_home), "setup", "--yes"])
    assert rc == 0
    py = str(good_home / "venv" / "Scripts" / "python.exe")
    assert commands == [
        [py, "-m", "pip", "install", "-r", str(pkg / "requirements.txt")],
        [py, "-m", "playwright", "install", "chromium"],
    ]


# ---- doctor の項目別の診断 ----


def test_doctor_は項目ごとの_OK_NG_と対処法を出す(tmp_path):
    home = tmp_path / "d"
    r = run_entry("--data", str(home), "doctor")
    out = text(r.stdout)
    assert r.returncode == 3
    assert "[OK] 作成元の Python" in out
    assert "[NG] 仮想環境: ありません" in out
    assert "対処" in out
    assert "setup --yes" in out


def test_doctor_は動かない_venv_を壊れていると診断する(tmp_path):
    home = tmp_path / "d"
    py = home / "venv" / "Scripts" / "python.exe"
    py.parent.mkdir(parents=True)
    py.write_bytes(b"")  # 実行できないファイル（基底の Python が消えた venv の代わり）
    r = run_entry("--data", str(home), "doctor")
    out = text(r.stdout)
    assert r.returncode == 3
    assert "[NG] 仮想環境: 壊れています" in out
    assert "作り直" in out


def test_doctor_以外のコマンドは診断の一覧を出さない(tmp_path):
    r = run_entry("--data", str(tmp_path / "d"), "build", "x", cwd=tmp_path)
    assert "[NG]" not in text(r.stdout)

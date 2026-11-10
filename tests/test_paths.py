# ruff: noqa: S101  # pytest の assert
import sys
import tempfile

import pytest
from slide_maker import cli, paths


@pytest.fixture
def temp_root(tmp_path, monkeypatch):
    """OS の一時フォルダを tmp_path の下に向ける（確認用の画像の置き場を、実際の一時フォルダに作らない）。"""
    root = tmp_path / "os-temp"
    root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(root))
    return root


def test_プラグイン本体に入口と_slide_maker_パッケージがある(pkg):
    assert (pkg / "run.py").is_file()
    assert (pkg / "slide_maker" / "cli.py").is_file()


def test_home_dir_は環境変数_SLIDE_MAKER_HOME_を返す(monkeypatch):
    monkeypatch.setenv("SLIDE_MAKER_HOME", r"C:\x\home")
    assert str(paths.home_dir()) == r"C:\x\home"


def test_環境変数がないと_home_dir_は_RuntimeError_で止まり_LOCALAPPDATA_へ戻らない(monkeypatch, tmp_path):
    monkeypatch.delenv("SLIDE_MAKER_HOME", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))  # フォールバックしないことを確かめるため残す
    with pytest.raises(RuntimeError, match="SLIDE_MAKER_HOME"):
        paths.home_dir()


def test_venv_の_python_は置き場の下の_venv_Scripts_python_exe(monkeypatch):
    monkeypatch.setenv("SLIDE_MAKER_HOME", r"C:\x\home")
    assert str(paths.venv_python()) == r"C:\x\home\venv\Scripts\python.exe"


@pytest.mark.parametrize(
    "bad",
    ["", "  ", ".", "..", "a/b", r"a\b"],
    ids=["空", "空白のみ", "ドット1つ", "ドット2つ", "スラッシュ", "バックスラッシュ"],
)
def test_不正な名前の一時フォルダは_ValueError_で拒否される(bad, temp_root):
    with pytest.raises(ValueError, match="一時フォルダの名前が不正です"):
        paths.temp_dir(bad)
    assert list(temp_root.iterdir()) == []  # 拒否したときは何も作らない


def test_clean_は空の成果物名なら終了コード2で止まり何も消さない(temp_root, tmp_path, capsys):
    (temp_root / "slide-maker").mkdir()
    (temp_root / "slide-maker" / "keep.txt").write_text("x", encoding="utf-8")
    rc = cli.main(["clean", tmp_path.anchor])  # ドライブ直下は成果物名が空になる
    assert rc == 2
    assert "エラー" in capsys.readouterr().err
    assert (temp_root / "slide-maker" / "keep.txt").read_text(encoding="utf-8") == "x"


def test_build_は空の成果物名なら終了コード2で止まり測定しない(deck_base, monkeypatch, capsys, temp_root):
    # 空の成果物名はドライブ直下でしか起きず、そこへは作れないので、成果物名の決定だけを差し替える
    assert cli.main(["init", str(deck_base)]) == 0
    capsys.readouterr()
    monkeypatch.setattr(paths, "deck_name", lambda work: "")
    monkeypatch.setitem(sys.modules, "playwright", None)  # 測定まで進めば ModuleNotFoundError になる
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    rc = cli.main(["build", str(deck_base)])
    cap = capsys.readouterr()
    assert rc == 2
    assert "エラー" in cap.err
    assert cap.out == ""


def test_pptx_のパスから元データのフォルダを決める(tmp_path):
    expected = (tmp_path / "out" / "slide-maker-source" / "a").resolve()
    assert paths.resolve_work(tmp_path / "out" / "a.pptx") == expected


def test_作業フォルダのパスはそのまま返り_deck_dir_は出力先_deck_name_は成果物名(tmp_path):
    work = tmp_path / "out" / "slide-maker-source" / "deck"
    resolved = paths.resolve_work(work)
    assert resolved == work.resolve()
    assert paths.deck_dir(resolved) == (tmp_path / "out").resolve()
    assert paths.deck_name(resolved) == "deck"


def test_旧配置のパスは未対応のエラーになる_template_json_がある場合(tmp_path):
    old = tmp_path / "demo"
    (old / "source").mkdir(parents=True)
    (old / "source" / "template.json").write_text("{}", encoding="utf-8")
    with pytest.raises(paths.LayoutError, match="旧配置は未対応"):
        paths.resolve_work(old)


def test_旧配置のパスは未対応のエラーになる_source_を渡した場合(tmp_path):
    with pytest.raises(paths.LayoutError, match="旧配置は未対応"):
        paths.resolve_work(tmp_path / "demo" / "source")


def test_slide_maker_source_の外のパスは_LayoutError(tmp_path):
    with pytest.raises(paths.LayoutError, match="slide-maker-source"):
        paths.resolve_work(tmp_path / "x")


def test_成果物名が空なら_LayoutError(tmp_path):
    with pytest.raises(paths.LayoutError):
        paths.resolve_work(tmp_path.anchor)


def test_cli_は_LayoutError_を終了コード2とエラー表示にする(tmp_path, capsys):
    rc = cli.main(["build", str(tmp_path / "x")])
    assert rc == 2
    assert "エラー" in capsys.readouterr().err


def test_旧配置の_pptx_パスは未対応のエラーになる(tmp_path):
    old = tmp_path / "demo"
    (old / "source").mkdir(parents=True)
    (old / "source" / "template.json").write_text("{}", encoding="utf-8")
    with pytest.raises(paths.LayoutError, match="旧配置は未対応"):
        paths.resolve_work(old / "demo.pptx")

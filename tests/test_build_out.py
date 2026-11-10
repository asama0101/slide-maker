"""build の出力先（--out・上書きの確認・書き込めない出力先）。

測定・検査・PPTX の書き出しは実物を通す（ブラウザを使う分は slow）。
「測定の前に止まる」ことは、Playwright を読み込めなくして（no_browser）、測定まで進めば別の失敗になる形で確かめる。
"""

# ruff: noqa: S101  # pytest の assert
import json
import shutil
import stat
import sys
import tempfile
from pathlib import Path

import pytest
from pptx import Presentation
from pptx_deck import cli, paths

from tests._flow import finalize_all, write_slide

PKG = Path(__file__).resolve().parent.parent / "plugins" / "slide-maker"


@pytest.fixture(scope="module")
def pristine_deck(tmp_path_factory) -> Path:
    """init → 選択結果 → finalize まで進めた成果物（final.html つき）。
    どのテストも変更しない（コピーして使う）。"""
    base = tmp_path_factory.mktemp("pristine") / "out" / "pptx-deck-source" / "deck"
    assert cli.main(["init", str(base)]) == 0
    work = paths.resolve_work(base)
    cover = (PKG / "assets" / "components" / "layouts" / "cover.html").read_text(encoding="utf-8")
    write_slide(work / "slides", "01", cover)
    assert finalize_all(work, choices_dir=base.parent.parent / "choices-src") == 0
    assert (work / "final.html").is_file()
    return base


@pytest.fixture
def work(pristine_deck, tmp_path) -> Path:
    """final.html まで進んだ成果物（作業フォルダ）。テストごとのコピー。"""
    base = tmp_path / "out" / "pptx-deck-source" / "deck"
    shutil.copytree(pristine_deck, base)
    return paths.resolve_work(base)


@pytest.fixture
def temp_root(tmp_path, monkeypatch):
    """確認用の画像の置き場（OS の一時フォルダ）を tmp_path の下に向ける。"""
    root = tmp_path / "os-temp"
    root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(root))
    return root


@pytest.fixture
def no_browser(monkeypatch):
    """Playwright を読み込めなくする。測定（ブラウザの起動）まで進んだら ModuleNotFoundError で落ちる。"""
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)


def build(work, out, capsys, force=False):
    """cmd_build を実物のまま呼ぶ。(終了コード, stdout, stderr)。"""
    argv = ["build", str(work), "--out", str(out)] + (["--force"] if force else [])
    capsys.readouterr()
    rc = cli.main(argv)
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


def _slide_count(pptx: Path) -> int:
    return len(Presentation(str(pptx)).slides)


# ---- --out の上書き ----


def test_既存の出力先は_force_なしで終了コード4で止まり中身を変えない(work, tmp_path, temp_root, no_browser, capsys):
    out = tmp_path / "other.pptx"
    out.write_bytes(b"old")
    rc, stdout, err = build(work, out, capsys)
    assert rc == 4
    assert "--force" in err
    assert out.read_bytes() == b"old"
    assert stdout == ""  # 測定・書き出しまで進んでいない（進めば結果の JSON が出る）


@pytest.mark.slow
def test_force_付きなら既存の出力先を新しい_pptx_で上書きする(work, tmp_path, temp_root, capsys):
    out = tmp_path / "other.pptx"
    out.write_bytes(b"old")
    rc, stdout, _ = build(work, out, capsys, force=True)
    assert rc == 0
    assert json.loads(stdout)["pptx"] == str(out)
    assert _slide_count(out) == 1


@pytest.mark.slow
def test_出力先が無ければ親フォルダを作って_pptx_を出す(work, tmp_path, temp_root, capsys):
    out = tmp_path / "sub" / "new.pptx"
    rc, _, _ = build(work, out, capsys)
    assert rc == 0
    assert _slide_count(out) == 1


# ---- 既定と同じパスを --out に渡す ----


def test_既定と同じパスの_out_が既存なら_force_なしで終了コード4で止まり中身を変えない(
    work, temp_root, no_browser, capsys
):
    out = paths.deck_dir(work) / "deck.pptx"
    out.write_bytes(b"original")
    rc, stdout, err = build(work, out, capsys)
    assert rc == 4
    assert "--force" in err
    assert "--out" in err
    assert out.read_bytes() == b"original"
    assert stdout == ""


@pytest.mark.slow
def test_既定と同じパスの_out_が既存でも_force_なら上書きされる(work, temp_root, capsys):
    out = paths.deck_dir(work) / "deck.pptx"
    out.write_bytes(b"original")
    rc, _, _ = build(work, out, capsys, force=True)
    assert rc == 0
    assert _slide_count(out) == 1


@pytest.mark.slow
def test_初回のビルドは_pptx_が無ければ止まらず出力する(work, temp_root, capsys):
    out = paths.deck_dir(work) / "deck.pptx"
    assert not out.exists()
    rc, _, _ = build(work, out, capsys)
    assert rc == 0
    assert _slide_count(out) == 1


# ---- 書き込めない出力先 ----


def test_書き込めない出力先は測定の前に終了コード2で止まり中身を変えない(work, tmp_path, temp_root, no_browser, capsys):
    out = tmp_path / "locked.pptx"
    out.write_bytes(b"old")
    out.chmod(stat.S_IREAD)  # 読み取り専用（PowerPoint で開いている状態の代わり）
    try:
        rc, stdout, err = build(work, out, capsys, force=True)
    finally:
        out.chmod(stat.S_IWRITE | stat.S_IREAD)
    assert rc == 2
    assert "PowerPoint" in err
    assert stdout == ""
    assert out.read_bytes() == b"old"


def test_書き込み確認は既存の出力先の中身を変えない(tmp_path):
    out = tmp_path / "keep.pptx"
    out.write_bytes(b"old")
    assert cli._check_writable(out) is None
    assert out.read_bytes() == b"old"


def test_書き込み確認は無い出力先を作らず親フォルダだけ用意する(tmp_path):
    out = tmp_path / "sub" / "x.pptx"
    assert cli._check_writable(out) is None
    assert not out.exists()
    assert out.parent.is_dir()
    assert list(out.parent.iterdir()) == []  # 確認用の一時ファイルも残さない


def test_保存に失敗しても前のPPTXを壊さない(tmp_path, monkeypatch):
    from pptx.presentation import Presentation as Prs
    from pptx_deck import build, paths, template, theme

    std = paths.ASSETS / "template" / "standard.potx"
    out = tmp_path / "deck.pptx"
    out.write_bytes(b"previous")

    def broken_save(self, file):
        Path(file).write_bytes(b"half")
        raise OSError("disk full")

    monkeypatch.setattr(Prs, "save", broken_save)
    with pytest.raises(OSError, match="disk full"):
        build.build([], std, template.analyze(std), theme.derive("#1F3A5F"), out, base_dir=tmp_path)
    assert out.read_bytes() == b"previous"
    assert list(tmp_path.glob("*.tmp")) == []

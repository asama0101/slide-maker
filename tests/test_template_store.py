"""テンプレートの置き場（<置き場>/templates/）と、template-import・template-list・template-remove。

置き換えるものはない（ファイルの読み書きは tmp_path の下に実物で行う）。
CLI は cli.main を直接呼び、出力と終了コードを確かめる。
"""

# ruff: noqa: S101  # pytest の assert
import json
import shutil
from pathlib import Path

import pytest
from pptx import Presentation
from pptx_deck import cli


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    h = tmp_path / "home"
    monkeypatch.setenv("PPTX_DECK_HOME", str(h))
    return h


def make_pptx(path: Path, wide: bool = True) -> Path:
    """python-pptx の既定テンプレート（題と本文のレイアウトがある）を、16:9 かどうかを選んで保存する。"""
    prs = Presentation()
    prs.slide_width, prs.slide_height = (12192000, 6858000) if wide else (9144000, 6858000)
    prs.save(str(path))
    return path


def run(capsys, *argv) -> tuple[int, str, str]:
    rc = cli.main(list(argv))
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


def test_インポートすると置き場にコピーされ_元のファイルはそのまま(home, tmp_path, capsys):
    src = make_pptx(tmp_path / "社内標準.pptx")
    before = src.read_bytes()
    rc, out, _ = run(capsys, "template-import", str(src))
    assert rc == 0
    dst = home / "templates" / "社内標準.pptx"
    assert dst.read_bytes() == before
    assert src.read_bytes() == before
    info = json.loads(out)
    assert (info["name"], Path(info["path"])) == ("社内標準", dst)


def test_name_を渡すと_その名前で登録される(home, tmp_path, capsys):
    src = make_pptx(tmp_path / "a.pptx")
    rc, _, _ = run(capsys, "template-import", str(src), "--name", "営業部")
    assert rc == 0
    assert [p.name for p in (home / "templates").iterdir()] == ["営業部.pptx"]


def test_potx_もインポートできる(home, pkg, capsys):
    src = pkg / "assets" / "template" / "standard.potx"
    rc, _, _ = run(capsys, "template-import", str(src), "--name", "標準のコピー")
    assert rc == 0
    assert (home / "templates" / "標準のコピー.potx").is_file()


@pytest.mark.parametrize("kind", ["非16対9", "拡張子違い", "ファイルなし", "壊れたファイル"])
def test_使えないファイルは何も置かず終了コード2(home, tmp_path, capsys, kind):
    if kind == "非16対9":
        src = make_pptx(tmp_path / "w.pptx", wide=False)
    elif kind == "拡張子違い":
        src = tmp_path / "メモ.txt"
        src.write_text("x", encoding="utf-8")
    elif kind == "ファイルなし":
        src = tmp_path / "ない.pptx"
    else:
        src = tmp_path / "壊れ.pptx"
        src.write_bytes(b"not a zip")
    rc, out, err = run(capsys, "template-import", str(src))
    assert rc == 2
    assert "エラー" in err
    assert out == ""
    assert not (home / "templates").exists() or list((home / "templates").iterdir()) == []


@pytest.mark.parametrize("name", ["a/b", "a\\b", "a:b", "a*b", 'a"b', "..", " ", "a.", "a|b"])
def test_使えない文字を含む名前は終了コード2(home, tmp_path, capsys, name):
    src = make_pptx(tmp_path / "t.pptx")
    rc, _, err = run(capsys, "template-import", str(src), "--name", name)
    assert rc == 2
    assert "名前" in err
    assert not (home / "templates").exists() or list((home / "templates").iterdir()) == []


def test_同じ名前があれば終了コード4で止まり_force_で置き換える(home, tmp_path, capsys):
    old = make_pptx(tmp_path / "t.pptx", wide=True)
    run(capsys, "template-import", str(old), "--name", "標準")
    new = tmp_path / "new.pptx"
    prs = Presentation(str(old))
    prs.core_properties.title = "新しい版"
    prs.save(str(new))
    kept = (home / "templates" / "標準.pptx").read_bytes()

    rc, _, err = run(capsys, "template-import", str(new), "--name", "標準")
    assert rc == 4
    assert "--force" in err
    assert (home / "templates" / "標準.pptx").read_bytes() == kept  # 触っていない

    rc, _, _ = run(capsys, "template-import", str(new), "--name", "標準", "--force")
    assert rc == 0
    assert (home / "templates" / "標準.pptx").read_bytes() == new.read_bytes()


def test_force_で形式が変わっても_同じ名前は1つだけ残る(home, tmp_path, pkg, capsys):
    run(capsys, "template-import", str(make_pptx(tmp_path / "t.pptx")), "--name", "標準")
    run(capsys, "template-import", str(pkg / "assets" / "template" / "standard.potx"), "--name", "標準", "--force")
    assert [p.name for p in (home / "templates").iterdir()] == ["標準.potx"]


def test_一覧は登録済みの名前と形式を出し_なければ空(home, tmp_path, capsys):
    rc, out, _ = run(capsys, "template-list")
    assert (rc, json.loads(out)) == (0, [])
    run(capsys, "template-import", str(make_pptx(tmp_path / "b.pptx")), "--name", "b")
    run(capsys, "template-import", str(make_pptx(tmp_path / "a.pptx")), "--name", "a")
    rc, out, _ = run(capsys, "template-list")
    items = json.loads(out)
    assert rc == 0
    assert [(i["name"], i["format"]) for i in items] == [("a", ".pptx"), ("b", ".pptx")]  # 名前順
    assert all(Path(i["path"]).is_file() for i in items)


def test_削除すると一覧から消え_ないものは終了コード2(home, tmp_path, capsys):
    run(capsys, "template-import", str(make_pptx(tmp_path / "t.pptx")), "--name", "消す")
    rc, _, _ = run(capsys, "template-remove", "消す")
    assert rc == 0
    assert json.loads(run(capsys, "template-list")[1]) == []
    rc, _, err = run(capsys, "template-remove", "消す")
    assert rc == 2
    assert "消す" in err


def test_削除の名前に区切り文字があれば置き場の外を消さず終了コード2(home, tmp_path, capsys):
    victim = make_pptx(tmp_path / "victim.pptx")
    (home / "templates").mkdir(parents=True)
    rc, _, _ = run(capsys, "template-remove", "../victim")
    assert rc == 2
    assert victim.is_file()


def test_登録したテンプレートのパスを_init_に渡して成果物を作れる(home, tmp_path, pkg, capsys):
    """通し: インポート → 一覧のパス → init --template。作業フォルダに _template/ へコピーされる。"""
    shutil.copy(pkg / "assets" / "template" / "standard.potx", tmp_path / "社内.potx")
    run(capsys, "template-import", str(tmp_path / "社内.potx"))
    path = json.loads(run(capsys, "template-list")[1])[0]["path"]
    work = tmp_path / "out" / "pptx-deck-source" / "資料"
    rc, _, err = run(capsys, "init", str(work), "--template", path)
    assert rc == 0, err
    assert (work / "_template" / "template.potx").is_file()

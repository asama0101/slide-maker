"""再監査 F3: 入力の読み取り・確認ページ（#7・#8・#12・#14・#19・#20・#27）。"""

# ruff: noqa: S101  # pytest の assert

import pytest
from slide_maker import candidates, cli, paths

FRAG_OK = '<div class="pp-text">x</div>'


@pytest.fixture
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


# ---- 断片のファイル名 ----


def make_slides(tmp_path, names):
    work = tmp_path / "out" / "slide-maker-source" / "d"
    (work / "slides").mkdir(parents=True)
    for n in names:
        (work / "slides" / n).write_text(FRAG_OK, encoding="utf-8")
    return work


@pytest.mark.parametrize(
    "bad",
    ["1-R1.html", "100-R1.html", "01-r1.html", "01-R1-d4.html"],
    ids=["桁が足りない", "桁が多い", "案が小文字", "デザイン番号が範囲外"],
)
def test_名前の違う断片はファイル名を挙げてValueErrorにする(tmp_path, bad):
    work = make_slides(tmp_path, ["02-R1.html", "02-R2.html", bad])
    with pytest.raises(ValueError, match=bad):
        candidates.collect(work)


def test_スライド断片でないhtmlは無視する(tmp_path):
    work = make_slides(tmp_path, ["01-R1.html", "01-R2.html", "draft-1.html", "memo.html"])
    assert list(candidates.collect(work)) == ["01"]


# ---- テキストの読み込み ----


def test_BOMを落として読む(tmp_path):
    f = tmp_path / "a.md"
    f.write_bytes(b"\xef\xbb\xbf## S01 \xe8\xa1\xa8\xe7\xb4\x99\n")
    assert paths.read_text(f) == "## S01 表紙\n"


def test_UTF8でない文書はファイル名つきのValueErrorにする(tmp_path):
    f = tmp_path / "script.md"
    f.write_bytes("## S01 表紙\n".encode("cp932"))
    with pytest.raises(ValueError, match="script.md") as e:
        paths.read_text(f)
    assert "script.md" in str(e.value)
    assert "UTF-8 で保存してください" in str(e.value)


def test_lint_scriptはcp932の原稿を終了コード2とUTF8の案内で断る(tmp_path, capsys):
    f = tmp_path / "script.md"
    f.write_bytes("## S01 表紙\n- layout: cover\n".encode("cp932"))
    rc = cli.entry(["lint-script", str(f)])
    assert rc == 2
    assert "UTF-8 で保存してください" in capsys.readouterr().err


def test_lint_scriptはBOMつきの原稿を読んで検査を通す(tmp_path, capsys):
    f = tmp_path / "script.md"
    f.write_bytes(b"\xef\xbb\xbf" + "## S01 表紙\n- layout: cover\n- ヘッドメッセージ: 表紙\n".encode())
    assert cli.main(["lint-script", str(f)]) == 0
    assert "ありません" not in capsys.readouterr().out
    # 対照: BOM だけの空の原稿はスライドなしとして落ちる（BOM つきでも中身を読んでいる）
    f.write_bytes(b"\xef\xbb\xbf")
    assert cli.main(["lint-script", str(f)]) == 1
    assert "スライド（## S01 …）がありません" in capsys.readouterr().out

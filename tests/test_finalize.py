# ruff: noqa: S101  # pytest の assert
"""finalize（選択結果 → final.html）のテスト。"""

import json

import pytest
from pptx_deck import cli, finalize, initdir, paths


def _slides(work, **frags):
    d = work / "slides"
    d.mkdir(parents=True, exist_ok=True)
    for f in d.glob("*.html"):
        f.unlink()
    for name, body in frags.items():
        (d / f"{name}.html").write_text(body, encoding="utf-8")


def _choice(base, nn, pick="R1", status="approved", comment=""):
    d = base / "choices"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{nn}.json").write_text(
        json.dumps({"at": "2026-11-08T00:00:00.000Z", "comment": comment, "pick": pick, "status": status}),
        encoding="utf-8",
    )


@pytest.fixture
def work(tmp_path):
    base = tmp_path / "out" / "pptx-deck-source" / "demo"
    initdir.init(base)
    w = paths.resolve_work(base)
    _slides(
        w,
        **{
            "01-R1": "<section>ONE</section>",
            "01-R2": "<section>ONE2</section>",
            "02-R1": "<section>TWO1</section>",
            "02-R2": "<section>TWO2</section>",
        },
    )
    return w


def test_all_approved(work, tmp_path):
    ch = tmp_path / "ch"
    _choice(ch, "02", "R2")
    _choice(ch, "01", "R1")
    out = finalize.finalize(work, ch)
    html = out.read_text(encoding="utf-8")
    assert out == work / "final.html"
    assert html.index("ONE") < html.index("TWO2")
    assert "TWO1" not in html
    assert html.endswith("</body></html>")


def test_final_html_has_no_review_markup(work, tmp_path):
    ch = tmp_path / "ch"
    _choice(ch, "01")
    _choice(ch, "02", "R1")
    finalize.finalize(work, ch)
    html = (work / "final.html").read_text(encoding="utf-8")
    assert "rv-" not in html
    assert not (work / "final-review.html").exists()


def test_unapproved_stops(work, tmp_path):
    ch = tmp_path / "ch"
    _choice(ch, "01")
    _choice(ch, "02", "R1", status="saved")
    with pytest.raises(ValueError, match="S02"):
        finalize.finalize(work, ch)


def test_empty_choices_stops(work, tmp_path):
    (tmp_path / "ch" / "choices").mkdir(parents=True)
    with pytest.raises(ValueError, match="空"):
        finalize.finalize(work, tmp_path / "ch")


def test_missing_page_stops(work, tmp_path):
    ch = tmp_path / "ch"
    _choice(ch, "01")
    with pytest.raises(ValueError, match="S02: 選択結果がありません"):
        finalize.finalize(work, ch)


def test_pick_missing_candidate(work, tmp_path):
    ch = tmp_path / "ch"
    _choice(ch, "01", "R3")
    _choice(ch, "02", "R1")
    with pytest.raises(ValueError, match="S01.*R3"):
        finalize.finalize(work, ch)


def test_pick_none_stops(work, tmp_path):
    ch = tmp_path / "ch"
    _choice(ch, "01", None)
    _choice(ch, "02", "R1")
    with pytest.raises(ValueError, match="S01"):
        finalize.finalize(work, ch)


def test_comment_stops_and_problems_are_collected(work, tmp_path):
    ch = tmp_path / "ch"
    _choice(ch, "01", "R1", comment="文言を直す")
    _choice(ch, "02", "R1", status="saved")
    with pytest.raises(ValueError, match="S01") as e:
        finalize.finalize(work, ch)
    assert "コメント未反映" in str(e.value)
    assert "S01" in str(e.value)
    assert "S02" in str(e.value)


def test_cli_choices(work, tmp_path, capsys):
    ch = tmp_path / "ch"
    _choice(ch, "01")
    _choice(ch, "02", "R1")
    assert cli.main(["finalize", str(work), "--choices", str(ch)]) == 0
    assert "TWO1" in (work / "final.html").read_text(encoding="utf-8")


def test_cli_choices_error_exit_2(work, tmp_path, capsys):
    ch = tmp_path / "ch"
    _choice(ch, "01", status="saved")
    _choice(ch, "02", "R1")
    assert cli.main(["finalize", str(work), "--choices", str(ch)]) == 2
    assert "エラー" in capsys.readouterr().err


def test_choices_なしは作業フォルダに触れず終了コード2(work, capsys):
    (work / "theme.css").unlink()
    assert cli.main(["finalize", str(work)]) == 2
    assert "--choices" in capsys.readouterr().err
    assert not (work / "theme.css").exists()  # 派生ファイルの再生成より先に止まる


def test_pick_が文字列でなければ_ValueError_で止まる(work, tmp_path):
    ch = tmp_path / "ch"
    _choice(ch, "01", pick=["R1"])
    _choice(ch, "02", "R1")
    with pytest.raises(ValueError, match="S01"):
        finalize.finalize(work, ch)

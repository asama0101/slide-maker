# ruff: noqa: S101  # pytest の assert
"""旧い作業フォルダ（v1 の回答・旧形式の断片・template.json の古いキー）を渡しても、
traceback を出さず、原因の分かるメッセージで止まるか、古いものを無視する。"""

import pytest
from slide_maker import cli, initdir, paths

from tests._flow import write_choices, write_slide

OLD_KEYS = {
    "answers_color": "#1F4E8C",
    "answers_color_from": "answers-1.md",
    "skipped_color": "#2E7D32",
    "answers_fontsizes": {"title": [40, "answers-1.md"]},
    "skipped_fontsizes": {"body": 20},
}


@pytest.fixture
def old_work(tmp_path):
    work = tmp_path / "out" / "slide-maker-source" / "deck"
    initdir.init(work)
    cfg = paths.read_cfg(work)
    cfg.update(OLD_KEYS)
    paths.write_cfg(work, cfg)
    (work / "answers-1.md").write_text("---\nround: 1\n---\n## S01\n- 選択: A\n- 判定: 承認\n", encoding="utf-8")
    (work / "answers-final.md").write_text("## S01\n- 判定: 承認\n", encoding="utf-8")
    write_slide(work / "slides", "01", "<section>ONE</section>")
    return work


def _run(capsys, *argv):
    capsys.readouterr()
    rc = cli.entry(list(argv))
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


@pytest.mark.parametrize("old", ["05-R.html", "02-B-d2.html"])
@pytest.mark.parametrize("cmd", ["finalize", "review-page"])
def test_旧形式の断片は旧い名前を挙げて終了コード2で止まる(old_work, tmp_path, capsys, cmd, old):
    (old_work / "slides" / old).write_text("<section>OLD</section>", encoding="utf-8")
    extra = ["--choices", str(write_choices(tmp_path / "ch", {"01": "R1"}))] if cmd == "finalize" else []
    rc, _, err = _run(capsys, cmd, str(old_work), *extra)
    assert rc == 2
    assert "エラー:" in err
    assert old in err
    assert "Traceback" not in err


def test_古いキーと回答ファイルは無視して_finalize_と_review_page_が通る(old_work, tmp_path, capsys):
    ch = write_choices(tmp_path / "ch", {"01": "R1"})
    assert _run(capsys, "finalize", str(old_work), "--choices", str(ch))[0] == 0
    assert "ONE" in (old_work / "final.html").read_text(encoding="utf-8")
    assert _run(capsys, "review-page", str(old_work))[0] == 0
    assert (old_work / "review.html").is_file()


def test_旧い作業フォルダの_build_は_final_html_がなければ終了コード2で止まる(old_work, capsys):
    rc, out, err = _run(capsys, "build", str(old_work))
    assert rc == 2
    assert "エラー:" in err
    assert "finalize" in err
    assert out == ""

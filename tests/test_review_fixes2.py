"""コードレビュー（2 回目）の指摘 1〜8 の再現テスト。ブラウザなしで動く。"""

# ruff: noqa: S101  # pytest の assert
from pathlib import Path

import pytest
from pptx import Presentation
from pptx.util import Emu
from pptx_deck import build, charts, lifecycle, paths, template


def _spec(**kw):
    s = {"type": "bar", "categories": ["a", "b"], "series": [{"name": "s", "values": [1, 2]}]}
    s.update(kw)
    return s


# ---- 1: グラフ指定の検査漏れ ----
@pytest.mark.parametrize(
    "spec",
    [
        _spec(series=[{"values": [1, 2]}]),
        _spec(series=[{"name": 3, "values": [1, 2]}]),
        _spec(gap="広い"),
        _spec(fmt=5),
        _spec(type=["bar"]),
    ],
    ids=["系列名なし", "系列名が数", "gap が文字", "fmt が数", "type が配列"],
)
def test_グラフ指定の型の不備は例外にせず_問題として返す(spec):
    assert charts.validate(spec)


def test_正しいグラフ指定は問題なし():
    assert charts.validate(_spec(gap=40, fmt="0.0")) == []


# ---- 3: 目次のレイアウトを本文に選ばない ----
def test_目次のレイアウトを本文に選ばない(tmp_path):
    prs = Presentation()
    prs.slide_width, prs.slide_height = 12192000, 6858000
    prs.slide_layouts[1].name = "Table of Contents"  # 題と本文の領域がある。先頭にある
    prs.slide_layouts[3].name = "Title and Content"
    src = tmp_path / "t.pptx"
    prs.save(str(src))
    assert template.analyze(src).body == 3


# ---- 4: 大きさ 0 の角丸図形 ----
def test_大きさ0の角丸図形でも_ゼロ除算にならない():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    el = {
        "shape": "round",
        "radius_px": 6,
        "rect": {"x": 10, "y": 10, "w": 100, "h": 0},
        "fill": None,
        "line": None,
    }
    build.add_shape(slide, el)
    assert len(slide.shapes) == 1
    assert slide.shapes[0].height == Emu(0)


# ---- 7: clean は一時フォルダを作って消すだけ ----
def test_clean_temp_は消したパスを返し_フォルダは残らない(tmp_path, monkeypatch):
    monkeypatch.setattr(paths.tempfile, "gettempdir", lambda: str(tmp_path))
    work = tmp_path / "out" / "pptx-deck-source" / "deck"
    d = paths.temp_dir("deck", work)
    (d / "x.png").write_bytes(b"x")
    r = lifecycle.clean_temp("deck", work)
    assert Path(r) == d
    assert not d.exists()

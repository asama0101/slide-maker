"""グラフ指定の検査（charts.validate）と、不正な指定で build が止まること。stacked100 は廃止。"""

# ruff: noqa: S101  # pytest の assert
import json
import os
import subprocess
import sys

import pytest
from pptx_deck import charts, initdir, paths

from tests._paths import PKG

pytestmark = pytest.mark.slow  # ブラウザ（Chromium）で測る

BOX = 'style="position:absolute;left:80px;top:120px;width:600px;height:360px"'


def _spec(**kw):
    s = {"type": "bar", "categories": ["a", "b", "c"], "series": [{"name": "s", "values": [1, 2, 3]}]}
    s.update(kw)
    return s


BAD_SPECS = {
    "area": (_spec(type="area"), "未対応のグラフ型: area"),
    "stacked100": (_spec(type="stacked100"), "未対応のグラフ型: stacked100"),
    "highlight": (_spec(highlight=5), "highlight 5 が範囲外です（0 〜 2）"),
    "axis": (_spec(axis={"min": 3, "max": 3}), "axis の min は max より小さくしてください（min=3, max=3）"),
    "waterfall": (
        _spec(type="waterfall", series=[{"name": "s", "values": [10, -20, 5]}]),
        "累計が 0 未満になります（2 番目）",
    ),
    "categories": (_spec(categories=[]), "categories（カテゴリ）が空です"),
    "series": (_spec(series=[]), "series（系列）が空です"),
    "長さ違い": (_spec(series=[{"name": "s", "values": [1, 2]}]), "カテゴリ数（3）と同じ長さの数値の配列"),
    "None": (_spec(series=[{"name": "s", "values": [1, None, 3]}]), "カテゴリ数（3）と同じ長さの数値の配列"),
    "文字列": (_spec(series=[{"name": "s", "values": [1, "2", 3]}]), "カテゴリ数（3）と同じ長さの数値の配列"),
    "bool": (_spec(series=[{"name": "s", "values": [1, True, 3]}]), "カテゴリ数（3）と同じ長さの数値の配列"),
    "waterfall2系列": (
        _spec(type="waterfall", series=[{"name": "s", "values": [10, 5, 3]}, {"name": "t", "values": [1, 2, 3]}]),
        "waterfall の series は 1 つだけです",
    ),
}


@pytest.mark.parametrize("t", ["bar", "barh", "line", "pie", "stacked"])
def test_正常な指定は問題なしを返す(t):
    assert charts.validate(_spec(type=t)) == []


def test_正常なウォーターフォールは問題なしを返す():
    assert charts.validate(_spec(type="waterfall", series=[{"name": "s", "values": [10, 5, -3]}])) == []


@pytest.mark.parametrize(("spec", "msg"), BAD_SPECS.values(), ids=BAD_SPECS.keys())
def test_不正な指定は_validate_が1件の文で理由を返す(spec, msg):
    got = charts.validate(spec)
    assert len(got) == 1
    assert msg in got[0]


def test_add_chart_は未対応型で従来の文言の例外にする():
    with pytest.raises(ValueError, match="未対応のグラフ型"):
        charts.add_chart(None, {"chart": _spec(type="area"), "rect": {}}, None)


@pytest.mark.slow
def test_不正なグラフ指定は_build_が_traceback_を出さずエラーで止まり_pptx_を書かない(tmp_path):
    base = tmp_path / "out" / "pptx-deck-source" / "deck"
    initdir.init(base, template_path=None, force=False, footer=None)
    work = paths.resolve_work(base)
    sec = (
        '<section class="slide" data-layout="content"><div class="pp-text" data-role="title" '
        'style="position:absolute;left:80px;top:40px;width:600px;height:50px">題</div>'
        f"<div class=\"pp-chart\" {BOX} data-chart='{json.dumps(_spec(type='area'))}'></div></section>"
    )
    (work / "final.html").write_text(
        '<!doctype html><html lang="ja"><head><meta charset="utf-8"><link rel="stylesheet" href="theme.css">'
        f'<link rel="stylesheet" href="base.css"></head><body>{sec}</body></html>',
        encoding="utf-8",
    )
    r = subprocess.run(  # noqa: S603  # 自分の入口を sys.executable で起動する（外部入力なし）
        [sys.executable, "-m", "pptx_deck", "build", str(base)],
        cwd=PKG,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert r.returncode == 2, r.stderr
    assert "Traceback" not in r.stderr
    assert "エラー: " in r.stderr
    assert "未対応のグラフ型: area" in r.stderr
    assert not (base.parent.parent / "deck.pptx").exists()


@pytest.mark.parametrize("totals", [5, "0", [9], [-1], [True], [1.5]])
def test_waterfall_の_totals_が不正なら例外にせず理由を返す(totals):
    spec = {"type": "waterfall", "categories": ["a", "b", "c"], "series": [{"name": "s", "values": [1, 2, 3]}]}
    got = charts.validate({**spec, "totals": totals})
    assert len(got) == 1
    assert "totals" in got[0]


def test_waterfall_の_totals_が正しければ通る():
    spec = {"type": "waterfall", "categories": ["a", "b", "c"], "series": [{"name": "s", "values": [1, 2, 3]}]}
    assert charts.validate({**spec, "totals": [0, 2]}) == []

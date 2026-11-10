"""中身が空の pp-text は、範囲の矩形（0,0）ではなく要素の rect を位置に使う。"""

# ruff: noqa: S101  # pytest の assert
import pytest
from pptx_deck import check, paths, template

from tests._measure import model_of

pytestmark = pytest.mark.slow  # ブラウザ（Chromium）で測る

EMPTY = '<div class="pp-text" style="position:absolute;left:100px;top:200px;width:300px;height:50px"></div>'


def test_空の_pp_text_の_box_は_rect_の位置になる():
    e = model_of(EMPTY)[0]["elements"][0]
    assert (e["rect"]["x"], e["rect"]["y"]) == (100, 200)
    assert (e["box"]["x"], e["box"]["y"]) == (100, 200)
    assert e["overflow"] is False


def test_空の_pp_text_で_outOfSlide_が出ない():
    info = template.analyze(paths.ASSETS / "template" / "standard.potx")
    vs = check.check_model(model_of(EMPTY), info)
    assert [v for v in vs if v["rule"] == "outOfSlide"] == []

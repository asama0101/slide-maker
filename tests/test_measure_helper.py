"""テスト用の補助 tests/_measure.model_of が、断片を測ってモデルを返すこと。"""

# ruff: noqa: S101  # pytest の assert
import pytest

from tests import _measure

pytestmark = pytest.mark.slow  # ブラウザ（Chromium）で測る


def test_model_of_は_pp_text_を1要素のモデルにする():
    model = _measure.model_of('<div class="pp-text" style="left:80px;top:80px;width:400px;height:60px">あ</div>')
    assert len(model) == 1
    els = model[0]["elements"]
    assert len(els) == 1
    assert els[0]["kind"] == "text"
    assert els[0]["paras"][0]["runs"][0]["text"] == "あ"

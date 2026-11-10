"""コードレビュー（1 回目の残り）の指摘の再現テスト。ブラウザなしで動く。"""

# ruff: noqa: S101  # pytest の assert
import dataclasses

import pytest
from pptx_deck import charts, check, paths, script_lint, template

BAND = {"x": 64.0, "y": 676.0, "w": 700.0, "h": 28.0}  # 本文レイアウトのフッターの位置


def _info():
    return template.analyze(paths.ASSETS / "template" / "standard.potx")


def _shape_in_footer(layout: str) -> list[dict]:
    el = {
        "kind": "shape",
        "idx": 0,
        "shape": "rect",
        "rect": dict(BAND),
        "role": None,
        "ph": None,
        "bg": "FFFFFF",
        "overlap": False,
        "chrome": False,
        "fill": None,
        "line": None,
    }
    return [{"index": 1, "layout": layout, "bg": "FFFFFF", "elements": [el]}]


def _keepout_rules(model, info):
    return [v for v in check.check_model(model, info) if v["rule"] == "keepout"]


# ---- 表紙・裏表紙は、自分のレイアウトの禁止領域で検査する ----
@pytest.mark.parametrize("layout", ["cover", "closing"])
def test_表紙と裏表紙は本文ではなく自分のレイアウトの禁止領域で検査する(layout):
    info = _info()
    idx = info.cover if layout == "cover" else info.closing
    # 表紙・裏表紙のレイアウトにはフッターがなく、本文にはある、テンプレートの状態
    own = dataclasses.replace(info, layout_keepout={**info.layout_keepout, str(idx): ()})
    assert _keepout_rules(_shape_in_footer(layout), own) == []
    # 自分のレイアウトにフッターがあれば、入ると違反
    zone = template.Rect.from_dict(BAND)
    own = dataclasses.replace(info, keepout=(), layout_keepout={**info.layout_keepout, str(idx): (zone,)})
    assert len(_keepout_rules(_shape_in_footer(layout), own)) == 1


def test_標準テンプレートは表紙と裏表紙の禁止領域を持つ():
    info = _info()
    assert str(info.cover) in info.layout_keepout
    assert info.closing is not None
    assert str(info.closing) in info.layout_keepout


# ---- 判断語: 「ある」「ない」を部分一致で数えない ----
NOUN_HEAD = "あるべき姿とこれまでの経緯の整理に関する今期の検討項目と各部署の担当範囲の概要一覧を示す"


def test_名詞句のヘッドメッセージは判断語なしと判定される():
    assert 30 <= len(NOUN_HEAD) <= 60
    assert any("判断語" in p for p in script_lint._head_problems("S01", NOUN_HEAD))


@pytest.mark.parametrize(
    "head",
    [
        "海外拠点の投資回収は三年以内に収まる見通しで、追加の資金調達を前提にしない計画が成り立つことが確認できた点が最も重要である",
        "既存システムの保守費は年間で二割を超えており、今期中に更改の方針を決めないと運用の継続に深刻な支障が出る恐れがある",
        "現行の運用では夜間の障害対応に要する人員の確保が難しく、委託先の見直しを含めた体制の再構築を急ぐ必要がない状況ではない",
    ],
)
def test_文末が_ある_ない_のヘッドメッセージは判断語として通る(head):
    assert not any("判断語" in p for p in script_lint._head_problems("S01", head))


# ---- ウォーターフォールの小さい増減の閾値 ----
def test_SMALL_STEP_は_8_パーセントで_コメントもそう書く():
    src = (paths.SKILL_DIR / "pptx_deck" / "charts.py").read_text(encoding="utf-8")
    assert charts.SMALL_STEP == 0.08
    assert "6%" not in src

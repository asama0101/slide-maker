"""テンプレートのレイアウト背景色の読み取り（マスターの継承・テーマ色・clrMapOvr・bgRef）。"""

# ruff: noqa: S101  # pytest の assert
import pytest
from lxml import etree
from pptx import Presentation
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx_deck import template

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"

SRGB_1F3A5F = '<p:bgPr><a:solidFill><a:srgbClr val="1F3A5F"/></a:solidFill><a:effectLst/></p:bgPr>'
SCHEME_TX1 = '<p:bgPr><a:solidFill><a:schemeClr val="tx1"/></a:solidFill><a:effectLst/></p:bgPr>'
BGREF_BG1 = '<p:bgRef idx="1001"><a:schemeClr val="bg1"/></p:bgRef>'
OVR = (
    '<a:overrideClrMapping bg1="dk1" tx1="lt1" bg2="dk2" tx2="lt2" accent1="accent1" accent2="accent2" '
    'accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
)


@pytest.fixture
def prs():
    return Presentation()  # python-pptx の既定テンプレート（マスターの背景は bgRef の bg1 = 白）


def set_layout_bg(layout, inner_xml: str):
    cSld = layout._element.find(f"{{{P}}}cSld")
    old = cSld.find(f"{{{P}}}bg")
    if old is not None:
        cSld.remove(old)
    cSld.insert(0, etree.fromstring(f'<p:bg xmlns:p="{P}" xmlns:a="{A}">{inner_xml}</p:bg>'))


def set_clr_map_ovr(layout, inner_xml: str):
    el = layout._element
    old = el.find(f"{{{P}}}clrMapOvr")
    if old is not None:
        el.remove(old)
    el.find(f"{{{P}}}cSld").addnext(
        etree.fromstring(f'<p:clrMapOvr xmlns:p="{P}" xmlns:a="{A}">{inner_xml}</p:clrMapOvr>')
    )


# ---- layout_bg_hex ----


def test_背景指定がなければマスターのテーマ色を継承する(prs):
    assert template.layout_bg_hex(prs, 0) == "#FFFFFF"


def test_レイアウトのsrgb指定を使う(prs):
    set_layout_bg(prs.slide_layouts[1], SRGB_1F3A5F)
    assert template.layout_bg_hex(prs, 1) == "#1F3A5F"


def test_レイアウトのテーマ色指定はテーマで解決する(prs):
    set_layout_bg(prs.slide_layouts[2], SCHEME_TX1)
    assert template.layout_bg_hex(prs, 2) == "#000000"


def test_色変換つきの指定は決められずNone(prs):
    set_layout_bg(
        prs.slide_layouts[4],
        '<p:bgPr><a:solidFill><a:schemeClr val="bg1"><a:lumMod val="95000"/></a:schemeClr></a:solidFill><a:effectLst/>'
        "</p:bgPr>",
    )
    assert template.layout_bg_hex(prs, 4) is None


def test_テーマ部品がなければsrgbは読めテーマ色はNone(prs):
    master = prs.slide_masters[0]
    for rId, rel in list(master.part.rels.items()):
        if rel.reltype == RT.THEME:
            master.part.rels.pop(rId)
    set_layout_bg(prs.slide_layouts[1], SRGB_1F3A5F)
    set_layout_bg(prs.slide_layouts[2], SCHEME_TX1)
    assert template.layout_bg_hex(prs, 1) == "#1F3A5F"
    assert template.layout_bg_hex(prs, 2) is None


def test_グラデーションは決められずNone(prs):
    set_layout_bg(
        prs.slide_layouts[3],
        '<p:bgPr><a:gradFill><a:gsLst><a:gs pos="0"><a:srgbClr val="000000"/></a:gs></a:gsLst></a:gradFill>'
        "<a:effectLst/></p:bgPr>",
    )
    assert template.layout_bg_hex(prs, 3) is None


def test_clrMapOvrの上書きを使う(prs):
    lay = prs.slide_layouts[1]
    set_layout_bg(lay, BGREF_BG1)
    assert template.layout_bg_hex(prs, 1) == "#FFFFFF"
    set_clr_map_ovr(lay, OVR)
    assert template.layout_bg_hex(prs, 1) == "#000000"


def test_masterClrMappingはマスターの対応を使う(prs):
    lay = prs.slide_layouts[1]
    set_layout_bg(lay, BGREF_BG1)
    set_clr_map_ovr(lay, "<a:masterClrMapping/>")
    assert template.layout_bg_hex(prs, 1) == "#FFFFFF"


def test_bgRefのスタイル表が1001を超える指定はNone(prs):
    set_layout_bg(prs.slide_layouts[1], '<p:bgRef idx="1003"><a:schemeClr val="bg1"/></p:bgRef>')
    assert template.layout_bg_hex(prs, 1) is None


# ---- 標準テンプレート ----


def test_標準テンプレートは表紙_本文_裏表紙の背景を白と読む(pkg):
    path = pkg / "assets" / "template" / "standard.potx"
    colors, notes = template.background_colors(path, template.analyze(path))
    assert colors == {"cover": "#FFFFFF", "body": "#FFFFFF", "closing": "#FFFFFF"}
    assert notes == []


def test_背景のCSSは画像を使わず変数だけで色を渡す(pkg):
    info = template.analyze(pkg / "assets" / "template" / "standard.potx")
    css = template.layout_css(info, "#FFFFFF", {"cover": "#112233", "body": "#FFFFFF", "closing": "#FFFFFF"})
    assert "background-image" not in css
    assert '.slide[data-layout="cover"] { --bg: #112233; }' in css

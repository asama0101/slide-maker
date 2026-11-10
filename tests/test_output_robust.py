"""束 E3: 節の除去・絵の範囲の取り方・環境調査のキャッシュ。"""

# ruff: noqa: S101  # pytest の assert
import re
import zipfile

import pytest
from pptx import Presentation
from pptx_deck import build, svgids, template

from tests._measure import model_of
from tests._paths import PKG

pytestmark = pytest.mark.slow  # ブラウザ（Chromium）で測る

TPL = PKG / "assets" / "template" / "standard.potx"
P14 = "http://schemas.microsoft.com/office/powerpoint/2010/main"
SECTION_EXT = (
    '<p:extLst xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
    f'<p:ext uri="{{521415D9-36F7-43E2-AB2F-B90AF26B5E84}}"><p14:sectionLst xmlns:p14="{P14}">'
    '<p14:section name="節1" id="{11111111-1111-1111-1111-111111111111}"><p14:sldIdLst/></p14:section>'
    "</p14:sectionLst></p:ext></p:extLst>"
)


def _template_with_sections(dst):
    with zipfile.ZipFile(TPL) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "ppt/presentation.xml":
                text = data.decode("utf-8")
                text = re.sub(r"<p:extLst>.*?</p:extLst>", "", text, flags=re.S)
                text = text.replace("</p:presentation>", SECTION_EXT + "</p:presentation>")
                data = text.encode("utf-8")
            zout.writestr(item, data)
    return dst


@pytest.mark.slow
def test_節を持つテンプレートから作った_pptx_には節の一覧が残らない(tmp_path):
    model = model_of(
        '<div class="pp-text" data-role="title" style="position:absolute;left:40px;top:40px;'
        'width:800px;height:60px;color:#000;font-size:32px">題</div>'
    )
    tpl = _template_with_sections(tmp_path / "sec.potx")
    assert "sectionLst" in zipfile.ZipFile(tpl).read("ppt/presentation.xml").decode("utf-8")
    info = template.analyze(tpl)
    out = build.build(model, tpl, info, None, tmp_path / "o.pptx", base_dir=tmp_path)
    xml = zipfile.ZipFile(out).read("ppt/presentation.xml").decode("utf-8")
    assert "sectionLst" not in xml
    assert len(Presentation(str(out)).slides) == 1


@pytest.mark.parametrize(
    ("frag", "want"),
    [
        (
            '<div class="pp-picture" data-alt="x"><div><svg><marker id="m"/></svg></div>'
            '<svg><path marker-end="url(#m)"/></svg></div>',
            '<div class="pp-picture" data-alt="x"><div><svg><marker id="p-m"/></svg></div>'
            '<svg><path marker-end="url(#p-m)"/></svg></div>',
        ),
        (
            '<div class="pp-picture" data-alt="a > b"><svg><marker id="m"/><path marker-end="url(#m)"/></svg></div>',
            '<div class="pp-picture" data-alt="a > b"><svg><marker id="p-m"/><path marker-end="url(#p-m)"/></svg>'
            "</div>",
        ),
        (
            '<div class="pp-picture" data-alt="x"><svg><g data-id="m"/><marker id="m"/></svg></div>',
            '<div class="pp-picture" data-alt="x"><svg><g data-id="m"/><marker id="p-m"/></svg></div>',
        ),
    ],
    ids=["絵の中の入れ子の_div", "属性値の中の_>", "data-id_は_id_ではない"],
)
def test_絵の_id_は絵の範囲の中だけ接頭辞つきに直す(frag, want):
    assert svgids.uniquify(frag, "p-") == want

"""テンプレートの表紙・本文・裏表紙のレイアウトを選び、PPTX に使う。（init の推定・build）"""

# ruff: noqa: S101  # pytest の assert
import json
import re
from pathlib import Path

import pytest
from pptx import Presentation
from pptx_deck import cli, paths, template

from tests._flow import finalize_all, write_slide

NAMES = {0: "表紙", 1: "本文", 2: "章扉", 3: "目次", 4: "スケジュール", 5: "裏表紙"}


def make_template(path: Path, names: dict[int, str]) -> Path:
    """python-pptx の既定テンプレート（11 レイアウト）を 16:9 にして、レイアウト名を付け替えて保存する。"""
    prs = Presentation()
    prs.slide_width, prs.slide_height = 12192000, 6858000
    for i, name in names.items():
        prs.slide_layouts[i]._element.cSld.set("name", name)
    for lay in prs.slide_layouts:  # 既定の配置は 4:3 用なので、本文のタイトルを標準テンプレートと同じ位置・幅にする
        for ph in lay.placeholders:
            if ph.placeholder_format.type in (1, 3):  # TITLE・CENTER_TITLE
                ph.left, ph.top, ph.width, ph.height = 64 * 9525, 36 * 9525, 1152 * 9525, 50 * 9525
    prs.save(str(path))
    return path


def strip_titles(path: Path, idxs) -> Path:
    prs = Presentation(str(path))
    for i in idxs:
        for ph in list(prs.slide_layouts[i].placeholders):
            if ph.placeholder_format.type == 1:  # TITLE
                ph._element.getparent().remove(ph._element)
    prs.save(str(path))
    return path


@pytest.fixture
def tpl(tmp_path):
    return make_template(tmp_path / "t.pptx", NAMES)


def run(capsys, *argv):
    rc = cli.main(list(argv))
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


def build_deck(capsys, base, comp, frags):
    """init 済みの作業フォルダに断片を並べ、全スライドを R1 案で承認して build し、PPTX のレイアウト名を返す。"""
    work = paths.resolve_work(base)
    for n, rel in enumerate(frags, 1):
        write_slide(work / "slides", f"{n:02d}", (comp / rel).read_text(encoding="utf-8"))
    assert finalize_all(work) == 0
    rc, out, err = run(capsys, "build", str(base))
    assert rc == 0, out + err
    return [s.slide_layout.name for s in Presentation(str(base.parent.parent / "demo.pptx")).slides]


# ---- 表紙・本文・裏表紙だけ ----


def test_template_uses_cover_body_closing_only(tpl):
    """章扉・目次・型ごとの専用レイアウトがあっても使わない。表紙・裏表紙以外は本文で代える。"""
    info = template.analyze(tpl)
    assert (info.cover, info.body, info.closing) == (0, 1, 5)
    assert not hasattr(info, "kinds")
    assert not hasattr(info, "types")
    for slide in (
        {"layout": "section", "type": "section"},
        {"layout": "agenda", "type": "agenda"},
        {"layout": "diagram", "type": "gantt"},  # スケジュールのレイアウトがあっても使わない
        {"layout": "content"},
    ):
        assert template.layout_index(info, slide) == info.body
    assert template.layout_index(info, {"layout": "cover", "type": "cover"}) == info.cover
    assert template.layout_index(info, {"layout": "closing"}) == info.closing


def test_裏表紙がなければ本文で代える(tmp_path):
    info = template.analyze(make_template(tmp_path / "nc.pptx", {0: "表紙", 1: "本文"}))
    assert info.closing is None
    assert template.layout_index(info, {"layout": "closing"}) == info.body


def test_専用レイアウトの注意書きを出さない(tpl):
    assert not any("章扉" in n or "目次" in n for n in template.analyze(tpl).notes)
    assert not any("章扉" in n for n in template.analyze(paths.ASSETS / "template" / "standard.potx").notes)


def test_英語の既定名のTwoContentは目次にしない(tmp_path):
    info = template.analyze(make_template(tmp_path / "en.pptx", {}))
    assert template.layout_index(info, {"layout": "agenda"}) == info.body


def test_to_dictとfrom_dictで往復し旧いtemplate_jsonも読める(tpl):
    info = template.analyze(tpl)
    again = template.TemplateInfo.from_dict(json.loads(json.dumps(info.to_dict())))
    assert again == info
    old = info.to_dict()
    old["kinds"] = {"section": 2, "agenda": 3}  # 旧版の template.json（専用レイアウト）
    old["types"] = {"gantt": 4}
    old["stale"] = 1
    loaded = template.TemplateInfo.from_dict(old)
    assert loaded == info
    assert template.layout_index(loaded, {"layout": "section", "type": "gantt"}) == info.body
    old.pop("layout_keepout")
    assert template.TemplateInfo.from_dict(old).layout_keepout == {}


def test_template_keepout_unchanged(tpl):
    """ヘッダー・フッター・ロゴの領域は、表紙・本文・裏表紙のぶんだけ従来どおり持つ。"""
    info = template.analyze(tpl)
    assert set(info.layout_keepout) == {str(info.cover), str(info.closing)}
    prs = Presentation(str(tpl))
    for i in (info.cover, info.closing):
        assert info.layout_keepout[str(i)] == template._layout_keepout(prs.slide_layouts[i])
    assert template.keepout_for(info, info.body) == info.keepout
    assert template.keepout_for(info, 2) == info.keepout  # 章扉は本文として検査する
    std = template.analyze(paths.ASSETS / "template" / "standard.potx")
    assert std.keepout
    assert template.keepout_for(std, std.cover) == std.layout_keepout[str(std.cover)]


def test_describeは表紙と本文と裏表紙だけの対応表を返す(tpl):
    info = template.analyze(tpl)
    d = template.describe(tpl, info)
    assert d["body"] == {"layout": "本文", "index": 1}
    assert [r["key"] for r in d["rows"]] == ["cover", "closing"]
    assert d["rows"][1]["layout"] == "裏表紙"
    assert len(d["layouts"]) == 11


# ---- build ----


@pytest.mark.slow
def test_PPTXは表紙と本文と裏表紙のレイアウトだけで作られる(tmp_path, capsys, pkg, tpl):
    base = tmp_path / "out" / "pptx-deck-source" / "demo"
    rc, out, err = run(capsys, "init", str(base), "--template", str(tpl))
    assert rc == 0, err
    assert "layout_map" in out
    names = build_deck(
        capsys,
        base,
        pkg / "assets" / "components",
        ["layouts/cover.html", "layouts/text.html", "tables/options.html", "tables/actions.html", "charts/bar.html"],
    )
    assert names == ["表紙", "本文", "本文", "本文", "本文"]


def test_template_mapは廃止された(tmp_path, capsys, tpl):
    base = tmp_path / "out" / "pptx-deck-source" / "demo"
    assert run(capsys, "init", str(base), "--template", str(tpl))[0] == 0
    with pytest.raises(SystemExit):
        cli.main(["template-map", str(base)])


# ---- 壊れたテンプレート ----


def test_本文レイアウトにタイトルがなければタイトルのあるレイアウトで代える(tmp_path):
    tpl = strip_titles(make_template(tmp_path / "t.pptx", NAMES), [1])
    info = template.analyze(tpl)
    assert info.body != 1


def test_タイトルのあるレイアウトが1つもなければ分かりやすいエラーで止まる(tmp_path, capsys):
    tpl = strip_titles(make_template(tmp_path / "t.pptx", NAMES), range(11))
    with pytest.raises(ValueError, match="本文に使えるレイアウト"):
        template.analyze(tpl)
    rc, _, err = run(capsys, "init", str(tmp_path / "d"), "--template", str(tpl))
    assert rc == 2
    assert "エラー" in err


@pytest.mark.parametrize("pptxでない", [False, True], ids=["存在しない", "pptxではない"])
def test_存在しないかpptxでないテンプレートは終了コード2で止まる(tmp_path, capsys, pptxでない):
    t = tmp_path / "nai.pptx"
    if pptxでない:
        t.write_text("pptx ではない", encoding="utf-8")
    rc, _, err = run(capsys, "init", str(tmp_path / "d2"), "--template", str(t))
    assert rc == 2
    assert "エラー" in err


@pytest.mark.parametrize("cmd", ["build", "review-page", "finalize", "check"])
def test_template_jsonがなければ終了コード2で案内する(tmp_path, capsys, cmd):
    deck = tmp_path / "out" / "pptx-deck-source" / "empty"
    deck.mkdir(parents=True)
    (deck / "final.html").write_text("<html></html>", encoding="utf-8")
    target = str(deck / "final.html") if cmd == "check" else str(deck)
    rc, _, err = run(capsys, cmd, target, *(["--choices", str(deck)] if cmd == "finalize" else []))
    assert rc == 2
    assert "template.json がありません" in err


# ---- テンプレートの色・章扉 ----


def _green_template(tmp_path) -> Path:
    """テーマの accent1 を緑、accent2 を橙にしたテンプレート。"""
    import zipfile

    src = make_template(tmp_path / "base.pptx", NAMES)
    dst = tmp_path / "green.pptx"
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for it in zin.infolist():
            data = zin.read(it.filename)
            if it.filename.startswith("ppt/theme/theme"):
                data = data.replace(b"4F81BD", b"2E7D32").replace(b"C0504D", b"B85A0B")
            zout.writestr(it, data)
    return dst


def test_accent_colorsはテーマのaccent1とaccent2を返す(tmp_path):
    assert template.accent_colors(_green_template(tmp_path)) == ("#2E7D32", "#B85A0B")
    assert template.accent_colors(tmp_path / "ない.pptx") == ()


def test_build_uses_template_accent_when_design_has_no_colors(tmp_path, capsys, pkg):
    tpl = _green_template(tmp_path)
    base = tmp_path / "out" / "pptx-deck-source" / "demo"
    assert run(capsys, "init", str(base), "--template", str(tpl))[0] == 0
    capsys.readouterr()
    work = paths.resolve_work(base)
    (work / "design.md").write_text("# 設計図\n", encoding="utf-8")  # 色の欄なし
    write_slide(work / "slides", "01", (pkg / "assets" / "components" / "charts" / "bar.html").read_text("utf-8"))
    assert finalize_all(work) == 0
    rc, out, err = run(capsys, "build", str(base))
    assert rc == 0, out + err
    chart = next(s for s in Presentation(str(base.parent.parent / "demo.pptx")).slides[0].shapes if s.has_chart)
    xml = chart.chart._chartSpace.xml
    hex6 = re.findall(r'srgbClr val="([0-9A-F]{6})"', xml)[0]
    r, g, b = (int(hex6[i : i + 2], 16) for i in (0, 2, 4))
    assert g > r  # 系列色が緑系
    assert g > b


def test_divider_スライドは本文レイアウトで作る(tmp_path, capsys, tpl, pkg):
    base = tmp_path / "out" / "pptx-deck-source" / "demo"
    assert run(capsys, "init", str(base), "--template", str(tpl))[0] == 0
    capsys.readouterr()
    assert template.layout_index(template.analyze(tpl), {"layout": "divider"}) == 1
    work = paths.resolve_work(base)
    html = (pkg / "assets" / "components" / "layouts" / "text.html").read_text("utf-8")
    write_slide(work / "slides", "01", html.replace('data-layout="content"', 'data-layout="divider"'))
    assert finalize_all(work) == 0
    rc, out, err = run(capsys, "build", str(base))
    assert rc == 0, out + err
    assert [s.slide_layout.name for s in Presentation(str(base.parent.parent / "demo.pptx")).slides] == ["本文"]

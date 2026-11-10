"""文字サイズの項目（fontsize.py）と、theme.css / base.css の変数化。"""

# ruff: noqa: S101  # pytest の assert
import json

import pytest
from pptx_deck import fontsize, initdir, paths

from tests._paths import PKG


def test_defaults():
    cur = fontsize.current()
    assert cur["title"] == 37
    assert cur["caption"] == 16
    assert cur["source"] == 14
    assert cur["chart-scale"] == 1.0


def test_items_order_and_source():
    keys = [i.key for i in fontsize.ITEMS]
    assert len(keys) == 10
    assert keys[keys.index("caption") + 1] == "source"
    src = fontsize.ITEMS[keys.index("source")]
    assert (src.var, src.default, src.kind) == ("--fs-source", 14, "px")


def _set_fontsizes(work, values):
    """template.json に古い fontsizes を書き、theme.css などを作り直す（書くコマンドはもうない）。"""
    cfg = paths.read_cfg(work)
    cfg["fontsizes"] = values
    paths.write_cfg(work, cfg)
    initdir.write_derived(work, cfg)


def test_theme_css_has_vars(tmp_path):
    base = tmp_path / "out" / "pptx-deck-source" / "deck"
    initdir.init(base)
    work = paths.resolve_work(base)
    css = (work / "theme.css").read_text(encoding="utf-8")
    assert "--fs-title: 37px;" in css
    assert "--fs-cover-sub: 22px;" in css
    assert "--fs-source: 14px;" in css
    assert "--num-scale: 1;" in css

    _set_fontsizes(work, {"title": 40})
    assert "--fs-title: 37px;" in (work / "theme.css").read_text(encoding="utf-8")  # 古い fontsizes は無視する


def test_init_force_は古い_fontsizes_を引き継がない(tmp_path):
    base = tmp_path / "out" / "pptx-deck-source" / "deck"
    initdir.init(base)
    work = paths.resolve_work(base)
    _set_fontsizes(work, {"title": 40})
    initdir.init(base, force=True)
    assert "fontsizes" not in paths.read_cfg(work)
    assert "--fs-title: 37px;" in (work / "theme.css").read_text(encoding="utf-8")


def test_base_css_reads_vars():
    css = (PKG / "assets" / "web" / "base.css").read_text(encoding="utf-8")
    for token in (
        "font-size: var(--fs-title, 37px)",
        "font-size: var(--fs-lead, 27px)",
        "font-size: var(--fs-body, 19px)",
        "font-size: var(--fs-caption, 16px)",
        "font-size: var(--fs-cover-title, 40px)",
        "font-size: var(--fs-cover-sub, 22px)",
        '[data-role="subhead"]',
        "font-size: var(--fs-subhead, 22px)",
        "calc(44px * var(--num-scale, 1))",
    ):
        assert token in css, token


def test_theme_css_vars_are_inside_balanced_root(tmp_path):
    import re

    base = tmp_path / "out" / "pptx-deck-source" / "deck"
    initdir.init(base)
    css = (paths.resolve_work(base) / "theme.css").read_text(encoding="utf-8")
    assert css.count("{") == css.count("}")
    roots = re.findall(r":root\s*\{([^{}]*)\}", css)
    assert roots
    inside = "\n".join(roots)
    for it in fontsize.ITEMS:
        assert f"{it.var}:" in inside
        assert css.count(f"{it.var}:") == 1


@pytest.fixture
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def test_chart_pt():
    from pptx_deck import charts

    assert charts.chart_pt(1.0) == 12
    assert charts.chart_pt(0.84) == 10
    assert charts.chart_pt(1.5) == 18
    assert charts.chart_pt(0.7) == 10


@pytest.mark.slow
def test_build_chart_font_ignores_stale_scale(pkg, tmp_path):
    import html
    import json

    from pptx import Presentation
    from pptx_deck import build, template

    from tests._measure import model_of

    base = tmp_path / "out" / "pptx-deck-source" / "deck"
    initdir.init(base)
    work = paths.resolve_work(base)
    _set_fontsizes(work, {"chart-scale": 1.25})
    spec = {"type": "bar", "categories": ["a", "b"], "series": [{"name": "x", "values": [1, 2]}]}
    box = 'style="position:absolute;left:100px;top:150px;width:600px;height:400px"'
    model = model_of(f"<div class=\"pp-chart\" {box} data-chart='{html.escape(json.dumps(spec), quote=True)}'></div>")
    from types import SimpleNamespace

    pal = SimpleNamespace(accent="#00AA55", accent_mid="#55AA88", accent_dark="#005522")
    tpl = pkg / "assets" / "template" / "standard.potx"
    out = build.build(model, tpl, template.analyze(tpl), pal, tmp_path / "o.pptx", base_dir=work)
    chart = [s for s in Presentation(str(out)).slides[0].shapes if s.has_chart][0].chart
    assert chart.font.size.pt == 12  # 古い fontsizes の倍率は無視して、既定の 12pt


@pytest.mark.slow
def test_preview_uses_scale(browser, pkg):
    import json

    js = (pkg / "assets" / "web" / "chart-preview.js").read_text(encoding="utf-8")
    spec = {"type": "bar", "categories": ["a", "b"], "series": [{"name": "x", "values": [1, 2]}]}
    html = (
        "<html><body><div class='pp-chart' style='position:relative;width:600px;height:400px' "
        f"data-chart='{json.dumps(spec)}'></div></body></html>"
    )

    def sizes(scale):
        page = browser.new_page()
        page.set_content(html)
        page.evaluate(f"document.documentElement.style.setProperty('--chart-scale', '{scale}')")
        page.add_script_tag(content=js)
        page.evaluate("document.querySelectorAll('.pp-chart').forEach(window.__chartPreview)")
        out = page.evaluate("[...document.querySelectorAll('svg text')].map(t => +t.getAttribute('font-size'))")
        page.close()
        return out

    base, big, small = sizes(1), sizes(1.5), sizes(0.84)
    assert base
    assert 13 in base
    assert all(abs(x - 13.333) > 0.01 for x in base)  # 既定の倍率では下限が効かず、見た目が変わらない
    assert max(big) > max(base)
    assert min(small) == pytest.approx(10 * 96 / 72)  # 縮小では 10pt を下限にする


# --- 断片の直書き（Task 3） ---
_COMP = PKG / "assets" / "components"
_ROLES = ("title", "lead", "body", "caption")
# 役割付きの要素で font-size を残してよいもの → 理由。
# 注記のうち、旧 base.css の 14px で表示されていたもの（表の見出し・出典・脚注）は var(--fs-source) を読む。
ROLE_VARS = {("caption", "var(--fs-source)")}
# (断片, 役割, 値) → 個数: 直書きがなく旧 base.css の役割の既定（題28・ヘッド22）で表示されていた要素。
#   今は該当する断片がない（増えたらテストが落ちる）。
ALLOWED_OLD_ROLE: dict = {}
# 役割のない太字で、小見出し（var(--fs-subhead)）にせず 24px のままのもの → 理由。
ALLOWED_SUBHEAD_HARDCODED: dict = {}
# (断片, 役割, 値): 役割の既定と違う直書き。表にない大きさとして残した。
ALLOWED: dict = {}
# 倍率にしない小さい数字: 0.7 倍で本文の下限 19px を割るため（倍率は 30px 以上だけ）。
NUM_SCALE_MIN = 30
# 役割のない 30px 以上の太字で、倍率にしないもの（数字ではない記号・言葉を含む見出し） → 理由。
ALLOWED_BIG_BOLD: dict = {}


def _fragment_elements():
    """(断片の相対パス, 属性の辞書) を、pp-picture の中を除いて返す。"""
    from html.parser import HTMLParser

    void = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    class P(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack: list[bool] = []
            self.found: list[dict] = []

        def handle_starttag(self, tag, attrs, empty=False):
            a = dict(attrs)
            pic = any(self.stack) or "pp-picture" in (a.get("class") or "").split()
            if not empty and tag not in void:
                self.stack.append(pic)
            if not pic:
                self.found.append(a)

        def handle_startendtag(self, tag, attrs):
            self.handle_starttag(tag, attrs, empty=True)

        def handle_endtag(self, tag):
            if tag not in void and self.stack:
                self.stack.pop()

    out = []
    for f in sorted(_COMP.rglob("*.html")):
        rel = f.relative_to(_COMP).as_posix()
        if rel.startswith("pictures/"):
            continue
        p = P()
        p.feed(f.read_text(encoding="utf-8"))
        out += [(rel, a) for a in p.found]
    return out


def _inline_size(a):
    import re

    m = re.search(r"(?:^|;)\s*font-size\s*:\s*([^;]*?)\s*(?:;|$)", a.get("style") or "")
    return m.group(1) if m else None


def test_fragments_have_no_hardcoded_role_sizes():
    from collections import Counter

    bad, old_role = [], Counter()
    for rel, a in _fragment_elements():
        role, size = a.get("data-role"), _inline_size(a)
        if role not in _ROLES or size is None:
            continue
        if (role, size) in ROLE_VARS:
            continue
        if (rel, role, size) in ALLOWED_OLD_ROLE:
            old_role[(rel, role, size)] += 1
        elif (rel, role, size) not in ALLOWED:
            bad.append((rel, a.get("data-part"), role, size))
    assert bad == []
    assert dict(old_role) == ALLOWED_OLD_ROLE  # 旧の値を書いた要素は、この表の個数どおり


def test_fragments_read_vars_for_body_note_and_subhead():
    """役割のない要素は、本文（19）・注記（16）・出典（14）・小見出し（太字の 21/22/24）の大きさを、直書きしない。"""
    bad = []
    for rel, a in _fragment_elements():
        size, cls = _inline_size(a), (a.get("class") or "").split()
        if a.get("data-role") or size is None or not size.endswith("px"):
            continue
        v = float(size[:-2])
        if v in (19, 16, 14):
            bad.append((rel, a.get("data-part"), size, "var(--fs-body|--fs-caption|--fs-source) を読む"))
        elif v in (21, 22, 24) and "b" in cls and "num" not in cls and (rel, size) not in ALLOWED_SUBHEAD_HARDCODED:
            bad.append((rel, a.get("data-part"), size, "var(--fs-subhead) を読む"))
    assert bad == []


def test_fragments_use_scale_for_num():
    bad = []
    for rel, a in _fragment_elements():
        size = _inline_size(a)
        if "num" not in (a.get("class") or "").split() or size is None or "calc(" in size:
            continue
        if not (size.endswith("px") and float(size[:-2]) < NUM_SCALE_MIN):
            bad.append((rel, a.get("data-part"), size))
    assert bad == []


@pytest.mark.slow
def test_default_check_violations_unchanged(tmp_path):
    from collections import Counter

    from pptx_deck import check, measure, template

    from tests._paths import REPO

    base = tmp_path / "out" / "pptx-deck-source" / "deck"
    initdir.init(base)
    work = paths.resolve_work(base)
    info = template.TemplateInfo.from_dict(json.loads((work / "template.json").read_text(encoding="utf-8"))["info"])
    got = {}
    for f in sorted(_COMP.rglob("*.html")):
        (work / "final.html").write_text(
            '<!doctype html><html lang="ja"><head><meta charset="utf-8"><link rel="stylesheet" href="theme.css">'
            '<link rel="stylesheet" href="base.css"></head><body>' + f.read_text(encoding="utf-8") + "</body></html>",
            encoding="utf-8",
        )
        c = Counter()
        for v in check.check_model(measure.measure(work / "final.html"), info):
            c[v["rule"] if v["severity"] == "error" else v["rule"] + ":warning"] += 1
        got[f.relative_to(_COMP).as_posix()] = dict(sorted(c.items()))
    want = json.loads((REPO / "tests" / "fixtures" / "fs_baseline.json").read_text(encoding="utf-8"))
    assert {k: v for k, v in got.items() if v != want.get(k)} == {}


def test_fragments_scale_big_bold_numbers():
    """役割のない 30px 以上の太字（.num のない大きな数字）は、倍率を読む。"""
    bad = []
    for rel, a in _fragment_elements():
        size, cls = _inline_size(a), (a.get("class") or "").split()
        if a.get("data-role") or "b" not in cls or size is None or not size.endswith("px"):
            continue
        if float(size[:-2]) >= NUM_SCALE_MIN and (rel, size) not in ALLOWED_BIG_BOLD:
            bad.append((rel, a.get("data-part"), size))
    assert bad == []

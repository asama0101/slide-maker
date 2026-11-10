"""pp-text の中で PPTX に取り込めなかった文字を lost に入れ、check_model が textLost のエラーにする。"""

# ruff: noqa: S101  # pytest の assert
import json
import re

import pytest
from pptx_deck import check, initdir, measure, paths, template

from tests._measure import model_of

pytestmark = pytest.mark.slow  # ブラウザ（Chromium）で測る

BOX = 'style="position:absolute;left:80px;top:80px;width:600px;height:300px"'


def _text(inner):
    return model_of(f'<div class="pp-text" {BOX}>{inner}</div>')


def _info():
    return template.analyze(paths.ASSETS / "template" / "standard.potx")


def _lost_rules(model):
    return [v for v in check.check_model(model, _info()) if v["rule"] == "textLost"]


def _para_texts(element):
    return [[r["text"] for r in p["runs"]] for p in element["paras"]]


@pytest.mark.parametrize(
    ("inner", "lost_text"),
    [
        ("<ul><li>親<ul><li>子の項目</li></ul></li></ul>", "子の項目"),
        ("前置き<p>段落</p>", "前置き"),
    ],
    ids=["入れ子の_ul", "裸の文字と_p_の混在"],
)
def test_取り込めない文字は_textLost_のエラーになる(inner, lost_text):
    vs = _lost_rules(_text(inner))
    assert len(vs) == 1
    assert vs[0]["severity"] == "error"
    assert lost_text in vs[0]["message"]


def test_div_の段落は取り込む():
    m = _text("<div>一</div><div>二</div>")
    e = m[0]["elements"][0]
    assert e["lost"] == ""
    assert _para_texts(e) == [["一"], ["二"]]
    assert _lost_rules(m) == []


@pytest.mark.parametrize("display", ["inline", "inline-block"])
def test_inline_の_div_は行内の文字として取り込む(display):
    m = _text(f'前<div style="display:{display}">中</div>後')
    e = m[0]["elements"][0]
    assert e["lost"] == ""
    assert _para_texts(e) == [["前", "中", "後"]]
    assert _lost_rules(m) == []


@pytest.mark.parametrize(
    ("inner", "paras"),
    [
        ("<p>あ</p><p>い<br>う</p>", 2),
        ("<ul><li>あ</li></ul>", 1),
        ("  あ\n  い  ", 1),
    ],
    ids=["p_と_br", "ul_li", "裸の文字"],
)
def test_通常の_p_と_ul_は_lost_が空(inner, paras):
    e = _text(inner)[0]["elements"][0]
    assert e["lost"] == ""
    assert len(e["paras"]) == paras


def test_表のセルの段落は変わらない():
    m = model_of(
        '<table class="pp-table" style="position:absolute;left:80px;top:80px;width:400px">'
        "<tr><td><div>一</div><div>二</div></td></tr></table>"
    )
    paras = m[0]["elements"][0]["table"]["rows"][0]["cells"][0]["paras"]
    assert [[r["text"] for r in p["runs"]] for p in paras] == [["一", "二"]]


@pytest.mark.slow
def test_部品の全断片を測って_textLost_が0件(pkg, tmp_path):
    """部品の全断片（各ファイルの最初の section）を 1 つの HTML にまとめて測り、textLost が 0 件。"""
    comp = pkg / "assets" / "components"
    sec = re.compile(r"<section\b.*?</section>", re.S)
    secs = []
    for f in sorted(comp.rglob("*.html")):
        m = sec.search(re.sub(r"<!--.*?-->", "", f.read_text(encoding="utf-8"), flags=re.S))
        if m:
            secs.append((f.relative_to(comp).as_posix(), m.group(0)))
    assert len(secs) == 16
    base = tmp_path / "out" / "pptx-deck-source" / "deck"
    initdir.init(base, template_path=None, force=False, footer=None)
    work = paths.resolve_work(base)
    info = template.TemplateInfo.from_dict(json.loads((work / "template.json").read_text(encoding="utf-8"))["info"])
    html = (
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<link rel="stylesheet" href="theme.css"><link rel="stylesheet" href="base.css"></head><body>'
        + "\n".join(s for _, s in secs)
        + "</body></html>"
    )
    (work / "final.html").write_text(html, encoding="utf-8")
    model = measure.measure(work / "final.html")
    assert len(model) == len(secs)
    bad = [(secs[v["slide"] - 1][0], v["message"]) for v in check.check_model(model, info) if v["rule"] == "textLost"]
    assert bad == []

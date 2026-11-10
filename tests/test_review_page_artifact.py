# ruff: noqa: S101  # pytest の assert
"""案を選ぶ Artifact ページ（review_page.build）のテスト。"""

import json
import re
from pathlib import Path

import pytest
from pptx_deck import cli, initdir, paths, review_page

from tests._flow import write_slide


def _work(tmp_path: Path) -> Path:
    s = tmp_path / "slides"
    s.mkdir()
    for k in ("R1", "R2"):
        (s / f"01-{k}.html").write_text(f'<div class="pp-text">MARK-01{k}</div>', encoding="utf-8")
    for k in ("R1", "R2", "R3"):
        (s / f"02-{k}.html").write_text(f'<div class="pp-text">MARK-02{k}</div>', encoding="utf-8")
    (tmp_path / "theme.css").write_text(":root{--bg:#fff;}", encoding="utf-8")
    (tmp_path / "base.css").write_text(".pp-text{color:red}", encoding="utf-8")
    (tmp_path / "chart-preview.js").write_text("window.__chartPreview=function(){};", encoding="utf-8")
    return tmp_path


def test_contains_every_candidate(tmp_path):
    html = review_page.build(_work(tmp_path)).read_text(encoding="utf-8")
    for m in ("MARK-01R1", "MARK-01R2", "MARK-02R1", "MARK-02R2", "MARK-02R3"):
        assert m in html
    assert (tmp_path / "review.html").exists()


def test_collection_and_fields(tmp_path):
    html = review_page.build(_work(tmp_path)).read_text(encoding="utf-8")
    assert review_page.COLLECTION == "choices"
    assert "choices/" in html
    for f in ("pick", "comment", "status", "approved", "saved"):
        assert f in html
    assert 'use?.("db")' in html
    assert 'use?.("comments")' in html
    assert "customAnchors" in html
    assert "<title>スライド案の選択</title>" in html


def test_capabilities_constant_and_module_comment():
    assert review_page.CAPABILITIES == {"db": {}, "comments": {"composer_only": True, "customAnchors": True}}
    first = Path(review_page.__file__).read_text(encoding="utf-8").splitlines()[0]
    assert '{"db": {}, "comments": {"composer_only": true, "customAnchors": true}}' in first


def test_cli_help_names_capabilities(capsys):
    with pytest.raises(SystemExit):
        cli.entry(["--help"])
    out = " ".join(capsys.readouterr().out.split())  # 長い行は折り返される
    assert '{"db": {}, "comments": {"composer_only": true, "customAnchors": true}}' in out


def test_declares_no_external_loads_except_google_font(tmp_path):
    html = review_page.build(_work(tmp_path)).read_text(encoding="utf-8")
    assert not re.search(r"<script[^>]+src=", html)
    links = re.findall(r"<link\b[^>]*>", html)
    assert links == [
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=BIZ+UDPGothic:wght@400;700&display=swap">'
    ]
    rest = html.replace(links[0], "")
    assert "http://" not in rest
    assert "https://" not in rest


def test_fragment_cannot_break_out_of_script(tmp_path):
    work = _work(tmp_path)
    write_slide(work / "slides", "01", "<div></script><b>EVIL</b></div>")
    html = review_page.build(work).read_text(encoding="utf-8")
    assert "</script><b>EVIL" not in html


def test_missing_asset_is_error(tmp_path):
    work = _work(tmp_path)
    (work / "base.css").unlink()
    with pytest.raises(ValueError, match="base.css"):
        review_page.build(work)


def _page_data(html: str) -> list:
    return json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S).group(1))


def test_shadow_css_has_theme_base_and_host_font(tmp_path):
    work = _work(tmp_path)
    (work / "theme.css").write_text(':root{--bg:#fff;}\n.slide[data-layout="cover"]{--bg:#123456;}', encoding="utf-8")
    html = review_page.build(work).read_text(encoding="utf-8")
    css = json.loads(re.search(r"^var BASE = (.*);$", html, re.M).group(1))
    # 表紙の色の規則と base.css は shadow root の中に要る（文書の <style> は shadow の中に届かない）
    assert '.slide[data-layout="cover"]{--bg:#123456;}' in css
    assert ".pp-text{color:red}" in css
    assert re.search(r":host\s*\{[^}]*font-family:\s*'BIZ UDPGothic'", css)
    # chart-preview.js が document の :root から変数を読むので、文書側にもテーマを残す
    assert html.index(":root{--bg:#fff;}") < html.index("var BASE")
    assert "adoptedStyleSheets" in html


def test_placeholder_in_fragment_is_not_substituted(tmp_path):
    work = _work(tmp_path)
    write_slide(work / "slides", "01", '<div class="pp-text">__BASE__ __CHART__ __COLLECTION__ __THEME__</div>')
    html = review_page.build(work).read_text(encoding="utf-8")
    assert _page_data(html)[0][1]["R1"] == '<div class="pp-text">__BASE__ __CHART__ __COLLECTION__ __THEME__</div>'


def test_variant_label_is_shown(tmp_path):
    work = _work(tmp_path)
    s = work / "slides"
    (s / "02-R1.html").write_text('<section class="slide" data-variant="自由設計｜左右の対比">x</section>', "utf-8")
    (s / "02-R2.html").write_text('<section class="slide" data-variant="&lt;縦&gt;の流れ">x</section>', "utf-8")
    html = review_page.build(work).read_text(encoding="utf-8")
    pages = _page_data(html)
    assert pages[0][2] == {"R1": "", "R2": ""}
    assert pages[1][2] == {"R1": "左右の対比", "R2": "<縦>の流れ", "R3": ""}


def test_page_title_comes_from_fragment(tmp_path):
    work = _work(tmp_path)
    s = work / "slides"
    write_slide(
        s, "01", '<section class="slide"><div class="pp-text" data-ph="title">表紙の<br>題 &amp; 副</div></section>'
    )
    for k in ("R1", "R2", "R3"):
        (s / f"02-{k}.html").write_text(
            '<section class="slide"><div class="pp-text" data-role="head">ヘッド</div>'
            '<div class="pp-text" data-role="title"><span>とても長い題で二十四文字を</span>'
            "超えてしまうページの題です</div>"
            "</section>",
            "utf-8",
        )
    write_slide(s, "03", '<section class="slide"><div class="pp-text">題なし</div></section>')
    pages = _page_data(review_page.build(work).read_text(encoding="utf-8"))
    assert [p[3] for p in pages] == ["表紙の題 & 副", "とても長い題で二十四文字を超えてしまうページの…", ""]


def _cli(capsys, *argv):
    capsys.readouterr()
    rc = cli.entry(["review-page", *argv])
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


@pytest.fixture
def deck(tmp_path):
    base = tmp_path / "out" / "pptx-deck-source" / "deck"
    initdir.init(base)
    work = paths.resolve_work(base)
    write_slide(work / "slides", "01", '<section class="slide">ONE</section>')
    return work


def test_cli_review_page_prints_path(deck, capsys):
    rc, out, err = _cli(capsys, str(deck))
    assert rc == 0
    assert json.loads(out)["path"] == str(deck / "review.html")
    assert (deck / "review.html").is_file()
    assert err == ""


def test_review_page_prints_warnings_and_succeeds(deck, capsys):
    """文字だけの案があっても警告を出すだけで、終了コードは 0。表紙（script.md の cover）は免除。"""
    (deck / "script.md").write_text("## S01 表紙\n- layout: cover\n", encoding="utf-8")
    write_slide(deck / "slides", "02", '<div class="pp-text">x</div>', '<div class="pp-chart"></div>')
    rc, out, _ = _cli(capsys, str(deck))
    assert rc == 0
    assert json.loads(out)["warnings"] == ["02-R1: 図・絵・表・グラフが主役になっていません"]


def test_cli_review_page_without_slides_dir(deck, capsys):
    (deck / "slides" / "01-R1.html").unlink()
    (deck / "slides" / "01-R2.html").unlink()
    (deck / "slides").rmdir()
    rc, out, err = _cli(capsys, str(deck))
    assert rc == 2
    assert err.startswith("エラー:")
    assert "slides" in err
    assert out == ""


def test_cli_review_page_with_bad_candidate_name(deck, capsys):
    (deck / "slides" / "02-B.html").write_text("<section>x</section>", encoding="utf-8")
    rc, _, err = _cli(capsys, str(deck))
    assert rc == 2
    assert err.startswith("エラー:")
    assert "02-B.html" in err
    assert not (deck / "review.html").exists()


def test_html_comment_open_is_neutralized_in_embedded_data(tmp_path):
    work = _work(tmp_path)
    write_slide(work / "slides", "01", "<div><!--<script>x</div>")
    html = review_page.build(work).read_text(encoding="utf-8")
    raw = re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S).group(1)
    assert "<!--" not in raw
    assert _page_data(html)[0][1]["R1"] == "<div><!--<script>x</div>"

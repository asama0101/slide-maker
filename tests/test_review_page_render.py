# ruff: noqa: S101  # pytest の assert
"""案を選ぶページ（review.html）をブラウザで開いて確かめる: shadow root の中の書体・表紙の色、
案の選択と承認の書き込み、標準のコメント欄（comments）の呼び出し。"""

import pytest
from slide_maker import initdir, paths, review_page

from tests._paths import PKG

pytestmark = pytest.mark.slow  # ブラウザ（Chromium）で開く

COMP = PKG / "assets" / "components"
# db と comments の偽物: set を window.__writes に、customAnchors の呼び出しを window.__calls に記録する
# （登録された関数は window.__handlers）。スナップショットは自分では届けず、テストが window.__snap(path, data) で届ける
# window.__failWrites で書き込みを失敗させ、window.__holdWrites で書き込みを止める（window.__release(失敗か) で終える）
# window.__holdComments で comments の準備を止める（window.__releaseComments() で進める）
FAKE_CLAUDE = """
window.__cbs = {};
window.__calls = [];
window.__snap = function (path, d) { window.__cbs[path]({exists: true, data: function () { return d; }}); };
window.claude = {use: async function (name) {
  if (name === 'comments') {
    if (window.__holdComments) await new Promise(function (r) { window.__releaseComments = r; });
    if (window.__noComments) return null;
    var cm = {openComposer: async function () { window.__calls.push(['openComposer']); return {opened: true}; }};
    if (!window.__noAnchors) cm.customAnchors = async function (handlers) {
      window.__handlers = handlers;
      return {
        placed: function (m) { window.__calls.push(['placed', m]); },
        exitMode: function () { window.__calls.push(['exitMode']); },
        domAnchor: function (el) { return [{anchorOf: el}]; },
        compose: async function (a, el) {
          window.__calls.push(['compose', a.anchorOf === el, el]);
          return window.__composerResult || {opened: true};
        }
      };
    };
    return cm;
  }
  if (name !== 'db') return null;
  return {doc: function (path) { return {
    set: function (d) {
      window.__writes = (window.__writes || []).concat([[path, d]]);
      if (window.__holdWrites) return new Promise(function (ok, ng) {
        window.__release = function (fail) { if (fail) ng({code: 'denied'}); else ok(); };
      });
      return window.__failWrites ? Promise.reject({code: 'denied'}) : Promise.resolve();
    },
    onSnapshot: function (cb) { window.__cbs[path] = cb; return function () {}; }
  }; }};
}};
"""
NO_SHEET = "window.CSSStyleSheet = undefined;"  # 共有シートが使えないブラウザ（<style> で代える）
NO_COMMENTS = "window.__noComments = true;"
NO_ANCHORS = "window.__noAnchors = true;"  # 位置をページが決める方式（customAnchors）がない
NOT_OPENED = "window.__composerResult = {opened: false};"
HOLD_COMMENTS = "window.__holdComments = true;"
EVIL = '<img src=x onerror="window.__xss=1"><b id="evil">太字</b>'
EVIL_TEXT = "&lt;img src=x onerror=&quot;window.__xss=1&quot;&gt;&lt;b id=&quot;evil&quot;&gt;太字&lt;/b&gt;"


def _open(p, tmp_path, init_script, slides):
    base = tmp_path / "out" / "slide-maker-source" / "deck"
    initdir.init(base)
    work = paths.resolve_work(base)
    # 表紙の色が違うテンプレートの代わり。この規則は文書の <style> からは shadow の中に届かない
    with (work / "theme.css").open("a", encoding="utf-8") as f:
        f.write('\n.slide[data-layout="cover"] { --bg: #123456; }\n')
    s = work / "slides"
    s.mkdir(exist_ok=True)
    for name, text in slides.items():
        (s / name).write_text(text, encoding="utf-8")
    body = review_page.build(work).read_text(encoding="utf-8")
    html = work / "review-test.html"
    html.write_text(f"<!doctype html><html><head><meta charset=utf-8></head><body>{body}</body></html>", "utf-8")
    pg = p.chromium.launch().new_page()
    errors = []
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    # 外へ取りに行かない（Web フォントの CSS は空で返す）
    pg.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
    pg.add_init_script(FAKE_CLAUDE + init_script)
    pg.goto(html.as_uri())
    pg.wait_for_function("document.getElementById('st').textContent.indexOf('接続しました') >= 0")
    return pg, errors


def _slides():
    text = (COMP / "layouts" / "text.html").read_text(encoding="utf-8")
    cover = (COMP / "layouts" / "cover.html").read_text(encoding="utf-8")
    bar = (COMP / "charts" / "bar.html").read_text(encoding="utf-8")
    return {
        "01-R1.html": cover,
        "01-R2.html": cover.replace('<section class="slide"', '<section class="slide" data-variant="別の表紙"', 1),
        "02-R1.html": bar,
        "02-R2.html": bar.replace('<section class="slide"', '<section class="slide" data-variant="別のグラフ"', 1),
        "03-R1.html": text,
        "03-R2.html": text.replace(
            '<section class="slide"', '<section class="slide" data-variant="自由設計｜縦の流れ"', 1
        ),
    }


@pytest.fixture
def page(tmp_path, request):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        pg, errors = _open(p, tmp_path, getattr(request, "param", ""), _slides())
        # 大きな表示 3 枚（ページごと）と、各ページの案の縮小 6 枚
        pg.wait_for_function("document.querySelectorAll('.rvh').length === 9")
        yield pg, errors


def _writes(pg):
    return pg.evaluate("window.__writes || []")


def _wait_writes(pg, n):
    pg.wait_for_function(f"(window.__writes || []).length === {n}")
    return _writes(pg)


def test_no_console_errors(page):
    pg, errors = page
    assert errors == []


@pytest.mark.parametrize("page", ["", NO_SHEET], indirect=True, ids=["共有シート", "style要素"])
def test_text_in_shadow_uses_slide_font(page):
    pg, errors = page
    assert errors == []
    font = pg.evaluate(
        "getComputedStyle(document.querySelector('.rvh').shadowRoot.querySelector('.pp-text')).fontFamily"
    )
    assert font.replace('"', "'").startswith("'BIZ UDPGothic'")


def test_cover_color_rule_applies_in_shadow(page):
    pg, _ = page
    bg = pg.evaluate(
        "getComputedStyle(document.querySelector('.rvh').shadowRoot.querySelector('.slide')).backgroundColor"
    )
    assert bg == "rgb(18, 52, 86)"


def test_chart_is_drawn_with_theme_colors(page):
    """グラフは文書に入ってから描く（入る前に描くと、変数が読めず灰色 #333 になる）。"""
    pg, _ = page
    fills = pg.evaluate(
        "[...document.querySelector('#pg-02 .rvbig .rvh').shadowRoot.querySelectorAll('.pp-chart rect')]"
        ".map(e => e.getAttribute('fill'))"
    )
    assert fills
    assert "#333" not in fills


def test_cards_nav_and_titles(page):
    pg, _ = page
    assert pg.evaluate("[...document.querySelectorAll('section.rvpg')].map(s => s.id)") == ["pg-01", "pg-02", "pg-03"]
    assert pg.evaluate(
        "[...document.querySelectorAll('section.rvpg')].every(s => s.hasAttribute('data-comment-target'))"
    )
    assert pg.evaluate("[...document.querySelectorAll('#nav a')].map(a => a.getAttribute('href'))") == [
        "#pg-01",
        "#pg-02",
        "#pg-03",
    ]
    # 題は断片の data-role="title"・data-ph="title" から
    assert "夜間切替の運用ルール" in pg.text_content("#pg-03 h2")
    assert pg.text_content("#pg-03 h2").startswith("スライド 03")
    assert "夜間切替の運用ルール" in pg.text_content("#nav a[href='#pg-03']")
    # 案の縮小の見出しに、data-variant の特徴が出る
    assert pg.text_content("#pg-03 .rvthumb[data-k='R2'] small") == "R2　縦の流れ"
    # どのページにも案の縮小が出る
    assert pg.evaluate("document.querySelectorAll('#pg-01 .rvthumb').length") == 2


def test_no_write_on_load(page):
    pg, _ = page
    pg.wait_for_timeout(300)
    assert _writes(pg) == []
    assert pg.text_content("#ptxt") == "承認 0/3　未承認 3"


def test_pick_writes_saved_choice_and_swaps_preview(page):
    pg, _ = page
    assert pg.get_attribute("#pg-03 .rvbig .rvf", "data-k") == "R1"  # 未選択のあいだは先頭の案を見せる
    pg.click("#pg-03 .rvthumb[data-k='R2']")
    ((path, d),) = _wait_writes(pg, 1)
    assert path == "choices/03"
    assert set(d) == {"pick", "comment", "status", "at"}
    assert (d["pick"], d["comment"], d["status"]) == ("R2", "", "saved")
    assert pg.get_attribute("#pg-03 .rvbig .rvf", "data-k") == "R2"
    assert "on" in pg.get_attribute("#pg-03 .rvthumb[data-k='R2']", "class")
    assert pg.text_content("#pg-03 .rvbd") == "選択中（未承認）"
    # 同じ案をもう一度押しても書かない
    pg.click("#pg-03 .rvthumb[data-k='R2']")
    pg.wait_for_timeout(200)
    assert len(_writes(pg)) == 1


def test_pick_on_approved_page_writes_saved(page):
    pg, _ = page
    pg.evaluate("window.__snap('choices/03', {pick: 'R1', comment: '', status: 'approved'})")
    assert pg.text_content("#pg-03 .rvbd") == "承認済み"
    pg.click("#pg-03 .rvthumb[data-k='R2']")
    ((_, d),) = _wait_writes(pg, 1)
    assert (d["pick"], d["status"]) == ("R2", "saved")


def test_approve_is_disabled_without_pick(page):
    pg, _ = page
    assert pg.is_disabled("#pg-03 button[data-act='approve']")
    assert pg.is_disabled("#pg-01 button[data-act='approve']")  # 案を選ぶまでは承認できない


def test_approve_and_undo(page):
    pg, _ = page
    assert pg.is_hidden("#pg-01 button[data-act='undo']")
    pg.click("#pg-01 .rvthumb[data-k='R1']")
    _wait_writes(pg, 1)
    pg.click("#pg-01 button[data-act='approve']")
    ((_, _), (path, d)) = _wait_writes(pg, 2)
    assert path == "choices/01"
    assert (d["pick"], d["comment"], d["status"]) == ("R1", "", "approved")
    assert pg.is_visible("#pg-01 button[data-act='undo']")
    assert pg.is_disabled("#pg-01 button[data-act='approve']")
    pg.click("#pg-01 button[data-act='undo']")
    w = _wait_writes(pg, 3)
    assert (w[2][0], w[2][1]["pick"], w[2][1]["status"]) == ("choices/01", "R1", "saved")
    assert pg.is_hidden("#pg-01 button[data-act='undo']")


def test_snapshots_update_counts_status_and_pick(page):
    pg, _ = page
    pg.evaluate("window.__snap('choices/01', {pick: 'A', comment: '', status: 'approved'})")
    pg.evaluate("window.__snap('choices/03', {pick: 'R2', comment: '', status: 'saved'})")
    assert pg.text_content("#ptxt") == "承認 1/3　未承認 2"
    assert pg.text_content("#nav a[href='#pg-01'] em") == "承認済み"
    assert pg.text_content("#nav a[href='#pg-03'] em") == "選択中（未承認）"
    assert pg.text_content("#nav a[href='#pg-02'] em") == "未承認"
    assert pg.get_attribute("#pg-03 .rvbig .rvf", "data-k") == "R2"
    assert pg.is_enabled("#pg-03 button[data-act='approve']")
    pg.wait_for_timeout(200)
    assert _writes(pg) == []  # 届いた値を書き戻さない


def test_comment_button_composes_on_preview(page):
    pg, _ = page
    pg.wait_for_function("window.__calls.some(c => c[0] === 'placed')")
    pg.click("#pg-02 button[data-act='comment']")
    pg.wait_for_function("window.__calls.some(c => c[0] === 'compose')")
    # 大きな表示の要素を、その要素の位置（domAnchor）とともに渡す
    ok, is_big = pg.evaluate(
        "(() => { const c = window.__calls.find(c => c[0] === 'compose');"
        " return [c[1], c[2] === document.querySelector('#pg-02 .rvbig')]; })()"
    )
    assert ok
    assert is_big
    assert ["openComposer"] not in pg.evaluate("window.__calls")
    assert _writes(pg) == []


def test_comment_anchors_are_registered_and_mode_ends_when_composer_closes(page):
    pg, _ = page
    pg.wait_for_function("window.__calls.some(c => c[0] === 'placed')")
    assert pg.evaluate("window.__calls") == [["placed", {}]]  # 登録の直後に、空の対応表を 1 回
    pg.evaluate("window.__handlers.threads([])")
    pg.evaluate("window.__handlers.composing(true)")
    assert pg.evaluate("window.__calls") == [["placed", {}], ["placed", {}]]
    pg.evaluate("window.__handlers.composing(false)")  # 入力欄が閉じたら、コメントのモードを終える
    assert pg.evaluate("window.__calls")[-1] == ["exitMode"]


@pytest.mark.parametrize("page", [NO_COMMENTS, NO_ANCHORS], indirect=True, ids=["comments なし", "customAnchors なし"])
def test_without_comment_anchors_button_is_disabled(page):
    pg, _ = page
    pg.wait_for_function("document.querySelector('#pg-02 button[data-act=comment]').disabled")
    assert pg.text_content("#m-02") == "この環境ではコメントを開けません"
    assert ["openComposer"] not in pg.evaluate("window.__calls")


def test_large_preview_is_same_size_for_single_and_multi_candidate_pages(page):
    pg, _ = page
    single, multi = pg.evaluate(
        "['#pg-01', '#pg-03'].map(s => { const b = document.querySelector(s + ' .rvbig');"
        " return [b.className, getComputedStyle(b).maxWidth, b.getBoundingClientRect().width]; })"
    )
    assert single == multi
    assert single[1] == "980px"


@pytest.mark.parametrize("page", [NOT_OPENED], indirect=True, ids=["開けない"])
def test_composer_not_opened_asks_to_retry(page):
    pg, _ = page
    pg.click("#pg-02 button[data-act='comment']")
    pg.wait_for_function("document.getElementById('m-02').textContent !== ''")
    assert pg.text_content("#m-02") == "コメント欄を開けませんでした。もう一度押してください"


def test_text_from_fragments_and_snapshots_is_never_interpreted_as_html(tmp_path):
    """断片の題・data-variant の特徴、届いたスナップショットの値を、HTML として解釈しない。"""
    text = (COMP / "layouts" / "text.html").read_text(encoding="utf-8")
    slides = {
        "01-R1.html": f'<section class="slide" data-variant="自由設計｜{EVIL_TEXT}">'
        f'<div class="pp-text" data-role="title">{EVIL_TEXT}</div></section>',
        "01-R2.html": text,
    }
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        pg, errors = _open(p, tmp_path, "", slides)
        pg.evaluate("d => window.__snap('choices/01', {pick: d, comment: d, status: d})", EVIL)
        pg.wait_for_timeout(200)  # 解釈されていれば、画像の読み込みの失敗（onerror）がここまでに起きる
        assert EVIL[:20] in pg.text_content("#pg-01 h2")
        assert EVIL[:20] in pg.text_content("#pg-01 .rvthumb[data-k='R1'] small")
        assert pg.evaluate("document.querySelectorAll('#evil, img[src=x]').length") == 0
        assert pg.evaluate("window.__xss") is None
        assert errors == []


def test_snapshot_applies_after_failed_write(page):
    """書き込みに失敗したら、選び直しの保護を解き、届いた選択を映す。"""
    pg, _ = page
    pg.evaluate("window.__failWrites = true")
    pg.click("#pg-03 .rvthumb[data-k='R2']")
    pg.wait_for_function("document.getElementById('w-03').textContent.indexOf('保存できませんでした') === 0")
    pg.evaluate("window.__snap('choices/03', {pick: 'R1', comment: '', status: 'saved'})")
    assert pg.get_attribute("#pg-03 .rvbig .rvf", "data-k") == "R1"
    assert "on" in pg.get_attribute("#pg-03 .rvthumb[data-k='R1']", "class")


def test_repick_on_approved_page_shows_unapproved_at_once_and_reverts_on_failure(page):
    pg, _ = page
    pg.evaluate("window.__snap('choices/03', {pick: 'R1', comment: '', status: 'approved'})")
    pg.evaluate("window.__holdWrites = true")
    pg.click("#pg-03 .rvthumb[data-k='R2']")
    _wait_writes(pg, 1)
    # 書き終わる前に、承認されていない状態を見せる
    assert pg.text_content("#pg-03 .rvbd") == "選択中（未承認）"
    assert pg.is_enabled("#pg-03 button[data-act='approve']")
    assert pg.is_hidden("#pg-03 button[data-act='undo']")
    pg.evaluate("window.__release(true)")
    pg.wait_for_function("document.getElementById('w-03').textContent.indexOf('保存できませんでした') === 0")
    # 失敗したら、元の状態（承認済み・R1）に戻す
    assert pg.text_content("#pg-03 .rvbd") == "承認済み"
    assert pg.get_attribute("#pg-03 .rvbig .rvf", "data-k") == "R1"
    assert pg.is_visible("#pg-03 button[data-act='undo']")
    assert pg.is_disabled("#pg-03 button[data-act='approve']")


@pytest.mark.parametrize("page", [HOLD_COMMENTS], indirect=True, ids=["準備中"])
def test_comment_button_is_disabled_until_comments_are_ready(page):
    pg, _ = page
    assert pg.is_disabled("#pg-02 button[data-act='comment']")
    pg.evaluate("window.__releaseComments()")
    pg.wait_for_function("!document.querySelector('#pg-02 button[data-act=comment]').disabled")
    assert pg.text_content("#m-02") == ""


@pytest.mark.parametrize("page", [NO_COMMENTS], indirect=True, ids=["comments なし"])
def test_comment_unavailable_message_is_not_overwritten_by_write_message(page):
    pg, _ = page
    pg.wait_for_function("document.getElementById('m-01').textContent !== ''")
    pg.click("#pg-01 .rvthumb[data-k='R1']")
    pg.click("#pg-01 button[data-act='approve']")
    pg.wait_for_function("document.getElementById('w-01').textContent === '承認しました'")
    assert pg.text_content("#m-01") == "この環境ではコメントを開けません"
    assert pg.is_disabled("#pg-01 button[data-act='comment']")


def test_html_comment_open_in_fragment_does_not_break_page(tmp_path):
    """断片の <!--<script は、埋め込んだデータの <script> の終わりを見失わせない。"""
    from playwright.sync_api import sync_playwright

    # 後ろに --> があると壊れ方が隠れるので、HTML のコメントを持たない断片だけにする
    slides = {
        "01-R1.html": '<section class="slide"><div class="pp-text">x<!--<script>y</div></section>',
        "01-R2.html": '<section class="slide"><div class="pp-text">w</div></section>',
        "02-R1.html": '<section class="slide"><div class="pp-text">z</div></section>',
        "02-R2.html": '<section class="slide"><div class="pp-text">v</div></section>',
    }
    with sync_playwright() as p:
        pg, errors = _open(p, tmp_path, "", slides)
        assert pg.evaluate("document.querySelectorAll('section.rvpg').length") == 2
        assert errors == []

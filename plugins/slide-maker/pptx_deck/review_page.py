# このページは Artifact として公開する。公開時は capabilities: {"db": {}, "comments": {"composer_only": true, "customAnchors": true}}（CAPABILITIES）を必ず付ける（選択の保存と、標準のコメント欄を開くのに要る）。
"""案を選ぶ Artifact ページの生成。`<作業フォルダ>/review.html` を書く（公開は Claude が Artifact ツールで行う）。

ページごとに 1 枚のカード（`id="pg-NN"`）に、選んだ案を大きく、案が複数あれば縮小を並べる。案は Shadow DOM の中に
1280x720 のまま入れて縮小して見せる（`theme.css` はページと各案の shadow root の両方に、`base.css` は shadow root に入れる。
`:root` の変数はページから継承し、`.slide[data-layout=…]` の規則は shadow の中で効く）。選択は `db.doc("choices/<NN>")` に
`{pick, comment, status, at}` として書く（`status` は "saved" か "approved"。`comment` は常に空で、互換のために残す）。
コメントはページに持たず、Artifact 標準のコメント欄を「このページにコメントする」で開く（Claude は ArtifactComments で読む）。"""

import base64
import html as htmllib
import json
import re
from html.parser import HTMLParser
from pathlib import Path

from . import candidates, paths

COLLECTION = "choices"
# 公開時に Artifact に付ける capabilities（db: 選択の保存、comments: 標準のコメント欄をページのボタンから開く）
CAPABILITIES = {"db": {}, "comments": {"composer_only": True, "customAnchors": True}}
# 題の文字数の上限（左の一覧と見出しに出す）
TITLE_CHARS = 24
# Artifact の上限は 16 MB。余裕を見てページ全体をこれ以下にする
MAX_PAGE_BYTES = 12 * 1024 * 1024
_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}
# 画像を指す属性は <img> の src と、SVG <image> の href・xlink:href。タグは引用符の中の > で止まらない
_IMG_TAG = re.compile(r"<(img|image)\b(?:[^>\x22']|\x22[^\x22]*\x22|'[^']*')*>", re.IGNORECASE)
_DATA_URI = re.compile(r"data:[\w.+/-]+;base64,[A-Za-z0-9+/=]+")
_VARIANT = re.compile(r"\bdata-variant\s*=\s*\x22([^\x22]*)\x22")
_PLACEHOLDER = re.compile(r"__(THEME|DATA|CHART|BASE|COLLECTION)__")
# shadow root には body がないので、スライドの文字の書体と色は :host から継承させる
_HOST_CSS = (
    ":host{font-family:'BIZ UDPGothic','BIZ UDPゴシック','BIZ UDGothic','Yu Gothic','Meiryo',sans-serif;"
    "color:var(--text)}"
)
_IMG_ATTR = re.compile(r"(?<![\w:-])((?:xlink:)?href|src)(\s*=\s*)([\x22'])(.*?)\3", re.IGNORECASE | re.DOTALL)

_PAGE = """<title>スライド案の選択</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=BIZ+UDPGothic:wght@400;700&display=swap">
<style>
__THEME__
/* 以下はこのページの枠。変数は --rv- を付け、テーマ側（--bg・--line など）と混ぜない */
:root { --rv-bg:#f2f4f7; --rv-surface:#fff; --rv-fg:#17202b; --rv-mut:#566272; --rv-line:#d8dde4; --rv-acc:#1f3a5f; --rv-acc-ink:#fff; --rv-ok:#18743f; --rv-sel:#a8510a; --rv-soft:#e7ecf3; color-scheme:light; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --rv-bg:#0f141a; --rv-surface:#171e27; --rv-fg:#e8edf3; --rv-mut:#9aa7b6; --rv-line:#2a3441; --rv-acc:#8fb2e0; --rv-acc-ink:#0d1722; --rv-ok:#5fd09a; --rv-sel:#f0a85a; --rv-soft:#1f2a38; color-scheme:dark; } }
:root[data-theme="dark"] { --rv-bg:#0f141a; --rv-surface:#171e27; --rv-fg:#e8edf3; --rv-mut:#9aa7b6; --rv-line:#2a3441; --rv-acc:#8fb2e0; --rv-acc-ink:#0d1722; --rv-ok:#5fd09a; --rv-sel:#f0a85a; --rv-soft:#1f2a38; color-scheme:dark; }
body { margin:0; background:var(--rv-bg); color:var(--rv-fg); font:15px/1.6 "BIZ UDPGothic","Yu Gothic UI","Meiryo",system-ui,sans-serif; padding-left:max(16px,env(safe-area-inset-left,0px)); padding-right:max(16px,env(safe-area-inset-right,0px)); padding-bottom:48px; }
button { font:inherit; color:inherit; cursor:pointer; }
#rv { max-width:1240px; margin:0 auto; }
.rvtop { position:sticky; top:0; z-index:20; background:var(--rv-bg); padding:14px 0 10px; border-bottom:1px solid var(--rv-line); display:flex; gap:12px 20px; align-items:center; flex-wrap:wrap; justify-content:space-between; }
.rvtop h1 { font-size:19px; margin:0; }
.rvprog { display:flex; align-items:center; gap:12px; font-size:14px; }
.rvbar { width:160px; height:8px; border-radius:4px; background:var(--rv-soft); overflow:hidden; }
.rvbar i { display:block; height:100%; background:var(--rv-ok); width:0; transition:width .25s; }
.rvptxt { color:var(--rv-mut); } .rvptxt b { color:var(--rv-fg); }
.rvintro { padding-top:12px; font-size:14px; color:var(--rv-mut); }
.rvintro p { margin:0 0 4px; }
.rvA { display:grid; grid-template-columns:200px minmax(0,1fr); gap:28px; align-items:start; padding-top:14px; }
.rvA nav { position:sticky; top:72px; display:grid; gap:2px; }
.rvA nav a { display:grid; grid-template-columns:14px 28px 1fr; gap:6px; align-items:center; padding:7px 10px; border-radius:6px; color:inherit; text-decoration:none; }
.rvA nav a:hover { background:var(--rv-soft); }
.rvA nav b { font-size:13px; } .rvA nav span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:14px; }
.rvA nav em { grid-column:3; font-style:normal; font-size:12px; color:var(--rv-mut); }
.rvA main { display:grid; gap:22px; min-width:0; }
section.rvpg { background:var(--rv-surface); border:1px solid var(--rv-line); border-radius:10px; padding:18px 20px; display:grid; gap:14px; scroll-margin-top:84px; min-width:0; }
section.rvpg h2 { margin:0; font-size:16px; display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
.rvbd { font-size:12px; padding:1px 10px; border-radius:11px; border:1px solid var(--rv-line); color:var(--rv-mut); white-space:nowrap; font-weight:400; }
.rvbd.ok { color:var(--rv-ok); border-color:var(--rv-ok); } .rvbd.sel { color:var(--rv-sel); border-color:var(--rv-sel); }
.rvdot { display:inline-block; width:10px; height:10px; border-radius:50%; border:2px solid var(--rv-mut); box-sizing:border-box; }
.rvdot.ok { background:var(--rv-ok); border-color:var(--rv-ok); } .rvdot.sel { background:var(--rv-sel); border-color:var(--rv-sel); }
.rvbig { max-width:980px; }
.rvf { width:100%; aspect-ratio:16/9; overflow:hidden; position:relative; background:#fff; border:1px solid var(--rv-line); border-radius:4px; }
.rvh { position:absolute; left:0; top:0; width:1280px; height:720px; transform-origin:0 0; }
.rvthumbs { display:flex; gap:10px; flex-wrap:wrap; }
.rvthumb { width:min(200px,30%); background:none; border:2px solid transparent; border-radius:8px; padding:3px; text-align:left; display:grid; gap:3px; }
.rvthumb.on { border-color:var(--rv-acc); }
.rvthumb small { font-size:12px; color:var(--rv-mut); } .rvthumb.on small { color:var(--rv-acc); }
.rvctl { display:grid; gap:6px; }
.rvrow { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
.rvbtn { border-radius:6px; padding:8px 16px; border:1px solid var(--rv-acc); background:transparent; color:var(--rv-acc); }
.rvbtn.pri { background:var(--rv-acc); color:var(--rv-acc-ink); font-weight:700; }
.rvbtn[disabled] { opacity:.4; cursor:not-allowed; }
.rvlnk { background:none; border:0; color:var(--rv-mut); text-decoration:underline; padding:4px; }
.rvmsg, .rvnote, .rvcm { font-size:13px; color:var(--rv-mut); }
.rvcm:empty { display:none; }
@media (max-width:820px) {
  .rvA { grid-template-columns:1fr; }
  .rvA nav { position:static; grid-auto-flow:column; justify-content:start; overflow-x:auto; }
  .rvA nav span, .rvA nav em { display:none; }
}
</style>
<div id="rv">
  <header class="rvtop">
    <h1>スライド案の選択</h1>
    <div class="rvprog"><div class="rvbar"><i id="bar"></i></div><span class="rvptxt" id="ptxt"></span></div>
  </header>
  <div class="rvintro">
    <p>各ページで案を選び、よければ「承認」を押してください。終わったら、チャットで Claude に知らせてください。</p>
    <p>コメントは「このページにコメントする」から。入力欄の「Claude に送信」にチェックを入れて送ると、Claude が読んで直します。</p>
    <p id="st">読み込み中…</p>
  </div>
  <div class="rvA"><nav id="nav"></nav><main id="pages"></main></div>
</div>
<script type="application/json" id="data">__DATA__</script>
<script>__CHART__</script>
<script>
var BASE = __BASE__;
(function () {
var PAGES = JSON.parse(document.getElementById("data").textContent);
var P = {}, S = {}, order = [], syncs = [], pending = [], busy = {}, again = {}, local = {}, db = null, CA;
var st = document.getElementById("st");
PAGES.forEach(function (p) {
  var ks = Object.keys(p[1]);
  order.push(p[0]);
  P[p[0]] = {keys: ks, c: p[1], labels: p[2], title: p[3]};
  // 1 案のページは選択済み。status は保存先から届いた値だけを持つ（読み込みでは書かない）
  S[p[0]] = {pick: ks.length === 1 ? ks[0] : null, status: null};
});
var SHEET = null;  // 同じ CSS を案ごとに複製しないよう、1 枚のシートを全 shadow root で共有する
try { SHEET = new CSSStyleSheet(); SHEET.replaceSync(BASE); } catch (e) { SHEET = null; }
// 要素を作る。文字は必ず textContent で入れる（断片の題・案の特徴・保存先の値を HTML として解釈しない）
function h(t, a, c) {
  var e = document.createElement(t);
  for (var k in (a || {})) { if (k === "class") e.className = a[k]; else if (k === "text") e.textContent = a[k]; else e.setAttribute(k, a[k]); }
  (c || []).forEach(function (x) { if (x) e.appendChild(x); });
  return e;
}
function $(id) { return document.getElementById(id); }
var ro = new ResizeObserver(function (es) { es.forEach(function (en) { var f = en.target; f.firstElementChild.style.transform = "scale(" + (f.clientWidth / 1280) + ")"; }); });
// 案の枠。中身は文書に入れたあとで flush() が入れる（グラフは文書に入った要素から変数を読む）
function frame(nn, k) { var f = h("div", {class: "rvf", "data-k": k}, [h("div", {class: "rvh"})]); pending.push([f, nn, k]); return f; }
function flush() {
  pending.splice(0).forEach(function (x) {
    var f = x[0], sh = f.firstChild.attachShadow({mode: "open"});
    sh.innerHTML = (SHEET ? "" : "<style>" + BASE + "</style>") + P[x[1]].c[x[2]];
    if (SHEET) sh.adoptedStyleSheets = [SHEET];
    sh.querySelectorAll(".pp-chart").forEach(function (c) { if (window.__chartPreview) window.__chartPreview(c); });
    if (window.__arrows) window.__arrows(sh);
    ro.observe(f);
  });
}
function info(nn) {
  var s = S[nn];
  if (s.status === "approved") return {c: "ok", t: "承認済み"};
  if (s.pick && P[nn].keys.length > 1) return {c: "sel", t: "選択中（未承認）"};
  return {c: "", t: "未承認"};
}
function refresh() { syncs.forEach(function (f) { f(); }); }
function shown(nn) { return S[nn].pick || P[nn].keys[0]; }
function setBig(nn) {
  var big = $("pg-" + nn).querySelector(".rvbig");
  if (big.firstChild && big.firstChild.dataset.k === shown(nn)) return;
  big.textContent = "";
  big.appendChild(frame(nn, shown(nn)));
  flush();
}
var nav = $("nav"), main = $("pages");
syncs.push(function () {
  var ok = order.filter(function (n) { return S[n].status === "approved"; }).length, t = $("ptxt");
  $("bar").style.width = (ok / order.length * 100) + "%";
  t.textContent = "";
  t.appendChild(h("b", {text: "承認 " + ok + "/" + order.length}));
  t.appendChild(document.createTextNode("　未承認 " + (order.length - ok)));
});
order.forEach(function (nn) {
  var p = P[nn], title = p.title || "";
  var dot = h("i", {class: "rvdot"}), em = h("em");
  nav.appendChild(h("a", {href: "#pg-" + nn}, [dot, h("b", {text: nn}), h("span", {text: title}), em]));
  var bd = h("span", {class: "rvbd"}), big = h("div", {class: "rvbig"});
  var thumbs = null;
  if (p.keys.length > 1) {
    thumbs = h("div", {class: "rvthumbs"});
    p.keys.forEach(function (k) {
      var b = h("button", {class: "rvthumb", type: "button", "data-k": k}, [frame(nn, k), h("small", {text: k + "　" + (p.labels[k] || "")})]);
      b.addEventListener("click", function () { pick(nn, k); });
      thumbs.appendChild(b);
    });
  }
  var cbtn = h("button", {class: "rvbtn", type: "button", "data-act": "comment", text: "このページにコメントする"});
  var ok = h("button", {class: "rvbtn pri", type: "button", "data-act": "approve", text: "承認"});
  var undo = h("button", {class: "rvlnk", type: "button", "data-act": "undo", text: "承認を取り消す"});
  // w-NN は書き込みの結果、m-NN はコメント欄の状態（互いに上書きしない）
  var msg = h("span", {class: "rvmsg", id: "w-" + nn}), cmsg = h("div", {class: "rvcm", id: "m-" + nn}), note = h("div", {class: "rvnote"});
  cbtn.addEventListener("click", function () { comment(nn); });
  ok.addEventListener("click", function () { write(nn, "approved", "承認しました"); });
  undo.addEventListener("click", function () { write(nn, "saved", "承認を取り消しました"); });
  var sec = h("section", {class: "rvpg", id: "pg-" + nn, "data-comment-target": ""}, [
    h("h2", {}, [h("span", {text: "スライド " + nn + (title ? "　" + title : "")}), bd]),
    big, thumbs,
    h("div", {class: "rvctl"}, [h("div", {class: "rvrow"}, [cbtn, ok, undo, msg]), cmsg, note])
  ]);
  main.appendChild(sec);
  big.appendChild(frame(nn, shown(nn)));
  syncs.push(function () {
    var i = info(nn), s = S[nn], appr = s.status === "approved";
    dot.className = "rvdot " + i.c; em.textContent = i.t;
    bd.className = "rvbd " + i.c; bd.textContent = i.t;
    if (thumbs) [].forEach.call(thumbs.children, function (b) { b.classList.toggle("on", b.dataset.k === s.pick); });
    ok.disabled = appr || !s.pick;
    ok.textContent = appr ? "承認済み ✓" : "承認";
    undo.hidden = !appr;
    cbtn.disabled = !CA;  // 準備が済むまで（undefined）も、使えないとき（null）も押せない
    note.textContent = appr ? "このページは承認済みです。" : !s.pick ? "案を選んでください。" : "直したい点があれば「このページにコメントする」。よければ「承認」。";
  });
});
flush();  // 枠をすべて文書に入れてから、中身を入れてグラフを描く
refresh();
function pick(nn, k) {
  var s = S[nn];
  if (s.pick === k) return;
  // 承認済みのページで選び直したら、承認し直してもらう（status は saved）。書き終わる前に未承認として見せ、
  // 失敗したらこの状態に戻す
  var prev = s.status === "approved" ? {pick: s.pick, status: s.status} : null;
  s.pick = k;
  if (prev) s.status = "saved";
  local[nn] = true;  // 書き終わるまで、届いたスナップショットで選択を戻さない
  setBig(nn);
  refresh();
  write(nn, "saved", "選択を保存しました（承認はまだです）", prev);
}
async function write(nn, status, done, prev) {
  var m = $("w-" + nn);
  if (!db) { m.textContent = "保存先に接続できません"; return; }
  if (status === "approved" && !S[nn].pick) { m.textContent = "案を選んでから承認してください"; return; }
  if (busy[nn]) { again[nn] = [status, done, prev]; return; }  // 1 つの文書には 1 件ずつ書く。最後の操作をあとで書く
  busy[nn] = true;
  var p = S[nn].pick;
  try {
    await db.doc("__COLLECTION__/" + nn).set({pick: p, comment: "", status: status, at: new Date().toISOString()});
    S[nn].status = status;
    if (S[nn].pick === p) local[nn] = false;
    m.textContent = done;
  } catch (e) {
    m.textContent = "保存できませんでした: " + (e.code || e.message);
    // そのあと選び直していなければ、保護を解いて保存先の値を映せるようにし、承認済みだった状態に戻す
    if (S[nn].pick === p) {
      local[nn] = false;
      if (prev) { S[nn].pick = prev.pick; S[nn].status = prev.status; setBig(nn); }
    }
  }
  busy[nn] = false;
  refresh();
  var next = again[nn];
  if (next) { again[nn] = null; write(nn, next[0], next[1], next[2]); }
}
async function comment(nn) {
  var m = $("m-" + nn);
  if (!CA) { m.textContent = CA === null ? "この環境ではコメントを開けません" : "コメント欄の準備中です。少し待ってもう一度押してください"; return; }
  try {
    var r = await openCommentComposer($("pg-" + nn).querySelector(".rvbig"));
    m.textContent = r && r.opened ? "" : "コメント欄を開けませんでした。もう一度押してください";
  } catch (e) { m.textContent = "コメントを開けません: " + (e.code || e.message); }
}
// ---- 標準のコメント欄を開く部分（開き方はここの 2 つの関数だけが知る） ----
// 位置をページが決める方式（customAnchors）で登録する。入力欄が閉じたらコメントのモードを終え、
// ページのボタンがまた押せるようにする。CA: undefined は準備中、null は使えない環境
// （openComposer には切り替えない。モードが入ったままになり、ボタンが押せなくなる）
async function initComments() {
  try {
    var cm = await window.claude?.use?.("comments");
    CA = cm ? await cm.customAnchors({
      mode: function () {},
      threads: function () { if (CA) CA.placed({}); },  // スレッドの印はページに出さない（空の対応表を返す）
      reveal: function () {},
      composing: function (open) { if (!open && CA) CA.exitMode(); }
    }) : null;
    if (CA) CA.placed({});
  } catch (e) { CA = null; }
  if (!CA) {
    CA = null;
    order.forEach(function (nn) { $("m-" + nn).textContent = "この環境ではコメントを開けません"; });
  }
  refresh();
}
// クリックの操作の中から呼ぶ。{opened} を返す
function openCommentComposer(anchorEl) { return CA.compose(CA.domAnchor(anchorEl)[0], anchorEl); }
// ---- ここまで ----
function paint(nn, d) {
  var s = S[nn];
  s.status = d && (d.status === "approved" || d.status === "saved") ? d.status : null;
  // 書いている途中の選び直しは残す。届いた選択は、このページの案の名前のときだけ映す
  if (d && !local[nn] && !busy[nn] && P[nn].keys.indexOf(d.pick) >= 0 && d.pick !== s.pick) { s.pick = d.pick; setBig(nn); }
  refresh();
}
initComments();
(async function () {
  try { db = await window.claude?.use?.("db"); } catch (e) { db = null; }
  if (!db) { st.textContent = "保存先（db）に接続できません。選択は保存されません。"; return; }
  st.textContent = "接続しました。選択と承認は Claude が読み取れます。";
  order.forEach(function (nn) {
    db.doc("__COLLECTION__/" + nn).onSnapshot(function (s) { paint(nn, s.exists ? s.data() : null); }, function (e) { st.textContent = "読み込みエラー: " + (e.code || e.message); });
  });
})();
})();
</script>
"""


def _asset(work: Path, name: str) -> str:
    f = work / name
    if not f.exists():
        raise ValueError(f"{f} がありません（init で作業フォルダを作り直してください）")
    return paths.read_text(f)


def _data_uri(work: Path, ref: str, cache: dict[str, str]) -> str:
    """作業フォルダ内の画像を data URI にする。問題があれば ValueError（メッセージは理由だけ）。"""
    if ref in cache:
        return cache[ref]
    f = (work / ref).resolve()
    if not f.is_relative_to(work.resolve()):
        raise ValueError("作業フォルダの外です")
    mime = _MIME.get(f.suffix.lower())
    if mime is None:
        raise ValueError("対応していない拡張子です（PNG・JPEG・GIF・WebP・SVG のみ）")
    if not f.is_file():
        raise ValueError("ファイルがありません")
    cache[ref] = f"data:{mime};base64,{base64.b64encode(f.read_bytes()).decode('ascii')}"
    return cache[ref]


def _embed_images(work: Path, nn: str, key: str, frag: str, cache: dict[str, str], errors: list[str]) -> str:
    """断片の相対パスの画像を data URI に置き換える。data:・http(s):・file:・#id はそのまま。"""

    def attr(m: re.Match, tag: str) -> str:
        name, eq, q, ref = m.groups()
        is_img = tag.lower() == "img"
        if (name.lower() == "src") != is_img or re.match(r"(data|https?|file):|#", ref, re.IGNORECASE):
            return m.group(0)
        try:
            return f"{name}{eq}{q}{_data_uri(work, ref, cache)}{q}"
        except ValueError as e:
            errors.append(f"スライド {nn} の案 {key}: {ref}（{e}）")
            return m.group(0)

    return _IMG_TAG.sub(lambda t: _IMG_ATTR.sub(lambda m: attr(m, t.group(1)), t.group(0)), frag)


def _label(frag: str) -> str:
    """断片の data-variant（案の特徴。旧形式の「…｜案の特徴」も受ける）から、案の特徴の部分を返す。"""
    m = _VARIANT.search(frag)
    return htmllib.unescape(m.group(1)).split("｜", 1)[-1] if m else ""


_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class _TitleText(HTMLParser):
    """最初の data-role="title"・data-ph="title" の要素の文字を集める。"""

    def __init__(self) -> None:
        super().__init__()
        self.depth = 0  # 題の要素の中の深さ（0 は外）
        self.done = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if self.done or tag in _VOID:
            return
        if self.depth:
            self.depth += 1
        elif ("data-role", "title") in attrs or ("data-ph", "title") in attrs:
            self.depth = 1

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        pass  # <br/> などは深さを変えない

    def handle_endtag(self, tag: str) -> None:
        if self.depth and tag not in _VOID:
            self.depth -= 1
            self.done = self.depth == 0

    def handle_data(self, data: str) -> None:
        if self.depth:
            self.parts.append(data)


def _title(frags: dict[str, str]) -> str:
    """案の断片から、ページの題（空白を詰め、TITLE_CHARS 字まで）を返す。なければ空文字。"""
    for frag in frags.values():
        p = _TitleText()
        p.feed(frag)
        text = " ".join("".join(p.parts).split())
        if text:
            return text if len(text) <= TITLE_CHARS else text[: TITLE_CHARS - 1] + "…"
    return ""


def build(work: Path) -> Path:
    """`<work>/review.html` を書いて、そのパスを返す。案・派生ファイルが足りなければ ValueError。"""
    work = Path(work)
    cands = candidates.collect(work)
    cache: dict[str, str] = {}
    errors: list[str] = []
    embedded = [
        [
            nn,
            {k: _embed_images(work, nn, k, frag, cache, errors) for k, frag in c.items()},
            {k: _label(frag) for k, frag in c.items()},
            _title(c),
        ]
        for nn, c in sorted(cands.items())
    ]
    if errors:
        raise ValueError("画像を埋め込めません:\n" + "\n".join(errors))
    # <script> の中で終わりを見失わせない（</ と、<!--<script の組み合わせ）。どちらも JSON の文字列の中だけに現れる
    data = json.dumps(embedded, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "\\u003c!--")
    theme = _asset(work, "theme.css")
    subs = {
        "THEME": theme,
        "DATA": data,
        "CHART": _asset(work, "chart-preview.js").replace("</script", "<\\/script"),
        # shadow root の CSS。テーマ（.slide[data-layout=…] の規則）・base.css・:host の書体
        "BASE": json.dumps(f"{theme}\n{_asset(work, 'base.css')}\n{_HOST_CSS}", ensure_ascii=False).replace(
            "</", "<\\/"
        ),
        "COLLECTION": COLLECTION,
    }
    # 1 回で置き換える（断片や CSS の中の __BASE__ などを、もう一度置き換えない）
    html = _PLACEHOLDER.sub(lambda m: subs[m.group(1)], _PAGE)
    size = len(html.encode("utf-8"))
    if size > MAX_PAGE_BYTES:
        images = sum(len(u) for u in _DATA_URI.findall(html))  # 同じ画像も、ページに入った回数だけ数える
        raise ValueError(
            f"案を選ぶページが大きすぎます（{size / 1048576:.1f} MiB。上限 {MAX_PAGE_BYTES / 1048576:.0f} MiB）。"
            f"うち画像が {images / 1048576:.1f} MiB です。画像を小さくしてください"
        )
    out = work / "review.html"
    out.write_text(html, encoding="utf-8", newline="\n")
    return out

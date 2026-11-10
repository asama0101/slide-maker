"""絵（pp-picture）の SVG の id を、絵ごとに一意にする。

`<symbol id="i-server">`・`<marker id="m-acc">` のような定義は、どの絵にも同じ名前で写して使う。
ところが 1 つの HTML（final.html・確認ページ）に絵が 2 枚以上あると、
`<use href="#i-server">` や `marker-end="url(#m-acc)"` は、
文書の中で最初に見つかった定義（前のスライドの絵）を参照してしまう。
絵を 1 枚ずつ撮るときは前のスライドが隠れているので、アイコンや矢じりが消える。
そこで、断片を束ねるときに、絵の中の id と参照へ接頭辞を付ける。
断片のファイル（<元データ>/slides/）は書き換えない。"""

import re

_ATTRS = r"""(?:[^>"']|"[^"]*"|'[^']*')*"""  # 属性の値の中の > を終わりと取り違えない
_DIV_OPEN = re.compile(rf"<div\b{_ATTRS}>")
_DIV_TOKEN = re.compile(rf"<div\b{_ATTRS}>|</div\s*>")
_CLASS = re.compile(r'(?<![\w-])class="[^"]*\bpp-picture\b[^"]*"')
_ID = re.compile(r"""(?<![\w-])id=(["'])(.+?)\1""")


def _pictures(fragment: str):
    """各 pp-picture の (開始タグの終わり, 閉じタグの始まり, 閉じタグの終わり)。
    入れ子の div を数えて対応する </div> を探す。"""
    pos = 0
    while True:
        for m in _DIV_OPEN.finditer(fragment, pos):
            if _CLASS.search(m.group(0)):
                break
        else:
            return
        depth = 1
        for t in _DIV_TOKEN.finditer(fragment, m.end()):
            depth += -1 if t.group(0).startswith("</") else 1
            if depth == 0:
                yield m.end(), t.start(), t.end()
                pos = t.end()
                break
        else:
            return


def uniquify(fragment: str, prefix: str) -> str:
    """断片の中の各 pp-picture について、<svg> の中の id（と href="#…"・url(#…) の参照）に prefix を付ける。"""

    def one(body: str) -> str:
        ids = {m.group(2) for m in _ID.finditer(body)}
        for i in sorted(ids, key=len, reverse=True):  # 長い id から（i-server と i-server2 の取り違えを避ける）
            e = re.escape(i)
            body = re.sub(rf"""((?<![\w-])id=(["'])){e}(?=\2)""", lambda m, i=i: m.group(1) + prefix + i, body)
            body = re.sub(rf"""(href=(["'])#){e}(?=\2)""", lambda m, i=i: m.group(1) + prefix + i, body)
            body = re.sub(rf"""(url\(\s*["']?#){e}(?=["']?\s*\))""", lambda m, i=i: m.group(1) + prefix + i, body)
        return body

    out, last = [], 0
    for start, end, _ in _pictures(fragment):
        out.append(fragment[last:start])
        out.append(one(fragment[start:end]))
        last = end
    return "".join(out) + fragment[last:]
